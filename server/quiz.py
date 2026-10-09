# -*- coding: utf-8 -*-
"""quiz.py — 选择题闯关：出题 / 校验 / 判分 / 复盘 / 落盘（纯标准库）。

复刻 yu-ai-learn 的「AI 出题 + 闯关答题」产品形态，落在现有零依赖后端上：
  1) 课程名按问答同一套 RAG 门槛检索知识库（RAG_MIN_SCORE/RAG_MIN_COVERAGE 不重调）；
  2) 联网搜索开关（web_search，默认开）：开启且配置了 STUDY_LIU_TAVILY_KEY 时走 Tavily
      search 取联网资料（标题+摘要，限长）作参考；关闭 / 无 key / 失败 / 超时均降级为空
      上下文（记 warning 日志），不拒绝，直接带主题走出题。
  2') 课程名以 http(s):// 开头视作「丢链接出题」：不经知识库，走 Tavily extract 抓取正文
      （截断 8000 字符）；无 key / 失败 / 超时回退 WEAK_HIT_ERROR（无 URL 内容无法出题）。
  3) 知识库为可选增强（与问答同 RAG 门槛），强命中注入 prompt；空上下文时 LLM 基于自身
      通用知识出题（不杜撰）。
      topic 题（非 URL）永不直接拒绝：搜索上下文为空也走出题，source 标 "topic"。
  4) 标准答案只存在服务端（data/quiz_runs.json），generate 响应不带 answer；
  5) 判分走 grade_quiz：服务端对照答案回 correct/answer/explanation；
  6) 复盘走 quiz_report：纯聚合 quiz_runs.json，无新状态文件。

不做（见 openspec/changes/2026-10-09-course-quiz-challenge/proposal.md）：
FastAPI / LangChain / Chroma / MySQL / 文生图 / 微信登录 / 异步轮询。
Tavily 仅以「可选联网搜索」形式存在（由联网搜索开关控制）：依赖环境变量注入的 key，不进仓库、不落盘。
"""

from __future__ import annotations

import json
import os
import re
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir
from core.agent_loop import RAG_MIN_SCORE, RAG_MIN_COVERAGE, RAG_TOP_K, RAG_PASSAGE_MAX

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DATA_DIR = _resolve_data_dir()
_RUNS_FILE = os.path.join(_DATA_DIR, "quiz_runs.json")

DIFFICULTIES = ("easy", "medium", "hard")
Q_TYPES = ("single", "multi", "judge")
_COUNT_MIN, _COUNT_DEFAULT, _COUNT_MAX = 3, 5, 8
# 有效题数下限：LLM 可能丢题，低于这个数就整单报错，不出残局
MIN_VALID_QUESTIONS = 3
MAX_RUNS_KEPT = 200

# Tavily 联网兜底：key 只从环境变量注入，绝不入库 / 不落盘
TAVILY_KEY_ENV = "STUDY_LIU_TAVILY_KEY"
TAVILY_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
TAVILY_TIMEOUT = 8
TAVILY_MAX_RESULTS = 3
TAVILY_SNIPPET_MAX = 500  # 单条联网资料的摘要限长（标题+摘要，控 prompt 体积）

# mixed 配比 single:multi:judge = 2:1:1（count=8 → 4+2+2）
MIXED_RATIO = {"single": 2, "multi": 1, "judge": 1}

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
# 检索 / 联网兜底
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


def _tavily_search(query, api_key, max_results=TAVILY_MAX_RESULTS, timeout=TAVILY_TIMEOUT):
    """联网检索兜底（纯标准库 urllib）。失败抛异常，由调用方回退。

    返回 [{title, url, content}]，最多 max_results 条。
    """
    body = json.dumps(
        {"api_key": api_key, "query": query, "max_results": max_results}
    ).encode("utf-8")
    req = urllib.request.Request(
        TAVILY_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = data.get("results") or []
    out = []
    for r in results[:max_results]:
        out.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "content": (r.get("content") or "").strip(),
        })
    return out


