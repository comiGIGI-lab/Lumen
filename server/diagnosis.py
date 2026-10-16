# -*- coding: utf-8 -*-
"""diagnosis.py — 诊断性前测：进课程前摸底，产出知识点掌握热力图。

产品意图：现在 Planner 只有 4 个主观自评字段（level/daily_hours/goal/deadline），
生成大纲时**不知道用户已经会什么**，只能按平均起点铺。加上诊断后：
    选课 → 6 道按章节均衡的摸底题 → 判分 → 热力图 → 重新生成大纲时按弱项加厚。

**为什么另起模块而不是塞进 quiz.py**：
  1) 闯关有对外契约（/api/quiz/*、quiz_runs.json、200 局上限），诊断不参与，混在一起会互相挤；
  2) 诊断必须**逐题带章节标签**才能按章节出热力图，而 `quiz._valid_question` 只保留它
     自己声明的字段（会把 `chapter` 过滤掉）—— 所以本模块自己收字段，只复用它的**校验**。

复用点（全部来自 server/quiz.py，本模块**不改动 quiz.py 一行**）：
  - `_retrieve(course)` / `_kb_blocks(hits)`：知识库接地，与出题同一套 RAG 门槛与拼装格式
  - `_valid_question(q, seen)`：单题形状/选项/答案/知识点校验（保证诊断题与闯关题同质量）
  - `_llm_chat(messages)`：模型调用（core.llm.chat）

⚠️ **与规格的一处偏差（有意为之，已注在代码里）**：规格提到复用 `_run_tool_agent`。
实测它是为「闯关」设计的多轮 Tavily 工具链，输出题目同样不带章节标签；诊断只要
5-8 道基础摸底题，走单次生成 + 显式要求 `chapter` 字段更省、且能保住「按章节」这条硬需求。
检索这半边（`_retrieve` / `_kb_blocks`）是完整复用的。

降级语义（沿用现有约定，不新造）：模型不可用 / 有效题数不足 → 退化为**纯大纲题**
（由大纲章节标题 + 要点确定性生成选择题，`degraded=True`、`source="outline"`），
不调模型也能出题；连大纲都拿不到时返回 `ok=False` + 明确原因，由前端跳过诊断。
"""

from __future__ import annotations

import json
import logging
import re
import threading

from core.paths import data_dir as _resolve_data_dir  # noqa: F401  (与其它模块一致的路径约定)
from tools import diagnosis_store as store

_log = logging.getLogger("diagnosis")

# 一次诊断的题量：规格要求 5-8 道；默认 6（章节一般 5-8 章，默认做到「一章一题」）
DEFAULT_COUNT = 6
MIN_COUNT = 5
MAX_COUNT = 8

# 大纲章节数兜底（与 planner 的建议章节数同量级；拿不到大纲时用它做「无章节」判断）
_CHAPTERS_MIN = 3

# 单题题干/选项长度上限，防模型吐超长题把 prompt 和前端撑爆
_MAX_STEM = 300

_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _clamp_count(n):
    """题量夹到 [MIN_COUNT, MAX_COUNT]；非法值回落 DEFAULT_COUNT。"""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return DEFAULT_COUNT
    return max(MIN_COUNT, min(MAX_COUNT, v))


def _as_text(v, limit=0):
    """压成字符串（容器值 → 空串），可选截断。防畸形入参炸下游。"""
    if isinstance(v, str):
        s = v.strip()
    elif isinstance(v, (int, float)):
        s = str(v)
    else:
        s = ""
    if limit and len(s) > limit:
        s = s[:limit]
    return s


def _extract_json(raw):
    """从模型输出里抠出 JSON（容忍 ```json 包裹 / 前后寒暄）。失败返回 None。"""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # 退一步：取第一个 '{' 到最后一个 '}' 之间（模型常带"好的，以下是…"前缀）
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(text[i:j + 1])
        except (ValueError, TypeError):
            return None
    return None


