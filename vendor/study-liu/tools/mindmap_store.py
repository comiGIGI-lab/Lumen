# mindmap_store.py — 思维导图存储
#
# 存储位置：data/mindmap.json（与 progress.json 同目录）
#
# 结构：
# {
#   "maps": {
#     "<client_id>::<课程名>": {
#       "course": "Python 入门",
#       "updated_at": "2026-09-25 19:10:00",
#       "nodes": [
#         {"id": "root", "parent": null, "text": "Python 入门"},
#         {"id": "n1",   "parent": "root", "text": "第一章 基础"},
#         {"id": "n1a",  "parent": "n1",   "text": "变量与赋值"}
#       ]
#     }
#   }
# }
#
# 用**扁平节点 + parent 引用**而不是嵌套结构：
# 增删改一个节点不用递归找父级，前端布局时再还原成树，两边都简单。

import json
import os
import re
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

_DATA_DIR = _resolve_data_dir()
_FILE = os.path.join(_DATA_DIR, "mindmap.json")

# 写入接口是公网无鉴权的，留天花防止被灌爆
MAX_NODES = 400
MAX_TEXT = 400
MAX_MAPS_PER_CLIENT = 60

_NODE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load():
    if not os.path.exists(_FILE):
        return {"maps": {}}
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"maps": {}}
        if not isinstance(data.get("maps"), dict):
            data["maps"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return {"maps": {}}


def _save(data):
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _FILE)


def _key(client_id, course):
    return "%s::%s" % (client_id or "anonymous", (course or "").strip())


def _clean_nodes(nodes):
    """校验并规整节点列表。返回 (clean, error)。"""
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

    # parent 必须存在（根节点除外），且不能自己指自己 —— 否则前端递归会栈溢出
    for n in clean:
        if n["parent"] is None:
            continue
        if n["parent"] == n["id"]:
            return None, "节点 %s 的 parent 指向了自己" % n["id"]
        if n["parent"] not in seen:
            return None, "节点 %s 的 parent「%s」不存在" % (n["id"], n["parent"])

    # 每张图必须恰好一个根
    roots = [n for n in clean if n["parent"] is None]
    if len(roots) != 1:
        return None, "需要恰好一个根节点，当前有 %d 个" % len(roots)

    # 环检测：从根出发能否到达全部节点
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


# ------------------------------------------------------------
# 读写
# ------------------------------------------------------------

def get_map(client_id, course):
    """取一张思维导图；没有则返回 None。"""
    data = _load()
    return data["maps"].get(_key(client_id, course))


def save_map(client_id, course, nodes):
    """保存（覆盖）一张思维导图。返回 (entry, error)。"""
    course = (course or "").strip()
    if not course:
        return None, "缺少课程名"

    clean, err = _clean_nodes(nodes)
    if err:
        return None, err

    data = _load()
    maps = data["maps"]
    k = _key(client_id, course)

    if k not in maps:
        mine = [x for x in maps.values()
                if x.get("_client") == client_id]
        if len(mine) >= MAX_MAPS_PER_CLIENT:
            return None, "思维导图数量已达上限 %d" % MAX_MAPS_PER_CLIENT

    entry = {
        "course": course,
        "updated_at": _now(),
        "nodes": clean,
        "_client": client_id,          # 仅用于计数，返回前会剔掉
    }
    maps[k] = entry

    _save(data)
    out = dict(entry)
    out.pop("_client", None)
    return out, None


def delete_map(client_id, course):
    data = _load()
    k = _key(client_id, course)
    if k in data["maps"]:
        del data["maps"][k]
        _save(data)
        return True
    return False


def list_maps(client_id):
    """列出该浏览器名下的所有导图（不含节点，只给列表用）。"""
    data = _load()
    out = []
    for entry in data["maps"].values():
        if entry.get("_client") != client_id:
            continue
        out.append({
            "course": entry.get("course", ""),
            "updated_at": entry.get("updated_at", ""),
            "count": len(entry.get("nodes") or []),
        })
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out
