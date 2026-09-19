# user_profile.py — 用户画像：水平 / 日时间 / 目标 / 截止日期

"""用户画像模块：把"想学什么"细化为"是什么样的人 / 多少时间 / 为什么学"。

设计：
- 4 个画像字段，每个有明确的可选值 + 默认值
- 持久化到 data/profile.json（与知识库 / 历史记录 同级）
- 提供 format_profile_text(profile) → 把画像拼成可读字符串，用于注入 prompt

字段定义：
    level:        入门 | 进阶 | 冲刺              默认 "入门"
    daily_hours:  1h | 2h | 4h                       默认 "2h"
    goal:         考试 | 项目 | 兴趣                  默认 "兴趣"
    deadline:     YYYY-MM-DD 或 ""（无截止日）         默认 ""

总可用时长估算（供 prompt）：
    days_left = (deadline - today).days  if  deadline  else  None
    derived_total_hours = days_left * daily_hours_h   if  days_left else None
"""

import json
import os
from datetime import datetime, date

from core.paths import data_dir as _resolve_data_dir


# ---------- 字段定义 ----------
LEVELS = ["入门", "进阶", "冲刺"]
DAILY_HOURS = ["1h", "2h", "4h"]
GOALS = ["考试", "项目", "兴趣"]

# 每日小时数映射（用于 prompt 里的"总时长估算"）
_DAILY_HOURS_NUM = {"1h": 1, "2h": 2, "4h": 4}

# 持久化路径（打包兼容，与 knowledge.json / progress.json 同级）
_DATA_DIR = _resolve_data_dir()
_PROFILE_FILE = os.path.join(_DATA_DIR, "profile.json")


# 默认画像
DEFAULT_PROFILE = {
    "level": "入门",
    "daily_hours": "2h",
    "goal": "兴趣",
    "deadline": "",
}


def _ensure_dir():
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)


def _normalize(profile):
    """保证返回值字段合法（防御性：UI 之外可能传入意外值）。"""
    if not isinstance(profile, dict):
        profile = {}
    out = dict(DEFAULT_PROFILE)
    for k in out.keys():
        v = profile.get(k, out[k])
        if k == "daily_hours" and v not in _DAILY_HOURS_NUM:
            v = out[k]
        if k == "level" and v not in LEVELS:
            v = out[k]
        if k == "goal" and v not in GOALS:
            v = out[k]
        if k == "deadline" and not isinstance(v, str):
            v = out[k]
        out[k] = v
    return out


def load_profile(filepath=None):
    """读取画像；文件不存在 / 损坏 → 返回 DEFAULT_PROFILE。"""
    path = filepath or _PROFILE_FILE
    if not os.path.exists(path):
        return dict(DEFAULT_PROFILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize(data)
    except (json.JSONDecodeError, IOError, OSError):
        return dict(DEFAULT_PROFILE)


def save_profile(profile, filepath=None):
    """保存画像到 JSON。"""
    path = filepath or _PROFILE_FILE
    _ensure_dir()
    normed = _normalize(profile)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normed, f, ensure_ascii=False, indent=2)
    return path


def _parse_date(s):
    """解析 YYYY-MM-DD；失败返回 None。"""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def derive_total_hours(profile):
    """根据截止日 + 每日时长算总可用小时数；返回 None 表示无法估算。"""
    p = _normalize(profile)
    hours_per_day = _DAILY_HOURS_NUM.get(p["daily_hours"], 0)
    if hours_per_day <= 0:
        return None
    dl = _parse_date(p["deadline"])
    if not dl:
        return None
    today = date.today()
    days_left = (dl - today).days
    if days_left <= 0:
        return 0
    return hours_per_day * days_left


def format_profile_text(profile):
    """把画像格式化成一段中文，用于注入到 prompt。

    示例：
        用户画像：入门水平；每天学习约 2 小时；目标：通过考试；
        截止日期：2026-10-30（剩余约 12 天 ≈ 24 小时）。

    """
    p = _normalize(profile)
    parts = [
        f"水平：{p['level']}",
        f"每日学习时间：{p['daily_hours']}",
        f"目标：{p['goal']}",
    ]
    dl = _parse_date(p["deadline"])
    if dl:
        today = date.today()
        days_left = (dl - today).days
        if days_left > 0:
            total_h = derive_total_hours(p)
            tail = f"（剩余约 {days_left} 天"
            if total_h:
                tail += f"，约 {total_h} 小时"
            tail += "）"
            parts.append(f"截止日期：{p['deadline']}{tail}")
        elif days_left == 0:
            parts.append(f"截止日期：{p['deadline']}（今天截止）")
        else:
            parts.append(f"截止日期：{p['deadline']}（已过期 {abs(days_left)} 天）")
    lines = "；".join(parts)
    return f"用户画像：{lines}。"


def suggest_plan_length(profile):
    """根据用户画像建议计划天数（5-30 天）。

    规则（v19.1 修复：截止日必须真正影响计划长度）：
    - 有截止日：天数 = 剩余天数，夹在 [5, 30]
      （剩 < 5 天 → 5 天冲刺；剩 > 30 天 → 封顶 30 天，避免超长清单）
    - 无截止日：按"每日时长 × 默认窗口"分档（>= 60h → 30；>= 20h → 14；否则 7）
    """
    p = _normalize(profile)
    dl = _parse_date(p["deadline"])
    if dl:
        days_left = (dl - date.today()).days
        if days_left <= 0:
            # 今天截止或已过期：给 5 天冲刺计划（Reviewer 要求 >= 5 天）
            return 5
        return min(30, max(5, days_left))

    total_h = derive_total_hours(profile)
    if total_h is None:
        return 7
    if total_h >= 60:
        return 30
    if total_h >= 20:
        return 14
    return 7


def is_valid_profile(profile):
    """画像是否合法（用于 UI 校验）。"""
    if not isinstance(profile, dict):
        return False
    for k in DEFAULT_PROFILE:
        if k not in profile:
            return False
    p = _normalize(profile)
    if p["level"] not in LEVELS:
        return False
    if p["daily_hours"] not in _DAILY_HOURS_NUM:
        return False
    if p["goal"] not in GOALS:
        return False
    if p["deadline"] and _parse_date(p["deadline"]) is None:
        return False
    return True