# Tasks：向量数据库 RAG + Agentic 联网检索

- [x] Task 1：失败回归先行（红）—— 建 `tests/run_vector_rag_regression.py`
  - Acceptance：覆盖 embeddings 请求体/分包/缓存/无 key 回 None、vector_store upsert/query/delete/scope 隔离、retrieval_hybrid 语义命中+三种回退、kb_ingest 向量失败不阻塞、范围闸放行 langchain_tavily；当前跑为红（模块未实现）。
  - Verify：`python tests/run_vector_rag_regression.py` 退出码非 0；chromadb 未装时相关用例 SKIP 不算失败。
  - Files：tests/run_vector_rag_regression.py（新）

- [x] Task 2：`vector-embed` —— `server/embeddings.py`
  - Acceptance：urllib 调百炼 /embeddings（model/dimensions/input≤10）；自动分包；`data/embed_cache.json` 按 sha1(text+model+dim) 缓存，命中不再发请求；无 key/失败返回 None；复用 `core.config` key。
  - Verify：run_vector_rag_regression.py 的 embeddings 用例转绿；monkeypatch urllib 验证分包与缓存。
  - Files：server/embeddings.py（新）

- [x] Task 3：`vector-store` —— `server/vector_store.py`
  - Acceptance：惰性 import chromadb，模块级 `AVAILABLE`；未装时公开方法 no-op 不抛 ImportError；`PersistentClient(path="data/chroma")`；upsert/query/delete；`where` 按 owner/scope 隔离。
  - Verify：装真 chromadb 时 query 返回按 owner/scope 过滤的结果；未装 SKIP。
  - Files：server/vector_store.py（新）

- [x] Task 4：`ingest-vector` —— `server/kb_ingest.py` 挂钩 + `server/embed_backfill.py`
  - Acceptance：kb_ingest 分块入库后追加向量化，embedding 失败不阻塞导入（笔记仅词法可检）；embed_backfill 为存量笔记补建向量，走缓存不重复计费。
  - Verify：run_vector_rag_regression.py 的 kb_ingest 用例绿；sidecar/safety/quiz/chat/plan/structured 回归不破。
  - Files：server/kb_ingest.py（改）、server/embed_backfill.py（新）

- [x] Task 5：`retrieval-hybrid` + api_server 装配 —— `server/retrieval_hybrid.py`
  - Acceptance：Chroma top-k + 词法 retrieve 按 `0.6×sim + 0.4×lex` 融合；`STUDY_LIU_VECTOR=0`/缺失/异常 → 直接返回词法；删除笔记路由挂钩 `vector_store.delete_note`；api_server 启动按 env 装配、本体不 import chromadb。
  - Verify：语义相关但词法不中的笔记排第一；三种回退结果与词法完全一致；删除笔记向量清理。
  - Files：server/retrieval_hybrid.py（新）、server/api_server.py（改）

- [x] Task 6（Phase B）：`web-tools` —— `server/web_tools.py` + 范围闸改法
  - Acceptance：langchain-tavily 4 实例 + 自写 tool-call 循环（不引 langgraph）；接入 agent_loop 弱命中联网补题；`tests/run_quiz_regression.py:112` 范围闸改为禁 `fastapi|langgraph|chromadb|mysql|裸 langchain`，放行 `from langchain_tavily import ...`；断言 quiz.py 不得 import chromadb。
  - Verify：quiz/新向量回归全绿；范围闸仍拦 chromadb/裸 langchain、放行 langchain_tavily。
  - Files：server/web_tools.py（新）、tests/run_quiz_regression.py（改）

- [x] Task 7：全量回归 + DEPLOY 第 15 节
  - Acceptance：六套既有回归全过（sidecar 106 / safety 84 / quiz 37 / chat 15 / plan 34 / structured 32）+ 向量新增回归全绿；`docs/DEPLOY.md` 追加第 15 节（队友装 chromadb/langchain-tavily + SQLite≥3.35 核验 + pm2 单实例 + embed_backfill + `STUDY_LIU_VECTOR=0` 一键回退）。
  - Verify：全部回归命绿；DEPLOY 第 15 节内容齐备。
  - Files：docs/DEPLOY.md（改）
