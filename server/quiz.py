# -*- coding: utf-8 -*-
"""quiz.py — 选择题闯关：出题 / 校验 / 判分 / 复盘 / 落盘。

复刻 yu-ai-learn 的「AI 出题 + 闯关答题」产品形态：
  1) 课程名按问答同一套 RAG 门槛检索知识库（RAG_MIN_SCORE/RAG_MIN_COVERAGE 不重调）；
  2) 联网出题走「Tavily 工具智能体」：实例化 tavily_search / tavily_search_deep /
      tavily_extract / tavily_extract_deep 四个工具，交给现有出题 LLM（core.llm.chat，
      纯文本返回）以自写 tool-call 循环驱动（不引 langgraph、不改 core.llm）。
      - 联网搜索开关（web_search，默认开）：关 / 无 key / 失败 / 超时均降级为空上下文
        （记 warning 日志），不拒绝，直接带主题走出题。
      - 用户给 URL → 用 extract；给主题 → 用 search；模型按复杂度自选自浅/深实例，
        可动态设 search_depth/time_range/include_domains；国内用户默认含中文域。
  2') 课程名以 http(s):// 开头视作「丢链接出题」：不经知识库，走 tavily_extract 抓取正文；
      无 key / 工具失败回退 WEAK_HIT_ERROR（无 URL 内容无法出题）。
  3) 知识库为可选增强（与问答同 RAG 门槛），强命中注入 prompt；空上下文时 LLM 基于自身
      通用知识出题（不杜撰）。topic 题（非 URL）永不直接拒绝：搜索上下文为空也走出题，
      source 标 "topic"。
  4) 标准答案只存在服务端（data/quiz_runs.json），generate 响应不带 answer；
  5) 判分走 grade_quiz：服务端对照答案回 correct/answer/explanation；
  6) 复盘走 quiz_report：纯聚合 quiz_runs.json，无新状态文件。

依赖约束（见 openspec/changes/2026-10-09-course-quiz-challenge/spec.md）：
  后端其余部分仍为标准库零依赖；仅「quiz 出题链路」经队长批准放宽零依赖约束，引入
  langchain-tavily（仅用于把 Tavily 封装成工具，供工具智能体调用）。Tavily key 只从
  环境变量 STUDY_LIU_TAVILY_KEY 注入（api_server 装配时映射到 TAVILY_API_KEY），
  不进仓库、不落盘。langchain_tavily 在 _build_tavily_tools 内延迟 import，未安装时
  不影响模块导入，仅联网出题真正调用时才需要。
"""

from __future__ import annotations

import json
import os
import re
import logging
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
Q_TYPES = ("single", "multi", "judge")
_COUNT_MIN, _COUNT_DEFAULT, _COUNT_MAX = 3, 5, 8
# 有效题数下限：LLM 可能丢题，低于这个数就整单报错，不出残局
MIN_VALID_QUESTIONS = 3
MAX_RUNS_KEPT = 200

# Tavily 联网出题：key 只从环境变量注入，绝不入库 / 不落盘
TAVILY_KEY_ENV = "STUDY_LIU_TAVILY_KEY"
# 工具智能体最多对话轮数（避免模型空转；多关键词变体检索需要更多轮）
MAX_AGENT_STEPS = 8
# 国内用户默认限定的中文域（浅层检索也带上，提升中文资料召回）
DOMESTIC_INCLUDE_DOMAINS = ["*.cn", "*.edu.cn", "*.gov.cn", "*.com.cn", "*.org.cn"]
# 检索条数下限（search 至少 10、deep 至少 15，结果少时便于「以多数为准」判断领域）
TAVILY_SEARCH_MAX = 10
TAVILY_SEARCH_DEEP_MAX = 15

# 联网出题需要 INFO 级日志（默认 root 仅 WARNING，会吞掉搜索过程）。
# 给 quiz 模块挂独立 stderr handler，确保「搜索工具名 / 参数 / 结果」全程可见。
_log = logging.getLogger("quiz")
if not _log.handlers:
    _lh = logging.StreamHandler()
    _lh.setLevel(logging.INFO)
    _lh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _log.addHandler(_lh)
    _log.setLevel(logging.INFO)
    _log.propagate = False

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


# 指定了章节但知识库一条都对不上时的固定报错。不要静默退回全课程：
# 用户明确收窄了范围，退回全量会让他以为在练所选章节。
NO_TOPIC_MATCH_ERROR = "所选章节在知识库中没有对应材料，请先导入该章节的资料或改选范围。"

# 闯关勾选「加入错题」时，由 api_server 注入的取数回调。quiz 不 import 存储层，
# 归属桶的判断留在 api_server。签名 (course) -> [{course, question, answer, reason, qtype}]。
_wrongbook_provider = None


def set_wrongbook_provider(fn):
    """注入错题取数回调。传 None 即关闭（回归测试用）。"""
    global _wrongbook_provider
    _wrongbook_provider = fn


