# Spec：课程问答选择题闯关

## Objective

在现有官网上复刻 yu-ai-learn 的「AI 出题 + 闯关答题」能力（可行范围）：用户按当前课程（科目）选择难度与题数，AI 基于知识库出单选题，逐题作答、服务端判分、即时讲解；答错自动入错题本，通关结算经验值。成功标准：评委在课程问答页即可完成一整局「出题 → 答题 → 讲解 → 结算 → 错题回顾」闭环。

## Tech Stack

- 后端：Python 3.9+ 标准库 `http.server`（新 `server/quiz.py`，**零第三方依赖；仅 quiz 出题联网链路经队长批准引入 `langchain-tavily`**）。
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
- **联网搜索开关 `web_search`**：默认 `true`。`api_server` 装配时把 `STUDY_LIU_TAVILY_KEY` 映射进 `TAVILY_API_KEY`（key 不入库）。开启且配置了 key 时，`server/quiz.py` 以**工具智能体**出题：用 `langchain-tavily` 实例化 4 个工具——`tavily_search`(basic,max_results=10,raw_content=False)、`tavily_search_deep`(advanced,max_results=15,include_raw_content=True)、`tavily_extract`(basic)、`tavily_extract_deep`(advanced)，绑到现有出题 LLM（`core.llm.chat`，纯文本、无原生工具调用，故自写 `<tool>`/`<finish>` prompt 工具循环，**不引 langgraph**）。工具智能体最多 `MAX_AGENT_STEPS=8` 轮（多关键词变体检索需要更多轮）。System prompt 指示：用户给 URL → 用 extract；给主题 → 用 search；按复杂度自选自浅/深实例，可动态设 `search_depth`/`time_range`/`include_domains`；**国内（中文）用户默认 `include_domains` 含中文域（*.cn/ *.edu.cn/ *.gov.cn/ *.com.cn/ *.org.cn）**；对专业/多义/易混淆词（如 "harness engineering"）须用多个关键词变体分别检索、结果少时继续换词，**综合所有结果以「多数领域」为准**判定主题，忽略指向错误领域的离群结果。模型取工具返回内容出题，题目 `source:"web"` + `sources:[{title,url}]`（extract 用该 URL）。**每次搜索都会记录 INFO 日志（工具名 / 调用参数 / 返回结果条数与摘要）**，便于排查；工具调用失败/超时 → 记 `logging.warning` 并降级为空上下文（**降级而非拒绝**），仍继续出题；无 key 或 URL 场景 extract 失败 → 拒绝 `WEAK_HIT_ERROR`。
- **私有知识库为可选增强**：课程名作 query 检索，命中则作为参考资料（题目 `source:"kb"`、`retrieved` 带 id/title/score）；弱命中或无结果**不再拒绝**，直接走入题（空上下文），题目 `source:"topic"`，前端按 `ok=true` 正常出题（不瞎编——由 `_build_prompt` 的 `material_rule` 约束「基于通用知识严谨出题，不杜撰」）。
- 课程名以 `http(s)://` 开头视作「丢链接出题」：跳过知识库与联网 search，直接让工具智能体用 `tavily_extract`/`tavily_extract_deep` 抓取该 URL 正文（截断至 8000 字符）作素材，题目 `source:"web"`、`sources:[{title,url}]`（用该 URL）；无 key 或 extract 失败/超时 → 拒绝 `{"ok": false, "error": WEAK_HIT_ERROR, "retrieved": []}`（无 URL 正文无法出题）。
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

- `server/quiz.py`（改）：出题 / 校验 / 判分 / 落盘；联网出题走 langchain-tavily 工具智能体（`_build_tavily_tools` + `_run_tool_agent`，自写 `<tool>`/`<finish>` 循环），依赖经队长批准、仅限出题联网链路，key 来自 `TAVILY_API_KEY` 环境变量不入库。
- `server/requirements.txt`（新）：记录 quiz 出题链路经批准的 `langchain-tavily` 依赖（窄例外，不污染其余零依赖约定）。
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

- `tests/run_quiz_regression.py`（TDD 先红后绿）：源检查（路由存在、安全闸顺序、answer 不下发、client 方法、QuizPanel/ChatPage/i18n 接线、web_search 开关接线、`langchain_tavily` 经批准的窄依赖）+ runtime（临时 data 目录注入假知识库 + mock llm.chat + **fake tavily 工具**注入，验证工具智能体 search/extract 出题并打 `source:"web"`/`sources`、国内域默认限定、工具失败降级、URL extract 失败拒绝、联网开关关闭/失败降级、无 key 降级、出题校验、判分、落盘）。
- 既有四套回归必须全数保持。

## Boundaries

- Always：先红后绿；每步跑回归；不碰 `/api/chat` 与 RAG 门槛；`answer` 不出 generate 响应。
- Ask first：改 `wrong_book_store`（本切片不改，source 字段已兼容 'quiz'）；新增任何依赖。
- Never：FastAPI / LangGraph / Chroma / 文生图 / 微信登录 / 异步任务表；`import` 侧车进 api_server；force push；SSH；提交 dist/.env/data。**联网出题仅允许 `langchain-tavily` 封装（经队长批准、仅 `server/quiz.py` 出题链路），禁止 `urllib` 直连 api.tavily.com、禁止引入 langchain/langgraph 其他组件、key 不入库。**

## Success Criteria

1. 课程问答页可发起闯关：选难度 + 题数 → 出题 → 逐题作答即时对错讲解 → 结算。
2. 主题题（非 URL）知识库弱命中不再拒绝，降级为空上下文并基于通用知识严谨出题（不杜撰）；仅「丢链接出题」在无 key/失败时才拒绝。
3. 答错题目出现在错题本，source=quiz。
4. 通关后学伴经验 +N（logExp('答题闯关')）。
5. 四套既有回归全过、新回归全绿。
