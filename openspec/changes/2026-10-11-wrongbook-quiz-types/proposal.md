# Proposal：错题本 × 闯关题型适配

## 为什么

Day5/Day6 的闯关已经能出单选 / 多选 / 判断三种题型，但答错入库这一段仍然写着
「单选时代」的假设：`QuizPanel.vue` 在前端把题干、选项、答案拼成字符串后写
`/api/wrongbook`，而三种题型的答案编码互不相同——

    single -> ["A"]          多选一个也是长度 1 的列表
    multi  -> ["A", "C"]     已排序，长度 >= 2
    judge  -> int 0 / 1      0=正确 1=错误，不是选项 key

前端那段 `options.find(o => o.key === (Array.isArray(sel) ? sel[0] : sel))`
对多选只会取到 **第一个选中项** 的文字：学员选了 A、C，错题本里「我的答案」
只显示 `A. 列表`，C 的整段文字丢了。判断题更糟——`sel` 是 `'0'/'1'`，
`find` 压根匹配不到任何选项，` my_answer` 退化成裸的 `0. `。

同时错题本里看不出一道题到底是单选还是多选（题干里没有题型），也没法把
「闯关来的」跟「自己手抄的」分开看。

## 变更范围

- 新增 `server/wrongbook_quiz.py`：纯转换模块（无 IO、无 import store），
  负责「结构化题目 → wrong_book_store.add_item 的字段」。
- 新增 `POST /api/wrongbook/from-quiz`：前端回传结构化题目，后端统一渲染。
- `GET /api/wrongbook` 增加 `source` / `type` 两个过滤维度，并在每条 item 上
  派生 `qtype` / `qtype_label` 返回给前端。
- 前端：`client.js` 加 `wrongBookAddFromQuiz` 并把两个过滤参数传下去；
  `QuizPanel.vue` 改为回传结构化题目；`WrongBookPage.vue` 加题型/来源徽标与
  两个筛选下拉；i18n 新增 `wrongBookQuiz.*`（中英）。
- 回归：`tests/run_wrongbook_quiz_regression.py`（TDD 先红后绿）。

## 关键约束

- **不改 `vendor/study-liu/tools/wrong_book_store.py`**：`add_item` 是封闭契约
  （多余入参直接 TypeError），且本仓库约定 vendor 零改动，Day5 OpenSpec 也写着
  「Ask first：改 wrong_book_store」。本切片再次确认：**不加字段**。
- 题型信息落在**本来就有**的字段上：
  `source='quiz'` + `tags` 里的 `题型:多选` + `question` 渲染成文本；
  `qtype` 不入库，每次读的时候从 tags 解出来挂在响应上。
- 前后端职责单一：格式化只存在于 Python 一侧，TypeScript 不再拼答案字符串。

## 不做

- 不做错题本分表 / 独立「闯关错题」页面（用筛选达成同样的取数）。
- 不改 `/api/quiz/*` 的出题与判分逻辑，也不改三种题型的答案编码。
- 不做迁移脚本：题型尚未被写入过，历史 `source='quiz'` 的老条目只会
  显示「闯关」徽标、不显示题型徽标（`qtype` 解不出来），不报错。
- 不提交 `dist/` `.env` `data/`；不 force push；不 SSH。