def _hit_matches_topic(hit, topics):
    """知识库命中是否命中任一限定章节（标题或正文含章节关键词即算）。"""
    note = hit[0] if isinstance(hit, (tuple, list)) else hit
    if not isinstance(note, dict):
        return False
    text = "%s\n%s" % (note.get("title", "") or "", note.get("content", "") or "")
    return any(str(t) in text for t in topics)


# ---------------------------------------------------------------------------
# 联网出题工具智能体（langchain-tavily）
# ---------------------------------------------------------------------------
# 队长批准放宽「零依赖」约束：仅 quiz 出题链路引入 langchain-tavily，用于把 Tavily 的
# search/extract 封装成工具，交给现有出题 LLM（core.llm.chat，纯文本返回）以「自写
# tool-call 循环」驱动（不引 langgraph、不改 core.llm）。key 只从环境变量注入。
# langchain_tavily 在 _build_tavily_tools 内延迟 import，未安装不影响模块导入。

# 工具调用 / 收尾的约定格式（模型按此输出，循环解析）
_TOOL_RE = re.compile(r"<tool>\s*(\{[\s\S]*?\})\s*</tool>", re.S)
_FINISH_RE = re.compile(r"<finish>\s*(\{[\s\S]*?\})\s*</finish>", re.S)


def _build_tavily_tools(api_key):
    """构造 4 个 Tavily 工具（延迟 import，便于无依赖时跳过 / 测试注入）。

    - tavily_search：浅层检索，至少 10 条，不含原文；
    - tavily_search_deep：深层检索，至少 15 条，含原文（raw_content）；
    - tavily_extract：浅层抓单页正文；
    - tavily_extract_deep：深层抓单页正文。
    返回 {工具名: BaseTool}。结果条数已显著上调，避免少数结果误导领域判断。
    """
    from langchain_tavily import TavilySearch, TavilyExtract
    return {
        "tavily_search": TavilySearch(
            tavily_api_key=api_key, search_depth="basic",
            max_results=TAVILY_SEARCH_MAX, include_raw_content=False,
        ),
        "tavily_search_deep": TavilySearch(
            tavily_api_key=api_key, search_depth="advanced",
            max_results=TAVILY_SEARCH_DEEP_MAX, include_raw_content=True,
        ),
        "tavily_extract": TavilyExtract(tavily_api_key=api_key, extract_depth="basic"),
        "tavily_extract_deep": TavilyExtract(tavily_api_key=api_key, extract_depth="advanced"),
    }


def _tavily_result_text(out, name, cap=16000):
    """把工具返回整理成紧凑可读文本（每条结果给标题+链接+摘要），便于模型看到
    全部结果并据「多数领域」判断；同时适合直接打印日志。"""
    if isinstance(out, dict) and isinstance(out.get("results"), list):
        is_search = "search" in name
        snip = 500 if is_search else 1500
        parts = []
        for i, r in enumerate(out["results"], 1):
            title = r.get("title") or r.get("url") or "(无标题)"
            url = r.get("url") or ""
            if is_search:
                body = r.get("content") or r.get("raw_content") or ""
            else:
                body = r.get("raw_content") or r.get("content") or ""
            body = (body or "").strip()
            if len(body) > snip:
                body = body[:snip] + "…"
            parts.append("【结果 %d】%s\n链接：%s\n%s" % (i, title, url, body))
        return "\n\n".join(parts)[:cap]
    return str(out)[:cap]


def _exec_tavily_tool(tools, name, args, collected):
    """执行一次工具调用，返回给模型的字符串结果；失败记 warning 并降级提示。

    collected：收集到的 sources（extract 时按 url 记录，供收尾兜底）。
    全程 INFO 日志：工具名、调用参数、返回结果条数与摘要（调试可见）。
    """
    tool = tools.get(name)
    if tool is None:
        _log.warning("Tavily 未知工具：%s（可用：tavily_search / tavily_search_deep / "
                     "tavily_extract / tavily_extract_deep）", name)
        return ("未知工具：%s（可用：tavily_search / tavily_search_deep / "
                "tavily_extract / tavily_extract_deep）" % name)
    # 只转发工具 schema 允许的字段，避免把模型臆造的参数喂给 pydantic
    allowed = set(getattr(tool, "args", {}) or {})
    clean = {k: v for k, v in (args or {}).items() if k in allowed}
    _log.info("Tavily 工具调用 → %s | 参数：%s", name, json.dumps(clean, ensure_ascii=False))
    try:
        out = tool.invoke(clean)
    except Exception as e:
        _log.warning("Tavily 工具 %s 调用失败，降级: %s", name, e)
        return "工具调用失败：%s（可改用浅层检索，或基于通用知识出题）" % e
    if name.startswith("tavily_extract"):
        for u in (clean.get("urls") or []):
            collected.append({"title": u, "url": u})
    text = _tavily_result_text(out, name)
    n = len(out.get("results", [])) if isinstance(out, dict) else 0
    _log.info("Tavily 工具 %s 返回 %d 条结果：\n%s", name, n, text[:4000])
    return text


