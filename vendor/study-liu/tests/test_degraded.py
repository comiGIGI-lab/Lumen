"""LLM 降级感知测试 —— v19.2。

背景：DeepSeek 账户余额不足（HTTP 402）导致每次 LLM 调用都失败，
planner/writer/searcher 全部静默走内置模板兜底，用户看到
"不管搜什么课方案都一样"却毫无原因提示。

修复后必须保证：
1. chat() 失败原因记入 LAST_ERROR，成功清空
2. 走兜底的 Agent 记入 DEGRADED_AGENTS
3. run_plan_pipeline 降级时 result 带 _degraded（LLM 模式）
4. LLM 模式下降级结果**不写缓存**（避免模板占坑 24h）
5. mock 模式行为不变（照常缓存，离线演示「命中缓存」是特性）

注意：全部不发真实网络请求。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import core.agent_loop as agent_loop
import core.llm as llm
import tools.cache_store as cs
import tools.rate_limiter as rl


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """缓存落 tmp 目录；限流器每个用例重置。"""
    monkeypatch.setattr(cs, "_get_cache_path", lambda: str(tmp_path / "cache.json"))
    rl.reset()
    yield
    rl.reset()


class _FakeResp:
    def __init__(self, content="ok", status_code=200):
        self._content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            import requests
            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


@pytest.fixture
def llm_mode(monkeypatch):
    """让 llm 模块认为「已在 LLM 模式」，请求默认返回 402（余额不足）。"""
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "get_api_key", lambda: "sk-fake-for-test")
    monkeypatch.setattr(llm, "get_base_url", lambda: "https://example.invalid/v1")
    monkeypatch.setattr(llm, "get_model", lambda: "fake-model")
    monkeypatch.setattr(llm.requests, "post", lambda *a, **kw: _FakeResp(status_code=402))
    return monkeypatch


class TestChatLastError:
    def test_failure_records_last_error(self, llm_mode):
        out = llm.chat([{"role": "user", "content": "q"}])
        assert out.startswith("[LLM 不可用]")
        assert llm.LAST_ERROR

    def test_402_mentions_balance(self, llm_mode):
        """核心回归：402 必须给出「余额不足」的可读解释。"""
        llm.chat([{"role": "user", "content": "q"}])
        assert "余额不足" in llm.LAST_ERROR

    def test_success_clears_last_error(self, llm_mode):
        llm.chat([{"role": "user", "content": "q"}])
        assert llm.LAST_ERROR
        # 换成 200 成功响应
        llm_mode.setattr(
            llm.requests, "post", lambda *a, **kw: _FakeResp(content="ok"),
        )
        llm.chat([{"role": "user", "content": "q"}])
        assert llm.LAST_ERROR == ""

    def test_mock_mode_records_reason(self, monkeypatch):
        monkeypatch.setattr(llm, "is_mock", lambda: True)
        out = llm.chat([{"role": "user", "content": "q"}])
        assert out.startswith("[LLM 不可用]")
        assert "mock" in llm.LAST_ERROR


class TestDegradedAgents:
    def test_planner_fallback_marks_degraded(self, monkeypatch):
        llm.reset_degraded()
        monkeypatch.setattr(llm, "is_mock", lambda: True)
        from agents.planner import plan_outline
        outline = plan_outline("某课程")
        assert outline  # 兜底大纲照常返回
        assert "planner" in llm.DEGRADED_AGENTS

    def test_writer_fallback_marks_degraded(self, monkeypatch):
        llm.reset_degraded()
        monkeypatch.setattr(llm, "is_mock", lambda: True)
        from agents.writer import write_plan
        plan = write_plan("某课程", ["第一章 x", "第二章 y", "第三章 z"])
        assert plan
        assert "writer" in llm.DEGRADED_AGENTS

    def test_reset_degraded_clears(self, monkeypatch):
        llm.reset_degraded()
        llm.mark_degraded("planner")
        llm.LAST_ERROR = "x"
        llm.reset_degraded()
        assert llm.DEGRADED_AGENTS == set()
        assert llm.LAST_ERROR == ""


class TestPipelineDegraded:
    def test_llm_mode_degraded_result_has_flag_and_no_cache(self, llm_mode):
        """LLM 模式全兜底 → result 带 _degraded，且不写缓存。"""
        llm.reset_degraded()
        r = agent_loop.run_plan_pipeline("降级测试课程", profile={"level": "入门"})
        assert r.get("_degraded", {}).get("agents")
        assert "余额不足" in r["_degraded"]["error"]
        # 降级结果绝不进缓存（否则模板占坑 24h，充值后仍命中旧模板）
        assert cs.get_cached("降级测试课程", {"level": "入门"}) is None

    def test_llm_mode_success_caches_without_flag(self, llm_mode):
        """LLM 正常 → 无 _degraded，照常写缓存。"""
        llm.reset_degraded()
        llm_mode.setattr(
            llm.requests, "post",
            lambda *a, **kw: _FakeResp(
                content="第1天：预习A\n第2天：学习B\n第3天：练习C\n第4天：复盘D\n第5天：总结E",
            ),
        )
        r = agent_loop.run_plan_pipeline("正常测试课程", profile={"level": "入门"})
        assert "_degraded" not in r
        cached = cs.get_cached("正常测试课程", {"level": "入门"})
        assert cached is not None
        assert "_degraded" not in cached

    def test_mock_mode_still_caches(self, monkeypatch):
        """mock 模式：降级标记照打，但缓存行为不变（离线演示特性）。"""
        llm.reset_degraded()
        monkeypatch.setattr(llm, "is_mock", lambda: True)
        r = agent_loop.run_plan_pipeline("缓存测试课程A", profile={"level": "入门"})
        assert "planner" in llm.DEGRADED_AGENTS  # mock 下也标记
        r2 = agent_loop.run_plan_pipeline("缓存测试课程A", profile={"level": "入门"})
        assert r2.get("_from_cache") is True     # 但缓存照常工作
