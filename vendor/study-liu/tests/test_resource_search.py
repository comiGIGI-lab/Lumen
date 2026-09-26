"""resource_search.py 单元测试。"""

import os
import sys

# 让测试可独立运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.resource_search import search_resources


class TestResourceSearchKnown:
    """精确匹配：内置资源库应有结果。"""

    def test_exact_match_returns_known_resources(self):
        """精确匹配“机器学习”应返回 >= 3 条资源。"""
        result = search_resources("机器学习")
        assert isinstance(result, list)
        assert len(result) >= 3
        # 所有项必须含 title/type
        for item in result:
            assert "title" in item
            assert "type" in item

    def test_exact_match_python(self):
        """Python 精确匹配。"""
        result = search_resources("Python")
        assert len(result) >= 3
        titles = [r["title"] for r in result]
        assert any("Python" in t for t in titles)


class TestResourceSearchFuzzy:
    """模糊匹配：包含/被包含。"""

    def test_fuzzy_match_substring(self):
        """子串应命中。"""
        result = search_resources("深度学习入门")
        assert len(result) >= 1

    def test_fuzzy_match_reverse(self):
        """反向子串（key in course）。"""
        result = search_resources("学习机器学习的算法")
        assert len(result) >= 1


class TestResourceSearchFallback:
    """未知课留给 searcher 按类型编码拼接；这里只出标题/类型，url 留空。"""

    def test_unknown_course_returns_typed_placeholders(self):
        """未命中课程返回视频/书籍/教程各一条，url 为空。"""
        result = search_resources("这个学科真的不存在-4086")
        assert isinstance(result, list)
        assert len(result) == 3
        types = {r["type"] for r in result}
        assert types == {"视频", "书籍", "教程"}
        assert all((r.get("url") or "") == "" for r in result)

    def test_no_placeholder_title(self):
        """不再出现“XXX入门教程”这种占位符。"""
        result = search_resources("超光速引擎学")
        for item in result:
            assert "入门教程" not in item["title"]
            assert "推荐视频课程" not in item["title"]
            assert "经典教材" not in item["title"]

    def test_fallback_title_is_course_name(self):
        """占位标题用课程名，编码拼接由 searcher 负责。"""
        result = search_resources("超光速引擎学")
        assert all(r["title"] == "超光速引擎学" for r in result)
        assert all((r.get("url") or "") == "" for r in result)

    def test_fallback_url_left_empty_for_searcher(self):
        """这里不自己拼未编码中文查询串。"""
        result = search_resources("量子计算")
        for item in result:
            assert item.get("url") == ""


class TestResourceSearchEdge:
    """边界输入。"""

    def test_empty_string(self):
        """空字符串应走到通用兜底。"""
        result = search_resources("")
        # 空串可能命中模糊匹配（任何 key 都包含空串），但至少返回一个 list
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_whitespace_only(self):
        """纯空白也应返回 list。"""
        result = search_resources("   ")
        assert isinstance(result, list)