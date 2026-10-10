# -*- coding: utf-8 -*-
"""思维导图存储（MySQL 主） —— 接口与 vendor/tools/mindmap_store.py 完全对齐。

api_server 用法：
  - mindmap_store_list_many(keys) 对每个桶调 list_maps 并去重（按 course）；
  - GET  /api/mindmap/<course> 对每个桶调 get_map，取到的第一条弹掉 _client 返回；
  - POST /api/mindmap         调 save_map(bucket, course, nodes) -> (entry, error)；
  - DEL  /api/mindmap/<course> 调 delete_map(bucket, course)。

桶键（"u:<user>" / "c:<id>"）映射到 mindmap 表的 owner_username / client_id 两列。
与 vendor 一致：get_map 返回含 _client 的原始条目；save_map 返回剔除 _client 的条目。
"""

import json
import re
import time
from datetime import datetime

import db

MAX_NODES = 400
MAX_TEXT = 400
MAX_MAPS_PER_CLIENT = 60

_NODE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def _now_ts():
    return int(time.time())


def _fmt_ts(epoch):
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def _scope_where(bucket):
    owner, cid = db.split_bucket(bucket)
    if owner:
        return "(owner_username=%s)", (owner,)
    return "(client_id=%s)", (cid,)


def _clean_nodes(nodes):
    """校验并规整节点列表。返回 (clean, error)，逻辑同 vendor。"""
    if not isinstance(nodes, list):
        return None, "nodes 必须是数组"
    if len(nodes) > MAX_NODES:
        return None, "节点数超过上限 %d" % MAX_NODES

    seen = set()
    clean = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not _NODE_ID.match(nid):
            return None, "节点 id 非法：%r" % nid
        if nid in seen:
            return None, "节点 id 重复：%s" % nid
        seen.add(nid)

        parent = n.get("parent")
        parent = str(parent).strip() if parent else None
        text = str(n.get("text") or "").strip()[:MAX_TEXT]
        clean.append({"id": nid, "parent": parent, "text": text})

    for n in clean:
        if n["parent"] is None:
            continue
        if n["parent"] == n["id"]:
            return None, "节点 %s 的 parent 指向了自己" % n["id"]
        if n["parent"] not in seen:
            return None, "节点 %s 的 parent「%s」不存在" % (n["id"], n["parent"])

    roots = [n for n in clean if n["parent"] is None]
    if len(roots) != 1:
        return None, "需要恰好一个根节点，当前有 %d 个" % len(roots)

    children = {}
    for n in clean:
        children.setdefault(n["parent"], []).append(n["id"])
    reachable = set()
    stack = [roots[0]["id"]]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(children.get(cur, []))
    if len(reachable) != len(clean):
        return None, "存在环形引用或游离节点（可达 %d / 共 %d）" % (len(reachable), len(clean))

    return clean, None


def _row_to_entry(row, bucket):
    course, updated_at, nodes_blob = row[0], row[1], row[2]
    try:
        nodes = json.loads(nodes_blob) if nodes_blob else []
    except (ValueError, TypeError):
        nodes = []
    return {
        "course": course,
        "updated_at": _fmt_ts(updated_at),
        "nodes": nodes,
        "_client": bucket,
    }


# ---------- 读 ----------
def get_map(bucket, course):
    where, params = _scope_where(bucket)
    sql = ("SELECT course, updated_at, nodes FROM mindmap "
           "WHERE %s AND course=%%s" % where)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params + (course,))
            r = cur.fetchone()
    finally:
        conn.close()
    return _row_to_entry(r, bucket) if r else None


def list_maps(bucket):
    where, params = _scope_where(bucket)
    sql = "SELECT course, updated_at, nodes FROM mindmap WHERE %s" % where
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    out = [{
        "course": r[0],
        "updated_at": _fmt_ts(r[1]),
        "count": len(json.loads(r[2]) if r[2] else []),
    } for r in rows]
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


# ---------- 写 ----------
def save_map(bucket, course, nodes):
    course = (course or "").strip()
    if not course:
        return None, "缺少课程名"
    clean, err = _clean_nodes(nodes)
    if err:
        return None, err

    owner, cid = db.split_bucket(bucket)
    now = _now_ts()
    nodes_json = json.dumps(clean, ensure_ascii=False)

    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            # 上限检查（按归属桶）
            if owner:
                cur.execute("SELECT COUNT(*) FROM mindmap WHERE owner_username=%s", (owner,))
            else:
                cur.execute("SELECT COUNT(*) FROM mindmap WHERE client_id=%s", (cid,))
            if (cur.fetchone()[0] or 0) >= MAX_MAPS_PER_CLIENT:
                return None, "思维导图数量已达上限 %d" % MAX_MAPS_PER_CLIENT
            cur.execute(
                "INSERT INTO mindmap (owner_username, client_id, course, nodes, updated_at) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE nodes=%s, updated_at=%s",
                (owner, cid, course, nodes_json, now, nodes_json, now))
        conn.commit()
    finally:
        conn.close()

    out = {"course": course, "updated_at": _fmt_ts(now), "nodes": clean}
    return out, None


def delete_map(bucket, course):
    where, params = _scope_where(bucket)
    sql = "DELETE FROM mindmap WHERE %s AND course=%%s" % where
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params + (course,))
            removed = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return removed > 0