def _parse_tool_call(raw):
    """解析 <tool>{...}</tool> 或裸 JSON {"tool":..,"args":..}，返回 (name, args) 或 None。"""
    m = _TOOL_RE.search(raw or "")
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and obj.get("name"):
                return obj["name"], obj.get("args") or {}
        except Exception:
            pass
    try:
        obj = json.loads((raw or "").strip())
        if isinstance(obj, dict) and obj.get("tool"):
            return obj["tool"], obj.get("args") or {}
    except Exception:
        pass
    return None


def _parse_finish(raw):
    """解析 <finish>{...}</finish>，返回 dict（含 questions / sources），否则 None。"""
    m = _FINISH_RE.search(raw or "")
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    try:
        obj = json.loads((raw or "").strip())
        if isinstance(obj, dict) and isinstance(obj.get("questions"), list):
            return obj
    except Exception:
        pass
    return None


def _norm_sources(srcs):
    out = []
    if not isinstance(srcs, list):
        return out
    for s in srcs:
        if isinstance(s, dict) and s.get("url"):
            out.append({"title": str(s.get("title") or s.get("url")), "url": str(s["url"])})
    return out


_TOOL_SYSTEM = """你是严谨的 AI 出题老师。你需要借助 Tavily 联网工具，为「课程主题」或「文档链接」生成选择题。

可用工具（由系统注入）：
- tavily_search：浅层检索，返回至少 10 条结果（标题+摘要，不含原文）。适合概念明确、资料量足够的主题。
- tavily_search_deep：深层检索，返回至少 15 条结果并含原文（raw_content）。适合复杂主题或需要权威出处。
- tavily_extract：浅层抓取单个网页正文。
- tavily_extract_deep：深层抓取单个网页正文（更完整）。

调用决策：
- 用户输入是 URL（以 http:// 或 https:// 开头）→ 用 tavily_extract 或 tavily_extract_deep，参数 urls=[该URL]。
- 用户输入是主题/课程名 → 用 tavily_search 或 tavily_search_deep，参数 query=用户输入的主题。
- 按复杂度自选自浅/深实例；需要时可动态覆盖 search_depth / time_range / include_domains。
- 国内用户默认 include_domains 含中文域（如 "*.cn"、"*.edu.cn"、"*.gov.cn"、"*.com.cn"），除非主题明显偏国际。

多关键词检索（重要）：
- 对专业、多义或易混淆的术语（例如 "harness engineering" 可能指汽车约束系统、软件测试框架、航空/汽车线束等），不要只搜一次。
- 必须用多个关键词变体分别检索，覆盖不同可能的含义，例如："harness engineering automotive"、
  "harness engineering software testing"、"harness system design"、"线束工程"、"约束系统 harness" 等。
- 单次检索结果很少（如仅 1~2 条）时，不要急于下结论；换更宽泛或更具体的关键词变体再搜，直到拿到足量结果。

领域判定（以多数为准）：
- 综合所有检索结果判断主题所属领域：以「多数结果」为准——若多数结果指向同一领域，则按该领域出题。
- 个别指向错误领域的离群结果应忽略，避免把主题识别到错误的领域。
- 只有当多数结果都指向某个领域时，才在该领域出题；否则继续多关键词检索以收敛判断。

出题要求：
- 每题带 type（single/multi/judge）；选项文本两两不同；题干/解析/知识点中文非空。
- single：4 个选项（key A-D），answer 为 1 个选项 key 的数组如 ["A"]。
- multi：4-5 个选项，answer 为正确选项 key 数组（至少 2 个，如 ["A","C"]）。
- judge：选项固定 [{"key":"0","text":"正确"},{"key":"1","text":"错误"}]，answer 为整数 0 或 1。
- 只能依据工具返回的联网内容（与已有知识库资料）出题，不得杜撰，事实须准确。

输出格式（务必遵守）：
1) 需要联网时，用下面格式发起一次工具调用（每轮最多一次）：
<tool>
{"name": "tavily_search", "args": {"query": "主题", "include_domains": ["*.cn"]}}
</tool>
2) 资料齐备后，用下面格式一次性输出最终题目（不要额外寒暄）：
<finish>
{"questions": [ ... ], "sources": [ {"title": "来源标题", "url": "https://..."} ]}
</finish>
若已有知识库资料足够，可直接用 <finish> 输出题目。"""


def _avoid_rule(avoid_stems):
    """把已出过的题干回传给模型，要求换题，降低批次之间题干撞车的概率。"""
    stems = [str(s).strip() for s in (avoid_stems or []) if str(s).strip()]
    if not stems:
        return ""
    shown = "\n".join("• %s" % s[:80] for s in stems[:12])
    return "以下题干已经出过，请换成考察点相同但题干完全不同的新题：\n%s\n\n" % shown


