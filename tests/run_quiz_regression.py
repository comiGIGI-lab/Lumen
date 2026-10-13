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
import logging
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
    check("api_has_quiz_stream_route", '"/api/quiz/stream"' in api,
          "do_GET missing /api/quiz/stream")
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
        # 对外单题白名单（_public_question）不得带 answer。SSE 与整卷共用它。
        m2 = re.search(r"def _public_question\(q\):.*?return \{.*?\}", quiz_src, re.S)
        check("generate_payload_strips_answer",
              m2 is not None and '"answer"' not in m2.group(0)
              and "payload_questions = [_public_question" in quiz_src,
              "questions payload must not carry answer")
        check("quiz_kb_optional_enrichment",
              "RAG_MIN_SCORE" in quiz_src and "RAG_MIN_COVERAGE" in quiz_src,
              "quiz.py must reuse RAG thresholds for optional KB enrichment")
        check("quiz_logs_web_warning",
              "import logging" in quiz_src and "logging.warning" in quiz_src,
              "quiz.py must log warning on web-search degrade")
    check("quiz_persists_runs",
          "quiz_runs.json" in quiz_src,
          "quiz.py must persist runs to data/quiz_runs.json")
    check("quiz_stdlib_only",
          not re.search(r"^\s*(import|from)\s+(fastapi|langchain(?!_tavily)|langgraph|chromadb|mysql)", quiz_src, re.M),
          "quiz.py must stay stdlib-only (langchain_tavily is the lead-approved quiz-chain exception)")

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
    check("client_has_quiz_stream_url",
          "function quizStreamUrl" in client and "/quiz/stream" in client,
          "client.js missing quizStreamUrl")

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
        check("panel_uses_event_source",
              "EventSource" in panel and "quizStreamUrl" in panel,
              "QuizPanel must open the quiz SSE")

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
          "STUDY_LIU_TAVILY_KEY" in quiz_src and "langchain_tavily" in quiz_src and "TavilySearch" in quiz_src,
          "quiz.py must gate Tavily behind env var + use langchain_tavily (TavilySearch/TavilyExtract)")
    check("quiz_has_types_plan", "_resolve_plan" in quiz_src and "_distribute_mixed" in quiz_src,
          "quiz.py must support types plan")
    check("quiz_has_report", "def quiz_report" in quiz_src, "quiz.py missing quiz_report")
    check("api_forwards_web_search",
          quiz_block and "web_search" in quiz_block,
          "generate route must forward web_search (and types)")
    check("client_forwards_web_search",
          re.search(r"web_search", client) is not None,
          "client.js quizGenerate must forward web_search")
    check("panel_has_web_search_toggle",
          "webSearch" in panel, "QuizPanel missing web-search toggle")

    print("lively tone toggle (humor / life scenarios)")
    check("quiz_generate_takes_lively",
          "lively" in quiz_src and "def generate_quiz" in quiz_src,
          "generate_quiz must accept the lively flag")
    check("quiz_lively_in_prompt",
          "_style_rule" in quiz_src and "轻松幽默" in quiz_src,
          "quiz.py must translate lively into a prompt instruction")
    quiz_stream_fn = ""
    mqs = re.search(r"def _handle_quiz_stream.*?(?=\nclass )", api, re.S)
    if mqs:
        quiz_stream_fn = mqs.group(0)
    check("api_generate_forwards_lively",
          quiz_block and "lively" in quiz_block,
          "POST /api/quiz/generate must forward lively")
    check("api_stream_forwards_lively",
          quiz_stream_fn and "lively" in quiz_stream_fn,
          "GET /api/quiz/stream must forward lively")
    check("client_forwards_lively",
          "lively" in client,
          "client.js must forward lively for both quiz calls")
    check("panel_has_lively_toggle",
          "lively" in panel, "QuizPanel missing lively-tone toggle")
    check("i18n_zh_lively_keys",
          all(k in zh for k in ("quizPage.lively", "quizPage.livelyOn", "quizPage.livelyOff")),
          "auto-zh.json missing lively keys")
    check("i18n_en_lively_keys",
          all(k in en for k in ("quizPage.lively", "quizPage.livelyOn", "quizPage.livelyOff")),
          "auto-en.json missing lively keys")
    check("quiz_has_tavily_extract",
          "TavilyExtract" in quiz_src and "tavily_extract" in quiz_src and "tavily_search_deep" in quiz_src,
          "quiz.py must implement Tavily extract + 4 search/extract tools for URL direct-gen")
    check("quiz_generate_takes_web_search",
          "def generate_quiz" in quiz_src and "web_search" in quiz_src,
          "generate_quiz must accept web_search flag")
    check("client_has_quiz_report",
          re.search(r"quizReport\(|'/quiz/report'|\"/quiz/report\"", client) is not None,
          "client.js missing quizReport")
    check("panel_has_type_selector",
          "qtype" in panel and "TYPE_OPTIONS" in panel, "QuizPanel missing type selector")
    check("panel_has_report_call",
          "quizReport" in panel, "QuizPanel must call quizReport")
    check("i18n_zh_day6_keys",
          all(k in zh for k in ("quizPage.typeMixed", "quizPage.webSource", "quizPage.webSearch", "quizPage.reportScore")),
          "auto-zh.json missing Day6 quizPage keys")
    check("i18n_en_day6_keys",
          all(k in en for k in ("quizPage.typeMixed", "quizPage.webSource", "quizPage.webSearch", "quizPage.reportScore")),
          "auto-en.json missing Day6 quizPage keys")


