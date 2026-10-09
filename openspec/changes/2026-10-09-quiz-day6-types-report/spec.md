# Spec: 选择题闯关 Day6

## 题型参数

`generate_quiz(course, difficulty, count, types, client_id)`：
- `types=None | "single" | ["single"]` → 全单选（默认）。
- `types="mixed" | ["mixed"]` → 按 2:1:1 拆 single/multi/judge，余数补 single。
- `types="multi" | "judge"` → 全该类。
- `types=["single","multi","judge"]` → 按列数均分 count（余数给首个类型）。

## 题目统一 schema（服务端 + generate 响应，响应不含 answer）

```
{
  "id": "q1", "type": "single|multi|judge", "stem": "...",
  "options": [{"key": "A", "text": "..."}, ...],
  "answer": ["A"] | ["A","C"] | 0/1,
  "explanation": "...", "knowledge_point": "...",
  "source": "kb" | "web", "sources": [{"title": "...", "url": "..."}]
}
```

- single：4 选项，answer 为 1 个 key 的数组。
- multi：4–5 选项，answer 为 ≥2 个正确 key 的数组。
- judge：2 选项（key 固定 "0"=正确 / "1"=错误），answer 为 0 或 1。

## 判分 `grade_quiz(quiz_id, question_id, selected)`

- single：`selected` 为 key 字符串，比对 `answer[0]`。
- multi：`selected` 为 key 数组，排序后与 `answer` 比对（全对才 correct）。
- judge：`selected` 为 "0"/"1"，转 int 比对 `answer`。
- 缺失 quiz/question 抛 `KeyError`（HTTP 404）。

## 复盘 `quiz_report(run_id)`

聚合自 `quiz_runs.json`，返回：
```
{
  "ok": true, "quiz_id", "course", "difficulty", "types", "source",
  "score", "total", "accuracy", "duration_s",
  "questions": [{id,type,stem,options,user_answer,correct_answer,correct,
                 answered_at,explanation,knowledge_point,source,sources}],
  "weak_points": [{"knowledge_point", "wrong"}] (Top3),
  "materials": [出题依据资料标题]
}
```
- `duration_s`：`started_at` 到最后一次 `answered_at`（或当前）的秒数。
- `weak_points`：答错题的 knowledge_point 计数降序取前 3。

## 路由（api_server）

- `POST /api/quiz/generate`：安全闸同 /api/chat；`types` 转发 `generate_quiz`。
- `POST /api/quiz/grade`：服务端判分。
- `POST /api/quiz/report`（`run_id` 取 body 或 `?run_id=`）：安全闸作用于本局 course。
