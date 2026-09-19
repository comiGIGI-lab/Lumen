"""calendar_export 模块测试 —— v19 第三梯队 #13-A。"""

import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from tools.calendar_export import (
    render_ics,
    export_plan_to_ics,
    suggest_ics_filename,
    count_events,
    _escape_ics,
    _fold_line,
    _parse_date,
)


@pytest.fixture
def sample_result():
    return {
        "course": "Python 入门",
        "outline": [
            {"chapter": 1, "title": "环境搭建"},
            {"chapter": 2, "title": "基础语法"},
            {"chapter": 3, "title": "函数"},
        ],
        "resources": [],
        "plan": [
            {
                "day": 1,
                "title": "环境搭建 + 变量",
                "tasks": ["安装 Python", "Hello World"],
                "chapters": ["1", "2"],
            },
            {
                "day": 2,
                "title": "条件语句与循环",
                "tasks": ["if/else", "for/while"],
                "chapters": ["3"],
            },
            {
                "day": 3,
                "title": "函数基础",
                "tasks": ["def", "参数"],
                "chapters": ["4"],
            },
        ],
    }


class TestEscape:
    def test_backslash(self):
        assert _escape_ics("a\\b") == "a\\\\b"

    def test_comma(self):
        assert _escape_ics("a,b") == "a\\,b"

    def test_semicolon(self):
        assert _escape_ics("a;b") == "a\\;b"

    def test_newline(self):
        assert _escape_ics("a\nb") == "a\\nb"
        assert _escape_ics("a\r\nb") == "a\\nb"

    def test_none(self):
        assert _escape_ics(None) == ""

    def test_combined(self):
        s = "Line1\nLine2, with; special \\ chars"
        out = _escape_ics(s)
        assert "\\\\" in out
        assert "\\;" in out
        assert "\\," in out
        assert "\\n" in out

    def test_chinese_no_extra_escape(self):
        # 中文逗号 U+FF0C 不是 RFC 5545 TEXT 字段的分隔符（仅 ASCII 逗号需要转义）
        out = _escape_ics("你好，世界")
        assert out == "你好，世界"

    def test_english_comma_with_chinese(self):
        # 英文逗号 + 中文混合
        out = _escape_ics("你好, world")
        assert out == "你好\\, world"


class TestFoldLine:
    def test_short_line_unchanged(self):
        assert _fold_line("hello") == "hello"

    def test_long_line_folded(self):
        line = "x" * 200
        out = _fold_line(line)
        assert "\r\n" in out
        for sub in out.split("\r\n")[1:]:
            assert sub.startswith(" ")


class TestParseDate:
    def test_iso_format(self):
        d = _parse_date("2026-09-18")
        assert d == dt.date(2026, 9, 18)

    def test_slash_format(self):
        d = _parse_date("2026/09/18")
        assert d == dt.date(2026, 9, 18)

    def test_dot_format(self):
        d = _parse_date("2026.09.18")
        assert d == dt.date(2026, 9, 18)

    def test_invalid(self):
        assert _parse_date("not a date") is None

    def test_none(self):
        assert _parse_date(None) is None

    def test_empty(self):
        assert _parse_date("") is None


