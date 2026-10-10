# Spec：向量数据库 RAG + Agentic 联网检索

## Objective

把知识库检索从纯词法升级为「向量语义为主 + 词法为辅」的混合检索，口语化/跨措辞提问命中显著改善；并把已定稿的 Tavily 联网检索汇合进主问答链路（Agentic 路由）。成功标准：开启 `STUDY_LIU_VECTOR=1` 后，语义相关但词法不中的笔记能排到检索前列；向量层不可用（未装 chromadb / 无 key / 断网 / 报错）时自动回退词法 RAG，行为与现状完全一致；既有全量回归不破。

## Tech Stack

- 后端：Python 3.9+ 标准库 `http.server`；新增 `server/embeddings.py` / `vector_store.py` / `retrieval_hybrid.py` / `web_tools.py` 均为**惰性依赖 chromadb/langchain-tavily**，api_server 本体不 import 二者。
- 向量库：Chroma 1.5.x（`pip3 install chromadb`），`PersistentClient(path="data/chroma")`，需 SQLite ≥3.35。
- Embedding：百炼 text-embedding-v4，urllib 直调 dashscope OpenAI 兼容接口，复用 `core.config.get_api_key()/get_base_url()`，key 不新增管理面。
- 联网：langchain-tavily（`pip3 install langchain-tavily`），仅 `from langchain_tavily import TavilySearch, TavilyExtract`，key 来自 `STUDY_LIU_TAVILY_KEY` 环境变量（不入库不入 git）。
- 检索：现有 `tools.knowledge_store.KnowledgeStore.retrieve`（词法，不动）；混合在 server 层包裹。
- 测试：标准库 `unittest`；本地 venv 装真 chromadb 跑向量用例，未装则 SKIP 不算失败。

## Commands

- 向量回归（仓库根）：`python tests/run_vector_rag_regression.py`
- 既有回归不破：`python tests/run_sidecar_regression.py`（106）、`run_safety_regression.py`（84）、`run_quiz_regression.py`（37）、`run_chat_retrieved_regression.py`（15）、`run_plan_kb_regression.py`（34）、`run_structured_parse_regression.py`（32）
- 存量回填：`python3 server/embed_backfill.py`
- 前端构建：`cd web && npm run build`（队友执行，不提交 dist）

## 模块契约

### server/embeddings.py
- `embed_texts(texts: list[str], *, model=EMBED_MODEL, dim=EMBED_DIM) -> list[list[float]] | None`：单请求 ≤10 条自动分包；缓存键 `sha1(text+model+dim)` → `data/embed_cache.json`；无 key、网络失败、非 200 → 返回 `None`（调用方回退词法）。
- `embed_query(text) -> list[float] | None`：单条封装。

### server/vector_store.py
- 惰性 `import chromadb`；模块级 `AVAILABLE` 标志；不可用时所有公开方法 no-op 返回空。
- `upsert_chunk(note_id, chunk_index, text, embedding, owner, scope, category)`；`delete_note(note_id)`；`query(vector, *, owner, scope, n_results=TOP_K) -> list[(note_id, chunk_index, score)]`。
- query 的 `where` 按 `(owner, scope)` 隔离，复用 `KnowledgeStore` 可见性规则。

### server/retrieval_hybrid.py
- `retrieve(query, *, owner, scope, top_k=3) -> list[Retrieved]`：向量可用时取向量 top-k，词法取 `KnowledgeStore.retrieve`，按 `0.6×sim + 0.4×lex` 融合排序；`STUDY_LIU_VECTOR=0` / chromadb 缺失 / 任何异常 → 直接返回词法结果。
- 融合分低于当前词法阈值时维持现有弱命中拒绝逻辑（不放水）。

### server/web_tools.py（Phase B）
- `TavilySearch`/`TavilyExtract` 4 实例（标准/深度 × search/extract）；自写 `<tool>`/`<finish>` tool-call 循环（不引 langgraph）。
- 接 `agent_loop` 弱命中分支：用户要求联网或弱命中时调用，结果作为参考资料回灌 LLM。

