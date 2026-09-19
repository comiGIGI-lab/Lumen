"""rate_limiter 模块测试 —— v19 第三梯队 #12。"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from tools.rate_limiter import (
    RateLimiter,
    acquire,
    retry_after,
    reset,
    status,
    wrap,
    get_limiter,
)


class TestBasicLimiter:
    """基础限流测试。"""

    def test_within_window_allows(self):
        lim = RateLimiter(max_calls=3, window_sec=60)
        assert lim.acquire() is True
        assert lim.acquire() is True
        assert lim.acquire() is True

    def test_over_window_blocks(self):
        lim = RateLimiter(max_calls=3, window_sec=60)
        for _ in range(3):
            assert lim.acquire() is True
        # 第 4 次应被拒绝
        assert lim.acquire() is False

    def test_window_expires(self):
        lim = RateLimiter(max_calls=2, window_sec=0.3)
        assert lim.acquire() is True
        assert lim.acquire() is True
        assert lim.acquire() is False
        # 等窗口过期
        time.sleep(0.4)
        assert lim.acquire() is True

    def test_retry_after(self):
        lim = RateLimiter(max_calls=1, window_sec=1.0)
        assert lim.acquire() is True
        ra = lim.retry_after()
        assert 0.0 <= ra <= 1.0

    def test_retry_after_when_empty(self):
        lim = RateLimiter(max_calls=5, window_sec=60)
        assert lim.retry_after() == 0.0


class TestCounter:
    """计数测试。"""

    def test_current_count(self):
        lim = RateLimiter(max_calls=10, window_sec=60)
        assert lim.current_count() == 0
        lim.acquire()
        lim.acquire()
        assert lim.current_count() == 2

    def test_reset(self):
        lim = RateLimiter(max_calls=2, window_sec=60)
        lim.acquire()
        lim.acquire()
        assert lim.acquire() is False
        lim.reset()
        assert lim.acquire() is True

    def test_set_limit(self):
        lim = RateLimiter(max_calls=2, window_sec=60)
        lim.set_limit(max_calls=5)
        assert lim.max_calls == 5
        lim.set_limit(max_calls=3, window_sec=30)
        assert lim.window_sec == 30


class TestStatus:
    """状态查询测试。"""

    def test_status_shape(self):
        s = status()
        assert "used" in s
        assert "max" in s
        assert "remaining" in s
        assert "retry_after" in s

    def test_status_updates(self):
        reset()
        acquire()
        acquire()
        s = status()
        assert s["used"] == 2


class TestSingleton:
    """单例测试。"""

    def test_get_limiter_returns_same(self):
        l1 = get_limiter()
        l2 = get_limiter()
        assert l1 is l2


class TestWrap:
    """wrap 装饰器测试。"""

    def test_wrap_allows_within_limit(self):
        @wrap
        def hello():
            return "hi"

        assert hello() == "hi"

    def test_wrap_blocks_over_limit(self):
        # 用一个独立的限流器，避免污染全局
        def f():
            return 1
        wrapped = wrap(f, max_calls=2, window_sec=60)
        assert wrapped() == 1
        assert wrapped() == 1
        with pytest.raises(RuntimeError, match="rate_limited"):
            wrapped()

    def test_wrap_preserves_function(self):
        @wrap
        def add(a, b):
            return a + b

        assert add(1, 2) == 3
        assert hasattr(add, "__wrapped__")
        assert add.__wrapped__(3, 4) == 7


class TestConcurrency:
    """并发测试。"""

    def test_concurrent_acquire(self):
        lim = RateLimiter(max_calls=10, window_sec=60)
        allowed = []
        lock = threading.Lock()

        def worker():
            ok = lim.acquire()
            with lock:
                allowed.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 20 个线程最多 10 个通过
        assert sum(allowed) == 10
        assert allowed.count(True) == 10
        assert allowed.count(False) == 10