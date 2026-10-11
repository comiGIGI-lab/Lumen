# Tasks：错题本 × 闯关题型适配

## 1. 勘查：确认不能加字段

- [x] 读 `vendor/study-liu/tools/wrong_book_store.py` 的 `add_item`：只认
      `course/question/my_answer/answer/reason/tags/source`，多余入参 TypeError。
- [x] 确认 Day5 OpenSpec 的 `Ask first：改 wrong_book_store` 仍然有效 → 本切片不改。
- [x] 记录三种题型的答案编码差异（`server/quiz.py` 的 `_norm_answer_*`）。

## 2. TDD 红：先写回归

- [x] 新建 `tests/run_wrongbook_quiz_regression.py`：源检查 13 项 + runtime 22 项。
- [x] 首跑 `0 passed, 12 failed`——其中 `panel_multi_first_only_bug_gone`
      **实锤了多选只取首个选项文字的旧 bug**，确认这不是我臆想的。
- [x] 入口加 UTF-8 reconfigure，避免 Windows GBK 把「断言全绿」打成 rc=1 的假红
      （沿用 `run_crisis_regression.py` 的修法）。

## 3. 后端：wrongbook_quiz 纯转换模块

- [x] `server/wrongbook_quiz.py`：`normalize_qtype` / `qtype_label` / `type_tag` /
      `_coerce_qtype` / `parse_qtype` / `is_quiz_item` / `render_question` /
      `human_answer` / `build_quiz_wrong`。
- [x] 题型标签定为**中文形态** `题型:多选`（tags 会被 `list_items` 的 keyword 扫，
      用户搜「多选」要能搜到）；`parse_qtype` 同时认 `题型:multi` 与裸 `多选`。
- [x] 长度上限与 store 对齐，选项文本先按 400 裁，避免整段渲染后被截断。

## 4. 后端：路由接线

- [x] `api_server.py` import `wrongbook_quiz`（放在 `SOURCE_DIR` 插 sys.path 之后，
      与 `import quiz` 同理）。
- [x] `GET /api/wrongbook` 支持 `source` / `type`，每条 item 派生 `qtype` /
      `qtype_label`（store 的 `list_items` 不认这两个维度，只能读时过滤）。
- [x] `POST /api/wrongbook/from-quiz`，必须排在 `startswith("/api/wrongbook/")` 之前。
- [x] `py_compile` 通过。

## 5. 前端接线

- [x] `client.js`：`wrongBookAddFromQuiz`；`wrongBookList` 增加 `source` / `type`。
- [x] `QuizPanel.vue`：删掉前端拼字符串的整段（连带修掉多选 bug），改回传结构化题目。
- [x] `WrongBookPage.vue`：题型徽标 + 闯关来源徽标 + 两个筛选下拉 + 清空筛选重置。
- [x] i18n 中英各补 7 个 `wrongBookQuiz.*` key。

## 6. 验证

- [x] 新回归 **35 passed / 0 failed**。
- [x] 十套既有回归全过：quiz 123、sidecar 106、safety、chat 15、plan 34、
      structured 42、kb_scope、crisis、vector 36/3 skipped。
- [x] `cd web && npm run build` 通过（112 modules，10.75s）。

## 7. 交付（待用户确认）

- [ ] OpenSpec 三件套落 `openspec/changes/2026-10-11-wrongbook-quiz-types/`。
- [ ] `docs/DEPLOY.md` 是否需要补一节（本切片无新依赖、无需服务器改动，倾向不补）。
- [ ] 按 `gitee-ff-push-locked-git` 流程做非 force 快进推送（先 `git ls-remote`
      核实时 tip，再三路合并）；给队友发发布说明。
