# 知识库页接口契约 v0.2

> 智教星途 Web 版 · 前端知识库页 ⇄ Python 后端
> 生成日期：2026-09-20　|　对应原型：`知识库页原型v0.3-2026-09-20.html`
> 线上地址（v3）：http://47.106.76.244
> 相对 v0.1 的变化：**后端技术栈修正**（v0.1 写的是 FastAPI，实测是 Python 标准库 `http.server`）；**接口前缀去掉 `/v1`**；**按阶段拆分**，阶段一对齐 v3 现状、阶段二保留三层模型作为目标态。

---

## 0. 通用约定

| 项 | v0.1 写法 | v0.2 修正后 | 依据 |
|---|---|---|---|
| 后端实现 | FastAPI | Python 标准库 `http.server`（`server/api_server.py`，`BaseHTTPRequestHandler`） | 实测源码，非 FastAPI |
| Base URL | `http://47.106.76.244`，前缀 `/api/v1` | `http://47.106.76.244`，前缀 `/api` | 现有路由全部为 `/api/*`，无 `/v1` |
| 可用方法 | 隐含支持 PATCH | **仅 GET / POST / OPTIONS** | 源码只有 `do_GET`/`do_POST`/`do_OPTIONS`，无 PUT/PATCH/DELETE |
| 字符编码 | UTF-8 | UTF-8 | 一致 |
| 时间格式 | ISO 8601 带时区 | 阶段一 `"YYYY-MM-DD HH:MM:SS"`；阶段二转 ISO 8601 | `KnowledgeStore.add` 用 `strftime("%Y-%m-%d %H:%M:%S")` |
| 分页 | `page`/`page_size` | **阶段一无分页**；阶段二再引入 | `list_all()` 直接返回全量 |
| 鉴权 | `Authorization: Bearer` | **阶段一无鉴权** | 源码无入站鉴权；第 326 行的 `Bearer` 是后端调 DeepSeek 的出站头 |
| CORS | 需放通 `Authorization` | `Allow-Origin: *`，`Allow-Methods: GET, POST, OPTIONS`，`Allow-Headers: Content-Type` | `api_server.py` 第 622–624 行 |

**响应包装（阶段一，对齐现状）**：成功返回业务对象，列表类返回 `{ items, total }`；失败返回 `{ "ok": false, "error": "..." }`。v0.1 设计的 `{ error: { code, message, details, request_id } }` 嵌套结构在阶段一不采用，阶段二再统一。

**CORS 的一个隐患**：`Access-Control-Allow-Headers` 只有 `Content-Type`。`9004991` 引入的 `X-Client-Id` 头不在允许列表里。当前 dev（Vite proxy）与生产（同源伺服）都不触发跨域预检所以没暴露，一旦前后端分域部署就会失败。阶段二若保留自定义头，需要同步加进 `Allow-Headers`。

---

## 1. 后端现状（阶段一契约的事实基础）

知识库存储由 `vendor/study-liu/tools/knowledge_store.py` 提供，单文件 `data/knowledge.json` 持久化，用 `threading.RLock` 保护读-改-写的原子性。类提供 `add` / `search` / `list_all` / `delete` 四个方法。

HTTP 层只接了一个路由：`GET /api/knowledge`（`api_server.py` 第 751–754 行），带 `?q=` 时走 `search(q)`，不带则走 `list_all()`，返回 `{ items, total }`。

**三个必须先讲清楚的缺口：**

其一，`add()` 与 `delete()` 在 `KnowledgeStore` 里有完整实现，但 HTTP 层没有对应路由 —— 没有任何接口能往知识库里写东西，也没有接口能删。

其二，全仓库检索下来，生产代码里只有 `core/agent_loop.py` 第 196 行调用过 `store.search()`，`add()` 仅出现在 `vendor/study-liu/tests/` 下。也就是说 v3 线上目前**没有任何写入路径**，知识库实际是空的。前端知识库页接上去只会看到空状态。

其三，`do_POST` 里没有 multipart 解析，文件上传在阶段一不支持。

**结论：阶段一的第一优先级不是列表页，而是先补写入端点。** 否则知识库页永远只能演示空状态。

---

## 2. 数据模型

### 2.1 阶段一：Note（平铺笔记，对齐 `KnowledgeStore` 现状）

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| `id` | int | 自增 ID（`max(id)+1`） | `7` |
| `title` | string | 标题 | `"高等数学 · 极限与连续"` |
| `content` | string | 正文 | `"本周重点：ε-N 定义…"` |
| `tags` | string[] | 标签列表，可为空数组 | `["高数", "极限"]` |
| `created_at` | string | 创建时间，本地时间无时区 | `"2026-09-12 09:10:00"` |

