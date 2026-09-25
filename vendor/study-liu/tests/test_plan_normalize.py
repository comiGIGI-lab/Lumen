"""tools/plan_normalize.py 的单元测试。

重点覆盖「真实 pipeline 输出用的是字符串 plan」这一事实，
以及由此引发的两个真实回归：

1. calendar_export 曾对字符串 `continue` → 导出的 .ics 0 个事件
2. progress_store 曾对字符串只写「Day N」→ 进度清单丢失任务正文
"""

import pytest

from tools.plan_normalize import (
    normalize_day,
    normalize_plan,
    outline_item_points,
    outline_item_title,
    plan_item_label,
)

# 真实 pipeline（agents/writer.py）产出的字符串样本
REAL_PLAN = [
    "第1天：通读章节内容，标记不懂的概念，预习思维导图——环境搭建与开发工具准备 与 基础语法与数据类型",
    "第2天：看配套视频课程，对照笔记补全关键点——基础语法与数据类型 与 控制流程：条件/循环/异常处理",
    "第3天：动手做课后习题 + 整理知识卡片（Anki）——控制流程：条件/循环/异常处理 与 函数与模块化编程",
    "第4天：完成实战小项目 / 案例练习——横跨前 4 章",
    "第5天：回顾错题与疑难，群里讨论或查资料——横跨前 5 章",
    "第6天：用 1 小时做综合训练，检验掌握程度——横跨前 6 章",
    "第7天：整理笔记 + 模拟测试 + 总结薄弱环节——横跨前 7 章",
]


class TestNormalizeDayString:
    """字符串形态（真实 pipeline）。"""

    def test_real_format_day_and_title(self):
        out = normalize_day(REAL_PLAN[0], 1)
        assert out["day"] == 1
        assert out["title"] == "通读章节内容，标记不懂的概念，预习思维导图"
        assert out["tasks"] == []
        assert "环境搭建与开发工具准备" in out["chapters"]

    def test_prefix_is_stripped(self):
        out = normalize_day("第3天：做题", 1)
        assert out["day"] == 3
        assert out["title"] == "做题"
        assert "第3天" not in out["title"]

    def test_explicit_day_beats_position(self):
        """显式「第5天」优先于列表位置。"""
        out = normalize_day("第5天：复习", 2)
        assert out["day"] == 5

    def test_chapters_split(self):
        out = normalize_day("第1天：任务——第一章 与 第二章", 1)
        assert out["chapters"] == ["第一章", "第二章"]

    def test_does_not_split_yu_inside_chapter_name(self):
        """回归：章节名内部的「与」不能被当成章节分隔符。

        writer 用「 与 」（带空格）拼接章节，而章节名自身也含「与」，
        早期裸切「与」会把「环境搭建与开发工具准备」切成两半。
        """
        out = normalize_day(
            "第1天：任务——环境搭建与开发工具准备 与 基础语法与数据类型", 1,
        )
        assert out["chapters"] == [
            "环境搭建与开发工具准备", "基础语法与数据类型",
        ]

    def test_does_not_split_slash_inside_chapter_name(self):
        """回归：「条件/循环/异常处理」是一个章节名，不该在「/」处切开。"""
        out = normalize_day(
            "第3天：做题——控制流程：条件/循环/异常处理 与 函数与模块化编程", 1,
        )
        assert out["chapters"] == [
            "控制流程：条件/循环/异常处理", "函数与模块化编程",
        ]

    def test_single_chapter(self):
        out = normalize_day("第7天：总结——横跨前 7 章", 1)
        assert out["chapters"] == ["横跨前 7 章"]

    def test_list_punctuation_still_splits(self):
        """明确的列表标点仍要拆开（便于手工书写的输入）。"""
        out = normalize_day("第1天：任务——A 与 B、C，D", 1)
        assert out["chapters"] == ["A", "B", "C", "D"]

    def test_no_separator_means_no_chapters(self):
        out = normalize_day("第1天：单纯一句话", 1)
        assert out["chapters"] == []
        assert out["title"] == "单纯一句话"

    def test_english_prefix(self):
        out = normalize_day("Day 4: read the book - chapter 2", 1)
        assert out["day"] == 4
        assert "read the book" in out["title"]

    def test_plain_string_without_prefix(self):
        out = normalize_day("没有任何格式", 3)
        assert out["day"] == 3
        assert out["title"] == "没有任何格式"

    def test_absurd_day_falls_back(self):
        out = normalize_day("第99999天：任务", 2)
        assert out["day"] == 2

    def test_zero_day_falls_back(self):
        out = normalize_day("第0天：任务", 2)
        assert out["day"] == 2