class TestRenderICS:
    def test_basic_structure(self, sample_result):
        ics = render_ics(sample_result, start_date="2026-10-01")
        assert ics.startswith("BEGIN:VCALENDAR\r\n")
        assert "END:VCALENDAR" in ics
        assert ics.endswith("END:VCALENDAR\r\n")

    def test_event_count(self, sample_result):
        ics = render_ics(sample_result, start_date="2026-10-01")
        assert count_events(ics) == 3

    def test_required_headers(self, sample_result):
        ics = render_ics(sample_result, start_date="2026-10-01")
        assert "VERSION:2.0" in ics
        assert "PRODID:" in ics
        assert "BEGIN:VEVENT" in ics
        assert "UID:" in ics
        assert "DTSTAMP:" in ics
        assert "DTSTART" in ics
        assert "DTEND" in ics
        assert "SUMMARY:" in ics
        assert "DESCRIPTION:" in ics

    def test_event_dates(self, sample_result):
        ics = render_ics(sample_result, start_date="2026-10-01")
        assert "DTSTART;VALUE=DATE:20261001" in ics
        assert "DTSTART;VALUE=DATE:20261002" in ics
        assert "DTSTART;VALUE=DATE:20261003" in ics
        assert "DTEND;VALUE=DATE:20261002" in ics
        assert "DTEND;VALUE=DATE:20261003" in ics
        assert "DTEND;VALUE=DATE:20261004" in ics

    def test_summary_includes_course(self, sample_result):
        ics = render_ics(sample_result)
        assert "Python 入门" in ics
        assert "Day 1" in ics

    def test_description_contains_tasks(self, sample_result):
        ics = render_ics(sample_result)
        assert "安装 Python" in ics
        assert "Hello World" in ics

    def test_alarm_included(self, sample_result):
        ics = render_ics(sample_result)
        assert "BEGIN:VALARM" in ics
        assert "END:VALARM" in ics
        assert "TRIGGER:-P1D" in ics

    def test_default_start_date_is_today(self, sample_result):
        ics = render_ics(sample_result)
        today = dt.date.today().strftime("%Y%m%d")
        assert f"DTSTART;VALUE=DATE:{today}" in ics

    def test_course_argument_overrides(self, sample_result):
        ics = render_ics(sample_result, course="覆盖的课程名")
        assert "覆盖的课程名" in ics

    def test_timezone_in_header(self, sample_result):
        ics = render_ics(sample_result, timezone_name="Asia/Shanghai")
        assert "Asia/Shanghai" in ics


class TestEdgeCases:
    def test_empty_plan(self):
        result = {"course": "Empty", "plan": []}
        ics = render_ics(result)
        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics
        assert count_events(ics) == 0

    def test_missing_course(self):
        result = {"plan": [{"day": 1, "title": "T"}]}
        ics = render_ics(result)
        assert "BEGIN:VCALENDAR" in ics
        assert "学习计划" in ics

    def test_string_day_is_rendered_not_skipped(self):
        """回归：真实 pipeline 的 plan 是**字符串列表**，必须渲染成事件。

        历史 bug：早期实现只处理 dict，对字符串直接 continue，
        导致导出的 .ics 里 VEVENT 数量为 0（日历导入后是空的）。
        详见 tools/calendar_export.py::_normalize_day。
        """
        result = {"plan": [{"day": 1, "title": "A"}, "第2天：看书——第一章", None]}
        ics = render_ics(result)
        # dict 1 条 + 字符串 1 条 = 2；只有 None 被跳过
        assert count_events(ics) == 2
        assert "看书" in ics
        assert "第一章" in ics

    def test_none_day_skipped(self):
        """None（空槽位）仍然跳过，不产生空事件。"""
        result = {"plan": [None, "第1天：只有这条"]}
        ics = render_ics(result)
        assert count_events(ics) == 1

    def test_blank_string_day_skipped(self):
        """纯空白字符串跳过。"""
        result = {"plan": ["   ", "第1天：有内容"]}
        ics = render_ics(result)
        assert count_events(ics) == 1

    def test_real_pipeline_plan_shape(self):
        """回归：直接吃 agents/writer.py 真实产出的『第N天：任务——章节』字符串。"""
        result = {
            "course": "数据结构",
            "plan": [
                "第1天：通读章节内容，标记不懂的概念——环境搭建 与 基础语法",
                "第2天：看配套视频课程，对照笔记补全关键点——基础语法 与 控制流程",
                "第3天：动手做课后习题 + 整理知识卡片（Anki）——控制流程 与 函数",
            ],
        }
        ics = render_ics(result, start_date="2026-09-20")
        assert count_events(ics) == 3
        # 日期从起始日逐天推进
        assert "DTSTART;VALUE=DATE:20260920" in ics
        assert "DTSTART;VALUE=DATE:20260922" in ics
        # 「第N天：」前缀被剥离，正文保留
        assert "SUMMARY:" in ics
        assert "通读章节内容" in ics
        assert "第1天：" not in ics
        # 「——」后的章节被拆成 Chapters 列表
        assert "环境搭建" in ics


