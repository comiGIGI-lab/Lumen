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
