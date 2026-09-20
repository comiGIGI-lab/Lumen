# 知识库页接口契约 v0.1

> 智教星途 Web 版 · 前端知识库页 ⇄ FastAPI 后端
> 生成日期：2026-09-20　|　对应原型：`知识库页原型v0.2-2026-09-20.html`
> 线上地址（v3）：http://47.106.76.244

---

## 0. 通用约定

| 项 | 约定 |
|---|---|
| Base URL | `http://47.106.76.244`（后端实际前缀以部署为准，下方统一写作 `/api/v1`） |
| 协议 | HTTP/1.1，JSON；文件上传用 `multipart/form-data` |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601，带时区偏移，如 `2026-09-19T14:32:00+08:00` |
| 分页 | `page`（从 1 开始）、`page_size`（默认 20，最大 100） |
| 鉴权 | v0.1 阶段 `Authorization: Bearer <token>`，未登录返回 `401`；Demo 部署可先用 `X-Demo-User` 头绕过，赛后移除 |
| CORS | 后端需放通前端来源，`Access-Control-Allow-Headers` 含 `Authorization, Content-Type` |
| 幂等 | 所有 GET 幂等；retry 接口重复调用返回同一任务，不重复入队 |

**响应包装（推荐统一）：**

成功时直接返回业务对象（列表类返回 `{ items, total, page, page_size }`）；失败时统一返回错误结构（见 §6）。

---

## 1. 数据模型

### 1.1 Note（笔记）

| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| `id` | string | 笔记唯一 ID | `"n1"` |
| `title` | string | 笔记标题，**由后端返回多语言版本或单一语言** | `"高等数学 · 极限与连续"` |
| `tag` | enum | `high-math` / `english` / `mistakes` / `others` | `"high-math"` |
| `remark` | string \| null | 备注正文 | `"本周重点：ε-N 定义…"` |
| `document_count` | int | 关联文档数 | `3` |
| `created_at` | string(datetime) | 创建时间 | `"2026-09-12T09:10:00+08:00"` |
| `updated_at` | string(datetime) | 最近更新 | `"2026-09-19T14:32:00+08:00"` |

### 1.2 Document（文档）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 文档 ID |
| `name` | string | 原始文件名 |
| `type` | enum | `pdf` / `image` / `audio` |
| `status` | enum | 见 §2 状态机 |
| `progress` | int(0-100) | 仅 `parsing` 时有意义 |
| `chunks` | int | 已完成分块数，`queue`/`parsing`/`failed` 时为 `0` |
| `size_bytes` | int | 文件字节数 |
| `page_count` | int \| null | PDF 页数，图片/音频为 `null` |
| `error` | object \| null | `failed` 时的错误详情，含 `code`、`message` |
| `created_at` / `updated_at` | datetime | 时间戳 |

### 1.3 Chunk（分块，用于预览）

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | string | 分块序号，`"#01"` |
| `text` | string | 分块正文 |
| `source` | object | `{ document_id, page: 12, source_type: "pdf" \| "ocr" \| "asr" }` |

---

## 2. 状态机

```
              ┌──────────── retry ────────────┐
              ↓                               │
  upload → queue ──→ parsing ──→ ready        │
                       │                      │
                       └──→ failed ───────────┘
```

| 状态值 | 前端展示（zh/en） | 是否可提问 | 说明 |
|---|---|---|---|
| `queue` | 排队中 / Queued | 否 | 已入队，等待解析资源 |
| `parsing` | 解析中 / Parsing | 否 | 含 `progress` 百分比 |
| `ready` | 已入库 / Ready | **是** | 已完成嵌入，可检索 |
| `failed` | 解析失败 / Failed | 否 | 含 `error.code`，前端展示红色行 + 重试按钮 |

**前端轮询建议**：存在 `queue`/`parsing` 文档时，`GET /notes/{id}/documents` 每 3s 轮询一次；全部 `ready`/`failed` 后停止。后续可替换为 SSE/WebSocket，字段名保持不变。

---

## 3. 接口定义

### 3.1 GET /api/v1/notes

