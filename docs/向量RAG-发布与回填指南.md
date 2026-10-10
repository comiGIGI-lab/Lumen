# 向量 RAG 发布与存量回填指南（队友执行）

> 适用对象：负责服务器部署的同学（admin，免密 sudo；改 nginx 才需 sudo）
> 对应合入：`b95ec08`（`37d8eaa` 之上的 fast-forward，1 个提交）
> 配套规格：`docs/DEPLOY.md` 第 15 节、`openspec/changes/2026-10-10-vector-rag-agentic/`

## 0. 这次上了什么

知识库检索从纯词法升级为「0.6×向量语义 + 0.4×词法」融合检索；主问答在知识库弱命中（无资料）时，可走 Tavily 联网检索回灌 LLM（Phase B，可选）。

三条保底：任一依赖缺失 / 无 key / 未预期异常，**静默回退纯词法**，行为与改造前完全一致。api_server 本体不 import chromadb 或 langchain_tavily（惰性 import，范围闸守住）。

本切片只动 `server/` 与 `tests/` 与 `docs/DEPLOY.md`，**未动前端**。前端 `web/` 的改动是另一条线，与本切片互不相关。

## 1. 部署前置（拉代码 + 重启）

在服务器上以 admin 执行：

```bash
git pull --ff-only        # 取 b95ec08（已是 fast-forward，不要 force）
npm run build             # 前端；本切片未改前端，可跳过，但建议保持最新
pm2 restart my-api        # 用你们现用的进程名
```

`git pull --ff-only` 必须成功（非 ff 说明远端有别人新提交，先协调，不要 `--force`）。

## 2. 安装依赖（仅向量层需要；缺失则自动降级）

向量能力依赖两个第三方库，通过惰性 import 引入，未装不会让服务启动失败，只会自动回退词法。

**chromadb（向量库，1.5.x）**

```bash
pip3 install "chromadb>=1.5,<1.6"   # 或 pip3 install chromadb
```

SQLite 要求 ≥ 3.35：若 `import chromadb` 报 sqlite3 版本相关错误，先升级系统 SQLite，或：

```bash
pip3 install pysqlite3-binary
# 在启动环境变量里加：SQLITE3_BINARY=pysqlite3
```

**langchain-tavily（仅启用联网补题时需要）**

```bash
pip3 install langchain-tavily
```

需要 Tavily API Key（见 §4）。不装 / 不设 key，则该能力自动停用，不影响其它功能。

> 依赖版本与现有 server 同一 Python 解释器一致即可；向量层独立于 api_server 主进程加载。

## 3. pm2 必须单实例（硬性约束）

Chroma `PersistentClient` 线程安全但**非进程安全**。若 pm2 用 cluster 模式或 `instances > 1`，多进程会并发写同一份 `data/chroma`，导致索引损坏。

确认启动配置为单实例：

```bash
# 命令行启动时
pm2 start <entry> -i 1          # 或 exec_mode: "fork"

# 用 ecosystem.config.js 时
# instances: 1, exec_mode: "fork"   # 不要 instances: N>1 / exec_mode: cluster
```

验证：

```bash
pm2 describe my-api | grep -i instance   # 应为 1（或 fork）
```

## 4. 环境变量（设在 my-api 的 pm2 env / ecosystem 里）

| 变量 | 取值 | 说明 |
|------|------|------|
| `STUDY_LIU_VECTOR` | `1`（默认） | 向量检索总开关；设 `0` 立即回退纯词法，无需回滚代码 |
| `STUDY_LIU_EMBED_KEY` | 百炼 embedding key（**推荐**，可选） | 独立 embedding key，与对话 provider 解耦；一旦设置优先生效，避免对话配 DeepSeek 时复用其 key 打 dashscope 报 401 |
| `DASHSCOPE_API_KEY` | 百炼 key（可选） | `STUDY_LIU_EMBED_KEY` 缺省时的回退；二者皆无才回退 `core.config` 的对话 key |
| `STUDY_LIU_EMBED_MODEL` | `text-embedding-v4`（默认） | 百炼 embedding 模型名 |
| `STUDY_LIU_EMBED_DIM` | `1024`（默认） | embedding 维度，改模型时需同步 |
| `STUDY_LIU_TAVILY_KEY` | Tavily Key（可选） | 联网补题用；api_server 启动时映射到 `TAVILY_API_KEY` |

