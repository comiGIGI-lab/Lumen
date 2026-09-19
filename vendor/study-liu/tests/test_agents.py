# test_agents.py — 测试三个 Agent 的输出格式

"""Agent 测试：用 mock 模式（不真调大模型）测三个 Agent 返回的格式对不对。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 确保 mock 模式
os.environ["LLM_PROVIDER"] = "mock"

from agents.planner import plan_outline
from agents.searcher import search_resources
from agents.writer import write_plan
from agents.reviewer import review


class TestPlanner:
    """Planner Agent 测试。"""

    def test_outline_is_list(self):
        """大纲返回的是列表。"""
        result = plan_outline("机器学习")
        assert isinstance(result, list)

    def test_outline_has_items(self):
        """大纲至少有 3 章（mock 兜底返回 3 章）。"""
        result = plan_outline("Python")
        assert len(result) >= 3

    def test_outline_items_are_str(self):
        """大纲每项是字符串。"""
        result = plan_outline("数据结构")
        for item in result:
            assert isinstance(item, str)

    def test_outline_contains_course_name(self):
        """大纲包含课程名（兜底数据）。"""
        result = plan_outline("操作系统")
        combined = " ".join(result)
        assert "操作系统" in combined


class TestSearcher:
    """Searcher Agent 测试。"""

    def test_resources_is_list(self):
        """资源返回的是列表。"""
        result = search_resources("机器学习")
        assert isinstance(result, list)

    def test_resources_has_items(self):
        """资源至少有 2 条。"""
        result = search_resources("Python")
        assert len(result) >= 2

    def test_resource_format(self):
        """每条资源有 title / type / url 字段。"""
        result = search_resources("机器学习")
        for res in result:
            assert "title" in res
            assert "type" in res
            assert "url" in res
            assert isinstance(res["title"], str)
            assert isinstance(res["type"], str)
            assert isinstance(res["url"], str)

    def test_resource_type_valid(self):
        """资源类型是教程/书籍/视频之一。"""
        valid_types = {"教程", "书籍", "视频"}
        result = search_resources("Python")
        for res in result:
            assert res["type"] in valid_types

    def test_unknown_course_fallback(self):
        """未知课程返回通用资源：v18+ 改为真实平台清单，URL 中带课程名。"""
        result = search_resources("量子计算导论")
        assert len(result) >= 2
        # 不再断言 title 包含课程名（v18 改用知乎/B站/慕课等真实平台）
        # 改为断言：URL 中带课程名（搜索查询更精准）
        url_hits = sum(
            1 for res in result
            if "量子计算导论" in res.get("url", "")
        )
        assert url_hits >= 1


class TestWriter:
    """Writer Agent 测试。"""

    def test_plan_is_list(self):
        """计划返回的是列表。"""
        outline = plan_outline("机器学习")
        result = write_plan("机器学习", outline)
        assert isinstance(result, list)

    def test_plan_has_items(self):
        """计划至少有 5 天（兜底返回 7 天）。"""
        outline = plan_outline("Python")
        result = write_plan("Python", outline)
        assert len(result) >= 5

    def test_plan_items_are_str(self):
        """计划每项是字符串。"""
        outline = plan_outline("数据结构")
        result = write_plan("数据结构", outline)
        for item in result:
            assert isinstance(item, str)


class TestReviewer:
    """Reviewer Agent 测试。"""

    def test_review_pass(self):
        """合格的结果通过检查。"""
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [{"title": "a", "type": "书", "url": ""}, {"title": "b", "type": "视频", "url": ""}],
            "plan": ["第1天", "第2天", "第3天", "第4天", "第5天"],
        }
        ok, comments = review(result)
        assert ok is True
        assert len(comments) == 0

    def test_review_fail_outline(self):
        """大纲不足 3 章不通过。"""
        result = {
            "outline": ["第一章"],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments = review(result)
        assert ok is False
        assert any("大纲" in c for c in comments)

    def test_review_fail_resources(self):
        """资源不足 2 条不通过。"""
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [{"title": "a"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments = review(result)
        assert ok is False
        assert any("资源" in c for c in comments)

    def test_review_fail_plan(self):
        """计划不足 5 天不通过。"""
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天", "第2天"],
        }
        ok, comments = review(result)
        assert ok is False
        assert any("计划" in c for c in comments)
