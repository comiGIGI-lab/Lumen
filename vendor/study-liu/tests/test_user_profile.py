"""用户画像模块测试。

覆盖：
- DEFAULT_PROFILE 结构
- load_profile 行为（不存在 / 损坏 / 字段不全 / 字段非法 → 全部归一化）
- save_profile + load_profile 往返
- format_profile_text 字段全 / 部分 / 空 / 截止日过去 / 截止日今天
- derive_total_hours：截止日缺失 / 已过 / 未来
- suggest_plan_length：< 20h / 20-60h / >= 60h / None
- is_valid_profile 真值表
"""

import json
import os
import sys
from datetime import date, timedelta

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from tools.user_profile import (
    DEFAULT_PROFILE,
    LEVELS,
    DAILY_HOURS,
    GOALS,
    load_profile,
    save_profile,
    format_profile_text,
    derive_total_hours,
    suggest_plan_length,
    is_valid_profile,
)


# ==========================================================
# DEFAULT_PROFILE
# ==========================================================
def test_default_profile_keys():
    assert set(DEFAULT_PROFILE.keys()) == {
        "level", "daily_hours", "goal", "deadline",
    }


def test_default_profile_values_in_options():
    assert DEFAULT_PROFILE["level"] in LEVELS
    assert DEFAULT_PROFILE["daily_hours"] in DAILY_HOURS
    assert DEFAULT_PROFILE["goal"] in GOALS
    assert DEFAULT_PROFILE["deadline"] == ""


def test_options_not_empty():
    assert len(LEVELS) >= 2
    assert len(DAILY_HOURS) >= 2
    assert len(GOALS) >= 2


# ==========================================================
# load_profile / save_profile
# ==========================================================
def test_load_profile_missing_returns_defaults(tmp_path):
    p = tmp_path / "p.json"
    prof = load_profile(filepath=str(p))
    assert prof == DEFAULT_PROFILE


def test_load_profile_corrupt_returns_defaults(tmp_path):
    p = tmp_path / "p.json"
    p.write_text("not json {{{", encoding="utf-8")
    prof = load_profile(filepath=str(p))
    assert prof == DEFAULT_PROFILE


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "p.json"
    profile = {
        "level": "冲刺",
        "daily_hours": "4h",
        "goal": "考试",
        "deadline": "2027-01-01",
    }
    path = save_profile(profile, filepath=str(p))
    assert path == str(p)
    loaded = load_profile(filepath=str(p))
    assert loaded == profile


def test_load_profile_normalizes_invalid_level(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps({"level": "不明", "daily_hours": "2h", "goal": "兴趣", "deadline": ""}),
        encoding="utf-8",
    )
    prof = load_profile(filepath=str(p))
    assert prof["level"] in LEVELS  # 兜底为默认


def test_load_profile_normalizes_invalid_daily_hours(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps({"level": "入门", "daily_hours": "5h", "goal": "兴趣", "deadline": ""}),
        encoding="utf-8",
    )
    prof = load_profile(filepath=str(p))
    assert prof["daily_hours"] in DAILY_HOURS


def test_load_profile_normalizes_invalid_goal(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps({"level": "入门", "daily_hours": "2h", "goal": "瞎学", "deadline": ""}),
        encoding="utf-8",
    )
    prof = load_profile(filepath=str(p))
    assert prof["goal"] in GOALS