几点说明：

- 百炼 embedding 端点已硬编码为百炼 dashscope 的 OpenAI 兼容接口（`https://dashscope.aliyuncs.com/compatible-mode/v1`），**不走** DeepSeek 的 `LLM_BASE_URL`。
- **必须给一个百炼 key**：优先 `STUDY_LIU_EMBED_KEY`，其次 `DASHSCOPE_API_KEY`；两者皆无才回退 `core.config.get_api_key()`（即 `settings.json` / `LLM_API_KEY` 里的对话 key）。若对话 provider 是 DeepSeek，仅靠回退 key 会 401 → 静默回退词法，语义检索不生效。该 key 已通过真实调用验证（`text-embedding-v4` 返回 1024 维向量）。
- 联网补题也可直接设 `TAVILY_API_KEY` 代替 `STUDY_LIU_TAVILY_KEY`。不设则该能力自动停用。
- 改完环境变量后必须 `pm2 restart my-api` 生效。

## 5. 数据目录（不要进 git）

- `data/chroma/`（Chroma 持久化索引）
- `data/embed_cache.json`（embedding 结果缓存，sha1 键，幂等）

确认 `.gitignore` 已忽略 `data/`；不要把这两类提交到仓库。

## 6. 存量笔记回填（关键一步）

新导入的笔记会在入库时自动向量化（kb_ingest 挂钩）。但**部署前已存在于 `knowledge.json` 的笔记没有向量**，检索会偏向纯词法。需做一次存量回填：

```bash
# 预览：只打印将回填多少条，不写库
python server/embed_backfill.py

# 执行：为「向量库里还没有」的笔记补齐向量（增量，幂等）
python server/embed_backfill.py --apply

# 全量重算：忽略已有向量，仍走 embed 缓存（换模型维度时用）
python server/embed_backfill.py --apply --force
```

要求：chromadb 已装 + 百炼 key 已配。回填可放在业务低峰；执行期间不影响线上词法检索。`--apply` 之前务必先用默认（dry-run）确认数量符合预期。

## 7. 验证

向量回归（chromadb 未装时相关用例 SKIP，不算失败）：

```bash
python tests/run_vector_rag_regression.py
```

功能体检：

- `GET /api/knowledge?q=关键词` 应返回结果；服务端日志可见向量可用性判定。
- 观察启动日志里 embedding / vector 初始化是否成功（失败会打印并回退词法）。

内存提醒：若服务器可用内存 < 约 600MB，暂缓安装 chromadb（会拖慢或 OOM）；不装则本切片自动降级为纯词法，功能不降级只是少了语义检索维度。

## 8. 一键回退（出问题用）

设 `STUDY_LIU_VECTOR=0` 并 `pm2 restart my-api` → 立即回到纯词法，行为与改造前完全一致，无需代码回滚、无需重新部署。向量库 `data/chroma` 留着无妨，重开开关即恢复。

## 9. 给队友的注意点

- 本切片与前端 `web/` 改动相互独立，合入的是 server/tests/docs，不影响前端那条线。
- 不要 force push；本切片已是 fast-forward 合入（`37d8eaa → b95ec08`）。
- 若日后更换 embedding 模型或维度，用 §6 的 `--force` 重新向量化即可。
- 完整能力边界与回退路径见 `docs/DEPLOY.md` 第 15 节与 `openspec/changes/2026-10-10-vector-rag-agentic/spec.md`。
