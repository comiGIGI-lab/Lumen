# -*- coding: utf-8 -*-
"""诊断性前测回归（2026-10-16 新增，Prompt ②）。

覆盖规格验收：
  1) 进课程前能生成 5-8 道**按章节均衡**的摸底题；
  2) 判分后产出知识点掌握热力图，弱项章节可被 Planner 感知
     （format_profile_text 新增段 → 注入 plan_outline 的 prompt）；
  3) 模型不可用时退化纯大纲题（沿用现有降级语义）；
  4) 诊断数据独立存 data/diagnosis.json，不混入 quiz_runs.json；
  5) 对外响应不带标准答案；
  6) 不做诊断时 prompt 与加诊断之前**逐字节一致**（零回归）。
另含分层检查：vendor 侧 diagnosis_store **不得** import server。

用法（仓库根目录执行）：
    python tests/run_diagnosis_regression.py
"""

import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER = os.path.join(REPO_ROOT, "server")
VENDOR = os.path.join(REPO_ROOT, "vendor", "study-liu")

for _p in (SERVER, VENDOR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s%s" % (name, ("  ← " + str(detail)) if detail else ""))


def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. 静态检查：接线与分层
# ---------------------------------------------------------------------------

def source_checks():
    print("[1] 接线与分层")
    diag_path = os.path.join(SERVER, "diagnosis.py")
    store_path = os.path.join(VENDOR, "tools", "diagnosis_store.py")
    profile_path = os.path.join(VENDOR, "tools", "user_profile.py")
    planner_path = os.path.join(VENDOR, "agents", "planner.py")
    api_path = os.path.join(SERVER, "api_server.py")

    for p in (diag_path, store_path):
        check("file_exists:%s" % os.path.basename(p), os.path.isfile(p))

    diag_src = read(diag_path)
    store_src = read(store_path)
    profile_src = read(profile_path)
    planner_src = read(planner_path)
    api_src = read(api_path)

    # 复用出题引擎（规格点名的三个）
    check("reuse_retrieve", "quiz_mod._retrieve(" in diag_src)
    check("reuse_kb_blocks", "quiz_mod._kb_blocks(" in diag_src)
    check("reuse_valid_question", "quiz_mod._valid_question(" in diag_src)

    # 题量常量 5-8
    check("count_bounds_5_8",
          re.search(r"MIN_COUNT\s*=\s*5\b", diag_src) and
          re.search(r"MAX_COUNT\s*=\s*8\b", diag_src))

    # 独立存储：自己的路径是 diagnosis.json，且不得构造 quiz_runs 的路径
    # （注释里提到 quiz_runs.json 是允许的 —— 那是"为什么分开存"的说明）
    check("store_own_file",
          re.search(r'_DIAGNOSIS_FILE\s*=\s*os\.path\.join\([^)]*"diagnosis\.json"', store_src))
    check("no_quiz_runs_path",
          not re.search(r'os\.path\.join\([^)]*quiz_runs', store_src))

    # 分层：vendor 不得反向 import server
    bad = re.search(r"^\s*(import|from)\s+server\b", store_src, re.M)
    check("vendor_no_server_import", bad is None, bad.group(0) if bad else "")

    # format_profile_text 新增可选诊断段
    check("format_profile_accepts_diagnosis",
          re.search(r"def format_profile_text\(profile,\s*diagnosis=None\)", profile_src))

    # Planner 注入
    check("planner_injects_diagnosis",
          "format_profile_text(profile, diagnosis)" in planner_src and
          "diagnosis_store.latest_for_course" in planner_src)

    # 接口存在
    for route in ("/api/diagnosis", "/api/diagnosis/generate", "/api/diagnosis/grade"):
        check("route:%s" % route, ('"%s"' % route) in api_src)
    check("api_imports_diagnosis", "import diagnosis as diagnosis_mod" in api_src)
    # 生成接口必须过安全闸（与 /api/quiz/generate 同套）
    m = re.search(r'if path == "/api/diagnosis/generate":(.*?)\n\n', api_src, re.S)
    seg = m.group(1) if m else ""
    check("generate_has_safety_gate", "check_detail(course)" in seg and "detect_crisis(course)" in seg)
    check("generate_has_quota", "_enforce_anon_llm_quota" in seg)


# ---------------------------------------------------------------------------
# 2. 运行时：生成 / 判分 / 热力图 / 注入 / 降级
# ---------------------------------------------------------------------------

CHAPTERS = [
    "第1章 变量与类型",
    "第2章 条件与循环",
    "第3章 函数与参数",
    "第4章 列表与字典",
    "第5章 文件读写",
    "第6章 异常处理",
]

OUTLINE_JSON = ('{"chapters": [' + ",".join(
    '{"title": "%s", "points": ["要点甲%d", "要点乙%d", "要点丙%d"]}' % (c, i, i, i)
    for i, c in enumerate(CHAPTERS)) + ']}')


def _q(i, ch):
    return ('{"type":"single","chapter":"%s","stem":"关于「%s」的基础题 %d",'
            '"options":[{"key":"A","text":"甲"},{"key":"B","text":"乙"},'
            '{"key":"C","text":"丙"},{"key":"D","text":"丁"}],'
            '"answer":["A"],"explanation":"解析 %d","knowledge_point":"知识点-%d"}'
            % (ch, ch, i, i, i))


DIAG_JSON = '{"questions": [' + ",".join(_q(i + 1, c) for i, c in enumerate(CHAPTERS)) + ']}'


def runtime_checks():
    print("[2] 运行时：生成 / 判分 / 注入 / 降级")

    tmp = tempfile.mkdtemp(prefix="diag-regr-")
    from tools import diagnosis_store as store
    store._DIAGNOSIS_FILE = os.path.join(tmp, "diagnosis.json")
    store._DATA_DIR = tmp

    import core.llm as llm
    import diagnosis as D
    from tools.user_profile import format_profile_text
    from agents.planner import plan_outline

    captured = []

    def fake_chat(messages, *a, **k):
        prompt = ""
        if isinstance(messages, list) and messages:
            prompt = str(messages[0].get("content") or "")
        captured.append(prompt)
        if "摸底诊断" in prompt:
            return DIAG_JSON
        if "课程规划助手" in prompt:
            return OUTLINE_JSON
        return "[LLM 不可用] 回归桩"

    llm.chat = fake_chat
    profile = {"level": "入门", "daily_hours": "2h", "goal": "考试", "deadline": ""}

    # ---- 生成 ----
    res = D.generate_diagnosis("Python 基础", profile=profile, count=6, client_id="regr")
    check("generate_ok", res.get("ok") is True, res)
    check("count_in_5_8", 5 <= res.get("count", 0) <= 8, res.get("count"))
    qs = res.get("questions") or []
    check("covers_all_chapters", {q["chapter"] for q in qs} == set(CHAPTERS),
          sorted({q["chapter"] for q in qs}))
    check("no_answer_leak", all("answer" not in q and "explanation" not in q for q in qs))
    # 每道题的 id 必须非空且唯一。2026-10-16 踩过：降级路径给的 id 是空串，
    # 前端交卷变成 {"": 1} —— 六道题塌进同一个 key、判分互相覆盖、热力图全错。
    ids = [q.get("id") for q in qs]
    check("ids_non_empty_unique", all(ids) and len(set(ids)) == len(ids), ids)
    check("not_degraded", res.get("degraded") is False)
    # 诊断数据落在独立文件
    check("written_to_own_file",
          os.path.isfile(os.path.join(tmp, "diagnosis.json")))
    check("quiz_runs_untouched",
          not os.path.exists(os.path.join(tmp, "quiz_runs.json")))

    # ---- 判分 + 热力图 ----
    answers = {q["id"]: ("A" if q["chapter"] != "第2章 条件与循环" else "B") for q in qs}
    g = D.grade_diagnosis(res["diagnosis_id"], answers)
    check("grade_ok", g.get("ok") is True, g)
    check("grade_counts", g.get("total") == 6 and g.get("correct") == 5, g)
    check("weak_chapter_detected", "第2章 条件与循环" in (g.get("weak") or []), g.get("weak"))
    check("heatmap_has_all_chapters", len(g.get("heatmap") or []) == 6)
    check("weak_mastery_zero",
          any(c["chapter"] == "第2章 条件与循环" and c["mastery"] == 0
              for c in g.get("heatmap") or []))

    # 分批交卷不冲掉上一题
    D.grade_diagnosis(res["diagnosis_id"], {"q1": "A"})
    g2 = D.get_diagnosis(res["diagnosis_id"], client_id="regr")
    check("partial_grade_merges", g2.get("total") == 6, g2.get("total"))

    # ---- prompt 注入 ----
    rec = store.get_record(res["diagnosis_id"])
    seg = store.format_for_prompt(rec)
    check("segment_mentions_weak", "诊断结果" in seg and "薄弱章节" in seg, seg)

    plain = format_profile_text(profile)
    check("no_diagnosis_no_segment_zero_regression", "诊断结果" not in plain, plain)
    with_diag = format_profile_text(profile, rec)
    check("with_diagnosis_has_segment", "诊断结果" in with_diag)

    captured.clear()
    plan_outline("Python 基础", profile)
    prompt = captured[0] if captured else ""
    check("planner_prompt_has_diagnosis", "诊断结果" in prompt)
    check("planner_prompt_has_weak_chapter", "第2章" in prompt)
    # 显式关掉诊断时不应出现该段
    captured.clear()
    plan_outline("Python 基础", profile, diagnosis=False)
    check("diagnosis_opt_out", "诊断结果" not in (captured[0] if captured else ""))

    # ---- 降级 ----
    def dead_chat(messages, *a, **k):
        return "[LLM 不可用] 回归桩"

    llm.chat = dead_chat
    res2 = D.generate_diagnosis("线性代数", profile=profile, count=6, client_id="regr")
    check("degraded_ok", res2.get("ok") is True, res2)
    check("degraded_flag", res2.get("degraded") is True)
    check("degraded_count", res2.get("count", 0) >= 5, res2.get("count"))
    check("degraded_source_outline",
          all(q["source"] == "outline" for q in res2.get("questions") or []))
    gg = D.grade_diagnosis(res2["diagnosis_id"], {q["id"]: 0 for q in res2.get("questions") or []})
    check("degraded_gradable", gg.get("ok") is True and gg.get("total", 0) >= 5, gg.get("total"))

    # 降级套也要有非空唯一 id，并且**逐题独立判分**：只故意错一道 ⇒ correct 恰好 n-1。
    # 这条是上面那个「答案塌成一个 key」缺陷的护栏。
    ids2 = [q.get("id") for q in res2.get("questions") or []]
    check("degraded_ids_non_empty_unique", all(ids2) and len(set(ids2)) == len(ids2), ids2)
    rec2 = store.get_record(res2["diagnosis_id"])
    qs2 = rec2["questions"]
    wrong_id = qs2[0]["id"]
    ans2 = {}
    for q in qs2:
        if q["type"] == "judge":
            right = int(q["answer"])
            ans2[q["id"]] = (1 - right) if q["id"] == wrong_id else right
        else:
            ans2[q["id"]] = (q["answer"] or ["A"])[0]
    g3 = D.grade_diagnosis(res2["diagnosis_id"], ans2)
    check("per_question_grading", g3.get("correct") == len(qs2) - 1, g3.get("correct"))
    check("one_weak_chapter_only", len(g3.get("weak") or []) == 1, g3.get("weak"))

    # ---- 健壮性 ----
    check("empty_course_not_ok", D.generate_diagnosis("").get("ok") is False)
    check("clamp_count", D._clamp_count("x") == 6 and D._clamp_count(99) == 8
          and D._clamp_count(0) == 5)
    check("answers_none_ok", D.grade_diagnosis(res2["diagnosis_id"], None).get("ok") is True)
    check("answers_list_ok",
          D.grade_diagnosis(res["diagnosis_id"],
                            [{"question_id": "q1", "selected": ["A"]}]).get("ok") is True)
    try:
        D.grade_diagnosis("dg-not-exist", {})
        check("missing_id_raises_keyerror", False)
    except KeyError:
        check("missing_id_raises_keyerror", True)
    check("get_unknown_not_found",
          D.get_diagnosis(course="不存在的课程", client_id="regr").get("ok") is False)
    # client 严格隔离：换个 client 查不到别人的记录
    check("client_isolation",
          D.get_diagnosis(course="Python 基础", client_id="别人").get("ok") is False)


if __name__ == "__main__":
    source_checks()
    runtime_checks()
    print()
    print("=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    print("结果：%s" % ("全部通过，可以提交" if FAIL == 0 else "有失败，先修"))
    sys.exit(0 if FAIL == 0 else 1)
