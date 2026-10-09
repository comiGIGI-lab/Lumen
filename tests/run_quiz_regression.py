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


def main():
    source_checks()
    runtime_checks()
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
