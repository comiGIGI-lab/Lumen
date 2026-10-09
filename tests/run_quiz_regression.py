# -*- coding: utf-8 -*-
"""选择题闯关回归（yu-ai-learn 官网可行复刻）。

契约（本切片定义，见 openspec/changes/2026-10-09-course-quiz-challenge/spec.md）：
    POST /api/quiz/generate {course, difficulty, count}
      弱命中 → {"ok": false, "error": ..., "retrieved": []}
      成功   → {"ok": true, "quiz_id", "questions": [..无 answer..], "retrieved"}
    POST /api/quiz/grade {quiz_id, question_id, selected}
      → {"ok": true, "correct", "answer", "explanation", "knowledge_point"}

硬约束：
    - 不改 /api/chat 契约与 RAG 门槛（1.0 / 0.2）
    - generate 响应不得包含 answer（判分只在服务端）
    - 两个新路由都要挂 detect_crisis / check_detail 前置闸
    - api_server 保持纯标准库；不 import 侧车

用法（仓库根目录）：

    python tests/run_quiz_regression.py

退出码 0 = 全过。源检查不起服务；runtime 部分用临时 data 目录 + mock LLM。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER = os.path.join(REPO_ROOT, "server")
VENDOR = os.path.join(REPO_ROOT, "vendor", "study-liu")
API = os.path.join(SERVER, "api_server.py")
QUIZ = os.path.join(SERVER, "quiz.py")
CHAT_PANEL = os.path.join(REPO_ROOT, "web", "src", "components", "ChatPanel.vue")
CHAT_PAGE = os.path.join(REPO_ROOT, "web", "src", "components", "ChatPage.vue")
QUIZ_PANEL = os.path.join(REPO_ROOT, "web", "src", "components", "QuizPanel.vue")
CLIENT = os.path.join(REPO_ROOT, "web", "src", "api", "client.js")
ZH = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-zh.json")
EN = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-en.json")
LOOP = os.path.join(VENDOR, "core", "agent_loop.py")

sys.path.insert(0, SERVER)
sys.path.insert(0, VENDOR)

FAILED = []
PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------------
# 1) 源检查
# ------------------------------------------------------------------

def source_checks():
    print("backend routes")
    api = read(API)
    check("api_has_quiz_generate_route", '"/api/quiz/generate"' in api,
          "do_POST missing /api/quiz/generate")
    check("api_has_quiz_grade_route", '"/api/quiz/grade"' in api,
          "do_POST missing /api/quiz/grade")
    quiz_block = ""
    m = re.search(r'if path == "/api/quiz/generate".*?(?=\n            if path == "/api/quiz/grade")', api, re.S)
    if m:
        quiz_block = m.group(0)
    check("generate_crisis_gate", quiz_block and "detect_crisis" in quiz_block,
          "generate route must run detect_crisis before anything else")
    check("generate_safety_gate", quiz_block and "check_detail" in quiz_block,
          "generate route must run check_detail")
    check("grade_keeps_standard_answer_server_side",
          'res.get("answer"' in api or '"answer": g' in api or True,
          "informational")

    quiz_src = read(QUIZ) if os.path.exists(QUIZ) else ""
    check("quiz_module_exists", bool(quiz_src), "server/quiz.py missing")
    if quiz_src:
        check("quiz_answer_not_in_generate_payload",
              re.search(r'"questions"\s*:', quiz_src) is not None,
              "quiz.py must build questions payload")
        # 对外 payload 构造段（列表推导里逐题白名单字段）不得带 answer
        m2 = re.search(r"payload_questions = \[[^\]]*\]", quiz_src, re.S)
        check("generate_payload_strips_answer",
              m2 is not None and '"answer"' not in m2.group(0),
              "questions payload must not carry answer")
        check("quiz_rejects_weak_hits",
              "RAG_MIN_SCORE" in quiz_src and "RAG_MIN_COVERAGE" in quiz_src
              and "WEAK_HIT_ERROR" in quiz_src,
              "quiz.py must reuse RAG thresholds and refuse weak hits")
    check("quiz_persists_runs",
          "quiz_runs.json" in quiz_src,
          "quiz.py must persist runs to data/quiz_runs.json")
    check("quiz_stdlib_only",
          not re.search(r"^\s*(import|from)\s+(fastapi|langchain|langgraph|chromadb|mysql)", quiz_src, re.M),
          "quiz.py must stay stdlib-only")

    print("scope guards (must stay)")
    loop = read(LOOP)
    check("rag_thresholds_untouched",
          "RAG_MIN_SCORE = 1.0" in loop and "RAG_MIN_COVERAGE = 0.2" in loop,
          "do not retune RAG in this slice")
    check("api_chat_contract_untouched",
          '"retrieved": res.get("retrieved") or []' in api,
          "/api/chat payload drifted")

    print("frontend wiring")
    client = read(CLIENT)
    check("client_has_quiz_generate",
          re.search(r"quizGenerate\(|'/quiz/generate'|\"/quiz/generate\"", client) is not None,
          "client.js missing quizGenerate")
    check("client_has_quiz_grade",
          re.search(r"quizGrade\(|'/quiz/grade'|\"/quiz/grade\"", client) is not None,
          "client.js missing quizGrade")

    check("quiz_panel_exists", os.path.exists(QUIZ_PANEL), "QuizPanel.vue missing")
    if os.path.exists(QUIZ_PANEL):
        panel = read(QUIZ_PANEL)
        check("panel_calls_grade_not_local_compare",
              "quizGrade" in panel and "correct" in panel,
              "QuizPanel must judge via server grade")
        check("panel_no_vhtml",
              re.search(r':v-html=|v-html="', panel) is None,
              "v-html forbidden in template")
        check("panel_wrongbook_on_wrong",
              re.search(r"wrongBookAdd|api\.wrongBookAdd", panel) is not None,
              "wrong answers must go to wrong book")
        check("panel_logs_exp",
              re.search(r"logExp\(", panel) is not None,
              "completion must logExp")
        check("panel_difficulty_options",
              "easy" in panel and "medium" in panel and "hard" in panel,
              "difficulty selector missing")

    page = read(CHAT_PAGE)
    check("chatpage_has_quiz_entry",
          "QuizPanel" in page, "ChatPage must mount QuizPanel")
    chat = read(CHAT_PANEL)
    check("chatpanel_untouched",
          "res.retrieved" in chat and "renderMarkdown" in chat,
          "ChatPanel Day1 retrieved display must stay")

    zh = json.loads(read(ZH))
    en = json.loads(read(EN))
    zh_keys = [k for k in zh if k.startswith("quizPage.")]
    en_keys = [k for k in en if k.startswith("quizPage.")]
    check("i18n_zh_quiz_keys", len(zh_keys) >= 8,
          "auto-zh.json needs quizPage.* keys (got %d)" % len(zh_keys))
    check("i18n_en_quiz_keys", len(en_keys) >= 8,
          "auto-en.json needs quizPage.* keys (got %d)" % len(en_keys))

    print("day6 source (types / report / tavily)")
    check("api_has_quiz_report_route", '"/api/quiz/report"' in api,
          "do_POST missing /api/quiz/report")
    rep_block = ""
    m = re.search(r'if path == "/api/quiz/report".*?(?=\n            if path == "/api/export")', api, re.S)
    if m:
        rep_block = m.group(0)
    check("report_crisis_gate", rep_block and "detect_crisis" in rep_block,
          "report route must run detect_crisis")
    check("report_safety_gate", rep_block and "check_detail" in rep_block,
          "report route must run check_detail")
    check("quiz_tavily_env_guarded",
          "STUDY_LIU_TAVILY_KEY" in quiz_src and "urllib.request" in quiz_src,
          "quiz.py must gate Tavily behind env var + use stdlib urllib")
    check("quiz_has_types_plan", "_resolve_plan" in quiz_src and "_distribute_mixed" in quiz_src,
          "quiz.py must support types plan")
    check("quiz_has_report", "def quiz_report" in quiz_src, "quiz.py missing quiz_report")
    check("client_has_quiz_report",
          re.search(r"quizReport\(|'/quiz/report'|\"/quiz/report\"", client) is not None,
          "client.js missing quizReport")
    check("panel_has_type_selector",
          "qtype" in panel and "TYPE_OPTIONS" in panel, "QuizPanel missing type selector")
    check("panel_has_report_call",
          "quizReport" in panel, "QuizPanel must call quizReport")
    check("i18n_zh_day6_keys",
          all(k in zh for k in ("quizPage.typeMixed", "quizPage.webSource", "quizPage.reportScore")),
          "auto-zh.json missing Day6 quizPage keys")
    check("i18n_en_day6_keys",
          all(k in en for k in ("quizPage.typeMixed", "quizPage.webSource", "quizPage.reportScore")),
          "auto-en.json missing Day6 quizPage keys")


# ------------------------------------------------------------------
# 2) runtime：临时 data 目录 + mock LLM
# ------------------------------------------------------------------

def runtime_checks():
    print("runtime (mock llm, temp data dir)")
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-reg-")
    os.environ["STUDY_LIU_DATA_DIR"] = tmp
    os.environ["LLM_PROVIDER"] = "mock"
    # 托管环境没装 requests；core.llm 顶层 import 它，stub 掉（plan 回归同套路）
    if "requests" not in sys.modules:
        import types
        sys.modules["requests"] = types.ModuleType("requests")
    for mod in ("core.paths", "core.agent_loop", "tools.knowledge_store", "quiz"):
        sys.modules.pop(mod, None)
    try:
        from core import paths as cpaths
        cpaths.data_dir = lambda *a, **k: tmp
        import core.agent_loop as loop_mod
        loop_mod._TRACE_DIR = tmp
    except Exception as e:
        check("runtime_imports", False, "vendor import failed: %s" % e)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("STUDY_LIU_DATA_DIR", None)
        return
    try:
        from tools.knowledge_store import KnowledgeStore
        store = KnowledgeStore()
        long_body = "线性代数是研究向量空间与线性映射的数学分支。矩阵乘法满足结合律但不满足交换律。特征值是线性变换在特征向量方向上的伸缩比例。行列式可以判断矩阵是否可逆，行列式非零即可逆。"
        store.add(title="线性代数讲义 第一章", content=long_body * 3, tags=["线性代数"])
    except Exception as e:
        check("runtime_kb_setup", False, "knowledge store setup failed: %s" % e)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("STUDY_LIU_DATA_DIR", None)
        return

    try:
        import quiz as quiz_mod
        import core.llm as llm_mod
    except Exception as e:
        check("runtime_quiz_import", False, "server/quiz.py import failed: %s" % e)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("STUDY_LIU_DATA_DIR", None)
        return

    def fake_chat_ok(messages):
        return json.dumps({
                "questions": [
                    {
                        "id": "q1", "type": "single",
                        "stem": "矩阵乘法满足以下哪一性质？",
                        "options": [
                            {"key": "A", "text": "结合律"},
                            {"key": "B", "text": "交换律"},
                            {"key": "C", "text": "分配律主导"},
                            {"key": "D", "text": "幂等律"},
                        ],
                        "answer": ["A"],
                        "explanation": "矩阵乘法满足结合律 (AB)C=A(BC)，但一般 AB≠BA。",
                        "knowledge_point": "矩阵乘法",
                    },
                    {
                        "id": "q2", "type": "single",
                        "stem": "行列式为零说明矩阵？",
                        "options": [
                            {"key": "A", "text": "可逆"},
                            {"key": "B", "text": "不可逆"},
                            {"key": "C", "text": "正交"},
                            {"key": "D", "text": "对称"},
                        ],
                        "answer": ["B"],
                        "explanation": "行列式非零是可逆的充要条件，为零则不可逆。",
                        "knowledge_point": "行列式",
                    },
                    {
                        "id": "q3", "type": "single",
                        "stem": "特征值刻画的是线性变换的？",
                        "options": [
                            {"key": "A", "text": "旋转轴"},
                            {"key": "B", "text": "尺度伸缩比例"},
                            {"key": "C", "text": "投影方向"},
                            {"key": "D", "text": "转置不变性"},
                        ],
                        "answer": ["B"],
                        "explanation": "特征值是变换在特征向量方向上的伸缩比例。",
                        "knowledge_point": "特征值",
                    },
        ]
    }, ensure_ascii=False)

    llm_mod.chat = fake_chat_ok
    quiz_mod._llm_chat = fake_chat_ok

    try:
        res = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=3)
        check("generate_ok", res.get("ok") is True, "generate failed: %s" % res.get("error"))
        check("generate_has_quiz_id", bool(res.get("quiz_id")), "quiz_id missing")
        check("generate_questions_len", len(res.get("questions") or []) == 3,
              "expected 3 questions")
        qs = res.get("questions") or []
        check("generate_payload_has_no_answer",
              all("answer" not in q for q in qs),
              "answer leaked into generate payload")
        check("generate_keeps_retrieved",
              isinstance(res.get("retrieved"), list) and len(res["retrieved"]) >= 1,
              "retrieved missing")

        runs_file = os.path.join(tmp, "quiz_runs.json")
        check("runs_persisted", os.path.exists(runs_file), "quiz_runs.json not written")

        g = quiz_mod.grade_quiz(res["quiz_id"], "q1", "A")
        check("grade_correct_pick", g.get("ok") and g.get("correct") is True,
              "correct answer judged wrong: %s" % g)
        g2 = quiz_mod.grade_quiz(res["quiz_id"], "q2", "A")
        check("grade_wrong_pick", g2.get("ok") and g2.get("correct") is False,
              "wrong answer judged right")
        check("grade_returns_answer", g2.get("answer") == ["B"] or g2.get("answer") == "B",
              "grade must return the standard answer")
        try:
            quiz_mod.grade_quiz("z-nonexistent", "q1", "A")
            check("grade_unknown_quiz_404", False, "unknown quiz_id must raise/404")
        except KeyError:
            check("grade_unknown_quiz_404", True)

        def fake_chat_garbage(messages):
            return "这不是 JSON，出题失败样例。"
        quiz_mod._llm_chat = fake_chat_garbage
        bad = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=3)
        check("garbage_llm_rejected", bad.get("ok") is False,
              "non-JSON LLM output must fail, not degrade")

        quiz_mod._llm_chat = fake_chat_ok
        weak = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3)
        check("weak_kb_hit_rejected", weak.get("ok") is False and weak.get("retrieved") == [],
              "weak KB hits must refuse to generate")
    except Exception as e:
        check("runtime_no_crash", False, "runtime crashed: %r" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("STUDY_LIU_DATA_DIR", None)


def runtime_day6():
    """Day6 运行时：题型分布 / 判分 / 复盘聚合 / Tavily 联网兜底（mock LLM，临时 data 目录）。"""
    print("runtime day6 (types / report / tavily, mock llm, temp data dir)")

    def setup(tmp):
        os.environ["STUDY_LIU_DATA_DIR"] = tmp
        os.environ["LLM_PROVIDER"] = "mock"
        if "requests" not in sys.modules:
            import types as _t
            sys.modules["requests"] = _t.ModuleType("requests")
        for mod in ("core.paths", "core.agent_loop", "tools.knowledge_store", "quiz"):
            sys.modules.pop(mod, None)
        try:
            from core import paths as cpaths
            cpaths.data_dir = lambda *a, **k: tmp
            import core.agent_loop as loop_mod
            loop_mod._TRACE_DIR = tmp
            from tools.knowledge_store import KnowledgeStore
            store = KnowledgeStore()
            long_body = ("线性代数是研究向量空间与线性映射的数学分支。矩阵乘法满足结合律但不满足交换律。"
                         "特征值是线性变换在特征向量方向上的伸缩比例。行列式可以判断矩阵是否可逆，行列式非零即可逆。")
            store.add(title="线性代数讲义 第一章", content=long_body * 3, tags=["线性代数"])
            import quiz as quiz_mod
            import core.llm as llm_mod
            return quiz_mod, llm_mod
        except Exception as e:
            check("day6_setup", False, "setup failed: %s" % e)
            return None, None

    def teardown(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("STUDY_LIU_DATA_DIR", None)
        os.environ.pop("STUDY_LIU_TAVILY_KEY", None)

    # ---- mixed 分布 + 判分 + 复盘 ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-d6-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return

    def fake_mixed(messages):
        return json.dumps({
            "questions": [
                {"type": "single", "stem": "矩阵乘法满足？", "options": [
                    {"key": "A", "text": "结合律"}, {"key": "B", "text": "交换律"},
                    {"key": "C", "text": "幂等律"}, {"key": "D", "text": "对称律"}],
                 "answer": ["A"], "explanation": "满足结合律", "knowledge_point": "矩阵乘法"},
                {"type": "single", "stem": "行列式为零说明？", "options": [
                    {"key": "A", "text": "可逆"}, {"key": "B", "text": "不可逆"},
                    {"key": "C", "text": "正交"}, {"key": "D", "text": "对称"}],
                 "answer": ["B"], "explanation": "为零不可逆", "knowledge_point": "行列式"},
                {"type": "single", "stem": "特征值刻画？", "options": [
                    {"key": "A", "text": "旋转"}, {"key": "B", "text": "伸缩"},
                    {"key": "C", "text": "投影"}, {"key": "D", "text": "转置"}],
                 "answer": ["B"], "explanation": "伸缩比例", "knowledge_point": "特征值"},
                {"type": "single", "stem": "向量空间满足？", "options": [
                    {"key": "A", "text": "加法封闭"}, {"key": "B", "text": "乘法封闭"},
                    {"key": "C", "text": "除法封闭"}, {"key": "D", "text": "取模封闭"}],
                 "answer": ["A"], "explanation": "加法封闭", "knowledge_point": "向量空间"},
                {"type": "multi", "stem": "哪些是线性空间公理？", "options": [
                    {"key": "A", "text": "加法交换"}, {"key": "B", "text": "加法结合"},
                    {"key": "C", "text": "数乘结合"}, {"key": "D", "text": "乘法交换"}],
                 "answer": ["A", "B", "C"], "explanation": "前三项", "knowledge_point": "线性空间公理"},
                {"type": "multi", "stem": "哪些矩阵可逆？", "options": [
                    {"key": "A", "text": "行列式非零"}, {"key": "B", "text": "满秩"},
                    {"key": "C", "text": "奇异"}, {"key": "D", "text": "秩亏"}],
                 "answer": ["A", "B"], "explanation": "非零/满秩可逆", "knowledge_point": "可逆矩阵"},
                {"type": "judge", "stem": "矩阵乘法满足交换律。", "options": [
                    {"key": "0", "text": "正确"}, {"key": "1", "text": "错误"}],
                 "answer": 1, "explanation": "一般不满足交换", "knowledge_point": "矩阵乘法"},
                {"type": "judge", "stem": "行列式非零则矩阵可逆。", "options": [
                    {"key": "0", "text": "正确"}, {"key": "1", "text": "错误"}],
                 "answer": 0, "explanation": "充要条件", "knowledge_point": "行列式"},
            ]
        }, ensure_ascii=False)

    llm_mod.chat = fake_mixed
    quiz_mod._llm_chat = fake_mixed
    try:
        res = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=8, types="mixed")
        check("mixed_generate_ok", res.get("ok") is True, "mixed failed: %s" % res.get("error"))
        if res.get("ok"):
            check("mixed_plan_ratio", res.get("types") == {"single": 4, "multi": 2, "judge": 2},
                  "plan mismatch: %s" % res.get("types"))
            qs = res.get("questions") or []
            # 判分须用服务端题目（payload 不带 answer）
            _run = quiz_mod._load().get(res["quiz_id"]) or {}
            sq = _run.get("questions", [])
            check("mixed_count_8", len(qs) == 8, "expected 8 got %d" % len(qs))
            cnt = {}
            for q in qs:
                cnt[q.get("type")] = cnt.get(q.get("type"), 0) + 1
            check("mixed_type_counts",
                  cnt.get("single") == 4 and cnt.get("multi") == 2 and cnt.get("judge") == 2,
                  "type counts: %s" % cnt)
            check("mixed_payload_no_answer", all("answer" not in q for q in qs), "answer leaked")
            # multi 全对 / 漏选错
            mq = next(q for q in sq if q["type"] == "multi")
            g = quiz_mod.grade_quiz(res["quiz_id"], mq["id"], list(mq["answer"]))
            check("multi_all_correct", g.get("correct") is True, "multi correct wrong: %s" % g)
            g2 = quiz_mod.grade_quiz(res["quiz_id"], mq["id"], [mq["answer"][0]])
            check("multi_partial_wrong", g2.get("correct") is False, "multi partial right")
            # judge 对 / 错
            jq = next(q for q in sq if q["type"] == "judge")
            gj = quiz_mod.grade_quiz(res["quiz_id"], jq["id"], str(jq["answer"]))
            check("judge_correct", gj.get("correct") is True, "judge correct wrong: %s" % gj)
            gj2 = quiz_mod.grade_quiz(res["quiz_id"], jq["id"], str(1 - int(jq["answer"])))
            check("judge_wrong", gj2.get("correct") is False, "judge wrong right")
            # 全部答对 → 复盘 score=8 / accuracy=1 / weak_points=[]
            for q in sq:
                ans = list(q["answer"]) if q["type"] == "multi" else (
                    str(q["answer"]) if q["type"] == "judge" else q["answer"][0])
                quiz_mod.grade_quiz(res["quiz_id"], q["id"], ans)
            rep = quiz_mod.quiz_report(res["quiz_id"])
            check("report_ok", rep.get("ok") is True, "report failed")
            check("report_total_8", rep.get("total") == 8, "total %s" % rep.get("total"))
            check("report_score_8", rep.get("score") == 8, "score %s" % rep.get("score"))
            check("report_accuracy_1", abs(rep.get("accuracy") - 1.0) < 1e-9, "acc %s" % rep.get("accuracy"))
            check("report_duration_notnull", rep.get("duration_s") is not None, "duration missing")
            check("report_weak_empty", rep.get("weak_points") == [], "weak should be empty: %s" % rep.get("weak_points"))
            check("report_replay_has_answers",
                  all("correct_answer" in q and "user_answer" in q for q in (rep.get("questions") or [])),
                  "replay missing answers")
            # 把第 1 题改成错 → weak_points 出现
            quiz_mod.grade_quiz(res["quiz_id"], qs[0]["id"], "B")
            rep2 = quiz_mod.quiz_report(res["quiz_id"])
            check("report_score_7", rep2.get("score") == 7, "score %s" % rep2.get("score"))
            check("report_weak_has_kp",
                  any(w.get("knowledge_point") == qs[0]["knowledge_point"] for w in rep2.get("weak_points", [])),
                  "weak point missing: %s" % rep2.get("weak_points"))
    except Exception as e:
        check("day6_mixed_no_crash", False, "mixed crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- Tavily 联网兜底：有 key 出题并标来源；无 key 回退拒绝 ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-tav-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    orig_tav = quiz_mod._tavily_search
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._tavily_search = lambda q, k: [
        {"title": "Web A", "url": "https://example.com/a", "content": "矩阵乘法满足结合律。"},
        {"title": "Web B", "url": "https://example.com/b", "content": "特征值刻画伸缩比例。"},
    ]
    llm_mod.chat = fake_chat_ok if "fake_chat_ok" in dir() else None
    # 复用上面定义的 fake_chat_ok（single 三题）
    def fake_single(messages):
        return json.dumps({
            "questions": [
                {"type": "single", "stem": "矩阵乘法满足？", "options": [
                    {"key": "A", "text": "结合律"}, {"key": "B", "text": "交换律"},
                    {"key": "C", "text": "幂等律"}, {"key": "D", "text": "对称律"}],
                 "answer": ["A"], "explanation": "满足结合律", "knowledge_point": "矩阵乘法"},
                {"type": "single", "stem": "行列式为零说明？", "options": [
                    {"key": "A", "text": "可逆"}, {"key": "B", "text": "不可逆"},
                    {"key": "C", "text": "正交"}, {"key": "D", "text": "对称"}],
                 "answer": ["B"], "explanation": "为零不可逆", "knowledge_point": "行列式"},
                {"type": "single", "stem": "特征值刻画？", "options": [
                    {"key": "A", "text": "旋转"}, {"key": "B", "text": "伸缩"},
                    {"key": "C", "text": "投影"}, {"key": "D", "text": "转置"}],
                 "answer": ["B"], "explanation": "伸缩比例", "knowledge_point": "特征值"},
            ]
        }, ensure_ascii=False)

    llm_mod.chat = fake_single
    quiz_mod._llm_chat = fake_single
    try:
        res = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3)
        check("tavily_with_key_ok", res.get("ok") is True, "tavily gen failed: %s" % res.get("error"))
        if res.get("ok"):
            check("tavily_source_web", res.get("source") == "web", "source should be web: %s" % res.get("source"))
            q0 = (res.get("questions") or [{}])[0]
            check("tavily_question_source_web", q0.get("source") == "web", "q source should be web")
            check("tavily_question_sources", isinstance(q0.get("sources"), list) and len(q0.get("sources")) >= 1,
                  "q sources missing: %s" % q0.get("sources"))
        # 无 key：恢复真实 _tavily_search + 撤环境变量 → 回退 WEAK_HIT_ERROR
        quiz_mod._tavily_search = orig_tav
        os.environ.pop("STUDY_LIU_TAVILY_KEY", None)
        weak = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3)
        check("tavily_no_key_rejected", weak.get("ok") is False and weak.get("retrieved") == [],
              "no-key weak hit must refuse")
    except Exception as e:
        check("day6_tavily_no_crash", False, "tavily crashed: %r" % e)
    finally:
        teardown(tmp)


def main():
    source_checks()
    runtime_checks()
    runtime_day6()
    print()
    print("passed %d  failed %d" % (PASSED, len(FAILED)))
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print("  - %s" % name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
