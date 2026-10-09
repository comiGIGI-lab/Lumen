# Spec：课程问答选择题闯关

## Objective

在现有官网上复刻 yu-ai-learn 的「AI 出题 + 闯关答题」能力（可行范围）：用户按当前课程（科目）选择难度与题数，AI 基于知识库出单选题，逐题作答、服务端判分、即时讲解；答错自动入错题本，通关结算经验值。成功标准：评委在课程问答页即可完成一整局「出题 → 答题 → 讲解 → 结算 → 错题回顾」闭环。

## Tech Stack

- 后端：Python 3.9+ 标准库 `http.server`（新 `server/quiz.py`，零第三方依赖）。
- LLM：`core.llm.chat`（DeepSeek 兼容，走 vendor/study-liu 现有封装），mock 模式下 `chat` 不可用则返回明确错误，不出兜底假题。
- 检索：`tools.knowledge_store.KnowledgeStore.retrieve`，门槛与问答相同（RAG_MIN_SCORE=1.0 / RAG_MIN_COVERAGE=0.2 / RAG_TOP_K=3，**不重调**）。
- 存储：`data/quiz_runs.json`（结构见下，与 wrong_book.json 同目录约定）。
- 前端：Vue3 `QuizPanel.vue` + `ChatPage.vue` 入口 + `client.js` 两个方法 + i18n（auto-zh/auto-en）。

## Commands

- 回归（仓库根目录）：`python tests/run_quiz_regression.py`
- 既有回归不破：`python tests/run_sidecar_regression.py`（106）、`python tests/run_safety_regression.py`（84）、`python tests/run_chat_retrieved_regression.py`（15）、`python tests/run_plan_kb_regression.py`（34）
- 前端构建：`cd web && npm run build`（由队友执行，本切片不提交 dist）

## API 契约

### POST /api/quiz/generate

请求：`{ "course": "线性代数", "difficulty": "easy|medium|hard", "count": 3..8, "types": "single|multi|judge|mixed", "web_search": true }`

- course 必填（非空，经 detect_crisis + check_detail 同 `/api/chat` 前置闸）。
- difficulty 默认 `medium`；count 默认 5，钳制到 [3,8]；types 默认 `mixed`（按 2:1:1 拆 single/multi/judge）。
- **联网搜索开关 `web_search`**：默认 `true`。开启且配置了 `STUDY_LIU_TAVILY_KEY` 时调 Tavily search（超时 + 条数上限）取标题+摘要（单条摘要限长 `TAVILY_SNIPPET_MAX=500` 字）作联网参考；关闭 / 无 key / 搜索失败或超时 → 联网上下文为空并记 `logging.warning`（**降级而非拒绝**），仍继续出题。
- **私有知识库为可选增强**：课程名作 query 检索，命中则作为参考资料（题目 `source:"kb"`、`retrieved` 带 id/title/score）；弱命中或无结果**不再拒绝**，直接走入题（空上下文），题目 `source:"topic"`，前端按 `ok=true` 正常出题（不瞎编——由 `_build_prompt` 的 `material_rule` 约束「基于通用知识严谨出题，不杜撰」）。
- 课程名以 `http(s)://` 开头视作「丢链接出题」：跳过知识库与联网搜索；若配置了 `STUDY_LIU_TAVILY_KEY`，走 `POST https://api.tavily.com/extract`（body `{"api_key", "urls":[<url>]}`，超时 8s），取 `results[0].raw_content` 截断至 8000 字符作素材，题目 `source:"web"`、`sources:[{title,url}]`；无 key 或 extract 失败/超时 → 拒绝 `{"ok": false, "error": WEAK_HIT_ERROR, "retrieved": []}`（无 URL 正文无法出题）。
- Prompt 组装规则：有资料（kb 或 web）→「只能依据下方资料出题」；无任何资料（topic）→「下方暂无参考资料，请基于你对该主题的可靠通用知识严谨出题，确保事实准确、不杜撰」。
- 命中 / 弱命中 / 降级均 → LLM 出题，题目逐条校验：`id` 唯一（q1..qN）、`stem` 非空、`options` 恰好 4 个（key A–D、text 非空）、`answer` 恰好 1 个且 ∈ 选项 key、`explanation` 非空、`knowledge_point` 非空。校验失败丢弃该题；有效题 <3 → 报错不降级。
- 成功：`{"ok": true, "quiz_id": "z-xxxx", "course": ..., "difficulty": ..., "count": N, "questions": [{id, stem, options:[{key,text}], explanation, knowledge_point}], "retrieved": [{id,title,score}]}`。**响应不含 answer**（判分走服务端，答案不下发前端）。
- 落盘：quiz_id、完整题目（含 answer）、course、difficulty、created_at、client_id、作答记录写 `data/quiz_runs.json`。

