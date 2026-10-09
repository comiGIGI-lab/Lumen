"""LLM 生成结果缓存 —— v19 第三梯队 #12。

设计：
- 按课程名 + 用户画像指纹做 cache key（同一课程不同画像不同缓存）
- LRU + TTL 混合淘汰：最近 N 次 / 默认 24 小时过期
- 磁盘持久化到 data/cache.json（原子写）
- 缓存命中时跳过 LLM 直接返回，节省 token

存储结构（cache.json）：
{
    "version": 2,
    "entries": {
        "<key_hash>": {
            "course": "机器学习",
            "profile_fp": "abc123...",
            "result": {...完整 result...},
            "created_at": 1700000000.0,
            "last_used": 1700000000.0
        }
    }
}
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Any

# ============================================================
# 配置常量
# ============================================================
MAX_ENTRIES = 30                # 最多缓存条目数（LRU 淘汰）
DEFAULT_TTL = 24 * 3600         # 默认过期时间 24 小时
CACHE_FILENAME = "cache.json"   # 相对 data/ 目录

# 结果结构版本。**改动 outline / resources / plan / retrieved 的输出结构时必须 +1** ——
# 它参与 cache key 派生，旧结构的历史缓存会自动失效。
# 背景：缓存 TTL 24h，若结构变了而 key 没变，部署后 24 小时内仍会命中
# 旧结构结果（例如大纲还是纯字符串、导出里继续显示「要点待补充」），
# 看起来像"改了没用"。
# v3：方案结果增加 retrieved，且 cache key 纳入知识库指纹。
CACHE_SCHEMA = 3


def _now() -> float:
    return time.time()


# ============================================================
# 路径管理
# ============================================================
def _get_cache_path() -> str:
    """获取 cache.json 的路径（统一走 core.paths，打包兼容）。"""
    from core.paths import data_path
    return data_path(CACHE_FILENAME)


# ============================================================
# Key 派生
# ============================================================
def knowledge_fingerprint() -> str:
    """知识库指纹：导入 / 删除笔记后必须让方案缓存失效。

    只吃 id / title / 正文长度，避免把整份课件塞进 key。
    读库失败时返回空指纹，等同「无知识库」，不阻断生成。
    """
    try:
        from tools.knowledge_store import KnowledgeStore
        notes = KnowledgeStore().list_all() or []
    except Exception:
        notes = []
    payload = [
        {
            "id": n.get("id"),
            "title": n.get("title") or "",
            "n": len(n.get("content") or ""),
        }
        for n in notes
        if isinstance(n, dict)
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def make_cache_key(course: str, profile: dict | None = None) -> str:
    """根据课程名 + 用户画像指纹 + 知识库指纹生成缓存 key。

    同一课程同一画像同一知识库 → 同一 key → 命中同一缓存。
    导入新材料后指纹变化，24h TTL 内也不会吃到旧方案。
    """
    # 课程名规范化：小写 + strip
    course_norm = (course or "").strip().lower()
    profile_str = json.dumps(profile or {}, sort_keys=True, ensure_ascii=False)
    kb_fp = knowledge_fingerprint()
    raw = f"v{CACHE_SCHEMA}|{course_norm}|{profile_str}|{kb_fp}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ============================================================
# 读写 cache.json
# ============================================================
def _load_raw() -> dict:
    """读取 cache.json，缺文件返回空。"""
    path = _get_cache_path()
    if not os.path.exists(path):
        return {"version": CACHE_SCHEMA, "entries": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "entries" not in data:
            return {"version": CACHE_SCHEMA, "entries": {}}
        if not isinstance(data["entries"], dict):
            data["entries"] = {}
        return data
    except Exception:
        # 损坏时静默回退到空缓存（不影响主流程）
        return {"version": CACHE_SCHEMA, "entries": {}}


def _save_raw(data: dict) -> None:
    """原子写 cache.json（先临时文件再 rename）。"""
    path = _get_cache_path()
    d = os.path.dirname(path)
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".cache-", suffix=".json", dir=d)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        # 写失败不影响主流程
        pass


def _evict_if_needed(entries: dict) -> None:
    """LRU 淘汰：超过 MAX_ENTRIES 时删掉 last_used 最小的。"""
    if len(entries) <= MAX_ENTRIES:
        return
    # 按 last_used 升序排序，淘汰最早的 (len - MAX)
    by_lru = sorted(entries.items(), key=lambda kv: kv[1].get("last_used", 0))
    n_to_remove = len(entries) - MAX_ENTRIES
    for k, _ in by_lru[:n_to_remove]:
        entries.pop(k, None)


# ============================================================
# 对外 API
# ============================================================
def get_cached(course: str, profile: dict | None = None, ttl: float | None = None) -> dict | None:
    """获取缓存结果。

    Args:
        course: 课程名
        profile: 用户画像 dict
        ttl: 过期时间（秒），默认 DEFAULT_TTL

    Returns:
        命中且未过期 → 返回 result dict
        未命中 / 已过期 → 返回 None
    """
    key = make_cache_key(course, profile)
    data = _load_raw()
    entry = data["entries"].get(key)
    if not entry:
        return None
    # 检查 TTL
    ttl_use = ttl if ttl is not None else DEFAULT_TTL
    if _now() - entry.get("created_at", 0) > ttl_use:
        # 过期删除
        data["entries"].pop(key, None)
        _save_raw(data)
        return None
    # 更新 last_used（LRU）
    entry["last_used"] = _now()
    data["entries"][key] = entry
    _save_raw(data)
    return entry.get("result")


def put_cache(course: str, result: dict, profile: dict | None = None) -> None:
    """写入缓存。

    Args:
        course: 课程名
        result: run_plan_pipeline 的完整返回 dict
        profile: 用户画像
    """
    if not course or not result:
        return
    key = make_cache_key(course, profile)
    data = _load_raw()
    data["entries"][key] = {
        "course": course,
        "profile_fp": _profile_fp(profile),
        "result": result,
        "created_at": _now(),
        "last_used": _now(),
    }
    _evict_if_needed(data["entries"])
    _save_raw(data)


def _profile_fp(profile: dict | None) -> str:
    """画像指纹（仅做展示，不参与 key 派生）。"""
    if not profile:
        return ""
    return hashlib.md5(
        json.dumps(profile, sort_keys=True).encode("utf-8"),
    ).hexdigest()[:8]


def list_cached() -> list[dict]:
    """列出所有缓存条目（按 last_used 倒序）。"""
    data = _load_raw()
    entries = data.get("entries", {})
    # 按 last_used 倒序排序（最近用过的在前）
    items = sorted(
        entries.items(),
        key=lambda kv: kv[1].get("last_used", 0),
        reverse=True,
    )
    return [
        {
            "key": k,
            "course": v.get("course", ""),
            "created_at": v.get("created_at", 0),
            "last_used": v.get("last_used", 0),
        }
        for k, v in items
    ]


def clear_cache(course: str | None = None) -> int:
    """清空缓存。

    Args:
        course: 指定课程名 → 只清该课程的；None → 清全部

    Returns:
        清掉的条目数
    """
    data = _load_raw()
    if course is None:
        n = len(data["entries"])
        data["entries"] = {}
        _save_raw(data)
        return n
    # 清指定课程：按 course 名精确匹配
    n = 0
    for k in list(data["entries"].keys()):
        if data["entries"][k].get("course") == course:
            data["entries"].pop(k, None)
            n += 1
    _save_raw(data)
    return n


def get_cache_path():
    """对外暴露 cache.json 路径（供 UI 显示）。"""
    return _get_cache_path()


def cache_stats() -> dict:
    """统计信息：条数、最老、最新、总大小。"""
    data = _load_raw()
    entries = data.get("entries", {})
    if not entries:
        return {"count": 0, "oldest": 0, "newest": 0}
    times = [v.get("created_at", 0) for v in entries.values()]
    return {
        "count": len(entries),
        "oldest": min(times),
        "newest": max(times),
    }