# -*- coding: utf-8 -*-
"""错误回显统一文案 —— 对用户只出固定话术，内部细节只进日志。

## 为什么要有这个文件

改造前，接口把底层异常的原文直接塞进 `error` 字段返回前端，例如：

    {"ok": false, "error": "HTTPError: HTTP 429: {'error': {'message': 'Rate limit
     reached for gpt-4o-mini...', 'type': 'insufficient_quota', ...}}"}

    {"ok": false, "error": "URLError: <urlopen error [Errno 111] Connection refused>"}

    {"ok": false, "error": "KeyError: 'plan_items'"}

这几类回显有三个问题：
  1. **泄露内部信息** —— 网关原文里带模型名、额度状态、账号类型；异常类名和
     代码里的键名属于实现细节，不该出现在用户界面
  2. **用户看不懂** ——「URLError: [Errno 111]」对使用者没有任何指导意义，
     他需要知道的是「该检查什么」，而不是异常叫什么
  3. **文案不统一** —— 同一个原因在不同调用点（searcher / reviewer / 全局兜底）
     说法各不相同，产品观感上是碎的

## 改法

出口统一走本模块的 `model_error()` / `internal_error()`，只返回固定文案；
原始异常仍然 `traceback.print_exc()` 打进后端日志（pm2 logs my-api），
**诊断能力一点没丢**，只是不再给用户看。

## 加新文案的约定

- 一句话说清「发生了什么 + 用户能做什么」，不要出现英文、类名、错误码
- 同一类问题全站共用一条，不要在调用点各写各的
"""

# ------------------------------------------------------------
# 固定文案（对外）
# ------------------------------------------------------------

MODEL_UNREACHABLE = "无法连接模型服务，请检查网络与模型配置后重试"
MODEL_HTTP_ERROR = "模型服务返回异常，请检查 API Key 与模型配置后重试"
MODEL_TIMEOUT = "模型响应超时，请稍后重试"
MODEL_RATE_LIMITED = "请求过于频繁，请稍等片刻再试"
INTERNAL_ERROR = "服务暂时不可用，请稍后重试"


def _text_of(exc) -> str:
    """拿异常的小写文本，仅用于**内部分流**，绝不返回给用户。"""
    try:
        return str(exc).lower()
    except Exception:
        return ""


def model_error(exc) -> str:
    """模型调用失败 → 固定文案。

    按异常类型分四类，给用户的建议各不相同：
      - 超时   → 让他稍后重试（重试确实可能成功）
      - 限流   → 让他等一会儿（马上重试一定还失败）
      - HTTP   → 让他查 Key 与模型名（配置类问题，重试没用）
      - 其它   → 按网络不通处理（最常见的是 Base URL 写错、断网）
    """
    import urllib.error

    name = type(exc).__name__
    low = _text_of(exc)

    if name == "HTTPError":
        code = getattr(exc, "code", 0)
        if code == 429 or "rate limit" in low or "quota" in low:
            return MODEL_RATE_LIMITED
        if code in (401, 403, 404):
            return MODEL_HTTP_ERROR
        return MODEL_HTTP_ERROR

    if name in ("timeout", "TimeoutError", "socket.timeout") or "timed out" in low:
        return MODEL_TIMEOUT
    if "rate limit" in low or "too many requests" in low:
        return MODEL_RATE_LIMITED

    return MODEL_UNREACHABLE


def internal_error(exc) -> str:
    """服务端未预期异常 → 固定文案（细节只进日志）。"""
    return INTERNAL_ERROR
