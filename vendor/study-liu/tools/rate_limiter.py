"""Rate limiter —— v19 第三梯队 #12。

设计：
- 滑动窗口：最近 N 秒内最多 M 次（默认 60 秒 10 次）
- 线程安全：所有操作加锁
- 不持久化：进程内有效（重启后归零），符合 API 限流的常规语义
- 提供装饰器风格的 wrap(...) 函数，方便接入 run_plan_pipeline

调用方式：
    from tools.rate_limiter import acquire, get_limiter
    if acquire():
        # 调用 LLM
    else:
        # 返回限流错误
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


# ============================================================
# 单例限流器
# ============================================================
class RateLimiter:
    """滑动窗口限流器。"""

    def __init__(self, max_calls: int = 10, window_sec: float = 60.0):
        self._max = max_calls
        self._window = window_sec
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """尝试获取一次调用权限。

        Returns:
            True = 允许
            False = 当前窗口已满，限流
        """
        with self._lock:
            now = time.time()
            # 弹出过期的
            while self._calls and (now - self._calls[0]) > self._window:
                self._calls.popleft()
            if len(self._calls) >= self._max:
                return False
            self._calls.append(now)
            return True

    def retry_after(self) -> float:
        """返回距下次可调用的等待秒数。"""
        with self._lock:
            if not self._calls:
                return 0.0
            now = time.time()
            # 最早一次调用距 now 的"老化时间"还剩多久？
            oldest = self._calls[0]
            elapsed = now - oldest
            remaining = self._window - elapsed
            return max(0.0, remaining)

    def current_count(self) -> int:
        """当前窗口内已用的次数。"""
        with self._lock:
            now = time.time()
            while self._calls and (now - self._calls[0]) > self._window:
                self._calls.popleft()
            return len(self._calls)

    def reset(self) -> None:
        """重置（清空所有计数）。"""
        with self._lock:
            self._calls.clear()

    def set_limit(self, max_calls: int, window_sec: float | None = None) -> None:
        """动态调整限流参数。"""
        with self._lock:
            self._max = max_calls
            if window_sec is not None:
                self._window = window_sec

    @property
    def max_calls(self) -> int:
        return self._max

    @property
    def window_sec(self) -> float:
        return self._window


# 模块级单例
_DEFAULT_LIMITER: RateLimiter | None = None
_SINGLETON_LOCK = threading.Lock()


def get_limiter() -> RateLimiter:
    """获取（或复用）默认限流器：10 次 / 60 秒。"""
    global _DEFAULT_LIMITER
    with _SINGLETON_LOCK:
        if _DEFAULT_LIMITER is None:
            _DEFAULT_LIMITER = RateLimiter(max_calls=10, window_sec=60.0)
        return _DEFAULT_LIMITER


def acquire() -> bool:
    """默认限流器 acquire 一次。"""
    return get_limiter().acquire()


def retry_after() -> float:
    """默认限流器 retry_after。"""
    return get_limiter().retry_after()


def reset() -> None:
    """重置默认限流器。"""
    get_limiter().reset()


def wrap(callable_fn: Callable, max_calls: int = 10, window_sec: float = 60.0) -> Callable:
    """装饰一个函数，被装饰后自动受限流约束。

    Usage:
        from tools.rate_limiter import wrap

        @wrap
        def call_llm(...):
            ...

    限流时抛 RuntimeError("rate_limited: ...")。
    """
    limiter = RateLimiter(max_calls, window_sec)

    def wrapped(*args, **kwargs):
        if not limiter.acquire():
            wait = limiter.retry_after()
            raise RuntimeError(
                f"rate_limited: 限流中，请在 {wait:.1f}s 后再试 "
                f"（{max_calls} 次 / {window_sec}s）",
            )
        return callable_fn(*args, **kwargs)

    wrapped.__wrapped__ = callable_fn
    wrapped.limiter = limiter
    return wrapped


# ============================================================
# 状态查询
# ============================================================
def status() -> dict:
    """返回当前限流状态（供 UI 显示）。"""
    lim = get_limiter()
    return {
        "used": lim.current_count(),
        "max": lim.max_calls,
        "window_sec": lim.window_sec,
        "remaining": max(0, lim.max_calls - lim.current_count()),
        "retry_after": lim.retry_after(),
    }