class TestNormalizeDayDict:
    """dict 形态（结构化输入 / 向后兼容）。"""

    def test_passthrough(self):
        out = normalize_day(
            {"day": 3, "title": "T", "tasks": ["a"], "chapters": ["c"]}, 1,
        )
        assert out == {"day": 3, "title": "T", "tasks": ["a"], "chapters": ["c"]}

    def test_missing_day_uses_idx(self):
        assert normalize_day({"title": "T"}, 4)["day"] == 4

    def test_name_alias(self):
        out = normalize_day({"name": "别名标题"}, 1)
        assert out["title"] == "别名标题"

    def test_single_task_wrapped_into_list(self):
        out = normalize_day({"title": "T", "tasks": "单个任务"}, 1)
        assert out["tasks"] == ["单个任务"]

    def test_chapter_alias(self):
        out = normalize_day({"title": "T", "chapter": "ch1"}, 1)
        assert out["chapters"] == ["ch1"]

    def test_none_tasks_becomes_empty_list(self):
        out = normalize_day({"title": "T", "tasks": None}, 1)
        assert out["tasks"] == []


class TestNeverEmptyTitle:
    """核心契约：永不返回空标题，否则调用方会静默丢掉这一天。"""

    @pytest.mark.parametrize("bad", [
        "", "   ", "第1天：", "第1天", "Day", None, 123, [], "——",
    ])
    def test_never_empty(self, bad):
        out = normalize_day(bad, 2)
        assert isinstance(out["title"], str)
        assert out["title"].strip()
        # 天号必须是合法的正整数（可能来自解析，也可能回退到 idx）
        assert isinstance(out["day"], int)
        assert 1 <= out["day"] <= 3660

    @pytest.mark.parametrize("bad", ["", "   ", "Day", None, 123, [], "——"])
    def test_day_falls_back_to_idx_when_unparseable(self, bad):
        """这些输入里没有可解析的天号 → 必须回退到位置 idx。"""
        assert normalize_day(bad, 2)["day"] == 2

    def test_parseable_prefix_keeps_its_own_day(self):
        """「第1天：」虽然正文为空，但天号是真解析出来的，不该被改成 idx。"""
        out = normalize_day("第1天：", 2)
        assert out["day"] == 1
        assert out["title"] == "第 1 天"

    def test_empty_dict_title(self):
        assert normalize_day({}, 3)["title"] == "第 3 天"


class TestNormalizePlan:
    def test_real_pipeline_plan_all_seven_days(self):
        out = normalize_plan(REAL_PLAN)
        assert len(out) == 7
        assert [d["day"] for d in out] == [1, 2, 3, 4, 5, 6, 7]
        assert all(d["title"].strip() for d in out)

    def test_skips_none_and_blank(self):
        out = normalize_plan([None, "第1天：有内容", "", "   ", "第2天：也有"])
        assert len(out) == 2
        assert out[0]["title"] == "有内容"
        assert out[1]["title"] == "也有"

    def test_skip_blank_false_keeps_none(self):
        out = normalize_plan([None, "第1天：x"], skip_blank=False)
        assert len(out) == 2

    def test_non_list_returns_empty(self):
        assert normalize_plan("not a list") == []
        assert normalize_plan(None) == []
        assert normalize_plan(123) == []

    def test_mixed_shapes(self):
        """字符串和 dict 混排也要能处理（历史数据/迁移场景）。"""
        out = normalize_plan([
            {"day": 1, "title": "dict 天"},
            "第2天：字符串天",
        ])
        assert len(out) == 2
        assert out[0]["title"] == "dict 天"
        assert out[1]["title"] == "字符串天"