def _tool_user(course, difficulty, plan, is_url, kb_ctx, lively=False, topics=None):
    lines = []
    if is_url:
        lines.append("待抓取的文档 URL：%s" % course)
    else:
        lines.append("出题主题（课程名）：%s" % course)
    lines.append("难度：%s" % difficulty)
    lines.append("题型要求：%s" % _plan_spec(plan, difficulty))
    if topics:
        lines.append("本次出题范围限定在以下章节 / 主题内，不要超出这些范围：\n"
                     + "\n".join("• %s" % t for t in topics))
    if kb_ctx and kb_ctx.strip():
        lines.append("【知识库已有资料，可与联网资料结合使用】\n%s" % kb_ctx)
    lines.append("文风：" + _style_rule(lively))
    lines.append("请先判断输入是 URL 还是主题，调用合适的 Tavily 工具获取资料，再用 <finish> 输出题目。")
    return "\n\n".join(lines)


def _run_tool_agent(course, difficulty, plan, api_key, is_url, kb_ctx="", lively=False, topics=None, avoid_stems=None):
    """工具智能体：驱动现有出题 LLM 走「调用 Tavily 工具 → 收尾出题」循环。

    返回 {"ok": bool, "questions": [...], "sources": [...], "error": str}。
    - 题目在收尾 <finish> 中由模型给出；sources 取模型返回，extract 时兜底用 URL。
    - 工具失败只记 warning 并反馈给模型（不中断），模型可改浅层或基于通用知识出题。
    """
    tools = _build_tavily_tools(api_key)
    messages = [
        {"role": "system", "content": _TOOL_SYSTEM},
        {"role": "user", "content": _avoid_rule(avoid_stems) + _tool_user(course, difficulty, plan, is_url, kb_ctx, lively, topics)},
    ]
    sources = []
    for step in range(1, MAX_AGENT_STEPS + 1):
        raw = _llm_chat(messages)
        if not isinstance(raw, str) or raw.startswith("[LLM 不可用]"):
            _log.warning("[工具智能体] 第 %d 轮：大模型不可用，终止出题", step)
            return {"ok": False, "error": "大模型不可用，无法出题。请检查 AI 模型设置。", "sources": sources}
        call = _parse_tool_call(raw)
        if call:
            name, args = call
            _log.info("[工具智能体] 第 %d 轮：模型发起工具调用 %s", step, name)
            result = _exec_tavily_tool(tools, name, args, sources)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "[工具结果]\n" + result})
            continue
        fin = _parse_finish(raw)
        if fin is not None:
            qs, _bad = _parse_llm_questions(json.dumps({"questions": fin.get("questions", [])}))
            if len(qs) >= MIN_VALID_QUESTIONS:
                srcs = _norm_sources(fin.get("sources")) or sources
                _log.info("[工具智能体] 第 %d 轮：模型收尾，产出 %d 题，来源 %d 条", step, len(qs), len(srcs))
                return {"ok": True, "questions": qs, "sources": srcs}
            _log.info("[工具智能体] 第 %d 轮：题目数量不足或校验未过，要求补充", step)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "题目数量不足或校验未过，请补充/修正后用 <finish> 输出。"})
            continue
        # 无标记：尝试直接当成题目 JSON 收尾
        qs, _bad = _parse_llm_questions(raw)
        if qs:
            _log.info("[工具智能体] 第 %d 轮：直接产出 %d 题", step, len(qs))
            return {"ok": True, "questions": qs, "sources": sources}
        _log.info("[工具智能体] 第 %d 轮：未识别到工具调用或题目，提示继续", step)
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": "未识别到工具调用或最终题目，请继续：需联网请调用工具，否则用 <finish>{...}</finish> 输出题目。"})
    _log.warning("[工具智能体] 超出 %d 轮仍未产出题目，终止", MAX_AGENT_STEPS)
    return {"ok": False, "error": "出题超时（模型未在限定步数内产出题目）。", "sources": sources}


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

def _plan_spec(plan, difficulty):
    """题型分布描述串（出题 prompt 与工具智能体 user 消息共用）。"""
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
    return "；".join(parts) if parts else "3 道单选题"


def _style_rule(lively):
    """文风只改表达，不改考点、答案和 JSON 形状。默认关闭。"""
    if not lively:
        return "行文保持严谨、直接，不要玩笑、不要生活化场景、不要比喻。"
    return (
        "文风要求：轻松幽默。每道题的题干用一个生活化场景或比喻把知识点讲出来，"
        "解析也用一句通俗比喻帮助理解。不得为了好玩改变知识点、正确选项或事实；"
        "不要网络烂梗，不要人身攻击。"
    )


