# agent_loop.py — Agent 循环 + trace 日志 + 回放

"""Agent 循环模块：编排 Planner/Searcher/Writer/Reviewer，每步写 trace 日志。"""

import json
import os
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

# trace 日志路径（打包兼容，见 core/paths.py）
_TRACE_DIR = _resolve_data_dir()
_TRACE_FILE = os.path.join(_TRACE_DIR, "trace.log")


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

    # 先搜知识库（关键词搜索只看当前问题，不混入历史）
    store = KnowledgeStore()
    results = store.search(question)
    if results:
        # 取第一条匹配
        best = results[0]
        answer = f"{best['title']}：{best['content']}"
        log_trace("chat_done", {"source": "knowledge", "title": best["title"]})
        return {"answer": answer, "source": "knowledge"}

    # 知识库没有，调大模型（多轮模式）
    log_trace("chat_llm_start", {"question": question})
    messages = []

    # 1) system 注入（可选）
    if course_context:
        messages.append({
            "role": "system",
            "content": (
                f"你是「{course_context}」课程的智能学习助手。"
                "回答简洁、聚焦课程本身，使用中文。"
            ),
        })

    # 2) 历史窗口（仅取最近 8 条，且过滤非标准 role / 非 dict）
    if history:
        trimmed = history[-8:] if len(history) > 8 else history
        for h in trimmed:
            if not isinstance(h, dict):
                continue  # 跳过非 dict（字符串、None 等）
            role = h.get("role")
            if role in ("user", "assistant") and h.get("content"):
                messages.append({"role": role, "content": h["content"]})

    # 3) 当前问题
    messages.append({"role": "user", "content": question})

    answer = chat(messages)
    source = "llm"
    if answer.startswith("[LLM 不可用]"):
        source = "llm"
        answer = f"知识库中没有相关内容，且大模型不可用。\n({answer})"
    log_trace("chat_done", {"source": source, "messages_count": len(messages)})
    return {"answer": answer, "source": source}
