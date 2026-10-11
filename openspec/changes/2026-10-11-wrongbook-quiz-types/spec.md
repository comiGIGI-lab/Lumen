# Spec：错题本 × 闯关题型适配

## Objective

让三种题型（single / multi / judge）的闯关错题进错题本后**信息完整、可读、可筛选**：
多选的每个选中项文字都在，判断题显示「正确 / 错误」而不是裸 `0`，列表能一眼看出
题型与来源，并能按「只要闯关题」「只要多选题」过滤。成功标准：评委做完一局混合题型
闯关后，错题本里的每条都带题型徽标、答错的选项文字齐全，且能筛出「闯关 + 多选」。

## Tech Stack

- 后端：Python 3.9+ 标准库（`server/wrongbook_quiz.py` 纯转换 + `api_server.py` 两个路由），
  **零新增依赖**。
- 存储：继续 `vendor/study-liu/tools/wrong_book_store.py`（`data/wrong_book.json`），
  **不改 vendor，不加字段**。
- 前端：Vue3（`QuizPanel.vue` / `WrongBookPage.vue`）+ `client.js` + i18n（auto-zh/auto-en）。

## Commands

- 本切片回归：`python tests/run_wrongbook_quiz_regression.py`（35 项）
- 既有回归不破：`run_quiz_regression.py`（123）、`run_sidecar_regression.py`（106）、
  `run_safety_regression.py`（84）、`run_chat_retrieved_regression.py`（15）、
  `run_plan_kb_regression.py`（34）、`run_structured_parse_regression.py`（42）、
  `run_kb_scope_regression.py`、`run_crisis_regression.py`、`run_vector_rag_regression.py`
- 前端构建：`cd web && npm run build`（dist 不入库）

## 数据契约

### 存储侧（沿用既有字段，不加新字段）

| 字段 | 闯关题写入的值 |
| --- | --- |
| `source` | `"quiz"`（Day5 已约定，保持不变） |
| `tags` | 知识点、`"闯关"`、`"题型:多选"`（题型标签，中文形态便于关键词检索） |
| `question` | `"[多选] 题干\nA. …\nB. …\nC. …\nD. …"` |
| `my_answer` | 多选 → `"B（B. 字典）"`；全选写法 `"A、C（A. 列表；C. 生成器）"` |
| `answer` | `"正确答案：A、C（A. 列表；C. 生成器）。<讲解>"` |
| `reason` | `"知识点：<kp>"` |

长度上限与 `wrong_book_store` 对齐（`MAX_QUESTION=4000` / `MAX_ANSWER=6000` /
`MAX_REASON=1000`）；选项文本先按 400 裁一次，避免半句截断。

### 答案格式化的三条路径（`wrongbook_quiz.human_answer`）

- `single`：`"A. 元组"`。
- `multi`：**必须列全每个选中项**——`"A、C（A. 列表；C. 生成器）"`（key 排序去重）。
- `judge`：正解可能是 `int 0/1`（`-norm_answer_judge` 的产物），前端选中值是
  选项 key `"A"/"B"`，两种形态都要认；认不出时退回选项文本（一般是「正确 / 错误」）。

### API 契约

#### POST /api/wrongbook/from-quiz

请求：

    { "course": "Python 入门",
      "question": { "type": "multi", "stem": "…", "options": [{"key":"A","text":"…"}, …] },
      "selected": ["B"],
      "answer": ["A","C"],
      "explanation": "…",
      "knowledge_point": "迭代协议",
      "tags": ["迭代协议", "闯关"] }        // tags 可选，后端会再补题型标签

- `question` 非对象或 `stem` 为空 → `400 {"ok": false, "error": "题干不能为空"}`。
- 落库满 500 条时 `store.add_item` 抛 `ValueError` → 400 透传原文案。
- 成功：`{"ok": true, "item": {…, "qtype": "multi"}, "stats": …, "courses": …}`。
- 课程名已经在 `/api/quiz/generate` 过过安全闸，这里**不再拦一次**（避免重复埋点）。