### POST /api/quiz/grade

请求：`{ "quiz_id": "z-xxxx", "question_id": "q1", "selected": "A" }`

- quiz_id 不存在 → 404；question_id 不在局内 → 404。
- 成功：`{"ok": true, "question_id": ..., "selected": ..., "correct": true|false, "answer": "A", "explanation": "...", "knowledge_point": "..."}`。
- 落盘作答记录（question_id → selected/correct/answered_at）。

## Project Structure

- `server/quiz.py`（新）：出题 / 校验 / 缓存 / 判分 / 落盘，纯标准库。
- `server/api_server.py`（改）：do_POST 加两个路由，安全闸复用 detect_crisis / check_detail / log_crisis / log_safety_hit。
- `web/src/components/QuizPanel.vue`（新）：闯关 UI；含难度/题数/题型选择 + 联网搜索开关（pill 切换，i18n `quizPage.webSearch*`）。
- `web/src/components/ChatPage.vue`（改）：顶栏加入口按钮切换 ChatPanel/QuizPanel。
- `web/src/api/client.js`（改）：`quizGenerate(course, difficulty, count, types, webSearch)` / `quizGrade(quizId, questionId, selected)`。
- `web/src/i18n/auto-zh.json` / `auto-en.json`（改）：`quizPage.*` 中英键。
- `tests/run_quiz_regression.py`（新）：源检查 + 后端 runtime（mock LLM）。

## Code Style

- Python：标准库 only；注释中文、说明「为什么」；`_clip` 风格入参清洗与 wrong_book_store 一致。
- Vue：`<script setup>`；`{{ }}` 插值，禁 `v-html`；i18n 一律走 `t('quizPage.N')`。

## Testing Strategy

- `tests/run_quiz_regression.py`（TDD 先红后绿）：源检查（路由存在、安全闸顺序、answer 不下发、client 方法、QuizPanel/ChatPage/i18n 接线、web_search 开关接线）+ runtime（临时 data 目录注入假知识库 + mock llm.chat，验证弱命中降级出题、联网开关关闭/失败降级、URL 无 key/失败拒绝、出题校验、判分、落盘）。
- 既有四套回归必须全数保持。

## Boundaries

- Always：先红后绿；每步跑回归；不碰 `/api/chat` 与 RAG 门槛；`answer` 不出 generate 响应。
- Ask first：改 `wrong_book_store`（本切片不改，source 字段已兼容 'quiz'）；新增任何依赖。
- Never：FastAPI / LangChain / Chroma / Tavily / 文生图 / 微信登录 / 异步任务表；`import` 侧车进 api_server；force push；SSH；提交 dist/.env/data。

## Success Criteria

1. 课程问答页可发起闯关：选难度 + 题数 → 出题 → 逐题作答即时对错讲解 → 结算。
2. 主题题（非 URL）知识库弱命中不再拒绝，降级为空上下文并基于通用知识严谨出题（不杜撰）；仅「丢链接出题」在无 key/失败时才拒绝。
3. 答错题目出现在错题本，source=quiz。
4. 通关后学伴经验 +N（logExp('答题闯关')）。
5. 四套既有回归全过、新回归全绿。
