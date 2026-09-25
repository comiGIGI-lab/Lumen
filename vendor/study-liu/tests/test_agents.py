# test_agents.py — 测试三个 Agent 的输出格式

"""Agent 测试：用 mock 模式（不真调大模型）测三个 Agent 返回的格式对不对。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from urllib.parse import quote

# 确保 mock 模式
os.environ["LLM_PROVIDER"] = "mock"

from agents.planner import plan_outline
from agents.searcher import search_resources, _parse_resources_from_llm, _search_url
from agents.writer import write_plan
from agents.reviewer import review


def _titles(outline):
    """从大纲里取章节名（章节项从 v20 起是 dict，兼容旧字符串）。"""
    out = []
    for ch in outline:
        if isinstance(ch, dict):
            out.append(ch.get("title") or ch.get("name") or "")
        else:
            out.append(str(ch))
    return out


def _ch(title, n=3):
    """造一个带 n 条要点的章节对象。"""
    return {"title": title, "points": [f"{title}-要点{i}" for i in range(1, n + 1)]}


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

    def test_outline_items_are_chapter_objects(self):
        """大纲每项是章节对象，含 title 与至少 3 条非空要点。"""
        result = plan_outline("数据结构")
        for item in result:
            assert isinstance(item, dict), f"章节应是对象，实际：{type(item)}"
            assert isinstance(item.get("title"), str) and item["title"].strip()
            points = item.get("points")
            assert isinstance(points, list)
            assert len(points) >= 3
            assert all(isinstance(p, str) and p.strip() for p in points)

    def test_outline_points_are_not_placeholder(self):
        """要点不能是「要点待补充」这类空话。"""
        result = plan_outline("操作系统")
        joined = " ".join(p for item in result for p in item["points"])
        assert "要点待补充" not in joined
        assert "暂无要点" not in joined

    def test_outline_contains_course_name(self):
        """大纲包含课程名（兜底数据第一章带课程前缀）。"""
        result = plan_outline("操作系统")
        combined = " ".join(_titles(result))
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


class TestSearcherUrlIsProgramGenerated:
    """v20：模型只给 title/type，url 一律由程序按标题拼搜索链接。"""

    def test_video_goes_to_bilibili_search(self):
        title = "吴恩达机器学习"
        url = _search_url(title, "视频")
        assert url.startswith("https://search.bilibili.com/")
        assert quote(title) in url

    def test_book_goes_to_douban_search(self):
        title = "机器学习（周志华）"
        url = _search_url(title, "书籍")
        assert "douban.com" in url
        assert quote(title) in url

    def test_other_goes_to_mooc_search(self):
        title = "CS188 人工智能导论"
        url = _search_url(title, "教程")
        assert "icourse163.org" in url
        assert quote(title) in url

    def test_model_url_is_discarded(self):
        """模型返回的 url 必须被丢弃，改由程序按标题生成。"""
        text = (
            '{"resources": ['
            '{"title": "机器学习", "type": "书籍", "url": "https://example.com/fake"},'
            '{"title": "统计学习方法", "type": "书籍", "url": "https://evil.test"}'
            ']}'
        )
        out = _parse_resources_from_llm(text, course="机器学习")
        assert len(out) == 2, "应解析出 2 条资源"
        for res in out:
            assert "example.com" not in res["url"]
            assert "evil.test" not in res["url"]
        # 书籍 → 豆瓣搜索
        assert all("douban.com" in r["url"] for r in out)

    def test_off_topic_resource_dropped(self):
        """课程名对不上的资源丢掉。"""
        text = (
            '{"resources": ['
            '{"title": "机器学习实战", "type": "书籍"},'
            '{"title": "红楼梦", "type": "书籍"}'
            ']}'
        )
        out = _parse_resources_from_llm(text, course="机器学习")
        titles = [r["title"] for r in out]
        assert "机器学习实战" in titles
        assert "红楼梦" not in titles


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

    def test_writer_accepts_object_outline(self):
        """v20：大纲是章节对象时，计划里要用 title（不能出现 dict 字面量）。"""
        outline = [_ch("环境搭建"), _ch("基础语法")]
        result = write_plan("Python", outline)
        joined = " ".join(result)
        assert "环境搭建" in joined
        assert "{" not in joined and "points" not in joined

    def test_writer_still_accepts_string_outline(self):
        """旧的纯字符串大纲仍要兼容（不抛异常）。"""
        result = write_plan("Python", ["第1章 环境", "第2章 语法"])
        assert isinstance(result, list)
        assert len(result) >= 5


class TestReviewer:
    """Reviewer Agent 测试。"""

    def test_review_pass(self):
        """合格的结果通过检查。"""
        result = {
            "outline": [_ch("第一章"), _ch("第二章"), _ch("第三章")],
            "resources": [{"title": "a", "type": "书", "url": ""}, {"title": "b", "type": "视频", "url": ""}],
            "plan": ["第1天", "第2天", "第3天", "第4天", "第5天"],
        }
        ok, comments = review(result)
        assert ok is True
        assert len(comments) == 0

    def test_review_fail_outline(self):
        """大纲不足 3 章不通过。"""
        result = {
            "outline": [_ch("第一章")],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments = review(result)
        assert ok is False
        assert any("大纲" in c for c in comments)

    def test_review_fail_thin_points(self):
        """每一章都要有至少 2 条非空要点，缺了就判失败。"""
        result = {
            "outline": [
                {"title": "第一章", "points": ["只有一个要点"]},
                {"title": "第二章", "points": ["a", "b"]},
                {"title": "第三章", "points": ["", "   "]},  # 全空 = 0 条
            ],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments = review(result)
        assert ok is False
        assert any("要点" in c for c in comments)

    def test_review_fail_resources(self):
        """资源不足 2 条不通过。"""
        result = {
            "outline": [_ch("第一章"), _ch("第二章"), _ch("第三章")],
            "resources": [{"title": "a"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments = review(result)
        assert ok is False
        assert any("资源" in c for c in comments)

    def test_review_fail_plan(self):
        """计划不足 5 天不通过。"""
        result = {
            "outline": [_ch("第一章"), _ch("第二章"), _ch("第三章")],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天", "第2天"],
        }
        ok, comments = review(result)
        assert ok is False
        assert any("计划" in c for c in comments)
