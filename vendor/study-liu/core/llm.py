# llm.py — DeepSeek 大模型封装：generate(prompt) -> str

"""大模型封装模块：调 DeepSeek API，失败返回错误说明。"""

import json
import os

import requests

from core.config import get_api_key, get_base_url, get_model, is_mock

# 单次 LLM 请求的超时秒数。
# 原来是写死的 30 秒 —— 对官方 API（通常 2~8 秒返回）够用，
# 但第三方中转网关常见 10~45 秒甚至更慢，30 秒会导致 Agent 全部超时降级，
# 界面上只显示「内置资源库（LLM 不可用时兜底）」，很难看出是超时导致的。
# 可用环境变量 LLM_TIMEOUT 覆盖。
def _llm_timeout() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT", "90"))
    except (TypeError, ValueError):
        return 90.0


LLM_TIMEOUT = _llm_timeout()

# 单次请求的 max_tokens 上限。
# 原来是写死的 2000 —— 对「非思考模型」够用，但 DeepSeek V4 系列、GLM 等
# 思考模型会先在 reasoning_content 里推理、再产出 content。实测：
#   max_tokens=2000 时，一个「列 8 个学习资源」的请求推理就用掉 2000 token
#   （reasoning_content 6289 字），finish_reason=length，**content 直接为空** ——
#   于是 searcher / writer 静默降级，而 planner（prompt 简单、推理短）却正常，
#   表现为"有的 Agent 好有的不好"，极难排查。4000 时同一请求正常结束。
# 可用环境变量 LLM_MAX_TOKENS 覆盖。
def _llm_max_tokens() -> int:
    try:
        return int(os.environ.get("LLM_MAX_TOKENS", "4000"))
    except (TypeError, ValueError):
        return 4000


LLM_MAX_TOKENS = _llm_max_tokens()


def generate(prompt):
    """
    调用大模型生成文本（单条 prompt，向后兼容保留）。
    参数：
        prompt: 输入提示词
    返回：
        大模型返回的文本字符串。如果不可用，返回以 "[LLM 不可用]" 开头的字符串。
    """
    return chat(messages=[{"role": "user", "content": prompt}])


# ============================================================
# 失败原因记录（v19.2 新增）
# 背景：LLM 失败后 planner/writer/searcher 会静默走内置模板兜底，
# 用户完全无感知，曾导致"DeepSeek 余额不足 → 不管搜什么课方案都一样"
# 却被当成 bug 反馈。现在把最近一次失败原因与降级 Agent 记在这里，
# 由 agent_loop 汇总进 result["_degraded"]，UI 显示明确警告。
# ============================================================
LAST_ERROR = ""          # 最近一次 chat 失败原因（成功时清空）
DEGRADED_AGENTS = set()  # 本次流水线中走了兜底的 Agent 名（planner/writer/searcher）


def mark_degraded(agent):
    """记录某个 Agent 走了兜底（幂等，供 planner/writer/searcher 调用）。"""
    try:
        DEGRADED_AGENTS.add(agent)
    except Exception:
        pass


def reset_degraded():
    """流水线开始时清空降级标记（线程内串行调用，进程级标记可接受）。"""
    global LAST_ERROR
    LAST_ERROR = ""
    try:
        DEGRADED_AGENTS.clear()
    except Exception:
        pass


def _fail(reason):
    """记录失败原因并返回统一格式的不可用标记。"""
    global LAST_ERROR
    LAST_ERROR = reason
    return f"[LLM 不可用] {reason}"


def chat(messages):
    """
    多轮对话调用。messages 形如 [{"role": "user|assistant|system", "content": "..."}]。
    返回大模型回复的文本，失败返回 "[LLM 不可用] xxx"（原因同步记入 LAST_ERROR）。
    """
    global LAST_ERROR
    # mock 模式：直接返回不可用标记，调用方走兜底
    if is_mock():
        return _fail("mock 模式，未配置 API Key")

    api_key = get_api_key()
    if not api_key:
        return _fail("未配置 LLM_API_KEY")

    base_url = get_base_url()
    model = get_model()
    # Base URL 兼容两种填法（以前只支持第 1 种，填成第 2 种会拼出
    # .../chat/completions/chat/completions → 404）：
    #   1) 只填到版本号 —— https://api.deepseek.com
    #                      https://open.bigmodel.cn/api/paas/v4
    #      → 自动补 /chat/completions
    #   2) 直接填完整端点 —— 很多第三方网关的文档就是直接给完整地址，
    #                       如 https://cpa.aqor.io/v1/chat/completions
    #      → 原样使用，不再拼接
    _base = (base_url or "").rstrip("/")
    if _base.endswith("/chat/completions"):
        url = _base
    else:
        url = f"{_base}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # 防御性：过滤掉非标准 role，确保 role 合法
    safe_messages = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content", "")
        if role not in ("system", "user", "assistant"):
            continue
        if not isinstance(content, str):
            content = str(content)
        safe_messages.append({"role": role, "content": content})
    if not safe_messages:
        return _fail("messages 为空")

    payload = {
        "model": model,
        "messages": safe_messages,
        "temperature": 0.7,
        "max_tokens": LLM_MAX_TOKENS,
    }

    # 滑动窗口限流：保护 API 额度，避免演示时误点把配额刷爆/被平台限流。
    # 限流模块自身出任何问题都**不能**阻断主流程，所以整体 try 包住。
    try:
        from tools.rate_limiter import acquire, retry_after
        if not acquire():
            wait = retry_after()
            return _fail(
                f"请求过于频繁（默认 10 次/60 秒），"
                f"请 {wait:.0f} 秒后再试"
            )
    except Exception:
        pass

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=LLM_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        # OpenAI 兼容格式：choices[0].message.content
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content")
        # 内容为空时必须显式判失败：静默当成功的话下游会拿到空大纲，
        # 而且日志里看不出原因（以前就是这样，表现为「某个 Agent 莫名降级」）。
        if not (content or "").strip():
            # 思考模型（DeepSeek V4 系、GLM 等）把 token 全用在推理上时，
            # content 会是空的但 reasoning_content 有大量内容 —— 这是最常见的原因，
            # 单独报出来，免得又被误判成"网关坏了"。
            if (msg.get("reasoning_content") or "").strip() or choice.get("finish_reason") == "length":
                return _fail(
                    f"模型推理占满了 max_tokens({LLM_MAX_TOKENS})，未产出正式回答"
                    f"（可调大环境变量 LLM_MAX_TOKENS）"
                )
            return _fail("模型返回空内容（网关未正常响应，请检查模型名是否可用）")
        LAST_ERROR = ""   # 成功即清空失败标记
        return content.strip()
    except requests.exceptions.Timeout:
        return _fail("请求超时")
    except requests.exceptions.ConnectionError:
        return _fail("网络连接失败")
    except requests.exceptions.HTTPError as e:
        # 补充常见 HTTP 状态码的可读解释（401=Key 无效，402=余额不足）
        hint = ""
        try:
            status = e.response.status_code
            if status == 401:
                hint = "（API Key 无效或已撤销）"
            elif status == 402:
                hint = "（账户余额不足，请到平台充值）"
            elif status == 429:
                hint = "（平台限流，稍后再试）"
        except Exception:
            pass
        return _fail(f"HTTP 错误：{e.response.status_code}{hint}")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return _fail(f"响应格式异常：{e}")
    except Exception as e:
        return _fail(f"未知错误：{e}")
