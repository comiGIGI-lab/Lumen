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
        """未知课程：后端按类型拼接 B站 / 豆瓣 / MOOC，标题 URL 编码。"""
        from urllib.parse import quote_plus
        result = search_resources("量子计算导论")
        assert len(result) >= 2
        encoded = quote_plus("量子计算导论")
        assert any("search.bilibili.com" in (r.get("url") or "") and encoded in r["url"] for r in result)
        assert any("book.douban.com" in (r.get("url") or "") and encoded in r["url"] for r in result)
        assert any("icourse163.org" in (r.get("url") or "") and encoded in r["url"] for r in result)

    def test_builtin_keeps_real_url(self):
        """内置库已有的真实链接不覆盖（模板资产）。"""
        result = search_resources("Python")
        kept = [r for r in result if "liaoxuefeng.com" in (r.get("url") or "")]
        assert kept, result

    def test_builtin_empty_url_filled_by_type(self):
        """内置库空 url 按类型拼接；书籍走豆瓣，标题编码。"""
        from urllib.parse import quote_plus
        result = search_resources("机器学习")
        books = [r for r in result if r.get("type") == "书籍"]
        assert books
        for r in books:
            assert "book.douban.com" in r["url"]
            assert quote_plus(r["title"]) in r["url"]

    def test_llm_url_discarded(self, monkeypatch):
        """LLM 即使写了 url 也丢弃，改由后端按类型拼接。"""
        import agents.searcher as s
        monkeypatch.setattr(s, "is_mock", lambda: False)
        monkeypatch.setattr(
            s, "generate",
            lambda prompt: '{"resources":['
            '{"title":"吴恩达机器学习","type":"视频","url":"https://fake.example/404","intro":"斯坦福公开课"},'
            '{"title":"机器学习（周志华）","type":"书籍","link":"https://fake.example/book"}'
            ']}',
        )
        result = s.search_resources("机器学习")
        assert len(result) >= 2
        assert all("fake.example" not in (r.get("url") or "") for r in result)
        videos = [r for r in result if r["type"] == "视频"]
        books = [r for r in result if r["type"] == "书籍"]
        assert videos and "search.bilibili.com" in videos[0]["url"]
        assert books and "book.douban.com" in books[0]["url"]
        assert videos[0].get("intro")

    def test_type_substring_video_course_goes_bilibili(self):
        """模型写「视频课程」也按视频走 B 站，标题编码。"""
        from urllib.parse import quote_plus
        from agents.searcher import url_for
        title = "吴恩达机器学习"
        url = url_for("视频课程", title)
        assert "search.bilibili.com" in url
        assert quote_plus(title) in url
        book = url_for("教材书籍", "机器学习（周志华）")
        assert "book.douban.com" in book
        other = url_for("公开课", "线性代数")
        assert "icourse163.org" in other
        assert quote_plus("线性代数") in other


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
        # v2: 关掉 URL 校验，测试纯结构（url="" 不会触发 HEAD）
        ok, comments, _ = review(result, check_urls=False)
        assert ok is True
        assert len(comments) == 0

    def test_review_fail_outline(self):
        """大纲不足 3 章不通过。"""
        result = {
            "outline": ["第一章"],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments, _ = review(result, check_urls=False)
        assert ok is False
        assert any("大纲" in c for c in comments)

    def test_review_fail_resources(self):
        """资源不足 2 条不通过。"""
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [{"title": "a"}],
            "plan": ["第1天"] * 5,
        }
        ok, comments, _ = review(result, check_urls=False)
        assert ok is False
        assert any("资源" in c for c in comments)

    def test_review_fail_plan(self):
        """计划不足 5 天不通过。"""
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [{"title": "a"}, {"title": "b"}],
            "plan": ["第1天", "第2天"],
        }
        ok, comments, _ = review(result, check_urls=False)
        assert ok is False
        assert any("计划" in c for c in comments)

    def test_review_url_check_removes_dead(self, monkeypatch):
        """v2: 非 2xx / 空 URL 应被剔除并计入 comments。"""
        import agents.reviewer as rv

        def fake_head(url, timeout=5):
            return (url.endswith("/ok"), 200 if url.endswith("/ok") else 404)

        monkeypatch.setattr(rv, "_head_ok", fake_head)
        result = {
            "outline": ["第一章", "第二章", "第三章"],
            "resources": [
                {"title": "活的", "type": "网站", "url": "https://example.com/ok"},
                {"title": "死的", "type": "网站", "url": "https://example.com/404"},
                {"title": "空链", "type": "书籍", "url": ""},
            ],
            "plan": ["第1天"] * 5,
        }
        ok, comments, returned = review(result, check_urls=True)
        assert ok is False
        assert any("URL 不可达" in c for c in comments)
        assert any("资源不足" in c for c in comments)
        assert len(returned["resources"]) == 1
        assert returned["resources"][0]["title"] == "活的"

    def test_review_encodes_unquoted_chinese_before_probe(self, monkeypatch):
        """未编码中文查询串先 quote 再探测，避免 Windows UnicodeEncodeError。"""
        from urllib.parse import quote
        import agents.reviewer as rv
        captured = []

        def fake_open(req, timeout):
            captured.append(req.full_url)
            return 200

        monkeypatch.setattr(rv, "_open", fake_open)
        raw = "https://search.bilibili.com/all?keyword=线性代数"
        encoded = rv._safe_url(raw)
        assert "线性代数" not in encoded
        assert quote("线性代数") in encoded
        ok, status = rv._head_ok(raw)
        assert ok is True
        assert status == 200
        assert captured and "线性代数" not in captured[0]
