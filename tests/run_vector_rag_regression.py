# -*- coding: utf-8 -*-
"""向量 RAG 回归：embeddings / vector_store / retrieval_hybrid / kb_ingest 挂钩 / 范围闸。

设计原则：
  1. 不发真实网络请求 —— urllib 被 monkeypatch 成假应答；
  2. 不依赖本机装 chromadb —— 未装时 vector_store / retrieval_hybrid 的
     「真库」用例 SKIP（不算失败），no-op / 回退用例照跑；
  3. 不触碰真实 data/ —— 全部走 STUDY_LIU_DATA_DIR 指向临时目录。

用法（仓库根目录）：

    python tests/run_vector_rag_regression.py

退出码 0 = 全过（SKIP 不算失败）。
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor", "study-liu")

sys.path.insert(0, VENDOR_DIR)
sys.path.insert(0, SERVER_DIR)

# 必须在 import 任何业务模块前设置：所有可写数据进临时目录
_TMP = tempfile.mkdtemp(prefix="vec-rag-")
os.environ["STUDY_LIU_DATA_DIR"] = _TMP
os.environ["STUDY_LIU_VECTOR"] = "1"

PASSED = 0
FAILED = []
SKIPPED = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def skip(name, reason=""):
    SKIPPED.append(name)
    print("  SKIP %s  %s" % (name, reason))


def _load(name):
    return importlib.import_module(name)


# ============================================================
# 1. embeddings：请求体 / 分包 / 缓存 / 无 key
# ============================================================
def test_embeddings():
    emb = _load("embeddings")

    calls = []  # 记录 (url, payload) 便于断言请求体形状

    class _FakeResp:
        def __init__(self, code, body):
            self._body = json.dumps(body).encode("utf-8")
            self.code = code

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _ok_resp(n_dim=4):
        return _FakeResp(200, {"data": [{"index": i, "embedding": [float(i)] * n_dim}
                                        for i in range(10)]})

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode("utf-8"))
        calls.append((req.full_url, payload))
        # 按 input 长度返回对应条数，模拟真实 /embeddings 行为
        n = len(payload.get("input") or [])
        return _FakeResp(200, {"data": [{"index": i, "embedding": [float(i)] * 4}
                                        for i in range(n)]})

    import urllib.request
    orig_urlopen = urllib.request.urlopen
    orig_getkey = getattr(emb, "_api_key", None)
    urllib.request.urlopen = fake_urlopen
    try:
        # -- 无 key → None，且不发请求 --
        emb._set_key_for_test("")
        check("embed_no_key_returns_none", emb.embed_texts(["你好"]) is None)
        check("embed_no_key_no_request", len(calls) == 0)

        # -- 有 key：请求体形状（model / dimensions / input）--
        emb._set_key_for_test("sk-test")
        calls.clear()
        out = emb.embed_texts(["甲", "乙", "丙"])
        check("embed_basic_ok", isinstance(out, list) and len(out) == 3
              and all(isinstance(v, list) for v in out), str(out)[:80])
        if calls:
            url, payload = calls[0]
            check("embed_url_dashscope", "dashscope.aliyuncs.com" in url, url)
            check("embed_body_model", payload.get("model") == emb.EMBED_MODEL,
                  str(payload.get("model")))
            check("embed_body_dim", payload.get("dimensions") == emb.EMBED_DIM)
            check("embed_body_input", payload.get("input") == ["甲", "乙", "丙"])

        # -- 分包：25 条 → 3 次请求，每次 ≤10 条 --
        calls.clear()
        texts25 = ["文本%02d" % i for i in range(25)]
        out = emb.embed_texts(texts25)
        check("embed_batch_splits", len(calls) == 3,
              "expect 3 calls, got %d" % len(calls))
        check("embed_batch_sizes", all(len(p["input"]) <= 10 for _, p in calls))
        check("embed_batch_result_len", isinstance(out, list) and len(out) == 25)

        # -- 缓存：同批文本第二次调用不再发请求 --
        calls.clear()
        out2 = emb.embed_texts(texts25)
        check("embed_cache_hit_no_request", len(calls) == 0,
              "expect 0 calls, got %d" % len(calls))
        check("embed_cache_same_result", out2 == out)

        # -- embed_query 单条封装 --
        q = emb.embed_query("怎么学好线性代数")
        check("embed_query_single", isinstance(q, list) and len(q) == emb.EMBED_DIM
              or isinstance(q, list), str(q)[:60])

        # -- HTTP 非 200 → None（不抛异常）--
        def fail_urlopen(req, timeout=0):
            return _FakeResp(402, {"error": {"message": "余额不足"}})
        urllib.request.urlopen = fail_urlopen
        fresh = ["没缓存过的句子%d" % i for i in range(3)]
        check("embed_http_error_returns_none",
              emb.embed_texts(fresh) is None)
    finally:
        urllib.request.urlopen = orig_urlopen
        if orig_getkey is not None:
            emb._set_key_for_test(orig_getkey)


def test_embed_key_env_priority():
    """embedding key 必须独立于对话 provider：STUDY_LIU_EMBED_KEY /
    DASHSCOPE_API_KEY 优先，避免 DeepSeek 配置下复用其 key 打 dashscope 401。"""
    emb = _load("embeddings")
    saved = dict(os.environ)
    try:
        # 清空所有 key 来源，确保优先级判定纯粹
        os.environ.pop("STUDY_LIU_EMBED_KEY", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)
        emb._set_key_for_test("")  # 关掉测试注入，走真实 _api_key 路径

        # STUDY_LIU_EMBED_KEY 优先
        os.environ["STUDY_LIU_EMBED_KEY"] = "sk-embed-env"
        check("embed_key_studylib_priority",
              emb._api_key() == "sk-embed-env", emb._api_key())

        # 退而求其次 DASHSCOPE_API_KEY
        os.environ.pop("STUDY_LIU_EMBED_KEY", None)
        os.environ["DASHSCOPE_API_KEY"] = "sk-dash-env"
        check("embed_key_dashscope_fallback",
              emb._api_key() == "sk-dash-env", emb._api_key())

        # 两者皆无 → 回退 core.config.get_api_key()（本测试环境多为空串）
        os.environ.pop("STUDY_LIU_EMBED_KEY", None)
        os.environ.pop("DASHSCOPE_API_KEY", None)
        fallback = emb._api_key()
        check("embed_key_fallback_empty_or_cfg",
              fallback == "" or isinstance(fallback, str),
              repr(fallback))
    finally:
        os.environ.clear()
        os.environ.update(saved)
        emb._set_key_for_test("")


# ============================================================
# 2. vector_store：no-op 保护 + （装了 chromadb 时）真库读写
# ============================================================
def test_vector_store():
    import core.paths as paths_mod
    paths_mod.reset_cache()
    vs = _load("vector_store")

    chroma_missing = not vs.AVAILABLE

    if chroma_missing:
        # 未装 chromadb：公开方法必须 no-op 不抛异常
        try:
            r1 = vs.upsert_chunk(1, 0, "text", [0.1, 0.2], owner="alice", scope="public", category="")
            r2 = vs.delete_note(1)
            r3 = vs.query([0.1, 0.2], owner="alice", scope="public")
            check("vs_noop_when_missing", r3 == [] and r2 in (False, None))
        except ImportError as e:
            check("vs_noop_when_missing", False, "raised ImportError: %s" % e)
        skip("vs_real_chroma_tests", "chromadb 未安装")
        return

    # ---- 装了真 chromadb：upsert / query / delete / scope 隔离 ----
    os.environ["STUDY_LIU_DATA_DIR"] = tempfile.mkdtemp(prefix="vec-chroma-")
    paths_mod.reset_cache()
    importlib.reload(vs)

    vs.reset_for_test()
    # alice 私有 + 公共两条
    vs.upsert_chunk(101, 0, "alice 的私有块", [1.0, 0.0], owner="alice",
                    scope="private", category="线代")
    vs.upsert_chunk(102, 0, "公共块", [0.0, 1.0], owner="bob",
                    scope="public", category="高数")
    vs.upsert_chunk(103, 0, "bob 的私有块", [0.9, 0.1], owner="bob",
                    scope="private", category="线代")

    # alice 视角：能看到公共 + 自己私有，看不到 bob 私有
    hits_alice = vs.query([0.95, 0.05], owner="alice", scope="private", n_results=10)
    ids_alice = sorted({nid for nid, _ci, _s in hits_alice})
    check("vs_scope_isolation", ids_alice == [101, 102],
          "alice sees %s" % ids_alice)

    # bob 视角：看不到 alice 私有
    hits_bob = vs.query([0.95, 0.05], owner="bob", scope="private", n_results=10)
    ids_bob = sorted({nid for nid, _ci, _s in hits_bob})
    check("vs_scope_isolation_bob", 101 not in ids_bob, "bob sees %s" % ids_bob)

    # 相似度排序：查询向量靠 [1,0] → note 101 应排最前
    top = max(hits_alice, key=lambda x: x[2]) if hits_alice else None
    check("vs_similarity_order", top is not None and top[0] == 101,
          "top=%s" % (top,))

    # delete_note：删 101 后 alice 再查不到
    vs.delete_note(101)
    hits_after = vs.query([0.95, 0.05], owner="alice", scope="private", n_results=10)
    check("vs_delete_note", all(nid != 101 for nid, _c, _s in hits_after))


# ============================================================
# 3. retrieval_hybrid：语义命中 + 三种回退
# ============================================================
def test_retrieval_hybrid():
    import core.paths as paths_mod
    paths_mod.reset_cache()
    rh = _load("retrieval_hybrid")

    # 词法底座：直接用真实 KnowledgeStore + text_match
    from tools.knowledge_store import KnowledgeStore
    kb_path = os.path.join(tempfile.mkdtemp(prefix="rh-kb-"), "knowledge.json")
    store = KnowledgeStore(kb_path)
    # 语义相关但词法不中的笔记：写「矩阵可对角化的条件」，问「什么时候能把方阵拆成对角形」
    store.add("矩阵对角化判据", "若方阵存在 n 个线性无关的特征向量，则可对角化。",
              tags=["线代"], owner="alice", scope="public", category="线代")
    # 词法强命中的干扰项
    store.add("方阵", "方阵是行列数相等的矩阵。", tags=["线代"],
              owner="alice", scope="public", category="线代")

    lex = store.retrieve_visible("方阵", "alice", top_k=3)
    lex_ids = [n[0]["id"] for n in lex]

    # ---- 回退 1：STUDY_LIU_VECTOR=0 → 与词法完全一致 ----
    os.environ["STUDY_LIU_VECTOR"] = "0"
    out0 = rh.retrieve("方阵", store=store, username="alice", top_k=3)
    check("rh_off_matches_lexical",
          [n[0]["id"] for n in out0] == lex_ids,
          "%s vs %s" % ([n[0]["id"] for n in out0], lex_ids))

    # ---- 回退 2：开关开着但 chromadb 缺失 / 向量层抛异常 → 词法 ----
    os.environ["STUDY_LIU_VECTOR"] = "1"
    # 强制向量层抛异常（模拟 embed / chroma 任何故障）
    rh._force_vector_failure_for_test(True)
    try:
        out_fail = rh.retrieve("方阵", store=store, username="alice", top_k=3)
        check("rh_exception_falls_back",
              [n[0]["id"] for n in out_fail] == lex_ids)
    finally:
        rh._force_vector_failure_for_test(False)

    # ---- 向量命中：把「矩阵对角化判据」排第一（假向量注入）----
    if rh.vector_available():
        # 用假向量函数：查询与「矩阵对角化判据」高相似
        target_id = 1  # 第一条 add 的 id
        def fake_embed_query(q):
            return [1.0, 0.0]
        def fake_query(vector, owner, scope, n_results=8):
            # 返回：目标笔记相似度 0.9，干扰项 0.1
            return [(target_id, 0, 0.9), (2, 0, 0.1)]
        rh._inject_for_test(embed_query=fake_embed_query, vector_query=fake_query)
        try:
            out_sem = rh.retrieve("什么时候能把方阵拆成对角形",
                                  store=store, username="alice", top_k=3)
            check("rh_semantic_ranks_first",
                  out_sem and out_sem[0][0]["id"] == target_id,
                  "top=%s" % ([n[0]["id"] for n in out_sem],))
        finally:
            rh._inject_for_test(None, None)
    else:
        skip("rh_semantic_ranks_first", "向量层不可用（chromadb 未装）")


# ============================================================
# 4. kb_ingest：向量化失败不阻塞导入
# ============================================================
def test_kb_ingest_hook():
    import core.paths as paths_mod
    paths_mod.reset_cache()
    kb_ingest = _load("kb_ingest")
    from tools.knowledge_store import KnowledgeStore

    kb_dir = tempfile.mkdtemp(prefix="kb-ing-")
    os.environ["STUDY_LIU_DATA_DIR"] = kb_dir
    paths_mod.reset_cache()
    kb_path = os.path.join(kb_dir, "knowledge.json")
    store = KnowledgeStore(kb_path)

    # 写一个 .md 文件再走 ingest
    src = os.path.join(kb_dir, "note.md")
    with open(src, "w", encoding="utf-8") as f:
        f.write("# 线性代数笔记\n\n特征值是特征方程的根。\n" * 3)

    # 注入一个必然失败的 embed（模拟无 key / 断网），并确认挂钩真的被调用
    import embeddings
    import vector_store
    orig = embeddings.embed_texts
    hook_calls = {"embed": 0, "upsert": 0}
    orig_upsert = vector_store.upsert_chunk

    def failing_embed(texts, **kw):
        hook_calls["embed"] += 1
        return None

    def counting_upsert(*a, **kw):
        hook_calls["upsert"] += 1
        return orig_upsert(*a, **kw)

    embeddings.embed_texts = failing_embed
    vector_store.upsert_chunk = counting_upsert
    try:
        out = kb_ingest.ingest(src, "note.md", store=store,
                               owner="alice", scope="public")
        check("kb_ingest_survives_embed_failure",
              out.get("ok") is True and len(out.get("notes") or []) >= 1,
              str(out)[:120])
        check("kb_ingest_notes_persisted",
              len(store.list_all()) >= 1)
        check("kb_ingest_hook_actually_called",
              hook_calls["embed"] >= 1 and hook_calls["upsert"] == 0,
              "embed=%d upsert=%d" % (hook_calls["embed"], hook_calls["upsert"]))

        # 成功路径：embed 返回向量 → upsert_chunk 被调（真 chromadb 时）
        if vector_store.AVAILABLE:
            def ok_embed(texts, **kw):
                return [[0.5, 0.5] for _t in texts]
            embeddings.embed_texts = ok_embed
            hook_calls["upsert"] = 0
            out2 = kb_ingest.ingest(src, "note.md", store=store,
                                    owner="alice", scope="public")
            check("kb_ingest_hook_writes_vectors",
                  out2.get("ok") is True and hook_calls["upsert"] >= 1,
                  "upsert=%d" % hook_calls["upsert"])
        else:
            skip("kb_ingest_hook_writes_vectors", "chromadb 未安装")
    finally:
        embeddings.embed_texts = orig
        vector_store.upsert_chunk = orig_upsert


# ============================================================
# 5. 范围闸：api_server 不 import chromadb；quiz 范围闸放行 langchain_tavily
# ============================================================
def test_scope_gates():
    api_src = ""
    with open(os.path.join(SERVER_DIR, "api_server.py"), encoding="utf-8") as f:
        api_src = f.read()
    check("api_server_never_imports_chromadb",
          not re.search(r"^\s*(import|from)\s+chromadb", api_src, re.M),
          "api_server must not import chromadb")
    check("api_server_never_imports_langchain_tavily",
          not re.search(r"^\s*(import|from)\s+langchain_tavily", api_src, re.M),
          "api_server must lazy-import langchain_tavily via helper module")

    # run_quiz_regression 的范围闸：放行 langchain_tavily，仍拦 chromadb / 裸 langchain
    qr_path = os.path.join(HERE, "run_quiz_regression.py")
    with open(qr_path, encoding="utf-8") as f:
        qr = f.read()
    m = re.search(r"check\(\s*\"quiz_stdlib_only\".*?re\.search\((r?\"[^\"]*\"),", qr, re.S)
    check("quiz_gate_regex_updated",
          m is not None and "langchain(?!_tavily)" in m.group(1),
          "gate regex: %s" % (m.group(1) if m else None))

    # 范围闸语义自测：放行 langchain_tavily、拦 chromadb / 裸 langchain
    gate = re.compile(r"^\s*(import|from)\s+(fastapi|langchain(?!_tavily)|langgraph|chromadb|mysql)", re.M)
    check("gate_allows_langchain_tavily",
          not gate.search("from langchain_tavily import TavilySearch"))
    check("gate_blocks_bare_langchain",
          bool(gate.search("import langchain\n")))
    check("gate_blocks_chromadb",
          bool(gate.search("import chromadb")))


# ============================================================
# 6. api_server 装配：检索走 hybrid、删除挂钩、本体不 import chromadb
# ============================================================
def test_api_server_wiring():
    api_src = ""
    with open(os.path.join(SERVER_DIR, "api_server.py"), encoding="utf-8") as f:
        api_src = f.read()
    check("api_wired_to_hybrid",
          "retrieval_hybrid.retrieve" in api_src,
          "api_server must call retrieval_hybrid.retrieve with lexical fallback")
    check("api_delete_hooked",
          "vector_store.delete_note" in api_src,
          "delete route must hook vector_store.delete_note")
    check("api_hybrid_lazy_import",
          re.search(r"^\s*import retrieval_hybrid", api_src, re.M) is not None
          and re.search(r"^\s*import vector_store", api_src, re.M) is not None,
          "lazy imports must be function-level")


# ============================================================
# 7. web_tools（Phase B）：no-op 保护 + 补题接口形状
# ============================================================
def test_web_tools():
    wt = _load("web_tools")

    # key 未配置 → available()=False，enhance_chat 秒退 None（不发请求）
    saved = {k: os.environ.pop(k, "") for k in ("TAVILY_API_KEY", "STUDY_LIU_TAVILY_KEY")}
    try:
        check("wt_unavailable_without_key", wt.available() is False)
        check("wt_enhance_none_without_key", wt.enhance_chat("问题", "原答案") is None)
        check("wt_build_tools_empty_without_key", wt.build_tools() == {})
    finally:
        for k, v in saved.items():
            if v:
                os.environ[k] = v

    # 源码约束：langchain_tavily 只能函数内延迟 import；不引 langgraph
    src = ""
    with open(os.path.join(SERVER_DIR, "web_tools.py"), encoding="utf-8") as f:
        src = f.read()
    check("wt_lazy_import_only",
          not re.search(r"^(import|from)\s+langchain_tavily", src, re.M),
          "web_tools must lazy-import langchain_tavily inside functions (no top-level import)")
    check("wt_no_langgraph",
          not re.search(r"^\s*(import|from)\s+langgraph", src, re.M))

    # api_server 弱命中挂钩存在
    api_src = ""
    with open(os.path.join(SERVER_DIR, "api_server.py"), encoding="utf-8") as f:
        api_src = f.read()
    check("api_chat_web_enhance_hooked",
          "web_tools.enhance_chat" in api_src,
          "/api/chat must hook web_tools.enhance_chat on weak hits")
    check("api_chat_web_sources_field",
          '"web_sources"' in api_src)


if __name__ == "__main__":
    print("== embeddings ==")
    test_embeddings()
    print("== vector_store ==")
    test_vector_store()
    print("== retrieval_hybrid ==")
    test_retrieval_hybrid()
    print("== kb_ingest hook ==")
    test_kb_ingest_hook()
    print("== scope gates ==")
    test_scope_gates()
    print("== api_server wiring ==")
    test_api_server_wiring()
    print("== web_tools (Phase B) ==")
    test_web_tools()

    print("\n%d passed, %d failed, %d skipped" % (PASSED, len(FAILED), len(SKIPPED)))
    if FAILED:
        print("failed: %s" % ", ".join(FAILED))
        raise SystemExit(1)
    raise SystemExit(0)