#### GET /api/wrongbook

在原有 `course` / `q` / `status` 之外新增两个可选过滤参数：

- `source=quiz|manual` —— 直接比对既有 `source` 字段。
- `type=single|multi|judge` —— 由服务端用 `wrongbook_quiz.parse_qtype(item)`
  从 tags 解出题型后比对（store 的 `list_items` 不认这两个维度，只能读时过滤）。

响应每条 item **额外挂两个派生字段**（不入库）：`"qtype"（"" 表示无题型）`、
`"qtype_label"`。

## Project Structure

- `server/wrongbook_quiz.py`（新）：`normalize_qtype` / `qtype_label` / `type_tag` /
  `parse_qtype` / `is_quiz_item` / `render_question` / `human_answer` /
  `build_quiz_wrong`。纯函数，不 import 任何 store、不发网络请求。
- `server/api_server.py`（改）：import `wrongbook_quiz`；GET 加过滤与派生字段；
  POST 加 `from-quiz` 路由（必须排在 `startswith("/api/wrongbook/")` 之前）。
- `web/src/api/client.js`（改）：`wrongBookAddFromQuiz`；`wrongBookList` 增加
  `source` / `type`。
- `web/src/components/QuizPanel.vue`（改）：删掉前端拼字符串那段（连带修掉多选
  只取首个选项文字的 bug），改为回传结构化题目。
- `web/src/components/WrongBookPage.vue`（改）：题型 / 来源徽标 + 两个筛选下拉。
- `web/src/i18n/auto-zh.json` / `auto-en.json`（改）：`wrongBookQuiz.*`。
- `tests/run_wrongbook_quiz_regression.py`（新）。

## Code Style

- Python：标准库 only；中文注释写「为什么」；`_clip` 入参清洗与 wrong_book_store 同风格。
- `wrongbook_quiz` **不得** `import` 任何 store / vendor 模块——保证回归可以直接单测。
- Vue：`<script setup>`；`{{ }}` 插值，禁 `v-html`；文案一律走 `t('wrongBookQuiz.…')`。

## Testing Strategy

- `tests/run_wrongbook_quiz_regression.py`（先红后绿）两段：
  - 源检查：模块存在、`from-quiz` 路由存在、列表支持 `source`/`type`、
    服务端用 `parse_qtype` 派生 `qtype`、`client.js` 方法、`QuizPanel` 改走新接口、
    **多选只取首个选项的旧写法已消失**、`WrongBookPage` 徽标与筛选、
    i18n 中英 key 齐平且页面用到的 key 都已声明。
  - runtime：题型归一化、三题型格式化（含多选列全、`judge` 的 int 与 key 两种形态）、
    `build_quiz_wrong` 各字段、tags 往返、超长裁剪，最后用**真实**
    `tools.wrong_book_store`（临时 `STUDY_LIU_DATA_DIR`）落盘往返一次。
- Windows 控制台 GBK 打不出 ✅/❌，测试入口统一 `sys.stdout.reconfigure(encoding="utf-8")`。
- 九套既有回归必须全数保持。

## Boundaries

- Always：先红后绿；每步跑回归；题型格式化只存在于 Python 一侧。
- Ask first：改 `wrong_book_store`（本切片**再次确认不改**，Day5 起的约定一致）。
- Never：给 `add_item` 传多余入参；改 `/api/quiz/*` 的答案编码；在前端拼答案文本；
  force push；SSH；提交 dist/.env/data。

## Success Criteria

1. 多选答错入错题本时，「我的答案」列出**所有**选中项的文字。
2. 判断题显示「正确 / 错误」，不出现裸 `0` / `1`。
3. 错题本列表的每条闯关错题都带题型徽标；`source=quiz` 与 `type=multi` 能叠加筛选。
4. 新回归 35 项全绿，九套既有回归不破，`npm run build` 通过。
5. vendor 目录零改动（`git status` 里不出现 `vendor/`）。
