# Proposal: 选择题闯关 Day6 — 题型扩展 + 复盘报告

## 为什么

Day5 已实现单选闯关（知识库 RAG 出题 + 服务端判分 + 错题本 + 弱命中拒绝）。
为提升练习深度与学习闭环，本变更扩展题型（多选 / 判断 / 混合），并新增
通关后的复盘报告，让学员看到得分、正确率、用时、逐题回放与薄弱知识点。

## 变更范围

- 题型：出题 `generate_quiz` 新增 `types` 参数（`single` / `multi` / `judge` / `mixed`），
  `mixed` 配比 `single:multi:judge = 2:1:1`（count=8 → 4+2+2）。
- 判分：`multi` 全对才给分（排序后数组比对）；`judge` 选项固定为「正确 / 错误」，
  `answer` 为整数 0/1。
- 复盘：新增 `GET/POST /api/quiz/report?run_id=...`，纯聚合 `quiz_runs.json`，
  输出 score / accuracy / duration_s / 逐题回放 / 薄弱知识点 Top3，不写新状态文件。
- 前端：题型选择器（默认混合）、多选复选框、判断双按钮、通关后复盘卡片。
- 弱命中兜底（Day5 决策）：环境变量 `STUDY_LIU_TAVILY_KEY` 存在时，弱命中改走
  Tavily 联网补题并标注来源（`source:"web"` + `sources`），无 key 或联网失败仍回退拒绝。

## 硬约束（与 Day5 一致）

- 标准答案只存服务端（`data/quiz_runs.json`），`generate` 响应不带 `answer`。
- `report` 仅在通关后下发答案，属讲解非泄题。
- 新路由复用 `/api/chat` 同一套安全闸（`detect_crisis` + `check_detail`）。
- 后端纯标准库；Tavily 经 `urllib.request`，key 绝不入库 / 不落盘。
- 不改 `/api/chat` 契约与 RAG 门槛（1.0 / 0.2）。