class TestNormalizeDay:
    """_normalize_day 的单元测试（两种输入形态的统一入口）。"""

    def _norm(self, day, idx=1):
        from tools.calendar_export import _normalize_day
        return _normalize_day(day, idx)

    def test_dict_passthrough(self):
        d = {"day": 5, "title": "T", "tasks": ["a"], "chapters": ["c"]}
        out = self._norm(d, idx=1)
        assert out["day"] == 5
        assert out["title"] == "T"
        assert out["tasks"] == ["a"]
        assert out["chapters"] == ["c"]

    def test_dict_missing_day_uses_idx(self):
        out = self._norm({"title": "T"}, idx=3)
        assert out["day"] == 3

    def test_chinese_prefix_parsed(self):
        out = self._norm("第7天：复习——第7章", idx=1)
        assert out["day"] == 7
        assert out["title"] == "复习"
        assert out["chapters"] == ["第7章"]

    def test_english_prefix_parsed(self):
        out = self._norm("Day 4: read book - chapter 2", idx=1)
        assert out["day"] == 4
        assert "read book" in out["title"]

    def test_no_prefix_whole_string_is_title(self):
        out = self._norm("随便一句没有格式的话", idx=2)
        assert out["day"] == 2
        assert out["title"] == "随便一句没有格式的话"
        assert out["chapters"] == []

    def test_chapters_split_by_multiple_separators(self):
        out = self._norm("第1天：任务——A 与 B、C，D", idx=1)
        assert out["chapters"] == ["A", "B", "C", "D"]

    def test_absurd_day_number_falls_back_to_idx(self):
        """异常的「第99999天」不可信，回退到位置序号，避免日期算到几百年后。"""
        out = self._norm("第99999天：任务", idx=2)
        assert out["day"] == 2

    def test_never_returns_empty_title(self):
        assert self._norm("第1天：", idx=1)["title"] == "第 1 天"
        assert self._norm({"day": 1}, idx=1)["title"] == "第 1 天"

    def test_invalid_start_date(self, sample_result):
        with pytest.raises(ValueError, match="start_date"):
            render_ics(sample_result, start_date="not-a-date")

    def test_result_not_dict(self):
        with pytest.raises(ValueError):
            render_ics("not a dict")

    def test_plan_not_list(self):
        with pytest.raises(ValueError):
            render_ics({"plan": "not a list"})


class TestExport:
    def test_export_to_file(self, sample_result, tmp_path):
        target = tmp_path / "plan.ics"
        result_path = export_plan_to_ics(
            sample_result, str(target), start_date="2026-10-01",
        )
        assert os.path.exists(result_path)
        with open(result_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "BEGIN:VCALENDAR" in content
        assert count_events(content) == 3

    def test_export_creates_directory(self, sample_result, tmp_path):
        target = tmp_path / "subdir" / "plan.ics"
        export_plan_to_ics(sample_result, str(target))
        assert target.exists()


class TestFilename:
    def test_basic(self):
        assert suggest_ics_filename("Python") == "Python_学习计划.ics"

    def test_special_chars(self):
        assert "/" not in suggest_ics_filename("a/b")
        assert "?" not in suggest_ics_filename("a?b")
        assert "<" not in suggest_ics_filename("a<b")

    def test_empty_course(self):
        assert suggest_ics_filename("") == "study_学习计划.ics"
        assert suggest_ics_filename(None) == "study_学习计划.ics"


class TestRealisticPipeline:
    def test_plan_pipeline_output(self, tmp_path):
        result = {
            "course": "数据结构",
            "outline": [
                {"chapter": 1, "title": "数组"},
                {"chapter": 2, "title": "链表"},
                {"chapter": 3, "title": "栈和队列"},
            ],
            "resources": [
                {"name": "算法导论", "url": "https://example.com"},
            ],
            "plan": [
                {"day": 1, "title": "数组", "tasks": ["动态数组", "双指针"], "chapters": ["1"]},
                {"day": 2, "title": "链表", "tasks": ["单向", "双向"], "chapters": ["2"]},
                {"day": 3, "title": "栈", "tasks": ["栈实现"], "chapters": ["3"]},
                {"day": 4, "title": "队列", "tasks": ["循环队列"], "chapters": ["3"]},
                {"day": 5, "title": "复习", "tasks": ["刷题"], "chapters": ["1", "2", "3"]},
                {"day": 6, "title": "真题", "tasks": ["考试"], "chapters": []},
                {"day": 7, "title": "复盘", "tasks": ["总结"], "chapters": []},
            ],
        }
        ics = render_ics(result, start_date="2026-12-01")
        assert count_events(ics) == 7
        for i in range(7):
            d = (dt.date(2026, 12, 1) + dt.timedelta(days=i)).strftime("%Y%m%d")
            assert f"DTSTART;VALUE=DATE:{d}" in ics

        target = tmp_path / "data_struct.ics"
        export_plan_to_ics(result, str(target))
        assert target.stat().st_size > 0