列表接口，对应原型左侧边栏。

**Query**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tag` | enum | 否 | 按标签过滤，不传表示全部 |
| `keyword` | string | 否 | 标题 + 标签模糊匹配 |
| `page` / `page_size` | int | 否 | 默认 1 / 20 |

**200 Response**

```json
{
  "items": [
    {
      "id": "n1",
      "title": "高等数学 · 极限与连续",
      "tag": "high-math",
      "remark": "本周重点：ε-N 定义…",
      "document_count": 3,
      "created_at": "2026-09-12T09:10:00+08:00",
      "updated_at": "2026-09-19T14:32:00+08:00"
    }
  ],
  "total": 8,
  "page": 1,
  "page_size": 20
}
```

> **多语言**：若启用服务端 i18n，增加 `Accept-Language: zh-CN \| en` 请求头，后端按该头返回 `title`；若由前端本地字典兜底（当前原型方案），后端只返回中文原文，前端按 `data-i18n` key 覆盖。建议 v0.1 采用后者，降低复杂度。

---

### 3.2 GET /api/v1/notes/{note_id}

单个笔记详情，对应原型主区「标题 + 元信息 + 备注」。

**200 Response**：同 Note 对象（§1.1）。

**错误**：`404 NOTE_NOT_FOUND`

---

### 3.3 GET /api/v1/notes/{note_id}/documents

文档列表，对应原型「关联文档」表格（含状态列）。

**Query**

| 参数 | 类型 | 说明 |
|---|---|---|
| `status` | enum | 可选，按状态过滤（`queue`/`parsing`/`ready`/`failed`） |

**200 Response**

```json
{
  "items": [
    {
      "id": "d101",
      "name": "第2章 极限与连续.pdf",
      "type": "pdf",
      "status": "ready",
      "progress": 100,
      "chunks": 42,
      "size_bytes": 2516582,
      "page_count": 18,
      "error": null,
      "created_at": "2026-09-12T09:10:00+08:00",
      "updated_at": "2026-09-12T09:12:31+08:00"
    },
    {
      "id": "d202",
      "name": "真题阅读扫描件.jpg",
      "type": "image",
      "status": "failed",
      "progress": 0,
      "chunks": 0,
      "size_bytes": 1130496,
      "page_count": null,
      "error": { "code": "OCR_FAILED", "message": "图片分辨率过低，OCR 未识别到文字" },
      "created_at": "2026-09-10T20:41:00+08:00",
      "updated_at": "2026-09-10T20:43:02+08:00"
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

**错误**：`404 NOTE_NOT_FOUND`

---

### 3.4 POST /api/v1/notes/{note_id}/documents/{doc_id}/retry

对应原型演示态 2「红色失败行 → 重试按钮」。

**202 Response**

```json
{ "id": "d202", "status": "queue", "message": "已重新加入解析队列" }
```

**错误**

- `404 DOC_NOT_FOUND`
- `409 DOC_NOT_RETRYABLE`（仅 `failed` 状态允许重试）

---

### 3.5 GET /api/v1/notes/{note_id}/documents/{doc_id}/chunks

对应原型「分块预览」区块。

**Query**：`page` / `page_size`

**200 Response**

```json
{
  "items": [
    {
      "chunk_id": "#01",
      "text": "数列极限的 ε-N 定义：对任意 ε>0，存在 N，当 n>N 时 |a_n - A| < ε…",
      "source": { "document_id": "d101", "page": 12, "source_type": "pdf" }
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

### 3.6 PATCH /api/v1/notes/{note_id}

对应原型「保存备注」按钮。

**Request**

```json
{ "title": "高等数学 · 极限与连续", "remark": "本周重点：ε-N 定义 + 两个重要极限" }
```

字段均可缺省。**200 Response**：更新后的 Note 对象。

---

### 3.7 POST /api/v1/notes

对应原型「+ 新建笔记」。

**Request**：`{ "title": "未命名笔记", "tag": "others" }` → **201** 返回新建 Note 对象。

---

## 4. 导入接口（与本次 DEMO 相关，另立文档详述）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/notes/{note_id}/documents:upload` | `multipart/form-data`，返回 Document 列表（`status=queue`） |
| GET | `/api/v1/tasks/{task_id}` | 解析任务详情（备用，可与轮询合并） |

> 文档导入页的完整 contract 另出一篇，此处仅保证知识库页的 DEMO 链路闭合。

---

## 5. 错误结构

所有非 2xx 响应统一：

```json
{
  "error": {
    "code": "DOC_NOT_FOUND",
    "message": "文档不存在或已被删除",
    "details": { "note_id": "n1", "doc_id": "d999" },
    "request_id": "req_8fa2c1b0"
  }
}
```

### 错误码表

| HTTP | code | 场景 | 前端处理 |
|---|---|---|---|
| 400 | `INVALID_TAG` | tag 取值非法 | 提示并回退到「全部」 |
| 401 | `UNAUTHORIZED` | 未登录 / token 失效 | 跳转登录 |
| 403 | `FORBIDDEN` | 访问他人笔记 | Toast 提示 |
| 404 | `NOTE_NOT_FOUND` | 笔记不存在 | 回退列表页 |
| 404 | `DOC_NOT_FOUND` | 文档不存在 | 刷新文档列表 |
| 409 | `DOC_NOT_RETRYABLE` | 非 failed 状态调用 retry | 禁用重试按钮 |
| 413 | `FILE_TOO_LARGE` | 文件超限 | 前端先做大小校验 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 类型不支持 | 前端限制 accept |
| 422 | `DOC_PARSE_FAILED` | 解析失败（落到行级 `error.code`） | 显示红色失败行 + 重试 |
| 429 | `RATE_LIMITED` | 轮询过频 | 退避到 5s |
| 500 | `INTERNAL_ERROR` | 服务异常 | Toast + 上报 `request_id` |

**约定**：文件上传/解析的业务失败**不用 HTTP 错误码表达**，而是落到 Document 的 `status=failed` + `error.code`，这样列表一次请求就能拿到全部状态，前端不用逐个查。

---

## 6. 原型假数据 → 接口字段映射（接后端时照这张表改）

| 原型变量 | 接口字段 | 改动说明 |
|---|---|---|
| `SEED_NOTES[].id / tag / updated / created` | `id / tag / updated_at / created_at` | 时间改 ISO 8601 字符串 |
| `I18N.zh['note.n1']` 标题 | `Note.title` | 若走前端字典则保留；服务端多语言则删本地 key |
| `SEED_DOCS[].name / type / status / chunks / progress / error` | 同名字段 | `type` 值域统一 pdf/image/audio |
| `STATUS_CLS` 色点映射 | `status` | 直接复用，无需改 |
| `DOCS[noteId]` 一次性全量 | `GET /notes/{id}/documents` | 切换为按当前 `currentNoteId` 拉取 |
| 侧边栏一次渲染 | `GET /notes?tag=&keyword=` | 搜索建议 debounce 300ms |

**前端切换清单（4 处）**

1. 新增 `api.js`：`fetchNotes(tag, keyword)`、`fetchDocuments(noteId)`、`retryDocument(noteId, docId)`，统一处理 401 / 错误 toast。
2. `renderSidebar()` 改为 `await` 拉取后渲染，加载中显示骨架屏。
3. `renderDetail()` 改为拉取文档列表；存在 `queue`/`parsing` 时启动 3s 轮询，全终态后 `clearInterval`。
4. `retryDocument()` 的本地 setTimeout 模拟 → 换成真实 POST，仍保留乐观更新（先改本地状态再收 202）。

---

## 7. 待定事项（需后端确认）

1. Base URL 前缀是否为 `/api/v1`，线上 47.106.76.244 是否走 HTTPS / 反代。
2. 标题多语言由服务端还是前端字典负责（建议 v0.1 前端字典）。
3. 轮询是否替换为 SSE；若替换，`Document` 结构保持不变即可平滑切换。
4. `notes` 是否需要软删除字段 `deleted_at`（影响列表默认过滤逻辑）。
