# web_tools.py — Tavily 联网工具共享模块（Phase B，Agentic 检索切片）
#
# 定位：把 quiz.py 里已落地的「langchain-tavily 4 实例 + 自写 tool-call 循环」
# 收敛为共享模块，供两条链路复用：
#   1. quiz 出题（既有，不改 quiz.py —— 它的循环带出题专属编排，不强行合并）；
#   2. 主问答弱命中联网补题（新增 enhance_chat）。
#
# 设计约束（见 openspec/changes/2026-10-10-vector-rag-agentic/spec.md）：
#   - langchain_tavily 只在函数内延迟 import（范围闸：api_server/quiz 本体不得
#     顶层 import 它，未安装时本模块照常导入、功能 no-op）；
#   - 不引 langgraph / 裸 langchain：tool-call 循环自写（正则 + JSON 协议）；
#   - key 只从环境变量 TAVILY_API_KEY / STUDY_LIU_TAVILY_KEY 注入，不入库不落盘；
#   - 任何失败返回 None，调用方保持原答案 —— 联网是增强路径，绝不能打挂问答。

from __future__ import annotations

import json
import logging
import os
import re

_log = logging.getLogger("web_tools")

# tool-call 文本协议（与 quiz.py 一致，模型侧零新概念）
_TOOL_RE = re.compile(r"<tool>\s*(\{[\s\S]*?\})\s*</tool>", re.S)

# 主问答补题的最大轮数 / 结果条数（控制延迟与 token；问答不像出题需要深挖）
_MAX_TURNS = 2
_MAX_RESULTS = 5


def available():
    """联网层是否可用（key 已配置且 langchain_tavily 可导入）。"""
    if not _api_key():
        return False
    try:
        import langchain_tavily  # noqa: F401
        return True
    except Exception as e:
        # 2026-10-16 复盘：静默降级会掩盖「依赖从未装过」的事实，必须留痕
        _log.warning("langchain_tavily 不可导入，联网补题停用：%s", e)
        return False


def _api_key():
    """key 优先级：TAVILY_API_KEY > STUDY_LIU_TAVILY_KEY（api_server 启动时
    已把后者映射到前者，这里双保险，独立调用本模块也能用）。"""
    return (os.environ.get("TAVILY_API_KEY")
            or os.environ.get("STUDY_LIU_TAVILY_KEY")
            or "").strip()


# ============================================================
# 工具实例（与 quiz.py _build_tavily_tools 同构）
# ============================================================
def build_tools(api_key=None):
    """构造 4 个 Tavily 工具实例。未安装 langchain_tavily 时返回 {}。"""
    api_key = api_key or _api_key()
    if not api_key:
        return {}
    try:
        from langchain_tavily import TavilySearch, TavilyExtract
    except Exception as e:
        # 2026-10-16 复盘：同 available()，缺依赖必须留 warning，不许静默
        _log.warning("langchain_tavily 不可导入，工具构造返回空（联网出题/补题停用）：%s", e)
        return {}
    return {
        "tavily_search": TavilySearch(
            tavily_api_key=api_key, search_depth="basic",
            max_results=_MAX_RESULTS),
        "tavily_search_deep": TavilySearch(
            tavily_api_key=api_key, search_depth="advanced",
            max_results=_MAX_RESULTS),
        "tavily_extract": TavilyExtract(tavily_api_key=api_key, extract_depth="basic"),
        "tavily_extract_deep": TavilyExtract(tavily_api_key=api_key, extract_depth="advanced"),
    }


def _result_text(out, cap=6000):
    """把 Tavily 返回压成紧凑文本（标题+链接+摘要），供注入 prompt。"""
    if isinstance(out, dict) and isinstance(out.get("results"), list):
        parts = []
        for i, r in enumerate(out["results"], 1):
            title = r.get("title") or r.get("url") or "(无标题)"
            url = r.get("url") or ""
            body = (r.get("content") or r.get("raw_content") or "").strip()
            if len(body) > 400:
                body = body[:400] + "…"
            parts.append("【%d】%s\n链接：%s\n%s" % (i, title, url, body))
        return "\n\n".join(parts)[:cap]
    return str(out)[:cap]


def web_search(query, deep=False):
    """一次性浅/深检索（无循环）。Returns: {"text", "sources"} 或 None。"""
    tools = build_tools()
    name = "tavily_search_deep" if deep else "tavily_search"
    tool = tools.get(name)
    if tool is None:
        return None
    allowed = set(getattr(tool, "args", {}) or {})
    args = {"query": query}
    if "max_results" in allowed:
        args["max_results"] = _MAX_RESULTS
    try:
        out = tool.invoke(args)
    except Exception as e:
        _log.warning("web_search(%s) 失败: %s", name, e)
        return None
    sources = []
    if isinstance(out, dict):
        for r in out.get("results") or []:
            if isinstance(r, dict) and r.get("url"):
                sources.append({"title": str(r.get("title") or r["url"]),
                                "url": str(r["url"])})
    return {"text": _result_text(out), "sources": sources}


# ============================================================
# 主问答弱命中补题
# ============================================================
_SYSTEM = (
    "你是学习助手。用户的问题在本地知识库中没有找到相关资料，"
    "下面是联网检索到的参考资料。请基于这些资料回答用户问题；"
    "资料不足以回答的部分按你的知识补充，但不要编造来源链接。"
    "回答保持简洁，使用中文。"
)


def enhance_chat(question, answer, history=None):
    """弱命中联网补题：检索 → 回灌 LLM 生成增强答案。

    参数：
        question: 用户原问题
        answer: 原链路（agent_loop.run_chat_pipeline）的答案，作为兜底
        history: 可选多轮历史（同 /api/chat 语义）

    返回：
        {"answer": 增强答案, "web_sources": [...], "source": "web"}
        任何失败返回 None —— 调用方保持原答案原样返回。
    """
    if not available():
        return None
    got = web_search(question)
    if not got or not (got.get("text") or "").strip():
        return None

    try:
        from core.llm import chat
    except Exception:
        return None

    messages = [{"role": "system",
                 "content": _SYSTEM + "\n\n联网资料：\n" + got["text"]}]
    for h in (history or [])[-8:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    try:
        enhanced = chat(messages)
    except Exception as e:
        _log.warning("enhance_chat LLM 失败: %s", e)
        return None
    if not enhanced or enhanced.startswith("[LLM 不可用]"):
        return None
    return {"answer": enhanced, "web_sources": got.get("sources") or [],
            "source": "web"}
