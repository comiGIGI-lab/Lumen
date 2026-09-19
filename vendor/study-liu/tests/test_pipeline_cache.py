"""缓存 / 限流接入链路测试 —— v19 第三梯队 #12 的集成层。

前面 test_cache_store.py / test_rate_limiter.py 只测了模块自身，
这里测的是**接线是否正确**：

- `run_plan_pipeline()` 是否真的命中缓存、跳过流水线、且写入缓存
- `core.llm.chat()` 是否真的被限流拦住（而不是只在模块里躺着）

注意：这两个测试都不发真实网络请求。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import core.agent_loop as agent_loop
import core.llm as llm
import tools.cache_store as cs
import tools.rate_limiter as rl


# ============================================================
# 缓存接线
# ============================================================
@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """缓存落 tmp 目录；限流器每个用例重置，避免相互影响。"""
    monkeypatch.setattr(cs, "_get_cache_path", lambda: str(tmp_path / "cache.json"))
    rl.reset()
    yield
    rl.reset()


class TestPlanPipelineCache:
    def test_second_call_hits_cache(self):
        """同一个课程 + 画像，第二次调用必须走缓存。"""
        r1 = agent_loop.run_plan_pipeline("缓存测试课程A", profile={"level": "入门"})
        assert not r1.get("_from_cache")

        r2 = agent_loop.run_plan_pipeline("缓存测试课程A", profile={"level": "入门"})
        assert r2.get("_from_cache") is True
        # 内容必须一致
        assert r2["outline"] == r1["outline"]
        assert r2["plan"] == r1["plan"]

    def test_use_cache_false_skips_cache(self):
        """use_cache=False 时既不读也不写缓存。"""
        agent_loop.run_plan_pipeline("缓存测试课程B", profile={"level": "入门"})
        r = agent_loop.run_plan_pipeline(
            "缓存测试课程B", profile={"level": "入门"}, use_cache=False,
        )
        assert not r.get("_from_cache")

    def test_different_profile_does_not_reuse_cache(self):
        """画像不同 → key 不同 → 不应命中别人的缓存。"""
        agent_loop.run_plan_pipeline("缓存测试课程C", profile={"level": "入门"})
        r = agent_loop.run_plan_pipeline(
            "缓存测试课程C", profile={"level": "冲刺"},
        )
        assert not r.get("_from_cache")

    def test_cache_is_actually_written(self):
        agent_loop.run_plan_pipeline("缓存测试课程D", profile={"level": "入门"})
        cached = cs.get_cached("缓存测试课程D", {"level": "入门"})
        assert cached is not None
        assert "plan" in cached and "outline" in cached

    def test_from_cache_flag_not_persisted(self):
        """`_from_cache` 是运行时标记，不该被写进缓存条目里。"""
        agent_loop.run_plan_pipeline("缓存测试课程E", profile={"level": "入门"})
        agent_loop.run_plan_pipeline("缓存测试课程E", profile={"level": "入门"})
        cached = cs.get_cached("缓存测试课程E", {"level": "入门"})
        assert "_from_cache" not in cached

    def test_cache_hit_still_traces_pipeline_start(self, tmp_path, monkeypatch):
        """回归：命中缓存提前 return 时，trace 里也不能丢掉 pipeline_start。

        历史问题：pipeline_start 原本写在缓存查找**之后**，一旦命中缓存就直接
        return，trace.log 里只剩一行 cache_hit —— 回放/排障时会误判成
        「请求根本没进来」，test_trace_log_writes 也会因为磁盘上有旧缓存而飘红。
        """
        monkeypatch.setattr(agent_loop, "_TRACE_DIR", str(tmp_path))
        monkeypatch.setattr(
            agent_loop, "_TRACE_FILE", os.path.join(str(tmp_path), "trace.log"),
        )

        agent_loop.run_plan_pipeline("缓存测试课程G", profile={"level": "入门"})
        agent_loop.run_plan_pipeline("缓存测试课程G", profile={"level": "入门"})

        log = os.path.join(str(tmp_path), "trace.log")
        content = open(log, encoding="utf-8").read()
        assert "cache_hit" in content
        # 两次调用各留一条开始 + 一条结束（命中缓存也要成对收口）
        assert content.count("pipeline_start") == 2
        assert content.count("pipeline_done") == 2

    def test_cache_failure_does_not_break_pipeline(self, monkeypatch):
        """缓存模块炸了也必须能正常生成（降级不中断）。"""
        def _boom(*a, **kw):
            raise RuntimeError("cache exploded")

        monkeypatch.setattr(cs, "get_cached", _boom)
        monkeypatch.setattr(cs, "put_cache", _boom)
        r = agent_loop.run_plan_pipeline("缓存测试课程F", profile={"level": "入门"})
        assert r["course"] == "缓存测试课程F"
        assert r["outline"]


# ============================================================
# 限流接线
# ============================================================
class _FakeResp:
    """假的 requests 响应，避免测试发真实请求。"""

    def __init__(self, content="ok"):
        self._content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture
def _fake_llm(monkeypatch):
    """让 chat() 认为「已在 LLM 模式」，但请求打到一个假响应上。"""
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "get_api_key", lambda: "sk-fake-for-test")
    monkeypatch.setattr(llm, "get_base_url", lambda: "https://example.invalid/v1")
    monkeypatch.setattr(llm, "get_model", lambda: "fake-model")
    monkeypatch.setattr(llm.requests, "post", lambda *a, **kw: _FakeResp())
    return monkeypatch


class TestChatRateLimit:
    def test_chat_is_rate_limited(self, _fake_llm):
        """默认 10 次 / 60 秒：第 11 次必须被拦住。"""
        for i in range(10):
            out = llm.chat([{"role": "user", "content": f"q{i}"}])
            assert "请求过于频繁" not in out, f"第 {i + 1} 次不该被限流：{out}"

        out = llm.chat([{"role": "user", "content": "第 11 次"}])
        assert "请求过于频繁" in out
        assert out.startswith("[LLM 不可用]")

    def test_rate_limit_message_mentions_wait(self, _fake_llm):
        for _ in range(10):
            llm.chat([{"role": "user", "content": "q"}])
        out = llm.chat([{"role": "user", "content": "q"}])
        assert "秒后再试" in out

    def test_reset_allows_calls_again(self, _fake_llm):
        for _ in range(10):
            llm.chat([{"role": "user", "content": "q"}])
        assert "请求过于频繁" in llm.chat([{"role": "user", "content": "q"}])
        rl.reset()
        assert "请求过于频繁" not in llm.chat([{"role": "user", "content": "q"}])

    def test_mock_mode_bypasses_rate_limit(self, monkeypatch):
        """mock 模式在限流之前就返回了，不消耗窗口。"""
        monkeypatch.setattr(llm, "is_mock", lambda: True)
        for _ in range(20):
            out = llm.chat([{"role": "user", "content": "q"}])
            assert "请求过于频繁" not in out
        assert rl.status()["used"] == 0

    def test_rate_limiter_failure_does_not_block_chat(self, _fake_llm):
        """限流模块异常不能阻断正常回答（降级必须通）。"""
        import types

        def _boom():
            raise RuntimeError("limiter exploded")

        # llm.chat 内部是「函数内 import」，所以替换 sys.modules 里的模块即可
        fake_mod = types.ModuleType("tools.rate_limiter")
        fake_mod.acquire = _boom
        fake_mod.retry_after = lambda: 0.0
        _fake_llm.setitem(sys.modules, "tools.rate_limiter", fake_mod)

        out = llm.chat([{"role": "user", "content": "q"}])
        assert "请求过于频繁" not in out
        assert out == "ok"