def _tavily_extract(url, api_key, timeout=TAVILY_TIMEOUT):
    """URL 直出题：抓取正文（纯标准库 urllib）。失败抛异常，由调用方回退。

    返回 results[0].raw_content 字符串；无结果返回 ""。
    """
    body = json.dumps(
        {"api_key": api_key, "urls": [url]}
    ).encode("utf-8")
    req = urllib.request.Request(
        TAVILY_EXTRACT_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = data.get("results") or []
    if not results:
        return ""
    first = results[0] or {}
    return (first.get("raw_content") or "").strip()


def _web_blocks(web):
    blocks = []
    for i, w in enumerate(web, 1):
        content = (w.get("content") or "").strip()
        if len(content) > TAVILY_SNIPPET_MAX:
            content = content[:TAVILY_SNIPPET_MAX] + "…"
        blocks.append("【联网资料 %d】%s\n%s\n%s" % (
            i, w.get("title", ""), w.get("url", ""), content))
    return "\n\n".join(blocks)


def _web_search_context(course, enable):
    """联网搜索上下文（受「联网搜索开关」控制）。

    enable=False / 无 key / 失败或超时 → 返回 ("", [])（降级，不拒绝，记 warning 日志）。
    成功 → 返回 (格式化正文, [{title, url}])。
    """
    if not enable:
        return "", []
    key = os.environ.get(TAVILY_KEY_ENV)
    if not key:
        return "", []
    try:
        web = _tavily_search(course, key)
    except Exception as e:
        logging.warning("Tavily 搜索失败，降级为空上下文: %s", e)
        return "", []
    if not web:
        return "", []
    return _web_blocks(web), [{"title": w["title"], "url": w["url"]} for w in web]


# ---------------------------------------------------------------------------
# 题型分布
# ---------------------------------------------------------------------------

def _distribute_mixed(count):
    """mixed：按 2:1:1 拆 single/multi/judge，余数补到 single。"""
    keys = ("single", "multi", "judge")
    ratio = [MIXED_RATIO[k] for k in keys]
    total = sum(ratio)
    raw = [count * r // total for r in ratio]
    rem = count - sum(raw)
    raw[0] += rem
    return dict(zip(keys, raw))


def _resolve_plan(types, count):
    """把 types 参数归一成 {single, multi, judge} 的题数计划。

    - None / "single" / ["single"]            → 全单选
    - "mixed" / ["mixed"]                     → 2:1:1 配比
    - 单类型字符串 "multi" / "judge"          → 全该类
    - 多类型列表 ["single","multi","judge"]    → 按列数均分（余数给首个）
    """
    if types in (None, "", "single", ["single"]):
        return {"single": count, "multi": 0, "judge": 0}
    if types == "mixed" or types == ["mixed"]:
        return _distribute_mixed(count)
    if isinstance(types, str):
        t = types.strip().lower()
        if t in Q_TYPES:
            return {"single": count if t == "single" else 0,
                    "multi": count if t == "multi" else 0,
                    "judge": count if t == "judge" else 0}
        return {"single": count, "multi": 0, "judge": 0}
    if isinstance(types, (list, tuple)):
        ts = [str(x).strip().lower() for x in types if str(x).strip().lower() in Q_TYPES]
        if not ts:
            return {"single": count, "multi": 0, "judge": 0}
        if len(ts) == 1:
            t = ts[0]
            return {"single": count if t == "single" else 0,
                    "multi": count if t == "multi" else 0,
                    "judge": count if t == "judge" else 0}
        n = len(ts)
        base = count // n
        plan = {"single": 0, "multi": 0, "judge": 0}
        rem = count - base * n
        for i, t in enumerate(ts):
            plan[t] += base + (1 if i < rem else 0)
        return plan
    return {"single": count, "multi": 0, "judge": 0}


# ---------------------------------------------------------------------------
# 出题 prompt
# ---------------------------------------------------------------------------

def _build_prompt(course, difficulty, plan, kb):
    hint = DIFFICULTY_HINT.get(difficulty, DIFFICULTY_HINT["medium"])
    parts = []
    if plan.get("single"):
        parts.append(
            "%d 道单选题（四选一，answer 为 1 个选项 key 的数组，如 [\"A\"]）" % plan["single"])
    if plan.get("multi"):
        parts.append(
            "%d 道多选题（4-5 个选项，answer 为正确选项 key 的数组，如 [\"A\",\"C\"]，"
            "至少 2 个正确）" % plan["multi"])
    if plan.get("judge"):
        parts.append(
            "%d 道判断题（选项固定为 [{\"key\":\"0\",\"text\":\"正确\"},"
            "{\"key\":\"1\",\"text\":\"错误\"}]，answer 为整数 0 或 1）" % plan["judge"])
    spec = "；".join(parts) if parts else "3 道单选题"
    if kb and kb.strip():
        material_rule = "只能依据下方资料出题，不得使用资料之外的知识。"
    else:
        material_rule = ("下方暂无参考资料，请基于你对该主题的可靠通用知识严谨出题，"
                        "确保事实准确、不杜撰。")
    return (
        "你是严谨的出题老师。%s\n\n"
        "课程：%s\n难度要求：%s\n\n"
        "请出：%s。只输出一个 JSON 对象，不要输出其他文字：\n"
        '{"questions": [{"type": "single", "stem": "题干", '
        '"options": [{"key": "A", "text": "选项"}, {"key": "B", "text": "选项"}, '
        '{"key": "C", "text": "选项"}, {"key": "D", "text": "选项"}], '
        '"answer": ["A"], "explanation": "解析", "knowledge_point": "知识点"}]}\n\n'
        "要求：每题必须带 type 字段（single/multi/judge）；选项文本两两不同；"
        "题干、解析、知识点都用中文且非空。\n\n"
        "出题依据的资料：\n%s" % (material_rule, course, hint, spec, kb)
    )


# ---------------------------------------------------------------------------
# 单题校验
# ---------------------------------------------------------------------------

def _norm_answer_single(answer, keys):
    if isinstance(answer, str):
        answer = [answer]
    if not isinstance(answer, list) or len(answer) != 1:
        return None
    a = str(answer[0]).strip().upper()
    return [a] if a in keys else None


def _norm_answer_multi(answer, keys):
    if isinstance(answer, str):
        answer = [x for x in answer.split(",")]
    if not isinstance(answer, list) or len(answer) < 2:
        return None
    a = [str(x).strip().upper() for x in answer if str(x).strip() != ""]
    if len(a) < 2 or any(x not in keys for x in a):
        return None
    return sorted(a)


def _norm_answer_judge(answer):
    if isinstance(answer, list):
        answer = answer[0] if answer else None
    try:
        a = int(answer)
    except (TypeError, ValueError):
        try:
            a = int(str(answer).strip())
        except (TypeError, ValueError):
            return None
    return a if a in (0, 1) else None


def _valid_question(q, seen_ids):
    """单题校验：形状不对直接判废（返回 None），不让半截题进局。"""
    if not isinstance(q, dict):
        return None
    qtype = str(q.get("type") or "single").strip().lower()
    if qtype not in Q_TYPES:
        qtype = "single"
    stem = str(q.get("stem") or "").strip()
    if not stem:
        return None
    options = q.get("options")
    if not isinstance(options, list) or len(options) < 2:
        return None
    cleaned = []
    keys = []
    for o in options:
        if not isinstance(o, dict):
            return None
        key = str(o.get("key") or "").strip()
        text = str(o.get("text") or "").strip()
        if not key or not text or key in keys:
            return None
        keys.append(key)
        cleaned.append({"key": key, "text": text})
    explanation = str(q.get("explanation") or "").strip()
    if not explanation:
        return None
    kp = str(q.get("knowledge_point") or "").strip()
    if not kp:
        return None
    # 选项文本两两互不相同（大小写归一后比较，防"Aabc/ aabc"式敷衍）
    texts = [o["text"].strip().lower() for o in cleaned]
    if len(set(texts)) != len(texts):
        return None

    # 题型专属校验
    if qtype == "single":
        if len(cleaned) != 4:
            return None
        ans = _norm_answer_single(q.get("answer"), keys)
    elif qtype == "multi":
        if not (4 <= len(cleaned) <= 5):
            return None
        ans = _norm_answer_multi(q.get("answer"), keys)
    else:  # judge
        if len(cleaned) != 2:
            return None
        ans = _norm_answer_judge(q.get("answer"))
    if ans is None:
        return None

    qid = str(q.get("id") or "").strip()
    if not qid or qid in seen_ids:
        qid = ""
    return {
        "id": qid, "type": qtype, "stem": stem, "options": cleaned,
        "answer": ans, "explanation": explanation, "knowledge_point": kp,
        "source": "kb", "sources": [],
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


# ---------------------------------------------------------------------------
# 出题
# ---------------------------------------------------------------------------

def generate_quiz(course, difficulty="medium", count=_COUNT_DEFAULT, types=None, client_id="", web_search=True):
    """出题入口。返回 dict（HTTP 层直接回 JSON）。

    流程：判断「联网搜索开关」web_search →
      - 关：搜索上下文为空，直接走出题；
      - 开且配 key：调 Tavily search（超时+条数上限），成功则格式化作参考，
        失败/超时记 warning 并降级为空上下文；
    主题题（非 URL）永不直接拒绝，空上下文也走出题（source 标 "topic"）；
    URL 题（丢链接出题）需要 extract，无 key/失败/超时回退 WEAK_HIT_ERROR。
    LLM 输出不可用 → 不出兜底假题。
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

    plan = _resolve_plan(types, count)

    # URL 直出题（「丢链接出题」）：需要 extract 抓取正文，无 key/失败/超时 → 拒绝（无 URL 内容无法出题）
    if re.match(r"https?://", course, re.I):
        key = os.environ.get(TAVILY_KEY_ENV)
        if not key:
            return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
        try:
            raw_doc = _tavily_extract(course, key)
        except Exception as e:
            logging.warning("Tavily extract 失败，拒绝出题: %s", e)
            return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
        if not raw_doc:
            return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
        ctx = "【在线文档】\n%s\n%s" % (course, raw_doc[:8000])
        citations = [{"title": course, "url": course}]
        src_kind = "web"
        src_list = [{"title": course, "url": course}]
    else:
        # 私有知识库：可选增强（非硬性门槛），强命中时作为参考资料
        hits = _retrieve(course)
        kb_ctx = _kb_blocks(hits) if hits else ""
        kb_citations = [
            {"id": n.get("id"), "title": n.get("title", ""), "score": round(s, 2)}
            for n, s, _ in hits
        ]
        # 联网搜索（开关 + 降级）：关闭 / 无 key / 失败都降级为空上下文，不拒绝
        web_ctx, web_sources = _web_search_context(course, bool(web_search))
        parts = [p for p in (kb_ctx, web_ctx) if p]
        ctx = "\n\n".join(parts)
        citations = kb_citations + web_sources
        if web_sources:
            src_kind = "web"
        elif hits:
            src_kind = "kb"
        else:
            src_kind = "topic"
        src_list = web_sources

    prompt = _build_prompt(course, difficulty, plan, ctx)
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

    # 统一标来源（topic / kb / web）与来源清单
    for q in questions:
        q["source"] = src_kind
        q["sources"] = src_list

    quiz_id = "z-%d-%s" % (
        int(datetime.now().strftime("%H%M%S")) + os.getpid() % 1000,
        os.urandom(3).hex(),
    )
    ts = _now()
    run = {
        "quiz_id": quiz_id,
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "types": plan,
        "source": src_kind,
        "client_id": str(client_id or "")[:64],
        "created_at": ts,
        "started_at": ts,
        # 完整题目（含 answer）只在服务端；对外负载由 grade/report 与调用方另行裁剪
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
            "id": q["id"], "type": q["type"], "stem": q["stem"], "options": q["options"],
            "explanation": q["explanation"], "knowledge_point": q["knowledge_point"],
            "source": q["source"], "sources": q["sources"],
        }
        for q in questions
    ]
    return {
        "ok": True,
        "quiz_id": quiz_id,
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "types": plan,
        "source": src_kind,
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
        qtype = q.get("type", "single")
        if qtype == "multi":
            sel = selected if isinstance(selected, list) else [selected]
            sel = [str(x).strip().upper() for x in sel if str(x).strip() != ""]
            correct = sorted(sel) == sorted(str(x).upper() for x in q["answer"])
        elif qtype == "judge":
            try:
                correct = int(selected) == int(q["answer"])
            except (TypeError, ValueError):
                correct = False
        else:
            correct = str(selected).strip().upper() == str(q["answer"][0]).upper()
        run.setdefault("answers", {})[question_id] = {
            "selected": selected,
            "correct": correct,
            "answered_at": _now(),
        }
        _save()
    return {
        "ok": True,
        "question_id": question_id,
        "type": qtype,
        "selected": selected,
        "correct": correct,
        "answer": q["answer"],
        "explanation": q["explanation"],
        "knowledge_point": q["knowledge_point"],
        "source": q.get("source", "kb"),
        "sources": q.get("sources", []),
    }


# ---------------------------------------------------------------------------
# 复盘
# ---------------------------------------------------------------------------

def quiz_report(run_id):
    """复盘聚合：纯读 quiz_runs.json，不写新状态文件。

    quiz_id 不存在抛 KeyError（HTTP 层转 404）。
    """
    with _LOCK:
        runs = _load()
        run = runs.get(run_id)
        if not run:
            raise KeyError("quiz_not_found")
        questions = run.get("questions") or []
        answers = run.get("answers") or {}
        started = run.get("started_at") or run.get("created_at")

        total = len(questions)
        correct = 0
        items = []
        weak = {}
        for q in questions:
            a = answers.get(q["id"])
            is_correct = bool(a.get("correct")) if a else False
            if is_correct:
                correct += 1
            else:
                kp = q.get("knowledge_point", "")
                weak[kp] = weak.get(kp, 0) + 1
            items.append({
                "id": q["id"],
                "type": q.get("type", "single"),
                "stem": q["stem"],
                "options": q["options"],
                "user_answer": a.get("selected") if a else None,
                "correct_answer": q["answer"],
                "correct": is_correct,
                "answered_at": a.get("answered_at") if a else None,
                "explanation": q["explanation"],
                "knowledge_point": q["knowledge_point"],
                "source": q.get("source", "kb"),
                "sources": q.get("sources", []),
            })

        duration_s = None
        if started:
            try:
                st = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
                end = datetime.now()
                lasts = [a.get("answered_at") for a in answers.values() if a.get("answered_at")]
                if lasts:
                    end = max(datetime.strptime(x, "%Y-%m-%d %H:%M:%S") for x in lasts)
                duration_s = int((end - st).total_seconds())
            except Exception:
                duration_s = None

        accuracy = (correct / total) if total else 0
        weak_points = sorted(weak.items(), key=lambda kv: -kv[1])[:3]
        weak_points = [{"knowledge_point": k, "wrong": v} for k, v in weak_points]
        materials = [c.get("title", "") for c in (run.get("retrieved") or [])]

    return {
        "ok": True,
        "quiz_id": run_id,
        "course": run.get("course", ""),
        "difficulty": run.get("difficulty", ""),
        "types": run.get("types", {}),
        "source": run.get("source", "kb"),
        "score": correct,
        "total": total,
        "accuracy": round(accuracy, 4),
        "duration_s": duration_s,
        "questions": items,
        "weak_points": weak_points,
        "materials": materials,
    }
