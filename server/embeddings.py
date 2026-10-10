# embeddings.py — 百炼 text-embedding-v4 适配 + 本地缓存（向量 RAG 切片）
#
# 设计约束（见 openspec/changes/2026-10-10-vector-rag-agentic/spec.md）：
#   1. 纯标准库（urllib），不引 openai SDK；
#   2. key 复用 core.config（settings.json > 环境变量），不新增密钥管理面；
#   3. 任何失败（无 key / 断网 / 非 200 / 响应畸形）返回 None，
#      调用方（retrieval_hybrid / kb_ingest）据此回退词法、不阻塞导入；
#   4. 单请求 ≤10 条自动分包（百炼 /embeddings 硬限制）；
#   5. sha1(text+model+dim) 缓存到 data/embed_cache.json ——
#      存量 ~25 条回填与后续导入都走缓存，不重复计费。
#
# 为什么不用 LLM_BASE_URL：它指向 DeepSeek（chat 模型），没有 embedding 端点。
# 百炼的 OpenAI 兼容地址是独立的，写死在这里；key 与 chat 共用同一把
# （百炼/通义系 key 也能在 DeepSeek 网关之外单独签发，但本项目统一用
# settings.json 里那把，若该 key 无百炼权限则向量化自然失败 → 回退词法，
# 不影响主流程）。

from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.request

# ---------- 默认参数（可用环境变量覆盖） ----------
EMBED_MODEL = os.environ.get("STUDY_LIU_EMBED_MODEL", "text-embedding-v4")
try:
    EMBED_DIM = int(os.environ.get("STUDY_LIU_EMBED_DIM", "1024"))
except ValueError:
    EMBED_DIM = 1024

# 百炼 OpenAI 兼容端点（与 LLM_BASE_URL 无关，见模块头注释）
_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 单请求条数上限（百炼 /embeddings 限制，超了会整批报错）
BATCH_LIMIT = 10

# 请求超时（秒）。embedding 比 chat 快得多，30s 足够覆盖慢网。
_TIMEOUT = 30

# ---------- key（测试可注入） ----------
_KEY_OVERRIDE = ""


def _api_key():
    if _KEY_OVERRIDE:
        return _KEY_OVERRIDE
    try:
        from core.config import get_api_key
        return get_api_key() or ""
    except Exception:
        return ""


def _set_key_for_test(key):
    global _KEY_OVERRIDE
    _KEY_OVERRIDE = key or ""


# ---------- 缓存（data/embed_cache.json） ----------
_CACHE_LOCK = threading.Lock()
_CACHE = None          # 惰性加载的 dict：sha1 → vector(list[float])
_CACHE_PATH = None


def _cache_path():
    global _CACHE_PATH
    if _CACHE_PATH is None:
        try:
            from core.paths import data_path
            _CACHE_PATH = data_path("embed_cache.json")
        except Exception:
            _CACHE_PATH = os.path.join(_TMP_FALLBACK(), "embed_cache.json")
    return _CACHE_PATH


def _TMP_FALLBACK():
    d = os.path.join(tempfile.gettempdir(), "study-liu-embed")
    os.makedirs(d, exist_ok=True)
    return d


import tempfile  # noqa: E402  （_TMP_FALLBACK 用；放这里避免顶部 import 与注释混排）


def _load_cache():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _cache_path()
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}
    _CACHE = data
    return _CACHE


def _save_cache():
    try:
        path = _cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass  # 缓存写失败不影响正确性，只损失一次计费


def _cache_key(text, model, dim):
    raw = "%s\u0000%s\u0000%d" % (text, model, dim)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def reset_cache_for_test():
    """清空内存缓存并指向当前 STUDY_LIU_DATA_DIR（测试隔离用）。"""
    global _CACHE, _CACHE_PATH
    _CACHE = None
    _CACHE_PATH = None


# ---------- HTTP ----------
def _post_embeddings(texts, model, dim, api_key):
    """发一次 /embeddings 请求。成功返回向量列表，失败返回 None。"""
    url = _BASE_URL + "/embeddings"
    payload = json.dumps({
        "model": model,
        "dimensions": dim,
        "input": texts,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer %s" % api_key)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if getattr(resp, "status", 200) != 200 and getattr(resp, "code", 200) != 200:
                return None
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    data = body.get("data")
    if not isinstance(data, list) or len(data) != len(texts):
        return None
    out = []
    # 服务端保证按 input 顺序返回（OpenAI 兼容契约），这里仍按 index 归位防御
    by_index = {}
    for item in data:
        try:
            by_index[int(item.get("index", 0))] = item.get("embedding")
        except Exception:
            return None
    for i in range(len(texts)):
        vec = by_index.get(i)
        if not isinstance(vec, list) or not vec:
            return None
        out.append(vec)
    return out


# ---------- 公开接口 ----------
def embed_texts(texts, model=EMBED_MODEL, dim=EMBED_DIM):
    """批量向量化。

    Returns:
        list[list[float]]，长度与 texts 一致；任何失败返回 None（调用方回退词法）。
    """
    texts = [str(t or "") for t in (texts or [])]
    if not texts:
        return []

    api_key = _api_key()
    if not api_key:
        return None

    with _CACHE_LOCK:
        cache = _load_cache()
        results = [None] * len(texts)
        missing_idx = []
        for i, t in enumerate(texts):
            hit = cache.get(_cache_key(t, model, dim))
            if isinstance(hit, list) and hit:
                results[i] = hit
            else:
                missing_idx.append(i)

        if not missing_idx:
            return results

        # 分包：每批 ≤ BATCH_LIMIT 条
        batch_start = 0
        while batch_start < len(missing_idx):
            batch_idx = missing_idx[batch_start:batch_start + BATCH_LIMIT]
            batch_texts = [texts[i] for i in batch_idx]
            vectors = _post_embeddings(batch_texts, model, dim, api_key)
            if vectors is None:
                return None  # 任何一批失败：整体回退，不返回半成品
            for local_i, vec in zip(batch_idx, vectors):
                results[local_i] = vec
                cache[_cache_key(texts[local_i], model, dim)] = vec
            batch_start += BATCH_LIMIT
        _save_cache()
        return results


def embed_query(text, model=EMBED_MODEL, dim=EMBED_DIM):
    """单条查询向量化（检索侧用）。失败返回 None。"""
    out = embed_texts([text], model=model, dim=dim)
    if not out:
        return None
    return out[0]


if __name__ == "__main__":
    # 手动冒烟：python server/embeddings.py <一句话>
    import sys as _sys
    arg = " ".join(_sys.argv[1:]) or "向量检索冒烟测试"
    v = embed_query(arg)
    if v is None:
        print("embedding 不可用（无 key / 网络失败）—— 将回退词法检索")
    else:
        print("dim=%d head=%s" % (len(v), v[:5]))
