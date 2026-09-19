"""markdown_export.py 单元测试。"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.markdown_export import (
    render_plan_markdown,
    export_plan_to_file,
    suggest_filename,
)


SAMPLE_RESULT = {
    "course": "Python 入门",
    "outline": [
        {"title": "基础语法", "points": ["变量", "数据类型"]},
        {"title": "控制流", "points": ["if", "for"]},
        "字符串与列表",  # 字符串也应兼容
    ],
    "resources": [
        {"title": "Python 官方文档", "type": "教程", "url": "https://docs.python.org/"},
        {"title": "Python编程：从入门到实践", "type": "书籍", "url": ""},
    ],
    "plan": [
        {"title": "环境与 hello world", "tasks": ["装 Python", "写第一个脚本"]},
        {"title": "数据类型", "tasks": ["int/str/list"]},
    ],
}


class TestRenderPlanMarkdown:
    """渲染 Markdown 文本。"""

    def test_renders_course_title(self):
        md = render_plan_markdown(SAMPLE_RESULT)
        assert "# 📘 Python 入门 学习方案" in md

    def test_renders_meta_block(self):
        md = render_plan_markdown(SAMPLE_RESULT, generated_at="2026-09-18 16:00:00")
        assert "2026-09-18 16:00:00" in md
        assert "章节数：**3**" in md
        assert "资源数：**2**" in md
        assert "计划天数：**2**" in md

    def test_renders_outline_chapters(self):
        md = render_plan_markdown(SAMPLE_RESULT)
        assert "## 第 1 章 — 基础语法" in md
        assert "- 变量" in md
        assert "## 第 3 章 — 字符串与列表" in md

    def test_renders_resources_table(self):
        md = render_plan_markdown(SAMPLE_RESULT)
        assert "| 标题 | 类型 | 链接 |" in md
        assert "| Python 官方文档 | 教程 | https://docs.python.org/ |" in md
        assert "| Python编程：从入门到实践 | 书籍 | — |" in md

    def test_renders_plan_tasks(self):
        md = render_plan_markdown(SAMPLE_RESULT)
        assert "### Day 1 — 环境与 hello world" in md
        assert "- [ ] 装 Python" in md
        assert "### Day 2 — 数据类型" in md

    def test_empty_result(self):
        """空 result 应仍能渲染出骨架。"""
        md = render_plan_markdown(
            {"course": "X", "outline": [], "resources": [], "plan": []},
        )
        assert "# 📘 X 学习方案" in md
        assert "（暂无大纲）" in md
        assert "（暂无推荐资源）" in md
        assert "（暂无每日计划）" in md

    def test_missing_keys(self):
        """result 字段不全应仍能渲染，不抛异常。"""
        md = render_plan_markdown({"course": "Y"})
        assert "# 📘 Y 学习方案" in md

    def test_override_course(self):
        """course 参数覆盖 result['course']。"""
        md = render_plan_markdown(SAMPLE_RESULT, course="机器学习")
        assert "# 📘 机器学习 学习方案" in md
        assert "Python 入门" not in md.split("学习方案")[0]


class TestExportPlanToFile:
    """导出到文件。"""

    def test_export_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.md")
            written = export_plan_to_file(SAMPLE_RESULT, path)
            assert os.path.exists(written)
            with open(written, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# 📘 Python 入门 学习方案" in content

    def test_export_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "a", "b", "c", "plan.md")
            written = export_plan_to_file(SAMPLE_RESULT, nested)
            assert os.path.exists(written)
            assert "c" in written


class TestSuggestFilename:
    """文件名清洗。"""

    def test_normal_course(self):
        assert suggest_filename("Python 入门") == "Python 入门.md"

    def test_empty_course(self):
        assert suggest_filename("") == "untitled.md"

    def test_unsafe_chars_replaced(self):
        # / \ : * ? " < > | 都被替换为 _
        out = suggest_filename("a/b\\c:d*e?f\"g<h>i|j")
        for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
            assert ch not in out

    def test_custom_ext(self):
        assert suggest_filename("test", ext=".txt") == "test.txt"