# Tasks：课程问答选择题闯关

- [x] Task 1：失败回归先行（红）
  - Acceptance：`tests/run_quiz_regression.py` 覆盖路由/安全闸/answer 不下发/前端接线/runtime 判分，当前跑为红。
  - Verify：`python tests/run_quiz_regression.py` 退出码非 0，输出存 `D:\wb\zjxt-quiz-red.txt`。✅ 红 4 过 / 12 失败。
  - Files：tests/run_quiz_regression.py（新）
- [x] Task 2：后端 server/quiz.py + api_server 路由（绿·后端半）
  - Acceptance：generate 弱命中拒绝、强命中出题校验、answer 不下发、grade 判分、落盘 data/quiz_runs.json；路由挂危机/安全闸。
  - Verify：run_quiz_regression.py 后端断言转绿；sidecar/safety 回归不破。✅
  - Files：server/quiz.py（新）、server/api_server.py（改，SOURCE_DIR 装配后 import quiz + 两个路由）
- [x] Task 3：前端 QuizPanel + ChatPage 入口 + client + i18n（绿·前端半）
  - Acceptance：难度/题数选择、逐题作答服务端判分即时讲解、结算 + logExp、答错 wrongBookAdd(source='quiz')。
  - Verify：run_quiz_regression.py 全绿；chat retrieved 15、plan kb 34 不破。✅
  - Files：web/src/components/QuizPanel.vue（新）、ChatPage.vue（改）、web/src/api/client.js（改）、web/src/i18n/auto-zh.json / auto-en.json（改）
- [x] Task 4：全量回归与记录
  - Acceptance：quiz 新回归全绿；sidecar 106 / safety 84 / chat 15 / plan 34 全过。
  - Verify：✅ quiz 37/0、sidecar 106/0、safety 全过、chat 15/0、plan 34/0（D:\wb\zjxt-*-green.txt）
  - Files：无新增

## 后续增强（均已完成，已随各 commit 快进推送）

- [x] Task 5：联网搜索开关 + 优雅降级（知识库弱命中不再拒绝）
  - Acceptance：web_search 开关默认开；关闭/无 key/搜索失败记 `logging.warning` 并降级为空上下文继续出题（不拒绝）；KB 弱命中改为可选增强（`source:"topic"`）；仅「丢链接出题」(URL) 在无 key/失败时才拒绝 `WEAK_HIT_ERROR`。
  - Verify：quiz 回归新增 `quiz_kb_optional_enrichment`/`weak_kb_*`/`web_search_off_*`/`web_search_fail_*`/`tavily_no_key_degraded` 等全绿；commit `1859eeb`。✅
- [x] Task 6：用 langchain-tavily 工具智能体重写联网出题（替代 urllib 直连）
  - Acceptance：实例化 4 个工具（tavily_search/search_deep/extract/extract_deep）绑现有出题 LLM（`core.llm.chat` 纯文本），自写 `<tool>`/`<finish>` prompt 工具循环（不引 langgraph）；`api_server` 装配时 `TAVILY_API_KEY = STUDY_LIU_TAVILY_KEY`，key 不入库；国内域默认限定；弱命中不再拒题。零依赖约束经队长批准对 quiz 出题链路放宽（`server/requirements.txt` 记录）。
  - Verify：quiz 93/0；commit `1d5cff2`。✅
- [x] Task 7：工具智能体日志与检索广度增强
  - Acceptance：每次搜索都打印工具名/调用参数/返回结果（quiz 模块独立 INFO logger，规避 root 默认 WARNING 吞日志）；`tavily_search` max_results 3→10、`tavily_search_deep` 8→15；`MAX_AGENT_STEPS` 4→8；system prompt 新增「多关键词检索」与「领域判定（以多数为准）」，多义词（如 "harness engineering"）用多关键词变体检索、综合多数结果判定领域。
  - Verify：quiz 98/0，新增 `agent_prompt_multi_keyword` 与 `agent_logs_tool_call`/`agent_logs_tool_result`/`agent_logs_query_param`/`agent_logs_generates`；commit `4719734`。✅

## 当前全量回归状态（2026-10-10 复核）
- quiz 98/0、sidecar 106/0、safety 84/0、chat_retrieved 15/0、plan_kb 34/0 —— 全部通过。Day5+6（含 Task 1–7）均已落地并快进推送至 master。
