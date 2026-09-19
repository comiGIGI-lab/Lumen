# test_intent.py — 测试意图识别模块

"""意图识别测试。

v18 更新：parse_intent 返回 dict，断言改为字典格式。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core.intent import parse_intent


class TestParseIntent:
    """意图识别测试用例。"""

    def test_plan_keyword_计划(self):
        """包含"计划"关键词 → generate"""
        r = parse_intent("机器学习学习计划")
        assert r["type"] == "generate"
        assert "机器学习" in r["course"]

    def test_plan_keyword_方案(self):
        """包含"方案"关键词 → generate"""
        r = parse_intent("帮我制定数据结构学习方案")
        assert r["type"] == "generate"

    def test_plan_keyword_大纲(self):
        """包含"大纲"关键词 → generate"""
        r = parse_intent("Python 课程大纲")
        assert r["type"] == "generate"

    def test_plan_keyword_怎么学(self):
        """包含"怎么学"关键词 → generate（v18 新增）"""
        r = parse_intent("python怎么学")
        assert r["type"] == "generate"

    def test_chat_keyword_什么是(self):
        """包含"什么是"问句 → chat"""
        r = parse_intent("什么是监督学习")
        assert r["type"] == "chat"

    def test_chat_keyword_为什么(self):
        """包含"为什么"问句 → chat"""
        r = parse_intent("为什么需要归一化")
        assert r["type"] == "chat"

    def test_chat_keyword_区别(self):
        """包含"区别"问句 → chat"""
        r = parse_intent("线性回归和逻辑回归的区别")
        assert r["type"] == "chat"

    def test_chat_question_mark(self):
        """包含问号 → chat"""
        r = parse_intent("梯度下降怎么理解？")
        assert r["type"] == "chat"

    def test_chat_default_bare_topic(self):
        """v18 行为变更：单课程名默认 chat（不再默认 redirect 到 generate）"""
        r = parse_intent("python的数据结构类型")
        assert r["type"] == "chat"

    def test_chat_default_bare_name(self):
        """v18：单个词也默认 chat"""
        r = parse_intent("机器学习")
        assert r["type"] == "chat"

    def test_chat_empty(self):
        """空输入 → chat"""
        assert parse_intent("")["type"] == "chat"
        assert parse_intent("   ")["type"] == "chat"

    def test_course_field_none_on_chat(self):
        """chat 意图的 course 应为 None"""
        r = parse_intent("什么是python")
        assert r["course"] is None

    def test_course_field_set_on_generate(self):
        """generate 意图的 course 应有值"""
        r = parse_intent("Python 学习计划")
        assert r["course"] is not None
        assert len(r["course"]) > 0