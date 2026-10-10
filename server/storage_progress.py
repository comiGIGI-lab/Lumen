# -*- coding: utf-8 -*-
"""方案进度 / 历史 / 课程归属存储（MySQL 主）。

- 进度是**全局**的：一门课一行 plan_courses，outline/plan 勾选项在 plan_items，
  完整方案 result 在 plan_results（与 vendor progress_store 全局模型一致）。
- 哪桶（"u:<user>" / "c:<id>"）访问过哪门课，记在 course_access —— 替代旧
  client_history.json，api_server 的 record_client_course / client_courses 转调这里。

接口与 vendor/tools/progress_store.py 对齐（save_result / list_courses / load_result /
get_progress / set_done / delete_course / get_stats），并新增 record_course / courses_of。

注：本模块不提供文件兜底（进度非回归必测项，MySQL 为系统记录源）；
数据库不可用时抛 db.DbUnavailable，由调用方降级。
"""

import json
import time
from datetime import datetime

import db


def _now_ts():
    return int(time.time())


def _fmt_ts(epoch):
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def _outline_to_progress(outline):
    from tools.plan_normalize import outline_item_title
    items = []
    for idx, chapter in enumerate(outline or [], start=1):
        items.append({"title": outline_item_title(chapter, idx), "done": False})
    return items


def _plan_to_progress(plan):
    from tools.plan_normalize import plan_item_label
    items = []
    for idx, day in enumerate(plan or [], start=1):
        items.append({"title": plan_item_label(day, idx, max_len=80), "done": False})
    return items


def _course_id(course):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM plan_courses WHERE course=%s", (course,))
            r = cur.fetchone()
        return r[0] if r else None
    finally:
        conn.close()


# ---------- 进度 ----------
def save_result(course, result):
    if not course:
        return
    now = _now_ts()
    cid = _course_id(course)
    existed = cid is not None

    new_outline = _outline_to_progress((result or {}).get("outline", []))
    new_plan = _plan_to_progress((result or {}).get("plan", []))

    if existed:
        # 保留旧勾选状态（按索引对齐）
        old = get_progress(course)
        old_out = [x.get("done", False) for x in old.get("outline", [])]
        old_pl = [x.get("done", False) for x in old.get("plan", [])]
        for i, it in enumerate(new_outline):
            it["done"] = bool(old_out[i]) if i < len(old_out) else False
        for i, it in enumerate(new_plan):
            it["done"] = bool(old_pl[i]) if i < len(old_pl) else False

    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            if existed:
                cur.execute(
                    "UPDATE plan_courses SET last_seen_at=%s WHERE id=%s", (now, cid))
            else:
                cur.execute(
                    "INSERT INTO plan_courses (course, created_at, last_seen_at) "
                    "VALUES (%s,%s,%s)", (course, now, now))
                cid = cur.lastrowid
            # 替换勾选项
            cur.execute("DELETE FROM plan_items WHERE course_id=%s", (cid,))
            for kind, items in (("outline", new_outline), ("plan", new_plan)):
                for idx, it in enumerate(items):
                    cur.execute(
                        "INSERT INTO plan_items (course_id, kind, title, done, sort_order) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (cid, kind, it["title"], 1 if it["done"] else 0, idx))
            # result
            blob = json.dumps(result, ensure_ascii=False)
            cur.execute(
                "INSERT INTO plan_results (course_id, result_json, generated_at) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE result_json=%s, generated_at=%s",
                (cid, blob, now, blob, now))
        conn.commit()
    finally:
        conn.close()


def list_courses():
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT course, created_at, last_seen_at FROM plan_courses "
                "ORDER BY last_seen_at DESC")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"course": r[0],
             "created_at": _fmt_ts(r[1]),
             "last_seen_at": _fmt_ts(r[2])} for r in rows]


def load_result(course):
    cid = _course_id(course)
    if not cid:
        return None
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT result_json FROM plan_results WHERE course_id=%s", (cid,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r or not r[0]:
        return None
    try:
        return json.loads(r[0])
    except (ValueError, TypeError):
        return None


def get_progress(course):
    cid = _course_id(course)
    if not cid:
        return {"outline": [], "plan": []}
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT kind, title, done FROM plan_items WHERE course_id=%s "
                "ORDER BY kind, sort_order", (cid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    outline, plan = [], []
    for kind, title, done in rows:
        item = {"title": title, "done": bool(done)}
        (outline if kind == "outline" else plan).append(item)
    return {"outline": outline, "plan": plan}


def set_done(course, kind, index, done):
    cid = _course_id(course)
    if not cid or kind not in ("outline", "plan"):
        return False
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE plan_items SET done=%s WHERE course_id=%s AND kind=%s AND sort_order=%s",
                (1 if done else 0, cid, kind, index))
            affected = cur.rowcount
            if affected:
                cur.execute("UPDATE plan_courses SET last_seen_at=%s WHERE id=%s",
                            (_now_ts(), cid))
        conn.commit()
        return affected > 0
    finally:
        conn.close()


def delete_course(course):
    cid = _course_id(course)
    if not cid:
        return False
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM plan_courses WHERE id=%s", (cid,))  # 级联删 items/results
            cur.execute("DELETE FROM course_access WHERE course=%s", (course,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_stats(course):
    info = get_progress(course)
    outline = info["outline"]
    plan = info["plan"]
    total = len(outline) + len(plan)
    done = (sum(1 for x in outline if x.get("done"))
            + sum(1 for x in plan if x.get("done")))
    ratio = (done / total) if total > 0 else 0.0
    return done, total, ratio


# ---------- 课程归属（替代 client_history.json）----------
def record_course(bucket, course):
    if not bucket or not course:
        return
    now = _now_ts()
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO course_access (owner, course, last_access_at) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE last_access_at=%s",
                (bucket, course, now, now))
        conn.commit()
    finally:
        conn.close()


def courses_of(bucket):
    if not bucket:
        return set()
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT course FROM course_access WHERE owner=%s", (bucket,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return set(r[0] for r in rows)
