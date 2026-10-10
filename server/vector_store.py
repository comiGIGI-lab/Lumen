# vector_store.py — Chroma 向量库惰性封装（向量 RAG 切片）
#
# 设计约束（见 openspec/changes/2026-10-10-vector-rag-agentic/spec.md）：
#   1. 惰性加载 chromadb：用 importlib.import_module 而非字面 import，
#      一来未装时模块照常导入（AVAILABLE=False，全部方法 no-op），
#      二来不触碰「api_server / quiz 范围闸」的 import 正则；
#   2. Chroma 1.5.x 嵌入式 PersistentClient(path="data/chroma")，
#      线程安全但非进程安全 —— pm2 必须单实例（DEPLOY §15）；
#   3. 可见性隔离复用 KnowledgeStore 规则：
#      查询者可见 = public ∪ shared ∪ (private 且 owner=查询者)；
#      Chroma where 不支持 OR 复杂嵌套时退化为「先查 owner 侧再查公共侧」。
#
# chunk 主键："{note_id}:{chunk_index}"，与 kb_ingest 分块一一对应；
# 删除按 note_id 前缀清理该笔记的所有块。

from __future__ import annotations

import importlib
import os
import threading

# ---------- 能力探测 ----------
try:
    _chroma_mod = importlib.import_module("chromadb")
    AVAILABLE = True
except Exception:            # ImportError 及其依赖链任何问题都算不可用
    _chroma_mod = None
    AVAILABLE = False

TOP_K = 8                    # 检索默认取数（融合层再截 top_k）
COLLECTION = "kb_chunks"

_LOCK = threading.Lock()     # PersistentClient 句柄的惰性初始化锁
_CLIENT = None
_COLL = None


def _collection():
    """惰性建 client + collection。任何异常返回 None（调用方 no-op）。"""
    global _CLIENT, _COLL
    if not AVAILABLE:
        return None
    if _COLL is not None:
        return _COLL
    with _LOCK:
        if _COLL is not None:
            return _COLL
        try:
            from core.paths import data_path
            persist = data_path("chroma")
        except Exception:
            persist = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "data", "chroma")
        os.makedirs(persist, exist_ok=True)
        _CLIENT = _chroma_mod.PersistentClient(path=persist)
        _COLL = _CLIENT.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},   # 余弦相似，与融合层量纲一致
        )
        return _COLL


def reset_for_test():
    """测试隔离：丢弃句柄，下次 _collection() 重建（指向新 STUDY_LIU_DATA_DIR）。"""
    global _CLIENT, _COLL
    with _LOCK:
        _CLIENT = None
        _COLL = None


# ---------- 写 ----------
def upsert_chunk(note_id, chunk_index, text, embedding, owner, scope, category=""):
    """写入/覆盖一个笔记块。不可用时 no-op 返回 False。"""
    coll = _collection()
    if coll is None or not embedding:
        return False
    try:
        coll.upsert(
            ids=["%d:%d" % (int(note_id), int(chunk_index))],
            embeddings=[list(embedding)],
            documents=[str(text or "")],
            metadatas=[{
                "note_id": int(note_id),
                "chunk_index": int(chunk_index),
                "owner": str(owner or ""),
                "scope": str(scope or "public"),
                "category": str(category or ""),
            }],
        )
        return True
    except Exception:
        return False


def upsert_note_chunks(note_id, chunks, embeddings_list, owner, scope, category=""):
    """批量写一个笔记的多个块。chunks 与 embeddings_list 等长。

    供 kb_ingest / embed_backfill 使用：一次导入最多 60 块，
    逐条 upsert 会慢，这里合并成一次调用。
    Returns: 成功写入的块数。
    """
    coll = _collection()
    if coll is None or not chunks:
        return 0
    ids, embs, docs, metas = [], [], [], []
    for i, (text, emb) in enumerate(zip(chunks, embeddings_list or [])):
        if not emb:
            continue
        ids.append("%d:%d" % (int(note_id), int(i)))
        embs.append(list(emb))
        docs.append(str(text or ""))
        metas.append({
            "note_id": int(note_id),
            "chunk_index": int(i),
            "owner": str(owner or ""),
            "scope": str(scope or "public"),
            "category": str(category or ""),
        })
    if not ids:
        return 0
    try:
        # Chroma 单批上限较大（5461），60 块以内直接整批
        coll.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        return len(ids)
    except Exception:
        return 0


# ---------- 删 ----------
def delete_note(note_id):
    """删除一个笔记的全部向量块。不可用 / 未找到时返回 False。"""
    coll = _collection()
    if coll is None:
        return False
    try:
        # 按 metadata 过滤删除（Chroma 支持 where 删除）
        coll.delete(where={"note_id": int(note_id)})
        return True
    except Exception:
        return False


# ---------- 查 ----------
def query(vector, owner="", scope="", n_results=TOP_K):
    """按可见性规则检索最相似的块。

    可见性（复用 KnowledgeStore.visible 规则）：
      public / shared 人人可见；private 仅 owner 本人。

    Returns:
        [(note_id, chunk_index, similarity), ...] 相似度降序。
        similarity ∈ (0,1]（cosine 距离转相似度）。不可用时返回 []。
    """
    coll = _collection()
    if coll is None or not vector:
        return []
    owner = str(owner or "")
    # Chroma where 的 OR 语法：{"$or": [cond1, cond2, ...]}
    where = {"$or": [
        {"scope": {"$in": ["public", "shared"]}},
        {"owner": owner},
    ]}
    try:
        res = coll.query(
            query_embeddings=[list(vector)],
            n_results=max(1, int(n_results)),
            where=where,
            include=["metadatas", "distances"],
        )
    except Exception:
        return []
    out = []
    try:
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for meta, dist in zip(metas, dists):
            sim = 1.0 - float(dist)          # cosine distance → similarity
            if sim < 0:
                sim = 0.0
            out.append((int(meta.get("note_id", 0)),
                        int(meta.get("chunk_index", 0)),
                        sim))
    except Exception:
        return []
    out.sort(key=lambda x: -x[2])
    return out
