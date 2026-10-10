# -*- coding: utf-8 -*-
"""错题本存储（MySQL 主） —— 接口与 vendor/tools/wrong_book_store.py 完全对齐。

api_server 的 _wrongbook_items(keys,...) 会对每个归属桶调 list_items 并按下 id 去重，
因此本模块：
  - 接受与 vendor 一致的「桶键」参数（登录 = "u:<user>"，匿名 = "c:<id>"）；
  - 返回的条目字典字段形状与 vendor 完全一致（含 id / client_id / 字符串时间戳），
    这样 api_server 的聚合与排序逻辑无需改动。
  - 桶键映射到 wrongbook 表的 owner_username / client_id 两列。

注：本模块不提供文件兜底（错题本非回归必测项，且 MySQL 才是系统记录源）；
数据库不可用时抛 db.DbUnavailable，由调用方决定降级。
"""

import json
import time
from datetime import datetime

import db

MAX_QUESTION = 4000
MAX_ANSWER = 6000
MAX_REASON = 1000
MAX_TAGS = 12
MAX_ITEMS_PER_CLIENT = 500


def _now_ts():
    return int(time.time())


def _fmt_ts(epoch):
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def _neg_time(ts):
    try:
        return -datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, TypeError):
        return 0.0


def _clip(text, limit):
    s = ('' if text is None else str(text)).strip()
    return s[:limit]


def _clean_tags(tags):
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace('，', ',').split(',')]
    if not isinstance(tags, list):
        return []
    out = []
    for t in tags:
        t = str(t).strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def _scope_where(bucket):
    """返回 (owner_username, client_id) —— 与 wrongbook 表两列对应。"""
    return db.split_bucket(bucket)


def _row_to_item(row, bucket):
    """把一行转成 vendor 同款字典。bucket 用于回填 client_id 字段（保持兼容）。"""
    return {
        "id": row[0],
        "client_id": bucket,
        "course": row[2] or "未归类",
        "question": row[3] or "",
        "my_answer": row[4] or "",
        "answer": row[5] or "",
        "reason": row[6] or "",
        "tags": json.loads(row[7]) if row[7] else [],
        "mastered": bool(row[8]),
        "review_count": row[9] or 0,
        "created_at": _fmt_ts(row[10]),
        "updated_at": _fmt_ts(row[11]),
        "last_review_at": _fmt_ts(row[12]),
        "source": row[13] or "manual",
    }


def _select_cols():
    return ("id, client_id, course, question, my_answer, answer, reason, tags, "
            "mastered, review_count, created_at, updated_at, last_review_at, source")


def _where_for(bucket):
    owner, cid = _scope_where(bucket)
    if owner:
        return "owner_username=%s", (owner,)
    return "client_id=%s", (cid,)


# ---------- 读 ----------
def list_items(bucket, course=None, keyword=None, status=None):
    where, params = _where_for(bucket)
    sql = "SELECT %s FROM wrongbook WHERE %s" % (_select_cols(), where)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    items = [_row_to_item(r, bucket) for r in rows]

    if course:
        items = [it for it in items if it.get("course") == course]
    if status == "unmastered":
        items = [it for it in items if not it.get("mastered")]
    elif status == "mastered":
        items = [it for it in items if it.get("mastered")]
    if keyword:
        kw = keyword.strip().lower()
        def hit(it):
            blob = ' '.join([
                str(it.get("question") or ''),
                str(it.get("answer") or ''),
                str(it.get("my_answer") or ''),
                str(it.get("reason") or ''),
                ' '.join(it.get("tags") or []),
            ]).lower()
            return kw in blob
        items = [it for it in items if hit(it)]

    items.sort(key=lambda it: (
        1 if it.get("mastered") else 0,
        _neg_time(it.get("updated_at") or it.get("created_at") or ''),
    ))
    return items


