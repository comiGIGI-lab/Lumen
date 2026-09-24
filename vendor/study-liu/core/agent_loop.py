# agent_loop.py — Agent 循环 + trace 日志 + 回放

"""Agent 循环模块：编排 Planner/Searcher/Writer/Reviewer，每步写 trace 日志。"""

import json
import os
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

# trace 日志路径（打包兼容，见 core/paths.py）
_TRACE_DIR = _resolve_data_dir()
_TRACE_FILE = os.path.join(_TRACE_DIR, "trace.log")

# ---------- RAG 参数 ----------
# 检索几条资料注入 prompt。取 3 而不是 1：单条容易漏，太多会稀释重点、
# 也会让 prompt 变长（知识库条目平均 200 字，3 条约 600 字，成本可忽略）。
RAG_TOP_K = 3
# 单条资料进 prompt 的字数上限。导入的 PDF 分块后可能较长，
# 这里截断是为了守住 prompt 体积与费用，不是知识库本身的限制。
RAG_PASSAGE_MAX = 1200
# 弱相关命中过滤：分数与覆盖率**两个条件都满足**才注入 prompt。
#
# 为什么需要：2-gram 检索偶尔会把「只是碰巧有共同字词」的笔记也带上来。
# 实测问「傅里叶变换的物理意义」会命中《物理实验报告·不确定度传递公式》
# （score 1.81、覆盖率很低）。这种弱命中若也注入，一是污染上下文，
# 二是会让 source 误报成 knowledge —— 前端显示「来源：知识库」，
# 但答案其实完全来自模型自身，答辩时被追问"引用的是哪条笔记"会答不上来。
#
# 分数受查询长度影响，所以加一个与长度无关的覆盖率门槛一起判断。
#
# ★ 2026-09-24 用真实浏览器端到端测试后调过一轮：
#   原来写的是 score>=2.5 且 coverage>=0.25。实测问
#   「BROWSER-E2E-9527 这个识别码是什么？它对应的文档讲了什么？」
#   时，正确的那条笔记明明被检索成了 top-1，却因为 score=2.30 差 0.2 分
#   被挡在门外，回答于是退回成"模型自己编"、不引用知识库。
#   原因是长问句天然带很多无关修饰词，覆盖率被摊薄 → 分数随问句变长而下降，
#   同一条笔记问得越完整反而越进不去（短问法 21.60 / 中问法 3.88 / 长问法 2.30）。
#
#   真正该起主要作用的是**覆盖率**（它与长度无关）：噪声命中实测 coverage
#   只有 0.059~0.062，而正确命中是 0.25 —— 两者差 4 倍，覆盖面完全够分开。
#   所以把 score 门槛降到 1.0 只作安全下限，coverage 留 0.2 作为主闸。
RAG_MIN_SCORE = 1.0
RAG_MIN_COVERAGE = 0.2


def _ensure_trace_dir():
    """确保 data 目录存在。"""
    if not os.path.exists(_TRACE_DIR):
        os.makedirs(_TRACE_DIR, exist_ok=True)


