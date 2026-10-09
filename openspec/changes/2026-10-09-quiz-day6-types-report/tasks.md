# Tasks: 选择题闯关 Day6

## 后端
- [x] `quiz.py`：`generate_quiz` 增加 `types` 参数与 `_resolve_plan` / `_distribute_mixed`。
- [x] `quiz.py`：`_valid_question` / `_parse_llm_questions` 支持 single/multi/judge 校验。
- [x] `quiz.py`：`grade_quiz` 支持 multi（数组比对）与 judge（0/1）。
- [x] `quiz.py`：run 增加 `started_at`；逐题 `answered_at` 已存在。
- [x] `quiz.py`：新增 `quiz_report` 纯聚合（score/accuracy/duration_s/回放/薄弱点）。
- [x] `quiz.py`：弱命中 Tavily 联网兜底（`urllib.request`，env key，标 source:"web"）。
- [x] `api_server.py`：新增 `POST /api/quiz/report`，复用安全闸。

## 前端
- [x] `client.js`：新增 `quizReport`；`quizGenerate` 转发 `types`。
- [x] `QuizPanel.vue`：题型选择器（默认混合）、多选复选、判断双按钮。
- [x] `QuizPanel.vue`：通关拉 `quizReport`，渲染复盘卡片（成绩/逐题/薄弱点/联网来源角标）。
- [x] `i18n`：新增 qtype / typeSingle/Multi/Judge/Mixed / webSource / report* 键（zh+en）。

## 测试与交付
- [x] `tests/run_quiz_regression.py`：扩展 mixed 分布、multi/judge 判分、report 聚合、Tavily 有/无 key。
- [x] 全套回归：quiz 71 / sidecar 106 / safety 84 / chat_retrieved 15 / plan_kb 34 全绿。
- [x] 快进推送（parent = live HEAD f45b188，非 force）。