def get_item(bucket, item_id):
    where, params = _where_for(bucket)
    sql = "SELECT %s FROM wrongbook WHERE %s AND id=%%s" % (_select_cols(), where)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params + (item_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    return _row_to_item(r, bucket) if r else None


def stats(bucket):
    items = list_items(bucket)
    total = len(items)
    mastered = sum(1 for it in items if it.get("mastered"))
    by_course = {}
    for it in items:
        c = it.get("course") or '未归类'
        slot = by_course.setdefault(c, {"course": c, "total": 0, "mastered": 0})
        slot["total"] += 1
        if it.get("mastered"):
            slot["mastered"] += 1
    courses = sorted(by_course.values(), key=lambda x: -x["total"])
    due = sum(1 for it in items
              if not it.get("mastered") and int(it.get("review_count") or 0) < 3)
    return {
        "total": total,
        "mastered": mastered,
        "unmastered": total - mastered,
        "due": due,
        "ratio": round(mastered / total, 4) if total else 0.0,
        "by_course": courses,
    }


def courses(bucket):
    where, params = _where_for(bucket)
    sql = "SELECT DISTINCT course FROM wrongbook WHERE %s" % where
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    seen = []
    for (c,) in rows:
        c = c or '未归类'
        if c not in seen:
            seen.append(c)
    return seen


# ---------- 写 ----------
def add_item(bucket, *, course='', question='', my_answer='', answer='',
             reason='', tags=None, source='manual'):
    question = _clip(question, MAX_QUESTION)
    if not question:
        return None
    owner, cid = _scope_where(bucket)
    now = _now_ts()
    tags_json = json.dumps(_clean_tags(tags), ensure_ascii=False)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            # 上限检查（按归属桶）
            if owner:
                cur.execute("SELECT COUNT(*) FROM wrongbook WHERE owner_username=%s",
                            (owner,))
            else:
                cur.execute("SELECT COUNT(*) FROM wrongbook WHERE client_id=%s",
                            (cid,))
            if (cur.fetchone()[0] or 0) >= MAX_ITEMS_PER_CLIENT:
                raise ValueError('错题本已达上限 %d 条，请先清理' % MAX_ITEMS_PER_CLIENT)
            cur.execute(
                "INSERT INTO wrongbook "
                "(owner_username, client_id, course, question, my_answer, answer, "
                " reason, tags, mastered, review_count, created_at, updated_at, source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s)",
                (owner, cid, _clip(course, 80), question,
                 _clip(my_answer, MAX_ANSWER), _clip(answer, MAX_ANSWER),
                 _clip(reason, MAX_REASON), tags_json, now, now,
                 _clip(source, 20) or 'manual'))
            item_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return get_item(bucket, item_id)


def update_item(bucket, item_id, **fields):
    item = get_item(bucket, item_id)
    if not item:
        return None
    now = _fmt_ts(_now_ts())
    sets, params = [], []
    if 'question' in fields:
        q = _clip(fields.get('question'), MAX_QUESTION)
        if not q:
            return None
        sets.append("question=%s"); params.append(q)
    if 'my_answer' in fields:
        sets.append("my_answer=%s")
        params.append(_clip(fields.get('my_answer'), MAX_ANSWER))
    if 'answer' in fields:
        sets.append("answer=%s")
        params.append(_clip(fields.get('answer'), MAX_ANSWER))
    if 'reason' in fields:
        sets.append("reason=%s")
        params.append(_clip(fields.get('reason'), MAX_REASON))
    if 'course' in fields:
        sets.append("course=%s"); params.append(_clip(fields.get('course'), 80))
    if 'tags' in fields:
        sets.append("tags=%s")
        params.append(json.dumps(_clean_tags(fields.get('tags')), ensure_ascii=False))
    if 'mastered' in fields:
        sets.append("mastered=%s"); params.append(1 if fields.get('mastered') else 0)
    sets.append("updated_at=%s"); params.append(_now_ts())
    where, wparams = _where_for(bucket)
    sql = "UPDATE wrongbook SET %s WHERE %s AND id=%%s" % (", ".join(sets), where)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params + list(wparams) + [item_id])
        conn.commit()
    finally:
        conn.close()
    return get_item(bucket, item_id)


def review_item(bucket, item_id, mastered=None):
    item = get_item(bucket, item_id)
    if not item:
        return None
    now = _now_ts()
    where, wparams = _where_for(bucket)
    # 注意：mastered_clause / where 是内部拼接（非用户输入）。mastered 仅在不传 None 时
    # 作为额外的 SET 项追加，且以 ", " 前缀接入，避免 SET 末尾出现悬空逗号。
    # 真正的参数占位符：last_review_at / updated_at / (可选)mastered / where 里的桶 / id。
    mastered_clause = ", mastered=%s" if mastered is not None else ""
    params_master = (1 if mastered else 0,)
    sql = ("UPDATE wrongbook SET review_count=review_count+1, last_review_at=%s, "
           "updated_at=%s" + mastered_clause + " WHERE " + where + " AND id=%s")
    exec_params = (now, now) + (params_master if mastered is not None else ()) + wparams + (item_id,)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, exec_params)
        conn.commit()
    finally:
        conn.close()
    return get_item(bucket, item_id)


def delete_item(bucket, item_id):
    where, wparams = _where_for(bucket)
    sql = "DELETE FROM wrongbook WHERE %s AND id=%%s" % where
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, wparams + (item_id,))
            removed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return removed > 0


def clear(bucket, only_mastered=False):
    where, wparams = _where_for(bucket)
    if only_mastered:
        sql = "DELETE FROM wrongbook WHERE %s AND mastered=1" % where
    else:
        sql = "DELETE FROM wrongbook WHERE %s" % where
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, wparams)
            removed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return removed