def _build_prompt(course, difficulty, plan, kb, lively=False, topics=None, avoid_stems=None):
    hint = DIFFICULTY_HINT.get(difficulty, DIFFICULTY_HINT["medium"])
    spec = _plan_spec(plan, difficulty)
    if kb and kb.strip():
        material_rule = "只能依据下方资料出题，不得使用资料之外的知识。"
    else:
        material_rule = ("下方暂无参考资料，请基于你对该主题的可靠通用知识严谨出题，"
                        "确保事实准确、不杜撰。")
    topic_rule = ""
    if topics:
        topic_rule = ("出题范围限定在以下章节 / 主题内，不要超出这些范围：\n"
                      + "\n".join("• %s" % t for t in topics) + "\n")
    return _avoid_rule(avoid_stems) + (
        "你是严谨的出题老师。%s\n%s\n%s\n\n"
        "课程：%s\n难度要求：%s\n\n"
        "请出：%s。只输出一个 JSON 对象，不要输出其他文字：\n"
        '{"questions": [{"type": "single", "stem": "题干", '
        '"options": [{"key": "A", "text": "选项"}, {"key": "B", "text": "选项"}, '
        '{"key": "C", "text": "选项"}, {"key": "D", "text": "选项"}], '
        '"answer": ["A"], "explanation": "解析", "knowledge_point": "知识点"}]}\n\n'
        "要求：每题必须带 type 字段（single/multi/judge）；选项文本两两不同；"
        "题干、解析、知识点都用中文且非空。\n\n"
        "出题依据的资料：\n%s" % (material_rule, _style_rule(lively), topic_rule, course, hint, spec, kb)
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

def _generate_from_prompt(prompt):
    """直接（非工具智能体）出题：调一次出题 LLM 并解析题目，失败返回空列表。"""
    raw = _llm_chat([{"role": "user", "content": prompt}])
    if not isinstance(raw, str) or raw.startswith("[LLM 不可用]"):
        return []
    qs, _ = _parse_llm_questions(raw)
    return qs


def _public_question(q):
    """对外单题：不含 answer。"""
    return {
        "id": q["id"], "type": q["type"], "stem": q["stem"], "options": q["options"],
        "explanation": q["explanation"], "knowledge_point": q["knowledge_point"],
        "source": q["source"], "sources": q["sources"],
    }


def _new_quiz_id():
    return "z-%d-%s" % (
        int(datetime.now().strftime("%H%M%S")) + os.getpid() % 1000,
        os.urandom(3).hex(),
    )


def _begin_run(course, difficulty, plan, questions, src_kind, src_list, citations, client_id):
    """第一题（及已校验题）先建局并落盘。后续题用 _append_question 追加。"""
    for q in questions:
        q["source"] = src_kind
        q["sources"] = src_list
    quiz_id = _new_quiz_id()
    ts = _now()
    run = {
        "quiz_id": quiz_id,
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "expected": sum(plan.values()) if isinstance(plan, dict) else len(questions),
        "types": plan,
        "source": src_kind,
        "client_id": str(client_id or "")[:64],
        "created_at": ts,
        "started_at": ts,
        "questions": questions,
        "answers": {},
        "retrieved": citations,
        "status": "streaming",
    }
    with _LOCK:
        runs = _load()
        runs[quiz_id] = run
        if len(runs) > MAX_RUNS_KEPT:
            ordered = sorted(runs.items(), key=lambda kv: kv[1].get("created_at") or "")
            for k, _v in ordered[: len(runs) - MAX_RUNS_KEPT]:
                del runs[k]
        _save()
    return run


def _append_question(quiz_id, q, src_kind, src_list):
    """后续题落盘。返回对外题目；局不存在返回 None。"""
    q["source"] = src_kind
    q["sources"] = src_list
    with _LOCK:
        runs = _load()
        run = runs.get(quiz_id)
        if not run:
            return None
        have = {x.get("id") for x in run["questions"]}
        stems = {x.get("stem") for x in run["questions"]}
        if q.get("stem") in stems:
            return None
        if q.get("id") in have:
            n = len(run["questions"]) + 1
            while ("q%d" % n) in have:
                n += 1
            q["id"] = "q%d" % n
        run["questions"].append(q)
        run["count"] = len(run["questions"])
        _save()
    return _public_question(q)


def _finish_run(quiz_id, status="done"):
    with _LOCK:
        runs = _load()
        run = runs.get(quiz_id)
        if not run:
            return None
        run["status"] = status
        run["count"] = len(run.get("questions") or [])
        _save()
        return run


def _iter_questions(questions, quiz_id):
    """已落盘题目按到达顺序对外推送。answer 不出现在事件里。"""
    for i, q in enumerate(questions):
        yield ("question", {
            "ok": True, "index": i, "question": _public_question(q), "quiz_id": quiz_id,
        })


# 去重丢掉题目后，最多再补这么多次。每次都把已出题干回传给模型避开，防止死循环补同一题。
_REFILL_LIMIT = 2


def _run_stems(quiz_id):
    """已落盘的题干，用于让后续批次避开重复题。"""
    with _LOCK:
        runs = _load()
        run = runs.get(quiz_id) or {}
        return [q.get("stem") or "" for q in run.get("questions") or []]


def _append_wrongbook(quiz_id, course, difficulty, client_id, include_wrong, start_index):
    """把本课程全部未掌握错题重做成新题，追加进当前局。失败不拖垮主流程。"""
    if not include_wrong or _wrongbook_provider is None:
        return []
    try:
        items = _wrongbook_provider(course) or []
    except Exception:
        logging.warning("读取错题本失败，本次不并入错题")
        return []
    if not items:
        return []
    res = generate_quiz_from_wrongbook(items, difficulty=difficulty, client_id=client_id)
    if not res.get("ok"):
        return []
    out = []
    with _LOCK:
        runs = _load()
        extra = list((runs.get(res["quiz_id"]) or {}).get("questions") or [])
        runs.pop(res["quiz_id"], None)
        _save()
    for q in extra:
        pub = _append_question(quiz_id, dict(q), "wrongbook", [])
        if pub:
            out.append(pub)
    return out


def _generate_fresh(course, difficulty, count, types, client_id, web_search, lively, topics,
                    avoid_stems):
    """要一批与已出题干不重复的题。count 可以小于整卷下限，调用方负责夹住。"""
    res = generate_quiz(
        course, difficulty=difficulty, count=count, types=types,
        client_id=client_id, web_search=web_search, min_questions=1, lively=lively,
        min_count=1, topics=topics, avoid_stems=avoid_stems,
    )
    return res


def iter_generate_quiz(course, difficulty="medium", count=_COUNT_DEFAULT, types=None,
                       client_id="", web_search=True, lively=False, topics=None,
                       include_wrong=False):
    """边出边推。默认拆成「先 1 题、再剩余题」两次模型调用。

    第一次调用返回并落盘后立刻 yield meta + question，调用方可以在第二次调用进行时判分。
    题量已经是 1，或注入的 _llm_chat 一次就给出全部题时，不再二次调用。
    第二次调用若与第一题题干撞车，会按差额再补，最多 _REFILL_LIMIT 次。
    include_wrong 为真时，在新题之外再并入本课程的全部未掌握错题重做题。
    yield (event, data)，data 不含 answer。整卷 POST 仍走 generate_quiz。
    """
    course = str(course or "").strip()
    try:
        total = int(count)
    except (TypeError, ValueError):
        total = _COUNT_DEFAULT
    total = max(_COUNT_MIN, min(_COUNT_MAX, total))

    def _emit_bundle(res):
        if not res.get("ok"):
            yield ("error", {"ok": False, "error": res.get("error") or "出题失败",
                             "retrieved": res.get("retrieved") or []})
            yield ("done", {"ok": False})
            return None
        quiz_id = res["quiz_id"]
        questions = res["questions"]
        yield ("meta", {
            "ok": True,
            "quiz_id": quiz_id,
            "course": res["course"],
            "difficulty": res["difficulty"],
            "expected": total,
            "types": res.get("types") or {},
            "source": res.get("source") or "kb",
            "retrieved": res.get("retrieved") or [],
        })
        yield from _iter_questions(questions, quiz_id)
        return quiz_id

    first_n = 1 if total > 1 else total
    gen = _emit_bundle(_generate_fresh(
        course, difficulty, first_n, types, client_id, web_search, lively, topics, None,
    ))
    quiz_id = None
    failed = False
    for item in gen:
        if item[0] == "meta":
            quiz_id = item[1].get("quiz_id")
        if item[0] in ("error", "done") and not item[1].get("ok"):
            failed = True
        yield item
    if failed or not quiz_id:
        return
    if first_n >= total:
        _finish_run(quiz_id, "done")
        yield ("done", {"ok": True, "quiz_id": quiz_id, "count": first_n})
        return

    # 后续题逐批补。第一批剩余题按原计划出，不带避让题干——那一批和首题同属一轮，
    # 提前回传题干会让模型换题，凑不满原计划的题数。
    # 批内与已出题干重复的由 _append_question 丢掉；只有真被丢掉才把已出题干回传，
    # 按差额再要，直到凑满 total 或补不出新题。
    added = 0
    avoid = None
    for _ in range(_REFILL_LIMIT + 1):
        need = total - first_n - added
        if need <= 0:
            break
        rest = _generate_fresh(
            course, difficulty, need, types, client_id, web_search, lively, topics, avoid,
        )
        if not rest.get("ok"):
            break
        with _LOCK:
            runs = _load()
            extra = list((runs.get(rest["quiz_id"]) or {}).get("questions") or [])
            runs.pop(rest["quiz_id"], None)
            _save()
        gained = 0
        for q in extra:
            if added >= total - first_n:
                break
            pub = _append_question(quiz_id, dict(q), q.get("source") or rest.get("source") or "topic",
                                   q.get("sources") or [])
            if pub:
                yield ("question", {
                    "ok": True, "index": first_n + added, "question": pub, "quiz_id": quiz_id,
                })
                added += 1
                gained += 1
        if gained == 0:
            break
        # 这一批有题被去重丢掉才需要换题干重出，否则下一轮差额请求会重复拿到同一题。
        if gained < len(extra):
            avoid = _run_stems(quiz_id)

    # 错题并入：不占 total 的名额，作为额外练习题追加在新题之后。
    wrong_added = _append_wrongbook(quiz_id, course, difficulty, client_id, include_wrong,
                                    first_n + added)
    for pub in wrong_added:
        yield ("question", {
            "ok": True, "index": first_n + added + wrong_added.index(pub),
            "question": pub, "quiz_id": quiz_id,
        })

    _finish_run(quiz_id, "done")
    yield ("done", {"ok": True, "quiz_id": quiz_id,
                    "count": first_n + added + len(wrong_added),
                    "expected": total, "short": first_n + added < total})


def _assemble(course, difficulty, plan, questions, src_kind, src_list, citations, client_id,
             min_questions=None):
    """统一标来源、落盘、裁剪对外负载（generate_quiz 收尾）。

    min_questions 默认仍是整卷下限。流式首段可以传 1，先把第一题交给前端。
    """
    need = MIN_VALID_QUESTIONS if min_questions is None else min_questions
    if len(questions) < need:
        return {"ok": False, "error": "本次生成的题目未通过格式校验，请重试。", "retrieved": citations}
    run = _begin_run(course, difficulty, plan, questions, src_kind, src_list, citations, client_id)
    _finish_run(run["quiz_id"], "done")

    payload_questions = [_public_question(q) for q in questions]
    return {
        "ok": True,
        "quiz_id": run["quiz_id"],
        "course": course,
        "difficulty": difficulty,
        "count": len(questions),
        "types": plan,
        "source": src_kind,
        "questions": payload_questions,
        "retrieved": citations,
    }


def generate_quiz(course, difficulty="medium", count=_COUNT_DEFAULT, types=None, client_id="", web_search=True, min_questions=None, lively=False, min_count=None, topics=None, avoid_stems=None):
    """出题入口。返回 dict（HTTP 层直接回 JSON）。

    联网出题走「Tavily 工具智能体」：URL 用 extract、主题用 search，模型按复杂度自选自浅/深
    实例，可动态设 search_depth/time_range/include_domains。联网搜索开关（web_search，默认开）：
      - 关 / 无 key / 工具失败或超时 → 降级为空上下文，仍基于通用知识出题（不拒绝，记 warning）；
    主题题（非 URL）永不直接拒绝，空上下文也走出题（source 标 "topic"）；
    URL 题（丢链接出题）需要 extract，无 key / 工具失败回退 WEAK_HIT_ERROR（无 URL 内容无法出题）。
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
    # min_count：只有流式路径会用。整卷接口仍按 _COUNT_MIN 夹住，保持对外契约不变；
    # 若不对流式放行，一次「只要 1 题」会被抬成整套题，「第一题先到」就失去意义。
    lo = _COUNT_MIN if min_count is None else max(1, int(min_count))
    count = max(lo, min(_COUNT_MAX, count))
    if not course:
        return {"ok": False, "error": "请先输入课程名", "retrieved": []}

    plan = _resolve_plan(types, count)
    is_url = bool(re.match(r"https?://", course, re.I))
    key = os.environ.get(TAVILY_KEY_ENV)

    # URL 直出题（「丢链接出题」）：必须 extract，无 key / 工具失败 → 拒绝（无 URL 内容无法出题）
    if is_url:
        if not key:
            return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
        agent = _run_tool_agent(course, difficulty, plan, key, is_url=True, kb_ctx="", lively=lively)
        if not agent["ok"]:
            return {"ok": False, "error": WEAK_HIT_ERROR, "retrieved": []}
        return _assemble(
            course, difficulty, plan, agent["questions"], "web",
            agent["sources"], agent["sources"], client_id, min_questions,
        )

    # 主题题：知识库可选增强 + 联网工具智能体（由 web_search 开关控制）
    topics = [str(t).strip() for t in (topics or []) if str(t).strip()]
    avoid = [str(s).strip() for s in (avoid_stems or []) if str(s).strip()]
    hits = _retrieve(course)
    # 限定章节出题：按主题词过滤。用户既已指定范围，命不中任何章节就明确报错，
    # 不再退回全课程——退回会让人误以为正在练所选章节。
    if topics:
        matched = [h for h in hits if _hit_matches_topic(h, topics)] if hits else []
        if not matched:
            return {"ok": False, "error": NO_TOPIC_MATCH_ERROR, "retrieved": []}
        hits = matched
    kb_ctx = _kb_blocks(hits) if hits else ""
    kb_citations = [
        {"id": n.get("id"), "title": n.get("title", ""), "score": round(s, 2)}
        for n, s, _ in hits
    ]
    if web_search and key:
        agent = _run_tool_agent(course, difficulty, plan, key, is_url=False, kb_ctx=kb_ctx, lively=lively, topics=topics, avoid_stems=avoid)
        if agent["ok"]:
            web_sources = agent["sources"]
            src_kind = "web" if web_sources else ("kb" if hits else "topic")
            return _assemble(
                course, difficulty, plan, agent["questions"], src_kind,
                web_sources, kb_citations + web_sources, client_id, min_questions,
            )
        # 联网工具智能体失败/异常 → 降级为空上下文，基于通用知识出题（不拒绝）
        logging.warning("联网工具智能体失败，降级为空上下文出题: %s", agent.get("error"))
    # 联网关闭 / 无 key / 降级：直接 KB 或通用知识出题
    questions = _generate_from_prompt(_build_prompt(course, difficulty, plan, kb_ctx, lively, topics, avoid))
    src_kind = "kb" if hits else "topic"
    return _assemble(
        course, difficulty, plan, questions, src_kind, [], kb_citations, client_id,
        min_questions,
    )


# ---------------------------------------------------------------------------
# 错题重做：为每道错题生成「同知识点」的新题（不联网，考点来自已存错题）
# ---------------------------------------------------------------------------

def _build_wrongbook_prompt(items, difficulty):
    """为每条错题（原题 / 正确答 / 解析）生成一道全新的同知识点练习。

    题型（single/multi/judge）必须与原题一致，避免多选变成单选丢信息；
    题干与选项文字都要与原题不同，确保是「练同一考点」而非「复读原题」。
    """
    hint = DIFFICULTY_HINT.get(difficulty, DIFFICULTY_HINT["medium"])
    lines = [
        "你是严谨的出题老师。下面列出用户之前答错的若干道题（含原题、正确答、解析）。",
        "请为每一道【原】题，生成一道【全新的】练习题：考点 / 知识点必须相同，"
        "但题干与各个选项文字都不得与原题雷同；题型（单选 single / 多选 multi / 判断 judge）"
        "必须与原题保持一致；题干、解析、知识点都用中文且非空。",
        "难度要求：%s" % hint,
    ]
    for i, it in enumerate(items, 1):
        q = (it.get("question") or "").strip()
        a = (it.get("answer") or "").strip()
        r = (it.get("reason") or "").strip()
        tp = (it.get("qtype") or "single").strip().lower()
        if tp not in Q_TYPES:
            tp = "single"
        block = "[%d] 原题题型：%s\n原题：%s" % (i, tp, q)
        if a:
            block += "\n正确答：%s" % a
        if r:
            block += "\n解析：%s" % r
        lines.append(block)
    lines.append("请只输出一个 JSON 对象，不要输出其他文字：")
    lines.append(
        '{"questions": [{"type": "single", "stem": "题干", '
        '"options": [{"key": "A", "text": "选项"}, {"key": "B", "text": "选项"}, '
        '{"key": "C", "text": "选项"}, {"key": "D", "text": "选项"}], '
        '"answer": ["A"], "explanation": "解析", "knowledge_point": "知识点"}]}'
    )
    lines.append(
        "要求：题目数量必须与上面的原题目的数量一致；每题必须带 type 字段（single/multi/judge）；"
        "选项文本两两不同；题干、解析、知识点都用中文且非空。"
    )
    return "\n\n".join(lines)


def generate_quiz_from_wrongbook(items, difficulty="medium", types=None, client_id=""):
    """错题重做入口：为每条错题产出一道同知识点的新选择题，复用 _assemble 同结构返回。

    items: [{course, question, answer, reason, qtype}] —— 由 api_server 从错题本读取。
    不联网（考点来自已存错题），直接走 _generate_from_prompt；返回与 generate_quiz
    相同的 {ok, quiz_id, course, difficulty, count, types, source, questions, retrieved}。
    """
    if not items:
        return {"ok": False, "error": "没有可重做的错题", "retrieved": []}
    difficulty = str(difficulty or "medium").strip().lower()
    if difficulty not in DIFFICULTIES:
        difficulty = "medium"

    # 单条错题也允许成局（min_questions=1）；批量时按 _assemble 下限即可
    questions = _generate_from_prompt(_build_wrongbook_prompt(items, difficulty))
    if not questions:
        return {"ok": False, "error": "本次生成的题目未通过格式校验，请重试。", "retrieved": []}

    # plan 由实际生成题的题型构成（错题重做保留每题原始题型）
    plan = {"single": 0, "multi": 0, "judge": 0}
    for q in questions:
        plan[q.get("type", "single")] = plan.get(q.get("type", "single"), 0) + 1

    return _assemble(
        items[0].get("course") or "",
        difficulty, plan, questions, "wrongbook", [], [], client_id,
        min_questions=1,
    )


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
