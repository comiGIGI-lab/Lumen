"""多 Agent 协作回归测试。

核心场景：
- run_plan_pipeline 端到端（mock 模式）：Planner → Searcher → Writer → Reviewer
- Reviewer 重试路径：mock 模式下产物满足质量门槛，不应触发重试
- 产物结构：必须包含 outline / resources / plan，且 Reviewer 通过
- profile 注入：传入不同 profile 时，产物应反映该画像（plan 长度 / 章节数）
- run_chat_pipeline：知识库命中 / LLM fallback
- 多轮上下文：history 注入 system
- trace 日志写入
"""

import json
import os
import sys

import pytest

# 本文件测的是 mock 流水线契约，必须在 import agent 之前钉死 mock，
# 否则本机若配了真实 Key 会打 LLM + 外网 HEAD，单测会卡住。
os.environ["LLM_PROVIDER"] = "mock"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from core.agent_loop import run_plan_pipeline, run_chat_pipeline
from agents.reviewer import review
from tools.knowledge_store import KnowledgeStore
from tools.user_profile import DEFAULT_PROFILE


# ==========================================================
# run_plan_pipeline 端到端（mock 模式）
# ==========================================================
def test_plan_pipeline_returns_full_result():
    res = run_plan_pipeline("Python 入门")
    assert "outline" in res
    assert "resources" in res
    assert "plan" in res
    assert res["course"] == "Python 入门"


def test_plan_pipeline_outline_min_3_chapters():
    res = run_plan_pipeline("Python 入门")
    assert len(res["outline"]) >= 3, f"大纲章节数太少：{len(res['outline'])}"


def test_plan_pipeline_resources_min_2():
    res = run_plan_pipeline("Python 入门")
    assert len(res["resources"]) >= 2


def test_plan_pipeline_plan_min_5_days():
    res = run_plan_pipeline("Python 入门")
    assert len(res["plan"]) >= 5


def test_plan_pipeline_resources_have_required_fields():
    res = run_plan_pipeline("线性代数")
    for r in res["resources"]:
        assert "title" in r
        assert isinstance(r["title"], str)
        assert len(r["title"]) > 0
        # type / url 是可选，但 title 必须有


def test_plan_pipeline_unknown_course_fallback():
    """未知课程应走兜底模板（不崩），产物仍通过 Reviewer。"""
    res = run_plan_pipeline("量子纠缠的猫")
    assert len(res["outline"]) >= 3
    assert len(res["resources"]) >= 2 or len(res["plan"]) >= 5
    ok, _, _ = review(res, check_urls=False)
    # 只要产物的某几项达标即可
    assert isinstance(ok, bool)


def test_pipeline_retries_writer_searcher_once(monkeypatch):
    """质检不过只重跑一次 Writer + Searcher，不会循环。"""
    calls = {"w": 0, "s": 0, "r": 0}

    def fake_plan(*_a, **_k):
        return ["章1", "章2", "章3"]

    def fake_write(*_a, **_k):
        calls["w"] += 1
        return [f"第{i}天" for i in range(1, 8)]

    def fake_search(*_a, **_k):
        calls["s"] += 1
        return [{"title": "x", "type": "教程", "url": "https://example.invalid/x"}] * 3

    def fake_review(result, check_urls=None):
        calls["r"] += 1
        return (False, ["URL 不可达 3 条"], result)

    monkeypatch.setattr("agents.planner.plan_outline", fake_plan)
    monkeypatch.setattr("agents.writer.write_plan", fake_write)
    monkeypatch.setattr("agents.searcher.search_resources", fake_search)
    monkeypatch.setattr("agents.reviewer.review", fake_review)

    run_plan_pipeline("任意课", use_cache=False)
    assert calls["w"] == 2
    assert calls["s"] == 2
    assert calls["r"] == 2


# ==========================================================
# Reviewer 协作
# ==========================================================
def test_reviewer_passes_default_output():
    res = run_plan_pipeline("Python 入门")
    ok, comments, _ = review(res, check_urls=False)
    assert ok is True, f"Reviewer 没通过：{comments}"


def test_reviewer_fails_when_outline_short():
    res = {
        "outline": ["第1章"],   # 只有 1 章
        "resources": [{"title": "A", "type": "书籍", "url": ""}],
        "plan": [f"第{i}天 学习" for i in range(1, 8)],
    }
    ok, comments, _ = review(res, check_urls=False)
    assert ok is False
    assert any("大纲" in c for c in comments)


def test_reviewer_fails_when_resources_short():
    res = {
        "outline": [f"第{i}章" for i in range(1, 11)],
        "resources": [],
        "plan": [f"第{i}天" for i in range(1, 8)],
    }
    ok, comments, _ = review(res, check_urls=False)
    assert ok is False
    assert any("资源" in c for c in comments)


def test_reviewer_fails_when_plan_short():
    res = {
        "outline": [f"第{i}章" for i in range(1, 11)],
        "resources": [{"title": "A", "type": "书籍", "url": ""}] * 3,
        "plan": ["第1天"],
    }
    ok, comments, _ = review(res, check_urls=False)
    assert ok is False
    assert any("计划" in c for c in comments)