阶段一**没有** `tag` 枚举、**没有** `updated_at`、**没有** `document_count`、**没有** Document / Chunk 概念。原型里左侧边栏的分类（高数/英语/错题/其他）由前端按 `tags` 本地归类，不依赖后端枚举。

### 2.2 阶段二目标态：Note / Document / Chunk 三层

保留 v0.1 §1.1–1.3 的三层模型定义不变，仅作两处调整：接口前缀去掉 `/v1`；时间格式统一为 ISO 8601。这一层是**目标态而非当前承诺**，后端在阶段一完成后再评估是否推进。

---

## 3. 阶段一接口定义

### 3.1 GET /api/knowledge

列表 / 搜索，对应知识库页主表格。**已实现，无需改动。**

**Query**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | string | 否 | 关键词；不传返回全量。匹配 `title` / `content` / `tags` 的子串，不区分大小写 |

**200 Response**

```json
{
  "items": [
    {
      "id": 1,
      "title": "高等数学 · 极限与连续",
      "content": "本周重点：ε-N 定义…",
      "tags": ["高数"],
      "created_at": "2026-09-12 09:10:00"
    }
  ],
  "total": 1
}
```

**已知行为约束（前端需适配）**：搜索是纯子串匹配，无分词、无相关度排序、无分页。结果顺序即文件存储顺序。关键词为空串时走全量返回。

---

### 3.2 POST /api/knowledge

新增笔记。**阶段一需新增**，直接复用 `KnowledgeStore.add()`。

**Request**

```json
{ "title": "高等数学 · 极限与连续", "content": "正文…", "tags": ["高数"] }
```

`tags` 可缺省（默认 `[]`）。

**200 Response**

```json
{ "ok": true, "id": 7, "item": { "id": 7, "title": "…", "content": "…", "tags": ["高数"], "created_at": "2026-09-20 16:40:12" } }
```

**错误**：`title` 与 `content` 均为空时返回 `400 { "ok": false, "error": "标题与内容不能同时为空" }`。

**建议同时接入敏感词过滤**：`check_sensitive(title + content)`，与 `POST /api/plan` 保持一致的拦截口径。过滤方案见同目录 `敏感词过滤-白名单为主的最小改动建议-2026-09-20.md`。

---

### 3.3 POST /api/knowledge/delete

删除笔记。**阶段一需新增**，复用 `KnowledgeStore.delete()`。

之所以用 POST 而不是 RESTful 的 `DELETE /api/knowledge/{id}`，是因为当前 handler 没有实现 `do_DELETE`。若后端愿意补一个 `do_DELETE`，路径改为 `DELETE /api/knowledge?id=7` 更规范，前端同样能接。

**Request**

```json
{ "id": 7 }
```

**200 Response**

```json
{ "ok": true, "id": 7 }
```

**错误**：ID 不存在时返回 `404 { "ok": false, "error": "笔记不存在" }`（`delete()` 返回 False）。

---

### 3.4 POST /api/knowledge/import

导入 MD / TXT 文本或粘贴内容。**阶段一需新增**，是把「文档导入页」跑通的最小入口。

**Request**

```json
{ "title": "第2章 极限与连续", "text": "（全文纯文本）", "tags": ["高数"], "source": "paste" }
```

`source` 取值 `paste` / `md` / `txt`，仅作记录用，阶段一不参与逻辑。

**200 Response**：同 §3.2。

**约束**：阶段一**不支持文件上传**（无 multipart 解析）。文件导入由前端读取本地文件后以纯文本形式走本接口，后端不接触二进制。PDF / 图片 / 音频的多模态解析（`vendor` 里已有 `document_importer`）留到阶段二。

---

## 4. 阶段二接口定义（目标态）

以下接口沿用 v0.1 §3 的定义，仅把前缀从 `/api/v1` 改为 `/api`，其余字段、状态机、错误码不变：

| 方法 | 路径（v0.2） | v0.1 原路径 | 说明 |
|---|---|---|---|
| GET | `/api/notes` | `/api/v1/notes` | 笔记列表，支持 tag / keyword / 分页 |
| GET | `/api/notes/{note_id}` | 同（去 v1） | 笔记详情 |
| GET | `/api/notes/{note_id}/documents` | 同（去 v1） | 关联文档列表（含状态列） |
| POST | `/api/notes/{note_id}/documents/{doc_id}/retry` | 同（去 v1） | 解析失败重试 |
| GET | `/api/notes/{note_id}/documents/{doc_id}/chunks` | 同（去 v1） | 分块预览 |
| PATCH | `/api/notes/{note_id}` | 同（去 v1） | 保存备注 |
| POST | `/api/notes` | 同（去 v1） | 新建笔记 |

