# progress_store.py — 方案进度与历史记录

"""方案进度存储：data/progress.json。
结构示例：
{
  "courses": {
    "Python 入门": {
      "created_at": "2026-09-18 16:00:00",
      "last_seen_at": "2026-09-18 17:00:00",
      "outline": [
        {"title": "基础语法", "done": false},
        ...
      ],
      "plan": [
        {"title": "Day 1 - 环境", "done": true},
        ...
      ],
      "result": { ... run_plan_pipeline 的原始 result ... }
    }
  }
}
"""

import json
import os
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

# 打包兼容：数据目录统一由 core.paths 解析（exe 同目录 / 不可写时回退用户目录）
_DATA_DIR = _resolve_data_dir()
_PROGRESS_FILE = os.path.join(_DATA_DIR, "progress.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load():
    """读取 progress.json；不存在则返回空结构。"""
    if not os.path.exists(_PROGRESS_FILE):
        return {"courses": {}}
    try:
        with open(_PROGRESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "courses" not in data:
            return {"courses": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"courses": {}}


def _save(data):
    """原子写 progress.json。"""
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PROGRESS_FILE)


def save_result(course, result):
    """保存或更新一个课程的完整方案（同时记录历史）。"""
    if not course:
        return
    data = _load()
    courses = data.setdefault("courses", {})
    now = _now()
    if course in courses:
        # 已存在：只更新 last_seen 与 result，不重置进度
        courses[course]["last_seen_at"] = now
        courses[course]["result"] = result
        # 若 outline / plan 长度变化，重新初始化未完成项
        old_outline = courses[course].get("outline", [])
        old_plan = courses[course].get("plan", [])
        new_outline = _outline_to_progress(result.get("outline", []))
        new_plan = _plan_to_progress(result.get("plan", []))
        # 对齐已勾选状态
        for new_item, old_item in zip(new_outline, old_outline):
            new_item["done"] = old_item.get("done", False)
        for new_item, old_item in zip(new_plan, old_plan):
            new_item["done"] = old_item.get("done", False)
        courses[course]["outline"] = new_outline
        courses[course]["plan"] = new_plan
    else:
        # 新增
        courses[course] = {
            "created_at": now,
            "last_seen_at": now,
            "outline": _outline_to_progress(result.get("outline", [])),
            "plan": _plan_to_progress(result.get("plan", [])),
            "result": result,
        }
    _save(data)


def _outline_to_progress(outline):
    """把大纲渲染为 [{title, done}] 列表。"""
    from tools.plan_normalize import outline_item_title

    items = []
    for idx, chapter in enumerate(outline or [], start=1):
        items.append({
            "title": outline_item_title(chapter, idx),
            "done": False,
        })
    return items


def _plan_to_progress(plan):
    """把计划渲染为 [{title, done}] 列表。

    回归修复：早期实现对字符串 plan 只写 `f"Day {idx}"`，
    **任务正文全丢**，进度清单变成一排没有内容的「Day 1 / Day 2」。
    现在统一走 tools/plan_normalize，标签形如「Day 3 · 动手做课后习题」。
    """
    from tools.plan_normalize import plan_item_label

    items = []
    for idx, day in enumerate(plan or [], start=1):
        items.append({
            "title": plan_item_label(day, idx, max_len=80),
            "done": False,
        })
    return items


def list_courses():
    """列出所有已保存课程（按 last_seen_at 倒序）。"""
    data = _load()
    courses = data.get("courses", {})
    items = []
    for name, info in courses.items():
        items.append({
            "course": name,
            "created_at": info.get("created_at", ""),
            "last_seen_at": info.get("last_seen_at", ""),
        })
    items.sort(key=lambda x: x.get("last_seen_at", ""), reverse=True)
    return items


def load_result(course):
    """加载某课程的完整方案 result。"""
    data = _load()
    info = data.get("courses", {}).get(course)
    if not info:
        return None
    return info.get("result")


def get_progress(course):
    """获取课程的进度（outline + plan 的勾选状态）。"""
    data = _load()
    info = data.get("courses", {}).get(course, {})
    return {
        "outline": info.get("outline", []),
        "plan": info.get("plan", []),
    }


def set_done(course, kind, index, done):
    """
    勾选/取消某项。
    参数：
        course: 课程名
        kind: "outline" 或 "plan"
        index: 项索引
        done: True / False
    """
    data = _load()
    courses = data.setdefault("courses", {})
    info = courses.get(course)
    if not info:
        return False
    items = info.get(kind, [])
    if index < 0 or index >= len(items):
        return False
    items[index]["done"] = bool(done)
    info["last_seen_at"] = _now()
    _save(data)
    return True


def delete_course(course):
    """从历史中删除一门课程。"""
    data = _load()
    courses = data.get("courses", {})
    if course in courses:
        del courses[course]
        _save(data)
        return True
    return False


def get_stats(course):
    """统计勾选进度：返回 (done, total, ratio)。"""
    info = get_progress(course)
    outline = info["outline"]
    plan = info["plan"]
    total = len(outline) + len(plan)
    done = sum(1 for x in outline if x.get("done")) + sum(1 for x in plan if x.get("done"))
    ratio = (done / total) if total > 0 else 0.0
    return done, total, ratio