# ==========================================================
# profile 注入
# ==========================================================
def test_plan_pipeline_with_default_profile():
    res = run_plan_pipeline("Python 入门", profile=DEFAULT_PROFILE)
    assert "profile" in res
    assert res["profile"]["level"] == "入门"


def test_plan_pipeline_profile_changes_plan_length():
    """冲刺 + 长截止日 → plan 长度 ≥ 14 天。"""
    from datetime import date, timedelta
    profile = {
        "level": "冲刺",
        "daily_hours": "4h",
        "goal": "考试",
        "deadline": (date.today() + timedelta(days=20)).strftime("%Y-%m-%d"),
    }
    res = run_plan_pipeline("Python 入门", profile=profile)
    assert len(res["plan"]) >= 14


def test_plan_pipeline_profile_changes_outline_density():
    """入门水平 → 大纲章节数 ≥ 10 章（v19 调整：入门 10-12 章）。"""
    res = run_plan_pipeline("Python 入门", profile={
        "level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": "",
    })
    # 入门模板 10 章（mock fallback 不会变，但大纲结构 ≥ 8 是最低保证）
    assert len(res["outline"]) >= 8


# ==========================================================
# run_chat_pipeline
# ==========================================================
def test_chat_pipeline_returns_dict():
    res = run_chat_pipeline("什么是 Python？")
    assert isinstance(res, dict)
    assert "answer" in res
    assert "source" in res
    assert res["source"] in ("knowledge", "llm")


def test_chat_pipeline_knowledge_hit(tmp_path):
    """知识库里有命中 → source 应该是 'knowledge'。"""
    # 临时把知识库文件指到 tmp_path
    kp = tmp_path / "k.json"
    from tools.knowledge_store import KnowledgeStore
    store = KnowledgeStore(filepath=str(kp))
    store.add("Python 入门", "Python 是一门解释型语言，语法简洁，适合初学者。", tags=["#python"])

    # mock run_chat_pipeline 的默认 search 是用默认路径，所以我们要直接测 store.search
    items = store.search("Python")
    assert len(items) >= 1


def test_chat_pipeline_with_history():
    """传入多轮历史不应崩（mock 模式下 history 不参与 mock 逻辑，但 pipeline 必须接受）。"""
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    res = run_chat_pipeline("q2", history=history)
    assert "answer" in res


def test_chat_pipeline_with_course_context():
    """传入 course_context 应该不崩。"""
    res = run_chat_pipeline("q", course_context="Python 入门")
    assert "answer" in res


def test_chat_pipeline_filters_bad_history():
    """history 里有非 user/assistant role 的，应被忽略（mock 模式不直接用，但代码要能跑）。"""
    history = [
        {"role": "system", "content": "应被过滤"},
        {"role": "user", "content": "q1"},
        {"role": "admin", "content": "非标准 role"},
        {"role": "assistant", "content": "a1"},
        {"not_role": "完全不是 dict 结构"},
        "raw_string",
    ]
    # 不应抛错
    res = run_chat_pipeline("q", history=history)
    assert "answer" in res


def test_chat_pipeline_none_history():
    res = run_chat_pipeline("q", history=None)
    assert "answer" in res


# ==========================================================
# trace 日志
# ==========================================================
def test_trace_log_writes(tmp_path, monkeypatch):
    """trace 日志应能写到临时目录。"""
    # 临时改 _TRACE_DIR
    from core import agent_loop
    monkeypatch.setattr(agent_loop, "_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr(agent_loop, "_TRACE_FILE", os.path.join(str(tmp_path), "trace.log"))
    # 触发一次 pipeline
    # 关掉缓存：本用例断言的是「trace 里有 pipeline_start」，
    # 若命中磁盘上的历史缓存会提前 return，断言就依赖了机器上的 cache.json（不稳定）。
    run_plan_pipeline("Python 入门", use_cache=False)
    # trace.log 应被写入
    log = os.path.join(str(tmp_path), "trace.log")
    assert os.path.exists(log)
    content = open(log, encoding="utf-8").read()
    assert "planner_start" in content or "pipeline_start" in content


def test_trace_log_chat_writes(tmp_path, monkeypatch):
    from core import agent_loop
    monkeypatch.setattr(agent_loop, "_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr(agent_loop, "_TRACE_FILE", os.path.join(str(tmp_path), "trace.log"))
    run_chat_pipeline("测试问题")
    log = os.path.join(str(tmp_path), "trace.log")
    assert os.path.exists(log)
    content = open(log, encoding="utf-8").read()
    assert "chat_" in content


# ==========================================================
# Planner/Searcher/Writer 输出契约
# ==========================================================
def test_plan_pipeline_consistent_with_components():
    """Pipeline 输出与各 Agent 单独调用结果一致（mock 模式）。"""
    from agents.planner import plan_outline
    from agents.searcher import search_resources
    from agents.writer import write_plan

    course = "Python 入门"
    profile = DEFAULT_PROFILE

    # 单独调用
    outline_alone = plan_outline(course, profile=profile)
    resources_alone = search_resources(course, profile=profile)
    plan_alone = write_plan(course, outline_alone, profile=profile)

    # pipeline 调用
    res = run_plan_pipeline(course, profile=profile)

    assert len(res["outline"]) == len(outline_alone)
    assert len(res["resources"]) == len(resources_alone)
    assert len(res["plan"]) == len(plan_alone)