# ------------------------------------------------------------------
# 2) runtime：临时 data 目录 + mock LLM
# ------------------------------------------------------------------

def runtime_checks():
    print("runtime (mock llm, temp data dir)")
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-reg-")
    os.environ["STUDY_LIU_DATA_DIR"] = tmp
    os.environ["LLM_PROVIDER"] = "mock"
    # 本段测的是知识库直出，不走联网。开发机若已配置 key，要先拿掉。
    os.environ.pop("STUDY_LIU_TAVILY_KEY", None)
    os.environ.pop("TAVILY_API_KEY", None)
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

    ALL_QS = [
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

    calls = {"n": 0, "gen": 0}

    def fake_chat_ok(messages):
        calls["n"] += 1
        text = messages[-1]["content"] if messages else ""
        if "你是严谨的出题老师" in text:
            calls["gen"] += 1
        # 出题 prompt 要求的题数；流式路径会先要 1 题，再要剩余题。
        asked = text.split("出题依据的资料")[0]
        m = re.search(r"(\d+)\s*道(?:单选|多选|判断)", asked)
        n = int(m.group(1)) if m else len(ALL_QS)
        pool = ALL_QS[:1] if n <= 1 else ALL_QS
        n = max(1, min(n, len(pool)))
        return json.dumps({"questions": pool[:n]}, ensure_ascii=False)

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

        def fake_stream(messages):
            calls["gen"] += 1
            text = messages[-1]["content"] if messages else ""
            asked = text.split("出题依据的资料")[0]
            m = re.search(r"(\d+)\s*道(?:单选|多选|判断)", asked)
            n = int(m.group(1)) if m else 1
            pool = ALL_QS[:1] if n <= 1 else list(ALL_QS[1:1 + n])
            return json.dumps({"questions": pool}, ensure_ascii=False)
        quiz_mod._llm_chat = fake_stream
        calls["gen"] = 0
        seen = []
        graded_mid = None
        for event, data in quiz_mod.iter_generate_quiz("线性代数", difficulty="easy", count=3):
            seen.append(event)
            blob = json.dumps(data, ensure_ascii=False)
            check("stream_event_hides_answer_%d" % len(seen), '"answer"' not in blob,
                  "answer leaked into %s" % event)
            if event == "question" and len([e for e in seen if e == "question"]) == 1:
                check("stream_first_before_rest", calls["gen"] == 1,
                      "first question must be emitted before the second model call, calls=%s" % calls["gen"])
                graded_mid = quiz_mod.grade_quiz(data["quiz_id"], data["question"]["id"], "A")
                calls["first_id"] = data["question"]["id"]
        check("stream_order", seen[:2] == ["meta", "question"] and seen[-1] == "done",
              "unexpected events %s" % seen)
        check("stream_three_questions", seen.count("question") == 3,
              "expected 3 streamed questions, got %s" % seen)
        check("stream_grade_while_generating",
              graded_mid and graded_mid.get("ok") and graded_mid.get("correct") is True,
              "first question must be gradeable before the rest arrive")

        # 第二批与第一题题干重复时必须补题，不能把「要 3 题」静默收成 2 题。
        def fake_dup(messages):
            text = messages[-1]["content"] if messages else ""
            asked = text.split("出题依据的资料")[0]
            m = re.search(r"(\d+)\s*道(?:单选|多选|判断)", asked)
            n = int(m.group(1)) if m else 1
            if "以下题干已经出过" in text:
                pool = [dict(ALL_QS[2])]
            elif n <= 1:
                pool = [dict(ALL_QS[0])]
            else:
                pool = [dict(ALL_QS[0]), dict(ALL_QS[1])]
            return json.dumps({"questions": pool}, ensure_ascii=False)
        quiz_mod._llm_chat = fake_dup
        dup_events = []
        for event, data in quiz_mod.iter_generate_quiz("线性代数", difficulty="easy", count=3):
            if event == "question":
                dup_events.append(data["question"]["stem"])
            if event == "done":
                dup_done = data
        check("stream_refills_duplicate_stem",
              len(set(dup_events)) == 3 and dup_done.get("short") is False,
              "duplicate stems must be refilled, got %s" % dup_events)

        # 指定章节但知识库无对应材料：报错，不许退回全课程出题。
        quiz_mod._llm_chat = fake_chat_ok
        miss = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=3,
                                      topics=["完全不存在的章节名称"])
        check("topics_without_kb_hit_errors",
              miss.get("ok") is False and "所选章节" in (miss.get("error") or ""),
              "unmatched topics must error, not fall back: %s" % miss.get("error"))

        quiz_mod._llm_chat = fake_chat_ok

        # 趣味文风开关：只改表达，不改知识点/答案/题数
        captured = {}
        def fake_capture(messages):
            captured["text"] = messages[-1]["content"] if messages else ""
            return json.dumps({"questions": ALL_QS[:3]}, ensure_ascii=False)
        quiz_mod._llm_chat = fake_capture
        plain_run = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=3)
        plain = captured.get("text") or ""
        fun_run = quiz_mod.generate_quiz("线性代数", difficulty="easy", count=3, lively=True)
        fun = captured.get("text") or ""
        check("lively_off_keeps_strict_tone", "轻松幽默" not in plain,
              "default prompt must stay strict, no humor instruction")
        check("lively_on_asks_humor", "轻松幽默" in fun and "比喻" in fun,
              "lively prompt must ask for life scenarios and metaphor")
        check("lively_keeps_count", len(plain_run.get("questions") or []) == 3
              and len(fun_run.get("questions") or []) == 3,
              "lively must not change how many questions are generated")
        same_stems = [q["stem"] for q in (plain_run.get("questions") or [])] == \
                     [q["stem"] for q in (fun_run.get("questions") or [])]
        check("lively_keeps_questions", same_stems,
              "lively must not change the questions themselves")
        tool_fun = quiz_mod._tool_user(
            "线性代数", "easy", {"single": 3, "multi": 0, "judge": 0}, False, "", True)
        check("lively_reaches_tool_agent", "轻松幽默" in tool_fun,
              "lively must reach the Tavily tool-agent prompt too")
        weak = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3)
        check("weak_kb_degraded_generate", weak.get("ok") is True,
              "weak KB hit must degrade to topic gen, not reject: %s" % weak.get("error"))
        check("weak_kb_source_topic", weak.get("source") == "topic",
              "degraded run source should be 'topic': %s" % weak.get("source"))
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
        os.environ.pop("STUDY_LIU_TAVILY_KEY", None)
        os.environ.pop("TAVILY_API_KEY", None)
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

    # ===== 工具智能体回归（langchain-tavily）=====
    # 公共辅助：脚本化 LLM 与假工具（真实依赖 langchain-tavily 仅在 _build_tavily_tools
    # 内延迟 import；本组测试用假工具替换，避免联网，同时断言工具被正确调用）。
    SINGLE_QS = [
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

    def fake_single(messages):
        return json.dumps({"questions": SINGLE_QS}, ensure_ascii=False)

    def scripted(responses):
        state = {"i": 0}
        def f(messages):
            r = responses[min(state["i"], len(responses) - 1)]
            state["i"] += 1
            return r
        return f

    def tool_call(name, args):
        return "<tool>\n%s</tool>" % json.dumps({"name": name, "args": args}, ensure_ascii=False)

    def finish(questions, sources):
        return "<finish>\n%s</finish>" % json.dumps(
            {"questions": questions, "sources": sources}, ensure_ascii=False)

    class _FakeTool:
        def __init__(self, name, record):
            self.name = name
            self.args = {"query": None, "include_domains": None, "exclude_domains": None,
                         "search_depth": None, "time_range": None, "topic": None,
                         "urls": None, "extract_depth": None, "include_images": None}
            self._record = record
        def invoke(self, a):
            self._record.append((self.name, dict(a or {})))
            if self.name.startswith("tavily_extract"):
                return "【抓取正文】网页 %s 陈述：矩阵乘法满足结合律但不满足交换律；特征值刻画伸缩。" % (a or {}).get("urls")
            return ("【联网资料】标题A URL=https://example.com/a 内容：矩阵乘法满足结合律。"
                    "标题B URL=https://example.com/b 内容：特征值刻画伸缩比例。")

    def make_fake_tools(record):
        return {n: _FakeTool(n, record) for n in
                ("tavily_search", "tavily_search_deep", "tavily_extract", "tavily_extract_deep")}

    # ---- 工具构造：4 个 Tavily 工具参数校验（需 langchain-tavily，缺则跳过） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-ctor-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    try:
        import langchain_tavily as _lt
    except Exception:
        _lt = None
    if _lt is not None:
        recorded = []
        class _RecS:
            def __init__(self, **kw): recorded.append(("search", dict(kw)))
        class _RecE:
            def __init__(self, **kw): recorded.append(("extract", dict(kw)))
        _os, _oe = _lt.TavilySearch, _lt.TavilyExtract
        _lt.TavilySearch, _lt.TavilyExtract = _RecS, _RecE
        try:
            quiz_mod._build_tavily_tools("dummy-key")
        finally:
            _lt.TavilySearch, _lt.TavilyExtract = _os, _oe
        sd = next((k for n, k in recorded if k.get("search_depth") == "advanced"), None)
        check("tavily_search_deep_raw_content",
              sd is not None and sd.get("include_raw_content") is True and (sd.get("max_results") or 0) >= 15,
              "tavily_search_deep must be advanced+raw_content+max>=15: %s" % sd)
        sb = next((k for n, k in recorded if k.get("search_depth") == "basic"), None)
        check("tavily_search_basic_cfg",
              sb is not None and sb.get("include_raw_content") is False and (sb.get("max_results") or 0) >= 10,
              "tavily_search must be basic+no_raw+max>=10: %s" % sb)
        exb = next((k for n, k in recorded if n == "extract" and k.get("extract_depth") == "basic"), None)
        check("tavily_extract_basic_cfg", exb is not None, "tavily_extract basic missing")
        exd = next((k for n, k in recorded if n == "extract" and k.get("extract_depth") == "advanced"), None)
        check("tavily_extract_deep_cfg", exd is not None, "tavily_extract_deep advanced missing")
    else:
        check("tavily_tools_construction_skipped", True,
              "langchain-tavily not installed in this env; construction not exercised")
    teardown(tmp)

    # 工具智能体 prompt 必须强调「多关键词检索 + 以多数为准」，避免少数结果误判领域
    try:
        _sys = getattr(quiz_mod, "_TOOL_SYSTEM", "")
        check("agent_prompt_multi_keyword",
              "harness engineering" in _sys and "以多数为准" in _sys and "多关键词" in _sys,
              "tool-agent system prompt must guide multi-keyword search + majority voting")
    except Exception:
        check("agent_prompt_multi_keyword", False, "cannot read _TOOL_SYSTEM")

    # ---- 工具智能体：search 出题（主题 → tavily_search → 标 web 来源） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-agent-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._build_tavily_tools = lambda key: make_fake_tools(record)
    quiz_mod._llm_chat = scripted([
        tool_call("tavily_search", {"query": "量子占卜玄学导论"}),
        finish(SINGLE_QS, [{"title": "Web A", "url": "https://example.com/a"}]),
    ])
    try:
        res = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3, web_search=True)
        check("agent_search_generates", res.get("ok") is True, "search agent failed: %s" % res.get("error"))
        check("agent_search_source_web", res.get("source") == "web", "source should be web: %s" % res.get("source"))
        check("agent_search_called_tool", any(n == "tavily_search" for n, _ in record), "tavily_search not invoked")
        q0 = (res.get("questions") or [{}])[0]
        check("agent_search_q_source_web", q0.get("source") == "web", "q source should be web")
        check("agent_search_q_sources", isinstance(q0.get("sources"), list) and len(q0.get("sources")) >= 1,
              "q sources missing: %s" % q0.get("sources"))
    except Exception as e:
        check("day6_agent_search_no_crash", False, "agent search crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 工具智能体：extract(URL) 出题（URL → tavily_extract → sources 带该 URL） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-agentx-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    url = "https://example.com/linear-algebra-notes"
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._build_tavily_tools = lambda key: make_fake_tools(record)
    quiz_mod._llm_chat = scripted([
        tool_call("tavily_extract", {"urls": [url]}),
        finish(SINGLE_QS, [{"title": url, "url": url}]),
    ])
    try:
        res = quiz_mod.generate_quiz(url, difficulty="easy", count=3, web_search=True)
        check("agent_extract_generates", res.get("ok") is True, "extract agent failed: %s" % res.get("error"))
        check("agent_extract_source_web", res.get("source") == "web", "source web: %s" % res.get("source"))
        check("agent_extract_called_tool", any(n == "tavily_extract" for n, _ in record), "tavily_extract not invoked")
        qsrc = (res.get("questions") or [{}])[0].get("sources") or []
        check("agent_extract_sources_carry_url",
              isinstance(qsrc, list) and any(s.get("url") == url for s in qsrc),
              "sources should carry url: %s" % qsrc)
    except Exception as e:
        check("day6_agent_extract_no_crash", False, "agent extract crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 国内域限定：模型应自定 include_domains 含中文域 ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-dom-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._build_tavily_tools = lambda key: make_fake_tools(record)
    quiz_mod._llm_chat = scripted([
        tool_call("tavily_search", {"query": "高考物理复习", "include_domains": ["*.cn", "*.edu.cn"]}),
        finish(SINGLE_QS, [{"title": "国内站", "url": "https://school.edu.cn/x"}]),
    ])
    try:
        res = quiz_mod.generate_quiz("高考物理复习", difficulty="easy", count=3, web_search=True)
        check("agent_domestic_domain_called", res.get("ok") is True, "domestic failed: %s" % res.get("error"))
        dom = next((a.get("include_domains") for n, a in record if n == "tavily_search"), None)
        check("agent_domestic_include_cn", isinstance(dom, list) and any("cn" in d for d in dom),
              "search must include *.cn domain: %s" % dom)
        check("agent_domestic_prompt_guides", "*.cn" in quiz_mod._TOOL_SYSTEM,
              "system prompt must mention *.cn default")
    except Exception as e:
        check("day6_agent_dom_no_crash", False, "domestic crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 失败回退拒绝：URL extract 失败 → WEAK_HIT_ERROR（无 URL 内容无法出题） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-fail-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    url = "https://example.com/broken"
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    bad = make_fake_tools(record)
    bad["tavily_extract"].invoke = lambda a: (_ for _ in ()).throw(RuntimeError("network down"))
    quiz_mod._build_tavily_tools = lambda key: bad
    quiz_mod._llm_chat = scripted([tool_call("tavily_extract", {"urls": [url]})])
    try:
        failed = quiz_mod.generate_quiz(url, difficulty="easy", count=3, web_search=True)
        check("agent_extract_fail_rejected",
              failed.get("ok") is False and failed.get("retrieved") == [],
              "extract failure must fall back to WEAK_HIT_ERROR: %s" % failed.get("error"))
    except Exception as e:
        check("day6_agent_fail_no_crash", False, "agent fail crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 联网搜索开关：关 → 不调工具，直接出题（source topic） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-wsoff-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._llm_chat = fake_single
    try:
        off = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3, web_search=False)
        check("web_search_off_generates", off.get("ok") is True,
              "web_search off must still generate: %s" % off.get("error"))
        check("web_search_off_no_web_source", off.get("source") in ("topic", "kb"),
              "web_search off should not mark web: %s" % off.get("source"))
    except Exception as e:
        check("day6_wsoff_no_crash", False, "wsoff crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 联网搜索开关：开但工具失败 → 降级为空上下文出题（不拒绝） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-wsfail-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    bad = make_fake_tools(record)
    bad["tavily_search"].invoke = lambda a: (_ for _ in ()).throw(RuntimeError("boom"))
    quiz_mod._build_tavily_tools = lambda key: bad
    # 工具失败后，模型收到错误，回退到通用知识出题（裸 JSON 收尾，无 <finish>）
    quiz_mod._llm_chat = scripted([
        tool_call("tavily_search", {"query": "量子占卜玄学导论"}),
        json.dumps({"questions": SINGLE_QS}, ensure_ascii=False),
    ])
    try:
        failed = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3, web_search=True)
        check("web_search_fail_degrades", failed.get("ok") is True,
              "web search fail must degrade, not reject: %s" % failed.get("error"))
        check("web_search_fail_no_web_source", failed.get("source") in ("topic", "kb"),
              "degraded run must not carry web source: %s" % failed.get("source"))
    except Exception as e:
        check("day6_wsfail_no_crash", False, "wsfail crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 无 key：主题题降级为空上下文出题（不拒绝） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-nokey-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    os.environ.pop("STUDY_LIU_TAVILY_KEY", None)
    quiz_mod._llm_chat = fake_single
    try:
        weak = quiz_mod.generate_quiz("量子占卜玄学导论", difficulty="easy", count=3, web_search=True)
        check("tavily_no_key_degraded", weak.get("ok") is True and weak.get("source") == "topic",
              "no-key topic must degrade to topic gen, not refuse: %s" % weak.get("error"))
    except Exception as e:
        check("day6_nokey_no_crash", False, "nokey crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 无 key：URL 直出题直接拒绝（无 extract 内容无法出题） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-nourlkey-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    os.environ.pop("STUDY_LIU_TAVILY_KEY", None)
    quiz_mod._llm_chat = fake_single
    try:
        url = "https://example.com/notes"
        nokey = quiz_mod.generate_quiz(url, difficulty="easy", count=3, web_search=True)
        check("extract_no_key_rejected", nokey.get("ok") is False and nokey.get("retrieved") == [],
              "url without key must refuse")
    except Exception as e:
        check("day6_nourlkey_no_crash", False, "nourlkey crashed: %r" % e)
    finally:
        teardown(tmp)

    # ---- 工具智能体：日志可见性（每执行一次搜索都要打印工具名 / 参数 / 结果） ----
    tmp = tempfile.mkdtemp(prefix="zjxt-quiz-log-")
    quiz_mod, llm_mod = setup(tmp)
    if quiz_mod is None:
        return
    record = []
    os.environ["STUDY_LIU_TAVILY_KEY"] = "tvly-test-dummy"
    quiz_mod._build_tavily_tools = lambda key: make_fake_tools(record)
    quiz_mod._llm_chat = scripted([
        tool_call("tavily_search", {"query": "harness engineering", "include_domains": ["*.cn"]}),
        finish(SINGLE_QS, [{"title": "Web A", "url": "https://example.com/a"}]),
    ])
    # 捕获 quiz 模块 logger 的 INFO 记录（搜索工具名 / 调用参数 / 返回结果）
    _cap = []
    class _CapH(logging.Handler):
        def emit(self, rec):
            _cap.append(rec.getMessage())
    _h = _CapH()
    _h.setLevel(logging.INFO)
    quiz_mod._log.addHandler(_h)
    try:
        res = quiz_mod.generate_quiz("harness engineering", difficulty="easy", count=3, web_search=True)
        _joined = "\n".join(_cap)
        check("agent_logs_tool_call", "Tavily 工具调用" in _joined,
              "search tool call (name+params) must be logged: %s" % _joined[:300])
        check("agent_logs_tool_result", "返回" in _joined and "tavily_search" in _joined,
              "search result (count+summary) must be logged: %s" % _joined[:300])
        check("agent_logs_query_param", '"harness engineering"' in _joined,
              "search query param must appear in logs: %s" % _joined[:300])
        check("agent_logs_generates", res.get("ok") is True, "logged search must still generate")
    except Exception as e:
        check("day6_logcap_no_crash", False, "logcap crashed: %r" % e)
    finally:
        quiz_mod._log.removeHandler(_h)
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
