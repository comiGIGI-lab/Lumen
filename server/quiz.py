# -*- coding: utf-8 -*-
"""quiz.py — 选择题闯关：出题 / 校验 / 判分 / 落盘（纯标准库）。

复刻 yu-ai-learn 的「AI 出题 + 闯关答题」产品形态，落在现有零依赖后端上：
  1) 课程名按问答同一套 RAG 门槛检索知识库（RAG_MIN_SCORE/RAG_MIN_COVERAGE 不重调）；
  2) 弱命中直接拒绝出题——绝不拿模型常识编题，评委追问"出自哪份材料"要答得上来；
  3) 强命中注入 prompt，LLM 产出结构化单选 JSON，逐题严格校验，坏题丢弃；
  4) 标准答案只存在服务端（data/quiz_runs.json），generate 响应不带 answer；
  5) 判分走 grade_quiz：服务端对照答案回 correct/answer/explanation。

不做（见 openspec/changes/2026-10-09-course-quiz-challenge/proposal.md）：
FastAPI / LangChain / Chroma / MySQL / Tavily / 文生图 / 微信登录 / 异步轮询。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir
from core.agent_loop import RAG_MIN_SCORE, RAG_MIN_COVERAGE, RAG_TOP_K, RAG_PASSAGE_MAX

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DATA_DIR = _resolve_data_dir()
_RUNS_FILE = os.path.join(_DATA_DIR, "quiz_runs.json")

DIFFICULTIES = ("easy", "medium", "hard")
_COUNT_MIN, _COUNT_DEFAULT, _COUNT_MAX = 3, 5, 8
# 有效题数下限：LLM 可能丢题，低于这个数就整单报错，不出残局
MIN_VALID_QUESTIONS = 3
MAX_RUNS_KEPT = 200

_LOCK = threading.RLock()
_RUNS = None  # 进程内缓存 {quiz_id: run dict}

DIFFICULTY_HINT = {
    "easy": "简单：考查对资料中基本概念、定义的直接识别，干扰项与正确项区分度明显。",
    "medium": "中等：考查概念理解与简单应用，干扰项具有常见混淆性，需要理解才能区分。",
    "hard": "困难：考查综合运用与易错细节，干扰项高度相似，贴近真实考试的高区分度题。",
}

WEAK_HIT_ERROR = (
    "知识库中没有与该课程足够相关的材料，无法出题。"
    "请先在「文档导入」页上传该课程的讲义或笔记，再回来闯关。"
)


# ---------------------------------------------------------------------------
# 存取
# ---------------------------------------------------------------------------

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load():
    global _RUNS
    if _RUNS is not None:
        return _RUNS
    if not os.path.exists(_RUNS_FILE):
        _RUNS = {}
        return _RUNS
    try:
        with open(_RUNS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _RUNS = data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        _RUNS = {}
    return _RUNS


def _save():
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _RUNS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_RUNS, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _RUNS_FILE)


# ---------------------------------------------------------------------------
# LLM 封装（延迟 import，方便测试注入 _llm_chat）
# ---------------------------------------------------------------------------

def _llm_chat(messages):
    from core.llm import chat
    return chat(messages)


# ---------------------------------------------------------------------------
# 出题
# ---------------------------------------------------------------------------

def _retrieve(course):
    """按问答同一套门槛检索知识库。失败返回空（弱命中处理由调用方兜）。"""
    try:
        from tools.knowledge_store import KnowledgeStore
        store = KnowledgeStore()
        raw = store.retrieve(course, top_k=RAG_TOP_K * 2)
    except Exception:
        return []
    return [
        h for h in raw
        if h[1] >= RAG_MIN_SCORE and (h[2].get("coverage") or 0) >= RAG_MIN_COVERAGE
    ][:RAG_TOP_K]


def _kb_blocks(hits):
    """命中片段拼进出题 prompt（与 run_chat_pipeline 的注入格式一致）。"""
    blocks = []
    for i, (note, _score, _detail) in enumerate(hits, 1):
        body = (note.get("content") or "").strip()
        if len(body) > RAG_PASSAGE_MAX:
            body = body[:RAG_PASSAGE_MAX] + "…"
        blocks.append("【资料 %d】%s\n%s" % (i, note.get("title", ""), body))
    return "\n\n".join(blocks)


def _build_prompt(course, difficulty, count, kb):
    hint = DIFFICULTY_HINT.get(difficulty, DIFFICULTY_HINT["medium"])
    return (
        "你是严谨的出题老师。只能依据下方资料出题，不得使用资料之外的知识。\n\n"
        "课程：%s\n难度要求：%s\n\n"
        "请出 %d 道四选一的单项选择题，只输出一个 JSON 对象，不要输出其他文字：\n"
        '{"questions": [{"id": "q1", "stem": "题干", '
        '"options": [{"key": "A", "text": "选项"}, {"key": "B", "text": "选项"}, '
        '{"key": "C", "text": "选项"}, {"key": "D", "text": "选项"}], '
        '"answer": ["A"], "explanation": "解析", "knowledge_point": "知识点"}]}\n\n'
        "要求：answer 恰好 1 个且必须是选项 key 之一；四 个选项文本互不相同；"
        "题干、解析、知识点都用中文且非空。\n\n"
        "出题依据的资料：\n%s" % (course, hint, count, kb)
    )


def _valid_question(q, seen_ids):
    """单题校验：形状不对直接判废（返回 None），不让半截题进局。"""
    if not isinstance(q, dict):
        return None
    stem = str(q.get("stem") or "").strip()
    if not stem:
        return None
    options = q.get("options")
    if not isinstance(options, list) or len(options) != 4:
        return None
    cleaned = []
    keys = []
    for o in options:
        if not isinstance(o, dict):
            return None
        key = str(o.get("key") or "").strip().upper()
        text = str(o.get("text") or "").strip()
        if not key or not text or key in keys:
            return None
        keys.append(key)
        cleaned.append({"key": key, "text": text})
    answer = q.get("answer")
    if isinstance(answer, str):
        answer = [answer]
    if not isinstance(answer, list) or len(answer) != 1:
        return None
    ans = str(answer[0] or "").strip().upper()
    if ans not in keys:
        return None
    explanation = str(q.get("explanation") or "").strip()
    if not explanation:
        return None
    kp = str(q.get("knowledge_point") or "").strip()
    if not kp:
        return None
    # 选项文本两两互不相同（大小写归一后比较，防"Aabc/ aabc"式敷衍）
    texts = [o["text"].strip().lower() for o in cleaned]
    if len(set(texts)) != 4:
        return None
    qid = str(q.get("id") or "").strip()
    if not qid or qid in seen_ids:
        qid = ""
    return {
        "id": qid, "stem": stem, "options": cleaned,
        "answer": [ans], "explanation": explanation, "knowledge_point": kp,
    }


def _parse_llm_questions(raw):
    """从 LLM 输出抽数组并校验。返回 (questions, bad_count)。"""
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return [], 0
    try:
        data = json.loads(m.group(0))
    except Exception:
        return [], 0
    items = None
    if isinstance(data, dict):
        for k in ("questions", "items", "data", "list"):
            if isinstance(data.get(k), list):
                items = data[k]
                break
    elif isinstance(data, list):
        items = data
    if not items:
        return [], 0
    out = []
    bad = 0
    for it in items:
        v = _valid_question(it, {q["id"] for q in out})
        if v:
            out.append(v)
        else:
            bad += 1
    # 统一重编号 q1..qN，answer 保留在服务端条目里
    for i, q in enumerate(out, 1):
        q["id"] = "q%d" % i
    return out, bad


def generate_quiz(course, difficulty="medium", count=_COUNT_DEFAULT, client_id=""):
    """出题入口。返回 dict（HTTP 层直接回 JSON）。

    弱命中 / LLM 输出不可用 → {"ok": false, "error": ..., "retrieved": []}，
    不出兜底假题。
    """
    course = str(course or "").strip()
    difficulty = str(difficulty or "medium").strip().lower()
    if difficulty not in DIFFICULTIES:
        difficulty = "medium"
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = _COUNT_DEFAULT
    count = max(_COUNT_MIN, min(_COUNT_MAX, count))
    if not course:
        return {"ok": False, "error": "请先输入课程名", "retrieved": []}

    hits = _retrieve(course)
    if not hits:
        return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
    citations = [
        {"id": n.get("id"), "title": n.get("title", ""), "score": round(s, 2)}
        for n, s, _ in hits
    ]

    prompt = _build_prompt(course, difficulty, count, _kb_blocks(hits))
    raw = ""
    try:
        raw = _llm_chat([{"role": "user", "content": prompt}])
    except Exception as e:
        return {"ok": False, "error": "出题失败（模型调用异常：%s）" % e, "retrieved": citations}
    if not isinstance(raw, str) or raw.startswith("[LLM 不可用]"):
        return {"ok": False, "error": "大模型不可用，无法出题。请检查 AI 模型设置。", "retrieved": citations}

    questions, _bad = _parse_llm_questions(raw)
    if len(questions) < MIN_VALID_QUESTIONS:
        return {"ok": False, "error": "本次生成的题目未通过格式校验，请重试。", "retrieved": citations}

    quiz_id = "z-%d-%s" % (
        int(datetime.now().strftime("%H%M%S")) + os.getpid() % 1000,
        os.urandom(3).hex(),
    )
    run = {
        "quiz_id": quiz_id,
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "client_id": str(client_id or "")[:64],
        "created_at": _now(),
        # 完整题目（含 answer）只在服务端；对外负载由 grade 与调用方另行裁剪
        "questions": questions,
        "answers": {},
    }
    with _LOCK:
        runs = _load()
        runs[quiz_id] = run
        # 只留最近 MAX_RUNS_KEPT 局，防止 JSON 无限膨胀
        if len(runs) > MAX_RUNS_KEPT:
            ordered = sorted(
                runs.items(),
                key=lambda kv: kv[1].get("created_at") or "",
            )
            for k, _v in ordered[: len(runs) - MAX_RUNS_KEPT]:
                del runs[k]
        _save()

    payload_questions = [
        {
            "id": q["id"], "stem": q["stem"], "options": q["options"],
            "explanation": q["explanation"], "knowledge_point": q["knowledge_point"],
        }
        for q in questions
    ]
    return {
        "ok": True,
        "quiz_id": quiz_id,
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "questions": payload_questions,
        "retrieved": citations,
    }


# ---------------------------------------------------------------------------
# 判分
# ---------------------------------------------------------------------------

def grade_quiz(quiz_id, question_id, selected):
    """判分入口。quiz_id/question_id 不存在抛 KeyError（HTTP 层转 404）。"""
    with _LOCK:
        runs = _load()
        run = runs.get(quiz_id)
        if not run:
            raise KeyError("quiz_not_found")
        q = next((x for x in run["questions"] if x.get("id") == question_id), None)
        if not q:
            raise KeyError("question_not_found")
        correct = str(selected or "").strip().upper() == q["answer"][0]
        run.setdefault("answers", {})[question_id] = {
            "selected": str(selected or "").strip().upper(),
            "correct": correct,
            "answered_at": _now(),
        }
        _save()
    return {
        "ok": True,
        "question_id": question_id,
        "selected": str(selected or "").strip().upper(),
        "correct": correct,
        "answer": q["answer"],
        "explanation": q["explanation"],
        "knowledge_point": q["knowledge_point"],
    }
