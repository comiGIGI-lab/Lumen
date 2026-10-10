# 决赛冲刺切片：向量数据库 RAG + Agentic 联网检索（混合检索升级）

只覆盖本切片：把知识库检索从「纯词法匹配」升级为「向量语义检索为主 + 词法为辅」的混合检索，并把已定稿的 Tavily 联网检索汇合进主问答链路。复刻外部参考方案（LangChain + Chroma + 百炼 text-embedding-v4 + Agentic RAG）的产品形态，但技术栈按本仓库硬约束改造（Chroma 嵌入式、urllib 直调百炼、仅放行 langchain-tavily）。

## 能力图

- `vector-embed`：`server/embeddings.py`。urllib 调百炼 text-embedding-v4（OpenAI 兼容），批 ≤10 自动分包，按 sha1(text+model+dim) 落 `data/embed_cache.json` 缓存；无 key/失败返回 None。复用 `core.config` 的 LLM key（同 dashscope）。
- `vector-store`：`server/vector_store.py`。**惰性 import chromadb**（未装绝不影响启动）；`PersistentClient(path="data/chroma")`；upsert/query/delete；metadata 含 note_id/owner/scope/category/chunk_index，查询按 owner/scope 复用现有可见性规则隔离。
- `retrieval-hybrid`：`server/retrieval_hybrid.py`。Chroma 向量 top-k + 现有词法 `KnowledgeStore.retrieve` → 加权融合（0.6×向量相似度 + 0.4×词法归一化分）；总开关 `STUDY_LIU_VECTOR`；任何异常/缺失/关闭 → 直接返回词法结果，行为与今天完全一致。
- `ingest-vector`：`server/kb_ingest.py` 挂钩（分块后追加向量化，失败不阻塞导入）+ `server/embed_backfill.py`（存量笔记一次性补建向量）。
- `web-tools`（Phase B）：`server/web_tools.py`。langchain-tavily 4 实例（search/extract × 标准/深度）+ 自写 tool-call 循环；接入主问答 agent_loop 的弱命中联网补题（quiz 已落地的 langchain-tavily 不变，此处收敛为共享模块）。

构建顺序：vector-embed → vector-store → retrieval-hybrid → ingest-vector；web-tools 可在 retrieval-hybrid 后并行，依赖 core/llm + TAVILY key。

## 为什么现在做

决赛演示的检索仍是纯词法，口语化/跨措辞提问命中差；参考方案已评审定稿（Chroma + 百炼 v4 + 放行 langchain-tavily），方案文档已出待开发。混合检索是「问答引用刚导入材料」「方案链路引用」之后最易感知的体验跃升，且回退机制保证零破坏、可一键关闭。

## 技术选型（已按官方文档核验，2026-10-10）

- 向量库：**Chroma 1.5.x** 嵌入式 `PersistentClient`；Rust 内核；`get_or_create_collection(embedding_function=None)` + 显式 `upsert`/`query`；**线程安全但非进程安全** → 单进程 pm2 可用，禁止双实例；需 SQLite ≥3.35。
- Embedding：**百炼 text-embedding-v4**，OpenAI 兼容 `POST /compatible-mode/v1/embeddings`；默认 1024 维；单请求 ≤10 条、单条 ≤8192 token（本仓库块 ≤700 字天然合规）；复用 LLM key，urllib 直调不引 SDK。
- 联网：**langchain-tavily**：`TavilySearch` + `TavilyExtract`（4 实例）；仅此包，不引 langchain/langgraph。
- 融合：加权 `0.6×向量 + 0.4×词法`，Chroma distance 按 `1/(1+distance)` 转相似度。

## 不做

- 不整体引入 LangChain 框架；api_server 零第三方依赖基线不破（chromadb 仅经惰性子模块，绝不 import 进 api_server）。
- 不换文档解析管线（自有 pypdf/MinerU + Docling/OOXML + blocks 强于 PyPDFLoader）。
- 不改 RAG 阈值（RAG_TOP_K=3 / MIN_SCORE=1.0 / MIN_COVERAGE=0.2）、不改 /api/chat 契约、不动前端、不改 vendor/study-liu/**。
- 不引 reranker、不建本地向量模型（1.6G 装不下）。