状态机（`queue` / `parsing` / `ready` / `failed`）与轮询建议沿用 v0.1 §2。**注意**：阶段二若要支持 PATCH，后端必须先补 `do_PATCH` handler，否则 405。

---

## 5. 阶段一降级清单（相对 v0.1，逐项说明为什么）

| v0.1 能力 | 阶段一 | 原因 | 前端怎么兜 |
|---|---|---|---|
| 三层模型（Note/Document/Chunk） | 降级为平铺笔记 | 后端无 Document 概念，无分块存储 | 原型「关联文档」表格暂不展示 |
| 解析状态机 + 进度 | 移除 | 无异步解析任务 | 演示态用本地假数据；真实链路阶段二再接 |
| 文件上传（multipart） | 不支持 | `do_POST` 无 multipart 解析 | 前端读本地文件转纯文本走 §3.4 |
| PDF / 图片 / 音频解析 | 不支持 | `document_importer` 在 vendor 未接 | 阶段一仅 MD / TXT / 粘贴 |
| retry 接口 | 移除 | 无失败态 | 演示态 2（红色失败行 + 重试）用本地模拟 |
| 分页 | 移除 | `list_all()` 全量返回 | 数据量小，前端本地截断 |
| 鉴权 / 401 | 移除 | 后端无入站鉴权 | 不跳转登录 |
| 结构化错误码 `{error:{code}}` | 降级为 `{ok, error}` | 与现有路由一致 | Toast 直接显示 `error` 字符串 |
| ISO 8601 时间 | 降级为 `YYYY-MM-DD HH:MM:SS` | `strftime` 现状 | 前端格式化时兼容两种 |

**演示相关的三个状态仍然要做**，只是靠前端本地假数据：空知识库空状态引导、解析失败红色行 + 重试按钮、导入弹窗上传进度动画。这三个是评委会看的点，不能因为没有后端就砍掉。

---

## 6. 原型假数据 → 接口字段映射

| 原型变量 | 阶段一接口字段 | 改动说明 |
|---|---|---|
| `SEED_NOTES[].id / tag / updated / created` | `id / tags[0] / — / created_at` | `updated` 阶段一取 `created_at`；`tag` 用 `tags[0]` |
| 笔记标题 | `Note.title` | 后端只返回中文，i18n 由前端 `data-i18n` 字典兜底 |
| `SEED_DOCS[]` 全表 | — | 阶段一无对应接口，保留本地假数据 |
| `STATUS_CLS` 色点映射 | — | 同上，演示态本地维护 |
| `DOCS[noteId]` 一次性全量 | — | 阶段二换 `GET /api/notes/{id}/documents` |
| 侧边栏一次渲染 | `GET /api/knowledge` | 搜索建议 debounce 300ms；无 `q` 时全量 |

**前端切换清单（阶段一）**

1. 新增 `api.js`：`fetchNotes(q)`、`createNote({title, content, tags})`、`deleteNote(id)`、`importText({title, text, tags})`，统一处理 `{ok:false}` 并 toast `error`。
2. `renderSidebar()` 改为 `await` 拉取后渲染，加载中显示骨架屏。
3. 新建 / 删除走真实接口，保留乐观更新；失败回滚并 toast。
4. 演示三态（空状态 / 失败重试 / 上传进度）用 `import.meta.env` 开关或 `?demo=1` 查询参数切到本地假数据，正式演示前确认走哪条路径。

---

## 7. 阻塞项与待后端确认

1. **最高优先级**：补 `POST /api/knowledge` 与删除端点。在补上之前，知识库在线上没有任何写入路径，前端接了也只能看到空列表。
2. 是否需要补 `do_DELETE` / `do_PATCH` handler（影响 §3.3 的路径形态与阶段二的 PATCH）。
3. `X-Client-Id` 头是否要加进 `Access-Control-Allow-Headers`（当前分域部署会挂）。
4. 阶段二是否推进三层模型与异步解析；若推进，轮询是否换成 SSE（`GET /api/plan/stream` 已有 SSE 实现可复用，也是 PPT 技术方案章节的核心亮点）。
5. 演示环境的知识库种子数据怎么来 —— 是手工写 `data/knowledge.json`，还是先调几次 `POST /api/knowledge` 灌进去。建议在演示前用真实接口灌 3–5 条，避免出现「接口通的但列表空的」尴尬场面。