def chapters_from_outline(outline):
    """从大纲里取章节标题列表。

    兼容三种 shape：`[{title,points}]`（现行）、`["第1章 …"]`（旧）、非列表。
    """
    out = []
    if not isinstance(outline, (list, tuple)):
        return out
    for i, ch in enumerate(outline):
        if isinstance(ch, dict):
            title = _as_text(ch.get("title") or ch.get("name"))
        else:
            title = _as_text(ch)
        out.append(title or ("第%d章" % (i + 1)))
    return out


def outline_items(outline):
    """规范化成 [{title, points}]，供降级出题用。"""
    items = []
    if not isinstance(outline, (list, tuple)):
        return items
    for i, ch in enumerate(outline):
        if isinstance(ch, dict):
            title = _as_text(ch.get("title") or ch.get("name")) or ("第%d章" % (i + 1))
            raw_points = ch.get("points") or ch.get("items") or []
        else:
            title = _as_text(ch) or ("第%d章" % (i + 1))
            raw_points = []
        points = [_as_text(p) for p in (raw_points if isinstance(raw_points, (list, tuple)) else [])]
        items.append({"title": title, "points": [p for p in points if p]})
    return items


def sample_quota(chapters, count):
    """把 count 道题**均衡**分到各章节，返回 [(章节, 题数)]。

    规则：先按顺序每章 1 题，剩下一题一题轮到前面的章节（保证相邻章节都覆盖到），
    章数 > 题数时均匀跳采（不取前 N 章，否则后面几章永远测不到）。
    """
    chapters = [c for c in (chapters or []) if c]
    if not chapters:
        return []
    n = _clamp_count(count)
    if len(chapters) >= n:
        # 章数比题多：等间隔采样 n 章，第一章与最后一章都要覆盖
        idx = []
        for k in range(n):
            pos = int(round(k * (len(chapters) - 1) / float(n - 1))) if n > 1 else 0
            if pos not in idx:
                idx.append(pos)
        # 四舍五入可能挤掉某个位置，补足到 n 个
        skip = [i for i in range(len(chapters)) if i not in idx]
        while len(idx) < n and skip:
            idx.append(skip.pop(0))
        return [(chapters[i], 1) for i in sorted(idx)]

    quota = [(c, 1) for c in chapters]
    extra = n - len(chapters)
    i = 0
    while extra > 0:
        quota[i % len(quota)] = (quota[i % len(quota)][0], quota[i % len(quota)][1] + 1)
        extra -= 1
        i += 1
    return quota


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

_DIAG_SYSTEM = """你是课程顾问，负责在正式开课前对学生做一次**摸底诊断**。

出题要求：
- 严格按「章节 → 题量」配额出题，覆盖全部给定章节，不许把题都压在某一章；
- 每题**必须带 chapter 字段**，值照抄给定章节名（不要改写、不要加书名号）；
- 难度以**基础概念题**为主（这是摸底，不是选拔），不要偏题怪题；
- 每题带 type：single（4 个选项，key A-D，answer 形如 ["A"]）、
  multi（4~5 个选项，answer 是至少 2 个 key 的数组）、
  judge（选项固定 [{"key":"0","text":"正确"},{"key":"1","text":"错误"}]，answer 为 0 或 1）；
- 同一题内选项文本两两不同；stem / explanation / knowledge_point 中文非空；
- 只能依据给定资料出题；资料没覆盖到的章节，出该章节**通用基础概念题**，不得杜撰事实。

只输出 JSON，不要任何寒暄或解释：
{"questions": [{"type": "single", "chapter": "章名", "stem": "题干",
  "options": [{"key": "A", "text": "选项"}], "answer": ["A"],
  "explanation": "解析", "knowledge_point": "知识点"}]}"""


def _build_prompt(course, quota, kb_text, profile_text):
    lines = ["课程：%s" % course, "", "章节 → 题量配额（必须全部覆盖）："]
    for ch, n in quota:
        lines.append("- %s：%d 题" % (ch, n))
    total = sum(n for _ch, n in quota)
    lines.append("")
    lines.append("共 %d 题。" % total)
    if profile_text:
        lines.append("")
        lines.append(profile_text.strip())
    if kb_text:
        lines.append("")
        lines.append("给定资料（优先据此出题）：")
        lines.append(kb_text)
    else:
        lines.append("")
        lines.append("给定资料：无（请依据该课程的通用基础知识出题）")
    return _DIAG_SYSTEM + "\n\n" + "\n".join(lines)