def test_load_profile_normalizes_non_dict(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    prof = load_profile(filepath=str(p))
    assert prof == DEFAULT_PROFILE


# ==========================================================
# derive_total_hours
# ==========================================================
def test_derive_total_hours_no_deadline():
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": ""}
    assert derive_total_hours(prof) is None


def test_derive_total_hours_past_deadline():
    past = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": past}
    assert derive_total_hours(prof) == 0


def test_derive_total_hours_future():
    future = (future_days := date.today() + timedelta(days=10))
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": future.strftime("%Y-%m-%d")}
    assert derive_total_hours(prof) == 20


def test_derive_total_hours_bad_date_format():
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": "不是日期"}
    assert derive_total_hours(prof) is None


# ==========================================================
# format_profile_text
# ==========================================================
def test_format_text_basic():
    prof = {"level": "进阶", "daily_hours": "2h", "goal": "项目", "deadline": ""}
    text = format_profile_text(prof)
    assert "进阶" in text
    assert "2h" in text
    assert "项目" in text
    assert "用户画像" in text


def test_format_text_with_future_deadline():
    future = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
    prof = {"level": "冲刺", "daily_hours": "4h", "goal": "考试", "deadline": future}
    text = format_profile_text(prof)
    assert future in text
    assert "剩余" in text or "天" in text


def test_format_text_with_past_deadline():
    past = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    prof = {"level": "冲刺", "daily_hours": "4h", "goal": "考试", "deadline": past}
    text = format_profile_text(prof)
    assert "过期" in text


def test_format_text_with_today_deadline():
    today = date.today().strftime("%Y-%m-%d")
    prof = {"level": "冲刺", "daily_hours": "4h", "goal": "考试", "deadline": today}
    text = format_profile_text(prof)
    assert "今天截止" in text


# ==========================================================
# suggest_plan_length
# ==========================================================
def test_suggest_plan_length_default():
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": ""}
    assert suggest_plan_length(prof) == 7


def test_suggest_plan_length_short():
    """截止日剩 5 天 → 5 天计划（v19.1：截止日驱动，下限 5 天）"""
    future = (date.today() + timedelta(days=5))
    prof = {
        "level": "冲刺", "daily_hours": "2h",
        "goal": "考试", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 5


def test_suggest_plan_length_medium():
    """截止日剩 20 天 → 20 天计划（即使总时长只有 40h）"""
    future = (date.today() + timedelta(days=20))  # 20 * 2h = 40h
    prof = {
        "level": "冲刺", "daily_hours": "2h",
        "goal": "考试", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 20


def test_suggest_plan_length_long():
    """截止日剩 20 天 + 4h/天 → 仍是 20 天（天数由截止日决定，不由总时长放大）"""
    future = (date.today() + timedelta(days=20))
    prof = {
        "level": "冲刺", "daily_hours": "4h",
        "goal": "考试", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert derive_total_hours(prof) >= 60
    assert suggest_plan_length(prof) == 20


# ==========================================================
# v19.1：截止日驱动的计划长度
# ==========================================================
def test_suggest_plan_length_deadline_7_days():
    """截止日剩 7 天 → 7 天计划"""
    future = (date.today() + timedelta(days=7))
    prof = {
        "level": "入门", "daily_hours": "2h",
        "goal": "兴趣", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 7


def test_suggest_plan_length_deadline_14_days():
    """截止日剩 14 天 → 14 天计划（不是旧逻辑的固定档位）"""
    future = (date.today() + timedelta(days=14))
    prof = {
        "level": "进阶", "daily_hours": "1h",
        "goal": "兴趣", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 14


def test_suggest_plan_length_deadline_capped_30():
    """截止日剩 90 天 → 封顶 30 天"""
    future = (date.today() + timedelta(days=90))
    prof = {
        "level": "入门", "daily_hours": "2h",
        "goal": "兴趣", "deadline": future.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 30


def test_suggest_plan_length_deadline_today():
    """今天截止 → 5 天冲刺计划"""
    prof = {
        "level": "入门", "daily_hours": "2h",
        "goal": "兴趣", "deadline": date.today().strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 5


def test_suggest_plan_length_deadline_past():
    """截止日已过期 → 5 天冲刺计划"""
    past = (date.today() - timedelta(days=3))
    prof = {
        "level": "入门", "daily_hours": "2h",
        "goal": "兴趣", "deadline": past.strftime("%Y-%m-%d"),
    }
    assert suggest_plan_length(prof) == 5


# ==========================================================
# is_valid_profile
# ==========================================================
def test_is_valid_default_true():
    assert is_valid_profile(dict(DEFAULT_PROFILE)) is True


def test_is_valid_non_dict_false():
    assert is_valid_profile("not a dict") is False
    assert is_valid_profile(None) is False


def test_is_valid_missing_key_false():
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣"}  # 缺 deadline
    assert is_valid_profile(prof) is False


def test_is_valid_bad_date_false():
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": "bad"}
    assert is_valid_profile(prof) is False


def test_is_valid_good_date_true():
    future = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
    prof = {"level": "入门", "daily_hours": "2h", "goal": "兴趣", "deadline": future}
    assert is_valid_profile(prof) is True


# ==========================================================
# 端到端：Planner/Writer 接收 profile
# ==========================================================
def test_planner_accepts_profile():
    """planner.plan_outline 必须支持 profile 参数（向后兼容）。"""
    from agents.planner import plan_outline
    # 不传 profile：返回非空列表
    out1 = plan_outline("Python 入门")
    assert isinstance(out1, list) and len(out1) > 0
    # 传 profile：也要返回非空列表
    out2 = plan_outline("Python 入门", profile=DEFAULT_PROFILE)
    assert isinstance(out2, list) and len(out2) > 0


def test_writer_accepts_profile():
    """writer.write_plan 必须支持 profile 参数。"""
    from agents.writer import write_plan
    p1 = write_plan("Python 入门", ["第1章 环境", "第2章 语法"])
    assert len(p1) >= 5
    # 冲刺 + 4h/天 + 截止日剩 20 天 → suggest_plan_length 返回 20 天（v19.1：截止日驱动）
    profile = {
        "level": "冲刺", "daily_hours": "4h", "goal": "考试",
        "deadline": (date.today() + timedelta(days=20)).strftime("%Y-%m-%d"),
    }
    p2 = write_plan("Python 入门", ["第1章 环境", "第2章 语法"], profile=profile)
    assert len(p2) == 20


def test_searcher_accepts_profile():
    """agents.searcher.search_resources 必须支持 profile 参数。"""
    from agents.searcher import search_resources
    r = search_resources("Python 入门")
    assert isinstance(r, list)
    r2 = search_resources("Python 入门", profile=DEFAULT_PROFILE)
    assert isinstance(r2, list)


def test_pipeline_accepts_profile():
    """core.agent_loop.run_plan_pipeline 必须支持 profile 参数。"""
    from core.agent_loop import run_plan_pipeline
    # mock 模式下应至少包含 outline / resources / plan / profile
    res = run_plan_pipeline("Python 入门", profile=DEFAULT_PROFILE)
    assert "outline" in res and "resources" in res and "plan" in res
    assert "profile" in res
    assert res["profile"]["level"] == "入门"