# 决赛冲刺切片：课程问答选择题闯关（复刻 yu-ai-learn 官网可行范围）

只覆盖本切片：按课程（科目）与知识库出单选题、难度三档可选、逐题服务端判分并即时讲解、答错进错题本、通关结算经验值。复刻对象是 [yu-ai-learn](https://github.com/liyupi/yu-ai-learn) 的产品形态（闯关答题 / AI 出题 / RAG 出题），不是它的技术栈。

## 能力图

- `quiz-generate`：`POST /api/quiz/generate`。课程名走 `_retrieve_course_hits` 同款门槛（1.0 / 0.2），弱命中**拒绝出题**；强命中注入 prompt，LLM（DeepSeek，`core/llm.chat`）产出结构化单选 JSON 并严格校验。`quiz_id` 进程内缓存 + `data/quiz_runs.json` 落盘。
- `quiz-grade`：`POST /api/quiz/grade`。服务端对照缓存的标准答案判分，回 `correct` / `answer` / `explanation`，前端不自行比对。
- `quiz-ui`：`ChatPage` 加闯关入口；`QuizPanel.vue` 选难度（easy/medium/hard）与题数（3–8，默认 5）、逐题作答、即时对错讲解、结算分数；答错写 `/api/wrongbook`（`source: 'quiz'`）；通关 `usePet.logExp('答题闯关', …)`。

## 为什么现在做

决赛演示缺「学完之后练」的闭环。yu-ai-learn 官方 6 模块里闯关答题 / AI 出题 / RAG 出题三项本仓库全无，而知识库、用户系统、错题本、经验值四项已有——补上出题判分即可成环。

## 技术选型（官网可行范围）

后端继续 `http.server` 纯标准库（新 `server/quiz.py`），LLM 继续走 `core/llm.chat`（DeepSeek），存储 `data/quiz_runs.json`，前端 Vue3。**不引入** FastAPI / LangChain / LangGraph / Chroma / MySQL / Tavily / 文生图 / 微信登录 / 异步轮询（Web 无小程序 60s 限制，不需要）。

## 不做

- 不改 `/api/chat` 字段与 `run_chat_pipeline` 契约；不改 `RAG_MIN_SCORE` / `RAG_MIN_COVERAGE`。
- 不改 `ChatPanel`（Day1 retrieved 展示保持原样）。
- 不做多选 / 判断 / mixed 难度 / 通关复盘报告 / AI 配图（后续切片）。
- 不提交 `dist/` `.env` `data/`；不 force push；不 SSH。