def _fallback_questions(course, items, quota):
    """纯大纲题（确定性、不调模型）：用章节标题 + 要点出判断题。

    形态：偶数题「某章要点包含 X（真实要点）」= 正确；奇数题「某章要点包含 Y（别章要点）」= 错误。
    这是**降级路径**，只保证「有题可做 + 形状合法」，不追求考察深度。
    标记 source=outline，调用方会置 degraded=True。
    """
    by_title = {it["title"]: it for it in items if it.get("title")}
    pools = [(it["points"] or []) for it in items]
    flat = [p for ps in pools for p in ps]
    qs = []
    for ch, n in quota:
        it = by_title.get(ch) or {"title": ch, "points": []}
        points = it["points"] or []
        for k in range(n):
            if len(qs) >= MAX_COUNT:
                break
            idx = len(qs)
            if points and idx % 2 == 0:
                p = points[0]
                stem = "这门课的大纲里，「%s」这一章的学习要点包含：%s。" % (ch, p)
                answer, why = 0, "据本课程大纲，「%s」的要点包含「%s」。" % (ch, p)
            elif len(flat) >= 2:
                outside = [p for p in flat if p not in points]
                p = (outside or flat)[idx % max(1, len(outside or flat))]
                stem = "这门课的大纲里，「%s」这一章的学习要点包含：%s。" % (ch, p)
                answer, why = 1, "「%s」属于其他章节的要点，不属于「%s」。" % (p, ch)
            else:
                stem = "这门课的大纲里包含「%s」这一章。" % ch
                answer, why = 0, "「%s」在本课程大纲中。" % ch
            qs.append({
                "id": "", "type": "judge",
                "stem": _as_text(stem, _MAX_STEM),
                "options": [{"key": "0", "text": "正确"}, {"key": "1", "text": "错误"}],
                "answer": answer,
                "explanation": why,
                "knowledge_point": ch,
                "chapter": ch,
                "source": "outline",
                "sources": [],
            })
    return qs


def _parse_questions(raw, quota, items):
    """解析模型输出 → 合规题列表（复用 quiz 的 _valid_question 做校验）。

    `chapter` 由本函数自己收（quiz 的校验会过滤掉未声明字段），并做一次配额兜底：
    某章一道都没出出来时，用纯大纲题补上，避免热力图缺章。
    """
    import quiz as quiz_mod

    data = _extract_json(raw)
    if isinstance(data, dict):
        raw_qs = data.get("questions")
    elif isinstance(data, list):
        raw_qs = data
    else:
        raw_qs = None
    if not isinstance(raw_qs, list):
        return []

    valid_titles = [ch for ch, _n in quota]
    out = []
    seen = set()
    for item in raw_qs:
        if not isinstance(item, dict):
            continue
        v = quiz_mod._valid_question(item, seen)   # 复用：形状/选项/答案/知识点校验
        if not v:
            continue
        ch = _as_text(item.get("chapter")) or v.get("knowledge_point") or ""
        if ch not in valid_titles:
            # 模型自己改了章名：就近归到配额里第一章含关键词的，否则用知识点兜底
            hit = next((t for t in valid_titles if t and (t in ch or ch in t)), "")
            ch = hit or (valid_titles[0] if valid_titles else ch)
        v["chapter"] = ch
        v["stem"] = _as_text(v.get("stem"), _MAX_STEM)
        v["id"] = "q%d" % (len(out) + 1)
        seen.add(v["id"])
        out.append(v)
    return out


def _course_outline(course, outline, profile):
    """拿章节来源：优先调用方传入，否则复用 Planner（LLM 不可用时会自动走它的兜底大纲）。"""
    if outline:
        return outline
    try:
        from agents.planner import plan_outline
        return plan_outline(course, profile, None)
    except Exception as e:                                  # noqa: BLE001
        _log.warning("诊断取大纲失败：%s", e)
        return None