## Project Structure

- `server/embeddings.py`（新）：百炼 embedding 适配 + 缓存。
- `server/vector_store.py`（新）：Chroma 惰性封装 + scope 隔离。
- `server/retrieval_hybrid.py`（新）：融合检索 + 总开关 + 回退。
- `server/web_tools.py`（新，Phase B）：langchain-tavily 4 实例 + tool-call 循环。
- `server/embed_backfill.py`（新）：存量笔记一次性向量回填。
- `server/kb_ingest.py`（改）：分块入库后挂钩向量化，失败不阻塞。
- `server/api_server.py`（改）：删除笔记路由挂钩 `vector_store.delete_note`；启动按 env 装配混合检索；本体不 import chromadb/langchain_tavily。
- `tests/run_vector_rag_regression.py`（新）：TDD 先行。
- `tests/run_quiz_regression.py`（改，第 112 行）：范围闸改法——禁 `fastapi|langgraph|chromadb|mysql|import langchain（裸）`，放行 `from langchain_tavily import ...`。
- `docs/DEPLOY.md`（改）：追加第 15 节（队友安装 chromadb/langchain-tavily + SQLite 核验 + 单实例 + 回填 + 一键回退）。

## Code Style

- Python：标准库 only（chromadb/langchain-tavily 仅惰性 import）；注释中文、说明「为什么」；与 `quiz.py` 的 `_clip`/安全闸风格一致。
- 新模块一律 `AVAILABLE` 标志 + 惰性 import，未装依赖时公开方法 no-op，绝不抛 ImportError 阻断启动。

## Testing Strategy

`tests/run_vector_rag_regression.py`（TDD 先红后绿）：
1. embeddings：请求体形状（model/dimensions/input≤10）、自动分包、缓存命中不再发请求、无 key 返回 None（monkeypatch urllib）。
2. vector_store：upsert/query/delete、where 按 owner/scope 隔离（本地 venv 装真 chromadb 跑；未装 SKIP 不算失败）。
3. retrieval_hybrid：向量命中把语义相关但词法不中的笔记排第一；融合分单调；`STUDY_LIU_VECTOR=0` / chromadb 缺失 / 抛异常 三种回退下结果与现有词法完全一致。
4. kb_ingest：embedding 失败时导入仍成功（notes 正常落库）。
5. 范围闸：改后正则仍拦 chromadb/裸 langchain、放行 langchain_tavily。
6. 全量回归保持绿：sidecar 106 / safety 84 / quiz 37 / chat 15 / plan 34 / structured 32。

## Boundaries

- Always：先红后绿；每步跑回归；向量层任何异常回退词法；导入向量化失败不阻塞；总开关一键禁用（`STUDY_LIU_VECTOR=0`）；桌面版（vendor）零改动。
- Ask first：新增 `chromadb` / `langchain-tavily` 依赖（已定稿放行，但安装动作由队友在服务器执行）；改 RAG 阈值；改 /api/chat 契约。
- Never：FastAPI / LangGraph / 裸 langchain / 文生图 / 微信登录；`import` chromadb 或 langchain_tavily 进 api_server；force push；SSH；提交 dist/.env/data；引 reranker 或本地向量模型。

## Success Criteria

1. `STUDY_LIU_VECTOR=1` 时，语义相关但词法不中的笔记能排在检索前列，问答引用质量提升。
2. `STUDY_LIU_VECTOR=0` / chromadb 未装 / 无 key / 断网 / 向量化抛异常 任一情况下，检索结果与现状词法 RAG 完全一致。
3. 存量 ~25 条笔记经 `embed_backfill.py` 补建向量，走免费额度，无重复计费（缓存命中）。
4. 删除笔记时其向量随之清理（delete_note 挂钩生效）。
5. 六套既有回归全过、向量新增回归全绿；范围闸放行 langchain_tavily、仍拦 chromadb/裸 langchain。
6. Phase B：主问答弱命中可走 Tavily 联网补题（复用已落地的 langchain-tavily，收敛为 web_tools 共享模块）。