class TestPlanItemLabel:
    def test_label_format(self):
        assert plan_item_label("第3天：做题", 1) == "Day 3 · 做题"

    def test_truncation(self):
        label = plan_item_label("第1天：" + "很长" * 60, 1, max_len=20)
        assert len(label) <= 20
        assert label.endswith("…")

    def test_no_truncation_when_max_len_zero(self):
        label = plan_item_label("第1天：做题", 1, max_len=0)
        assert label == "Day 1 · 做题"

    def test_uses_position_for_dict_without_day(self):
        assert plan_item_label({"title": "T"}, 6) == "Day 6 · T"


class TestOutlineItemTitle:
    def test_string(self):
        assert outline_item_title("第一章 绪论", 1) == "第一章 绪论"

    def test_dict(self):
        assert outline_item_title({"title": "T"}, 1) == "T"

    def test_empty_string_falls_back(self):
        assert outline_item_title("", 5) == "第5章"

    def test_none_falls_back(self):
        assert outline_item_title(None, 2) == "第2章"


class TestOutlineItemPoints:
    """章节要点：v20 起大纲项是 {"title","points"} 对象。"""

    def test_points_from_dict(self):
        assert outline_item_points({"title": "T", "points": ["a", "b"]}) == ["a", "b"]

    def test_items_alias(self):
        assert outline_item_points({"title": "T", "items": ["a"]}) == ["a"]

    def test_single_string_wrapped(self):
        assert outline_item_points({"title": "T", "points": "单个要点"}) == ["单个要点"]

    def test_blank_filtered(self):
        assert outline_item_points({"title": "T", "points": ["a", "", "  ", "b"]}) == ["a", "b"]

    def test_string_chapter_has_no_points(self):
        assert outline_item_points("第一章 绪论") == []

    def test_none_has_no_points(self):
        assert outline_item_points(None) == []


class TestConsumerRegressions:
    """两个曾被这个数据形态坑到的消费方的回归测试。"""

    def test_calendar_export_renders_string_plan(self):
        """回归：字符串 plan 必须渲染出 VEVENT，不能是空日历。"""
        from tools.calendar_export import count_events, render_ics

        ics = render_ics({"course": "数据结构", "plan": REAL_PLAN},
                         start_date="2026-09-20")
        assert count_events(ics) == 7
        assert "DTSTART;VALUE=DATE:20260920" in ics
        assert "DTSTART;VALUE=DATE:20260926" in ics

    def test_progress_store_keeps_task_text(self):
        """回归：进度清单不能只显示「Day N」，必须带上任务正文。"""
        from tools.progress_store import _plan_to_progress

        items = _plan_to_progress(REAL_PLAN)
        assert len(items) == 7
        assert items[0]["title"].startswith("Day 1 · ")
        assert "通读章节内容" in items[0]["title"]
        # 关键断言：不是只有「Day 1」这种空壳
        assert items[0]["title"] != "Day 1"

    def test_markdown_export_keeps_task_text(self):
        """回归：Markdown 里不能出现 `### Day 1 — Day 1` 这种重复标题。"""
        from tools.markdown_export import render_plan_markdown

        md = render_plan_markdown({"course": "数据结构", "plan": REAL_PLAN})
        assert "### Day 1 — Day 1" not in md
        assert "通读章节内容" in md
        assert "环境搭建与开发工具准备" in md