def generate_diagnosis(course, outline=None, profile=None, count=DEFAULT_COUNT, client_id=""):
    """生成一次诊断：返回对外结构（**不含标准答案**）。

    course 为空 → {"ok": False, "error": ...}；拿不到任何章节 → ok=False（调用方跳过诊断）。
    """
    import quiz as quiz_mod

    course = _as_text(course)
    if not course:
        return {"ok": False, "error": "请先输入课程名"}

    n = _clamp_count(count)
    outline = _course_outline(course, outline, profile)
    items = outline_items(outline)
    chapters = [it["title"] for it in items]
    if len(chapters) < _CHAPTERS_MIN:
        return {
            "ok": False,
            "error": "拿不到足够的课程章节，已跳过摸底诊断（不影响正常生成方案）",
            "course": course,
            "skipped": True,
        }

    quota = sample_quota(chapters, n)
    covered = [ch for ch, _k in quota]

    # 知识库接地：与出题同一套 RAG 门槛（弱命中就按无资料走，不硬凑）
    kb_text = ""
    try:
        hits = quiz_mod._retrieve(course)
        kb_text = quiz_mod._kb_blocks(hits) if hits else ""
    except Exception as e:                                  # noqa: BLE001
        _log.warning("诊断检索失败，按无资料出题：%s", e)

    profile_text = ""
    try:
        from tools.user_profile import format_profile_text
        profile_text = format_profile_text(profile) if profile else ""
    except Exception:                                       # noqa: BLE001
        profile_text = ""

    degraded = False
    prompt = _build_prompt(course, quota, kb_text, profile_text)
    try:
        raw = quiz_mod._llm_chat([{"role": "user", "content": prompt}])
    except Exception as e:                                  # noqa: BLE001
        _log.warning("诊断出题调用失败，退化纯大纲题：%s", e)
        raw = ""
    qs = _parse_questions(raw, quota, items)

    # 有效题不足 → 整体退化纯大纲题（沿用"模型不可用则降级"的既有语义）
    if len(qs) < MIN_COUNT:
        _log.warning("诊断有效题只有 %d 道，退化纯大纲题", len(qs))
        qs = _fallback_questions(course, items, quota)
        degraded = True
    else:
        # 有章节一道都没出出来 → 用大纲题补齐该章，保证热力图不缺章
        have = {q.get("chapter") for q in qs}
        missing = [(ch, k) for ch, k in quota if ch not in have]
        if missing:
            for q in _fallback_questions(course, items, missing):
                q["id"] = "q%d" % (len(qs) + 1)
                qs.append(q)
            degraded = True

    if not qs:
        return {"ok": False, "error": "诊断题生成失败，已跳过摸底（不影响正常生成方案）",
                "course": course, "skipped": True}

    # ⚠️ 统一发号：**所有路径**都必须拿到非空且互不相同的 id。
    # 2026-10-16 实测踩过：降级路径（_fallback_questions）给的 id 是空串，
    # 结果前端交卷变成了 {"": 1} —— 全部题塌进同一个 key，判分互相覆盖，
    # 六道题只剩最后一道的结果，热力图全错。发号这一步不能分散在各分支里。
    for i, q in enumerate(qs):
        q["id"] = "q%d" % (i + 1)
    seen_ids = [q["id"] for q in qs]
    if len(set(seen_ids)) != len(seen_ids):
        return {"ok": False, "error": "诊断题编号冲突，已跳过摸底（不影响正常生成方案）",
                "course": course, "skipped": True}

    rec = {
        "diagnosis_id": store.new_id(),
        "course": course,
        "client_id": str(client_id or "")[:64],
        "created_at": store._now(),                          # noqa: SLF001  (同模块族的私有工具函数)
        "graded_at": "",
        "count": len(qs),
        "chapters": covered,
        "degraded": degraded,
        "questions": qs,
        "answers": {},
        "status": "open",
    }
    store.save_record(rec)
    return {
        "ok": True,
        "diagnosis_id": rec["diagnosis_id"],
        "course": course,
        "count": len(qs),
        "chapters": covered,
        "degraded": degraded,
        "created_at": rec["created_at"],
        "questions": store.public_questions(rec),
    }