def log_trace(event, data=None):
    """
    写一行 trace 日志到 data/trace.log，同时打印到 console。
    参数：
        event: 事件名称（如 "planner_start"）
        data: 附加数据（字典）
    """
    _ensure_trace_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {event}"
    if data:
        line += f" | {json.dumps(data, ensure_ascii=False)}"
    print(line)
    try:
        with open(_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程


def run_plan_pipeline(course, profile=None, use_cache=True):
    """
    运行生成方案的完整 Agent 流程：
    Planner → Searcher → Writer → Reviewer（不过则重跑一次 Writer + Searcher）
    参数：
        course: 课程名
        profile: 可选，用户画像 dict（level/daily_hours/goal/deadline），
                 None 时不注入个性化
        use_cache: 是否使用结果缓存（默认 True）。命中缓存时跳过整条流水线，
                   演示时重复点「生成方案」不会重复消耗 API 额度。
    返回：
        包含 outline / resources / plan 的字典
        （命中缓存时额外带 "_from_cache": True）
    """
    from agents.planner import plan_outline
    from agents.searcher import search_resources
    from agents.writer import write_plan
    from agents.reviewer import review

    # ---- 先记请求开始，再查缓存 ----
    # 顺序很重要：缓存命中会提前 return，若把 pipeline_start 写在后面，
    # trace 日志里就只剩一行 cache_hit —— 回放/排障时会误以为请求没进来。
    log_trace("pipeline_start", {
        "course": course,
        "profile": bool(profile),
        "use_cache": bool(use_cache),
    })

    # ---- 缓存查找：命中就直接返回，跳过 4 个 agent ----
    if use_cache:
        try:
            from tools.cache_store import get_cached
            cached = get_cached(course, profile)
            if cached:
                result = dict(cached)
                result["_from_cache"] = True
                log_trace("cache_hit", {"course": course})
                log_trace("pipeline_done", {
                    "course": course, "ok": True, "from_cache": True,
                })
                return result
        except Exception as e:
            # 缓存读写失败绝不能影响生成
            log_trace("cache_lookup_failed", {"error": str(e)})

    # 流水线开始：清空上一次的 LLM 失败记录与降级标记
    try:
        from core import llm as _llm
        _llm.reset_degraded()
    except Exception:
        pass

    # 第一步：Planner 生成大纲
    log_trace("planner_start", {"course": course})
    outline = plan_outline(course, profile=profile)
    log_trace("planner_done", {"outline_count": len(outline)})

    # 第二步：Searcher 搜索资源
    log_trace("searcher_start", {"course": course})
    resources = search_resources(course, profile=profile)
    log_trace("searcher_done", {"resource_count": len(resources)})

    # 第三步：Writer 生成学习计划
    log_trace("writer_start", {"course": course})
    plan = write_plan(course, outline, profile=profile)
    log_trace("writer_done", {"plan_count": len(plan)})

    # 第四步：Reviewer 质检
    result = {
        "course": course,
        "outline": outline,
        "resources": resources,
        "plan": plan,
        "profile": profile or {},
    }
    log_trace("reviewer_start", {"course": course})
    ok, comments = review(result)
    log_trace("reviewer_done", {"ok": ok, "comments": comments})

    # 质检不过，重跑一次 Writer 和 Searcher
    if not ok:
        log_trace("reviewer_retry", {"comments": comments})
        plan = write_plan(course, outline, profile=profile)
        resources = search_resources(course, profile=profile)
        result = {
            "course": course,
            "outline": outline,
            "resources": resources,
            "plan": plan,
            "profile": profile or {},
        }
        ok, comments = review(result)
        log_trace("reviewer_retry_done", {"ok": ok, "comments": comments})

    log_trace("pipeline_done", {"course": course, "ok": ok})

    # ---- 降级检测：LLM 失败走兜底时，把原因带出去供 UI 警告 ----
    # 关键设计：降级结果**不写缓存**——否则模板内容会占坑 24 小时，
    # 用户修好 API（如充值）后再生成仍命中旧模板，以为"修了也没用"。
    try:
        from core import llm as _llm
        if _llm.DEGRADED_AGENTS:
            result["_degraded"] = {
                "agents": sorted(_llm.DEGRADED_AGENTS),
                "error": _llm.LAST_ERROR or "LLM 调用失败",
            }
            log_trace("degraded", {
                "course": course,
                "agents": result["_degraded"]["agents"],
                "error": result["_degraded"]["error"],
            })
    except Exception:
        pass

    # ---- 写入缓存（按 课程名 + 画像指纹 做 key，24h TTL，LRU 30 条）----
    # 降级结果不缓存（见上方说明）；但 mock 模式例外——离线演示的
    # 「⚡ 命中缓存」本身是特性，且 mock 模式天然永远是模板内容。
    _skip_cache = False
    if "_degraded" in result:
        try:
            # 以 llm 模块的实际运行模式为准（生产环境与 core.config.is_mock
            # 是同一函数；测试里 monkeypatch llm.is_mock 时也保持一致）
            from core import llm as _llm_mod
            _skip_cache = not _llm_mod.is_mock()
        except Exception:
            _skip_cache = True
    if use_cache and not _skip_cache:
        try:
            from tools.cache_store import put_cache
            to_cache = {k: v for k, v in result.items() if k != "_from_cache"}
            put_cache(course, to_cache, profile)
        except Exception as e:
            log_trace("cache_store_failed", {"error": str(e)})

    return result


def run_chat_pipeline(question, history=None, course_context=None):
    """
    运行问答流程：先搜知识库，搜到就用知识库回答，否则调大模型（支持多轮）。
    参数：
        question: 用户问题
        history: 可选，多轮历史 [{"role": "user|assistant", "content": "..."}]
                 最多取最近 8 条；system role 不会从 history 拼入
        course_context: 可选，当前正在学哪门课程。注入 system 让 LLM 更聚焦
    返回：
        {"answer": "回答文字", "source": "knowledge" 或 "llm"}
    """
    from tools.knowledge_store import KnowledgeStore
    from core.llm import chat

    log_trace("chat_start", {"question": question, "history_len": len(history or [])})

    # 1) 检索知识库（只看当前问题，不混入历史）
    #
    # 改造前：store.search(question) 是「整句子串匹配」，命中就直接把笔记原文
    #         甩给用户（不上大模型），不命中就完全不带知识库地调模型 ——
    #         既不是 RAG，两头体验也都差。
    # 改造后：retrieve() 打分检索 top-k，把片段**注入 system prompt**，
    #         由大模型基于资料生成答案 —— 这才是 RAG（检索增强生成）。
    store = KnowledgeStore()
    # 多取几条再筛：只把「分数够 + 覆盖率够」的强相关命中注入 prompt。
    # 弱命中既不注入、也不计入 citations —— 这样 source 才诚实
    # （见文件头 RAG_MIN_SCORE 处的说明）。
    raw_hits = store.retrieve(question, top_k=RAG_TOP_K * 2)
    hits = [
        h for h in raw_hits
        if h[1] >= RAG_MIN_SCORE and (h[2].get("coverage") or 0) >= RAG_MIN_COVERAGE
    ][:RAG_TOP_K]
    citations = [
        {"id": n.get("id"), "title": n.get("title", ""), "score": round(s, 2)}
        for n, s, _ in hits
    ]
    if raw_hits and not hits:
        log_trace("chat_retrieve_rejected", {
            "reason": "弱相关，未注入",
            "top_title": (raw_hits[0][0].get("title") or "")[:40],
            "top_score": round(raw_hits[0][1], 2),
            "top_coverage": (raw_hits[0][2] or {}).get("coverage"),
        })
    if hits:
        log_trace("chat_retrieve", {
            "hits": len(hits),
            "top_title": citations[0]["title"],
            "top_score": citations[0]["score"],
        })

    # 2) system 注入：角色（可选）+ 检索到的资料
    messages = []
    system_parts = []
    if course_context:
        system_parts.append(
            f"你是「{course_context}」课程的智能学习助手。"
            "回答简洁、聚焦课程本身，使用中文。"
        )
    if hits:
        blocks = []
        for i, (note, _score, _detail) in enumerate(hits, 1):
            body = (note.get("content") or "").strip()
            if len(body) > RAG_PASSAGE_MAX:
                body = body[:RAG_PASSAGE_MAX] + "…"
            blocks.append(f"【资料 {i}】{note.get('title', '')}\n{body}")
        system_parts.append(
            "下面是本课程知识库中检索到的资料。请**优先依据这些资料**回答；\n"
            "资料不足以回答时，可以补充你自己的知识，但要说明哪部分来自资料、哪部分是补充；\n"
            "若资料与问题无关，直接按常识回答即可。不要复述「资料1/资料2」这种编号。\n\n"
            + "\n\n".join(blocks)
        )
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # 3) 历史窗口（仅取最近 8 条，且过滤非标准 role / 非 dict）
    if history:
        trimmed = history[-8:] if len(history) > 8 else history
        for h in trimmed:
            if not isinstance(h, dict):
                continue  # 跳过非 dict（字符串、None 等）
            role = h.get("role")
            if role in ("user", "assistant") and h.get("content"):
                messages.append({"role": role, "content": h["content"]})

    # 4) 当前问题
    messages.append({"role": "user", "content": question})

    log_trace("chat_llm_start", {"question": question, "with_context": bool(hits)})
    answer = chat(messages)

    if answer.startswith("[LLM 不可用]"):
        # 降级：模型不可用时，退回到「直接把检索到的资料给用户」——
        # 这正是改造前的老行为，留作兜底比只回一句"大模型不可用"有用得多。
        if hits:
            top = hits[0][0]
            log_trace("chat_done", {"source": "knowledge", "degraded": "llm_unavailable"})
            return {
                "answer": f"{top['title']}：{top['content']}",
                "source": "knowledge",
                "retrieved": citations,
                "degraded": "llm_unavailable",
            }
        log_trace("chat_done", {"source": "llm", "degraded": "llm_unavailable"})
        return {
            "answer": f"知识库中没有相关内容，且大模型不可用。\n({answer})",
            "source": "llm",
            "retrieved": [],
        }

    # source 仍沿用 knowledge / llm 两个值 —— 前端的「来源」标签只认这几个，
    # 新造一个值会让它落到兜底分支显示成「来源：错误」。
    # 命中知识库时附上 retrieved（带 id/title/score），供 UI 展示「参考资料」。
    source = "knowledge" if hits else "llm"
    log_trace("chat_done", {"source": source, "messages_count": len(messages)})
    return {"answer": answer, "source": source, "retrieved": citations}
