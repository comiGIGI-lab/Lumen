# retrieval_hybrid.py — 混合检索：向量语义 + 词法兜底（向量 RAG 切片）
#
# 融合策略（见 openspec/changes/2026-10-10-vector-rag-agentic/spec.md）：
#     score = 0.6 × cosine相似度(向量) + 0.4 × 词法分(归一化)
#
# 三条回退（任何一条触发都直接返回词法结果，行为与现状完全一致）：
#     1. STUDY_LIU_VECTOR=0（总开关，一键禁用）
#     2. 向量层不可用（chromadb 未装 / 无 key / embed 失败 / chroma 报错）
#     3. 任何未预期异常
#
# 返回形状与 KnowledgeStore.retrieve_visible 完全一致：
#     [(note, score, detail), ...]
# note 是 KnowledgeStore.normalize 后的 dict（含 id/title/content/owner/scope），
# score 为融合分，detail 附 {"mode": "hybrid"|"lexical", "sim": 向量相似度}。
# 这样 api_server 只需把调用换成 retrieval_hybrid.retrieve，其余零改动。

from __future__ import annotations

import os

# 融合权重：向量为主、词法为辅
W_VECTOR = 0.6
W_LEXICAL = 0.4

# 向量检索取数（略大于最终 top_k，给融合排序留余量）
_VECTOR_TOP_K = 8


# ---------- 测试注入钩子 ----------
_INJECT = {"embed_query": None, "vector_query": None}
_FORCE_FAIL = False


def _inject_for_test(embed_query=None, vector_query=None):
    """测试注入假向量层（None 恢复真实实现）。"""
    _INJECT["embed_query"] = embed_query
    _INJECT["vector_query"] = vector_query


def _force_vector_failure_for_test(flag):
    """强制向量层视为失败，验证回退路径。"""
    global _FORCE_FAIL
    _FORCE_FAIL = bool(flag)


def vector_available():
    """向量层当前是否可用（开关 + chromadb + 有 key）。"""
    if _FORCE_FAIL:
        return False
    if os.environ.get("STUDY_LIU_VECTOR", "1").strip() in ("0", "false", "no"):
        return False
    try:
        import vector_store
        if not vector_store.AVAILABLE:
            return False
    except Exception:
        return False
    try:
        import embeddings
        if not embeddings._api_key():
            return False
    except Exception:
        return False
    return True


def _vector_enabled():
    """只看总开关（不看依赖），供回退 1 的判定。"""
    return os.environ.get("STUDY_LIU_VECTOR", "1").strip() not in ("0", "false", "no")


# ---------- 主入口 ----------
def retrieve(query, store=None, username="", top_k=3):
    """混合检索。

    参数：
        query: 用户问题
        store: KnowledgeStore 实例（词法底座 + 笔记正文回填）
        username: 当前账号（可见性隔离）
        top_k: 返回条数

    返回：[(note, score, detail), ...]，与词法 retrieve 同构。
    """
    if store is None:
        from tools.knowledge_store import KnowledgeStore
        store = KnowledgeStore()

    # 词法结果永远先算：它是回退底座，也是融合的一路输入
    lex = store.retrieve_visible(query, username, top_k=max(top_k, _VECTOR_TOP_K))

    # ---- 回退 1：总开关关闭 → 纯词法 ----
    if not _vector_enabled():
        return lex[:top_k] if top_k else lex

    # ---- 向量层 ----
    vec_hits = None   # None = 不可用/失败；list = 拿到了（可为空）
    try:
        if vector_available():
            embed_fn = _INJECT["embed_query"]
            if embed_fn is None:
                import embeddings as emb_mod
                embed_fn = emb_mod.embed_query
            qvec = embed_fn(query)
            if qvec:
                query_fn = _INJECT["vector_query"]
                if query_fn is None:
                    import vector_store
                    query_fn = lambda v, owner, scope, n_results=_VECTOR_TOP_K: \
                        vector_store.query(v, owner=owner, scope=scope,
                                           n_results=n_results)
                vec_hits = query_fn(qvec, owner=username, scope="private",
                                    n_results=_VECTOR_TOP_K)
    except Exception:
        vec_hits = None   # 回退 2/3：任何异常回词法

    # ---- 回退 2/3：向量层不可用或失败 → 纯词法 ----
    if vec_hits is None:
        return lex[:top_k] if top_k else lex

    # ---- 融合 ----
    # 词法分归一化到 0~1（按本批最高分），保证两路量纲可比
    lex_by_id = {}
    max_lex = 0.0
    for note, score, detail in lex:
        lex_by_id[note["id"]] = (note, score, detail)
        if score > max_lex:
            max_lex = score

    # 向量分按 note 聚合（一个笔记多块取最高相似度）
    sim_by_id = {}
    for note_id, _ci, sim in vec_hits:
        if note_id not in sim_by_id or sim > sim_by_id[note_id]:
            sim_by_id[note_id] = sim

    # 候选 = 词法命中 ∪ 向量命中；笔记正文从 store 回填（向量库只存块文本）
    visible = {n["id"]: n for n in store.visible(username)}
    fused = []
    for note_id in set(lex_by_id) | set(sim_by_id):
        note = visible.get(note_id)
        if note is None:
            continue   # 向量库里有但知识库已删（理论上 delete_note 挂钩后不会出现）
        lex_score = 0.0
        detail = {}
        if note_id in lex_by_id:
            _n, lex_score, detail = lex_by_id[note_id]
            lex_score = (lex_score / max_lex) if max_lex > 0 else 0.0
        sim = sim_by_id.get(note_id, 0.0)
        score = W_VECTOR * sim + W_LEXICAL * lex_score
        det = dict(detail)
        det["mode"] = "hybrid"
        det["sim"] = round(sim, 3)
        fused.append((note, score, det))

    fused.sort(key=lambda x: (-x[1], str(x[0].get("title", ""))))
    return fused[:top_k] if top_k else fused
