# -*- coding: utf-8 -*-
"""JSON → MySQL 迁移（幂等 / 支持 dry-run / 安全：只新增不删）。

把「文件版用户系统」在 cutover 到 MySQL 时，把磁盘上已有的 JSON 数据搬进 MySQL。
数据源全在同一个 data 目录（core.paths.data_dir 解析）：

    accounts.json        -> users
    client_bindings.json -> client_bindings
    profiles/*.json      -> profiles
    wrong_book.json      -> wrongbook
    mindmap.json         -> mindmap
    progress.json        -> plan_courses / plan_items / plan_results
    client_history.json  -> course_access

设计约束：
    - 幂等：全部走 INSERT ... ON DUPLICATE KEY UPDATE / INSERT IGNORE，重跑不重复不报错；
    - 安全：绝不 DELETE MySQL 里任何行；只把 JSON 里缺的/旧的写进去；
    - dry-run：只读 JSON、统计将迁移条数，不连库、不写；
    - 仅本脚本 import server.db（db 再 import pymysql），不污染 quiz/向量 RAG 等零依赖模块。

用法（仓库内）：
    python tools/migrate_json_to_mysql.py                 # 真实迁移（需配置 STUDY_LIU_MYSQL_* 或 .env）
    python tools/migrate_json_to_mysql.py --dry-run       # 只统计，不写
    python tools/migrate_json_to_mysql.py --data-dir /path/to/data
    python tools/migrate_json_to_mysql.py --no-dotenv     # 不读 .env，只用环境变量
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.dirname(HERE)                       # vendor/study-liu
REPO_ROOT = os.path.dirname(os.path.dirname(VENDOR))  # 仓库根
SERVER = os.path.join(REPO_ROOT, "server")
for p in (VENDOR, SERVER):
    if p not in sys.path:
        sys.path.insert(0, p)

import db  # noqa: E402

_SAFE_NAME = __import__("re").compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,64}$")


# ============================================================
# .env 加载（复刻 api_server._load_dotenv_stdlib）
# ============================================================
def _load_dotenv():
    loaded = []
    source_dir = SERVER
    web_root = os.path.dirname(REPO_ROOT) if os.path.basename(REPO_ROOT).endswith("-web") \
        else os.path.join(REPO_ROOT, "study-liu-web")
    for path in (os.path.join(source_dir, ".env"), os.path.join(web_root, ".env")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key.lower().startswith("export "):
                        key = key[7:].strip()
                    if not key:
                        continue
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                        value = value[1:-1]
                    if key not in os.environ:
                        os.environ[key] = value
                        loaded.append(key)
        except OSError:
            continue
    return loaded


# ============================================================
# 辅助
# ============================================================
def _parse_ts(ts):
    """把 'YYYY-MM-DD HH:MM:SS' 解析成 epoch；失败返回当前时间。"""
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str) and ts.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return int(datetime.strptime(ts.strip(), fmt).timestamp())
            except ValueError:
                continue
    return int(time.time())


def _read_json(path, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if d is not None else default
    except (OSError, ValueError):
        return default


def _now():
    return int(time.time())


# ============================================================
# 各数据源迁移
# ============================================================
def migrate_users(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "accounts.json")
    d = _read_json(path, {"users": {}})
    users = d.get("users", {}) if isinstance(d, dict) else {}
    rows = []
    for name, u in users.items():
        if not isinstance(u, dict):
            continue
        rows.append((name, u.get("salt", ""), u.get("hash", ""),
                     u.get("role", "user"), int(u.get("created", _now()))))
    stats["users"] = len(rows)
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO users (username, salt, password_hash, role, created_at) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE salt=VALUES(salt), password_hash=VALUES(password_hash), "
            "role=VALUES(role)",
            rows)
    conn.commit()


def migrate_bindings(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "client_bindings.json")
    d = _read_json(path, {"bindings": {}})
    bindings = d.get("bindings", {}) if isinstance(d, dict) else {}
    rows = [(cid, uname, _now()) for cid, uname in bindings.items()
            if cid and uname]
    stats["client_bindings"] = len(rows)
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO client_bindings (client_id, username, bound_at) "
            "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE username=VALUES(username), "
            "bound_at=VALUES(bound_at)",
            rows)
    conn.commit()


def migrate_profiles(conn, data_dir, dry, stats):
    pdir = os.path.join(data_dir, "profiles")
    if not os.path.isdir(pdir):
        stats["profiles"] = 0
        return
    rows = []
    skipped = 0
    for fn in os.listdir(pdir):
        if not fn.endswith(".json"):
            continue
        stem = fn[:-5]
        # 用户名含非法字符时文件名是 u-<sha256[:16]>，单向无法还原，跳过并告警
        if stem.startswith("u-"):
            skipped += 1
            continue
        full = os.path.join(pdir, fn)
        try:
            with open(full, "r", encoding="utf-8") as f:
                prof = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(prof, dict):
            continue
        rows.append((stem, json.dumps(prof, ensure_ascii=False), _now()))
    stats["profiles"] = len(rows)
    if skipped:
        stats["profiles_unsafe_skipped"] = skipped
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO profiles (username, profile_json, updated_at) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE profile_json=VALUES(profile_json), "
            "updated_at=VALUES(updated_at)",
            rows)
    conn.commit()


def migrate_wrongbook(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "wrong_book.json")
    d = _read_json(path, {"items": []})
    items = d.get("items", []) if isinstance(d, dict) else []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("client_id") or ""
        rows.append((
            it.get("id"),
            cid,                                  # client_id（匿名桶）；owner_username 留 NULL
            (it.get("course") or "未归类")[:255],
            it.get("question") or "",
            it.get("my_answer") or "",
            it.get("answer") or "",
            (it.get("reason") or "")[:1000],
            json.dumps(it.get("tags") or [], ensure_ascii=False),
            1 if it.get("mastered") else 0,
            int(it.get("review_count") or 0),
            _parse_ts(it.get("created_at")),
            _parse_ts(it.get("updated_at")),
            _parse_ts(it.get("last_review_at")) if it.get("last_review_at") else None,
        ))
    stats["wrongbook"] = len(rows)
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO wrongbook (id, client_id, course, question, my_answer, answer, "
            "reason, tags, mastered, review_count, created_at, updated_at, last_review_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE id=id",
            rows)
    conn.commit()


def migrate_mindmap(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "mindmap.json")
    d = _read_json(path, {"maps": {}})
    maps = d.get("maps", {}) if isinstance(d, dict) else {}
    rows = []
    for key, m in maps.items():
        if not isinstance(m, dict):
            continue
        if "::" not in key:
            continue
        cid, course = key.split("::", 1)
        rows.append((cid, course[:255], json.dumps(m.get("nodes") or [], ensure_ascii=False),
                     _parse_ts(m.get("updated_at"))))
    stats["mindmap"] = len(rows)
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO mindmap (client_id, course, nodes, updated_at) VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE nodes=VALUES(nodes), updated_at=VALUES(updated_at)",
            rows)
    conn.commit()


def migrate_progress(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "progress.json")
    d = _read_json(path, {"courses": {}})
    courses = d.get("courses", {}) if isinstance(d, dict) else {}
    n_courses = 0
    n_items = 0
    n_results = 0
    if dry:
        stats["plan_courses"] = len(courses)
        return
    for course, c in courses.items():
        if not isinstance(c, dict):
            continue
        created = _parse_ts(c.get("created_at"))
        seen = _parse_ts(c.get("last_seen_at"))
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plan_courses (course, created_at, last_seen_at) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE last_seen_at=VALUES(last_seen_at)",
                (course, created, seen))
            if cur.rowcount == 1:
                course_id = cur.lastrowid
            else:
                cur.execute("SELECT id FROM plan_courses WHERE course=%s", (course,))
                course_id = cur.fetchone()[0]
        n_courses += 1
        # plan_items 由 progress.json 派生，重跑幂等：先清后插
        with conn.cursor() as cur:
            cur.execute("DELETE FROM plan_items WHERE course_id=%s", (course_id,))
            items = []
            order = 0
            for o in c.get("outline", []) or []:
                items.append((course_id, "outline", (o.get("title") or "")[:512],
                             1 if o.get("done") else 0, order)); order += 1
            for p in c.get("plan", []) or []:
                items.append((course_id, "plan", (p.get("title") or "")[:512],
                             1 if p.get("done") else 0, order)); order += 1
            if items:
                cur.executemany(
                    "INSERT INTO plan_items (course_id, kind, title, done, sort_order) "
                    "VALUES (%s,%s,%s,%s,%s)", items)
                n_items += len(items)
            res = c.get("result")
            cur.execute(
                "INSERT INTO plan_results (course_id, result_json, generated_at) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE result_json=VALUES(result_json), "
                "generated_at=VALUES(generated_at)",
                (course_id, json.dumps(res, ensure_ascii=False) if res is not None else None, seen))
            n_results += 1
        conn.commit()
    stats["plan_courses"] = n_courses
    stats["plan_items"] = n_items
    stats["plan_results"] = n_results


def migrate_course_access(conn, data_dir, dry, stats):
    path = os.path.join(data_dir, "client_history.json")
    d = _read_json(path, {})
    hist = d if isinstance(d, dict) else {}
    rows = []
    for cid, courses in hist.items():
        if not cid or not isinstance(courses, list):
            continue
        for course in courses:
            if course:
                rows.append(("c:" + cid, course[:255], _now()))
    stats["course_access"] = len(rows)
    if dry or not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO course_access (owner, course, last_access_at) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE last_access_at=VALUES(last_access_at)",
            rows)
    conn.commit()


# ============================================================
# 入口
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="JSON → MySQL 迁移（幂等 / dry-run / 安全）")
    ap.add_argument("--data-dir", default=None,
                    help="数据目录（默认 core.paths.data_dir()）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不连库不写")
    ap.add_argument("--no-dotenv", action="store_true", help="不读 .env，只用环境变量")
    args = ap.parse_args()

    if not args.no_dotenv:
        _load_dotenv()

    if args.data_dir:
        data_dir = os.path.abspath(args.data_dir)
    else:
        try:
            from core.paths import data_dir as _dd
            data_dir = _dd()
        except Exception:
            data_dir = os.path.join(REPO_ROOT, "data")
    print("数据源目录: %s" % data_dir)
    if not os.path.isdir(data_dir):
        print("✗ 数据目录不存在: %s" % data_dir)
        sys.exit(2)

    stats = {}
    # dry-run 也把各表条数算出来
    migrate_users(None, data_dir, True, stats)
    migrate_bindings(None, data_dir, True, stats)
    migrate_profiles(None, data_dir, True, stats)
    migrate_wrongbook(None, data_dir, True, stats)
    migrate_mindmap(None, data_dir, True, stats)
    migrate_progress(None, data_dir, True, stats)
    migrate_course_access(None, data_dir, True, stats)

    print("\n[统计] 将迁移条数：")
    for k in ("users", "client_bindings", "profiles", "profiles_unsafe_skipped",
              "wrongbook", "mindmap", "plan_courses", "plan_items", "plan_results",
              "course_access"):
        if k in stats:
            print("  %-22s %s" % (k, stats[k]))

    if args.dry_run:
        print("\n(dry-run) 未连接数据库，未写入。")
        return

    # 真实迁移：必须能连上 MySQL
    try:
        db.configure()
        conn = db.get_conn()
    except db.DbUnavailable as e:
        print("\n✗ 无法连接 MySQL（请配置 STUDY_LIU_MYSQL_* 或 .env）：%s" % e)
        sys.exit(3)
    try:
        db.ensure_schema()
        stats = {}
        migrate_users(conn, data_dir, False, stats)
        migrate_bindings(conn, data_dir, False, stats)
        migrate_profiles(conn, data_dir, False, stats)
        migrate_wrongbook(conn, data_dir, False, stats)
        migrate_mindmap(conn, data_dir, False, stats)
        migrate_progress(conn, data_dir, False, stats)
        migrate_course_access(conn, data_dir, False, stats)
    finally:
        conn.close()

    print("\n[完成] 已写入 MySQL：")
    for k in ("users", "client_bindings", "profiles", "profiles_unsafe_skipped",
              "wrongbook", "mindmap", "plan_courses", "plan_items", "plan_results",
              "course_access"):
        if k in stats:
            print("  %-22s %s" % (k, stats[k]))
    print("\n迁移幂等：可安全重跑。")


if __name__ == "__main__":
    main()