# ---------------------------------------------------------------------------
# 判分
# ---------------------------------------------------------------------------

def _is_correct(q, selected):
    """判分：语义与 quiz.grade_quiz 对齐（single/multi/judge 三型）。"""
    qtype = str(q.get("type") or "single")
    if qtype == "multi":
        sel = selected if isinstance(selected, list) else [selected]
        sel = [str(x).strip().upper() for x in sel if str(x).strip() != ""]
        return sorted(sel) == sorted(str(x).upper() for x in (q.get("answer") or []))
    if qtype == "judge":
        try:
            return int(selected) == int(q.get("answer"))
        except (TypeError, ValueError):
            return False
    ans = q.get("answer") or []
    first = str(ans[0]) if ans else ""
    return str(selected).strip().upper() == first.upper()


def _normalize_answers(answers):
    """接受两种入参：{"q1": "A"} 或 [{"question_id":"q1","selected":"A"}]。"""
    out = {}
    if isinstance(answers, dict):
        for k, v in answers.items():
            out[str(k)] = v
    elif isinstance(answers, list):
        for it in answers:
            if not isinstance(it, dict):
                continue
            qid = _as_text(it.get("question_id") or it.get("id"))
            if qid:
                out[qid] = it.get("selected")
    return out


def grade_diagnosis(diagnosis_id, answers):
    """判分并落盘，返回热力图。diagnosis_id 不存在抛 KeyError（HTTP 层转 404）。"""
    rec = store.get_record(_as_text(diagnosis_id))
    if not rec:
        raise KeyError("diagnosis_not_found")

    picked = _normalize_answers(answers)
    with _LOCK:
        graded = {}
        for q in rec.get("questions") or []:
            qid = q.get("id")
            if qid in picked:
                graded[qid] = {
                    "selected": picked[qid],
                    "correct": bool(_is_correct(q, picked[qid])),
                    "answered_at": store._now(),             # noqa: SLF001
                }
        # 合并式写入：允许分批交卷（前端一题一判时不会把上一题的记录冲掉）
        merged = dict(rec.get("answers") or {})
        merged.update(graded)
        rec["answers"] = merged
        rec["status"] = "done"
        rec["graded_at"] = store._now()                      # noqa: SLF001
        store.save_record(rec)

    chapters, kps, weak = store.heatmap(rec)
    answered = [c for c in chapters if c.get("done")]
    total = sum(c["total"] for c in answered)
    correct = sum(c["correct"] for c in answered)
    return {
        "ok": True,
        "diagnosis_id": rec["diagnosis_id"],
        "course": rec.get("course", ""),
        "status": "done",
        "graded": len(graded),
        "total": total,
        "correct": correct,
        "score": store._mastery(correct, total),              # noqa: SLF001
        "heatmap": chapters,
        "knowledge_points": kps,
        "weak": weak,
    }


def get_diagnosis(diagnosis_id=None, course=None, client_id=None):
    """读一次诊断（题目无答案 + 已判分则带热力图）。找不到返回 ok=False。"""
    rec = None
    did = _as_text(diagnosis_id)
    if did:
        rec = store.get_record(did)
    if not rec:
        rec = store.latest_for_course(_as_text(course), client_id)
    if not rec:
        return {"ok": False, "error": "没有可用的诊断记录", "not_found": True}

    chapters, kps, weak = store.heatmap(rec)
    answered = [c for c in chapters if c.get("done")]
    total = sum(c["total"] for c in answered)
    correct = sum(c["correct"] for c in answered)
    return {
        "ok": True,
        "diagnosis_id": rec.get("diagnosis_id", ""),
        "course": rec.get("course", ""),
        "status": rec.get("status", "open"),
        "degraded": bool(rec.get("degraded")),
        "created_at": rec.get("created_at", ""),
        "graded_at": rec.get("graded_at", ""),
        "chapters": rec.get("chapters") or [],
        "count": rec.get("count", 0),
        "total": total,
        "correct": correct,
        "score": store._mastery(correct, total),              # noqa: SLF001
        "heatmap": chapters,
        "knowledge_points": kps,
        "weak": weak,
        "questions": store.public_questions(rec),
    }
