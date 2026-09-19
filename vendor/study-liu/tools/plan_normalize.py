"""plan / outline 数据归一化 —— v19 统一入口。

## 为什么需要这个模块

`run_plan_pipeline()` 返回的 `plan` 在不同来源下形态不同：

1. **真实 pipeline（agents/writer.py）** —— 字符串列表：
   ```
   "第1天：通读章节内容，标记不懂的概念，预习思维导图——环境搭建 与 基础语法"
   ```
   格式：`第{天}天：{任务}——{章节} 与 {章节}`

2. **结构化输入 / 早期测试** —— dict 列表：
   ```
   {"day": 1, "title": "...", "tasks": ["..."], "chapters": ["..."]}
   ```

在此之前，每个消费方（日历导出 / 进度勾选 / Markdown 导出）都各自写了一遍
`if isinstance(day, dict) ... else ...`，且各写各的兜底，造成过两个真实缺陷：

- `tools/calendar_export.py`：非 dict 直接 `continue` → 导出的 .ics **一个事件都没有**
- `tools/progress_store.py`：非 dict 只写 `f"Day {idx}"` → 进度清单**丢失任务正文**

所以统一到这里：**解析一次，多处复用**，任何消费方都不再需要自己判断形态。

## 设计约束

- 零依赖（只用标准库）
- 永不抛异常：任何诡异输入都退化成「用原文当标题」
- 永不返回空标题：宁可回退成「第 N 天」也不让调用方丢掉这一天
"""

from __future__ import annotations

import re
from typing import Any

# ------------------------------------------------------------
# 解析用正则
# ------------------------------------------------------------
# 中文前缀：「第3天：」/「第 3 天:」/「第3天 」
_DAY_PREFIX_ZH = re.compile(r"^\s*第\s*(\d+)\s*天\s*[：:]?\s*")
# 英文前缀：「Day 3:」/「day 3.」/「Day 3-」
_DAY_PREFIX_EN = re.compile(r"^\s*[Dd]ay\s*(\d+)\s*[：:.\-]?\s*")
# 任务与章节之间的分隔：writer 用「——」，宽容接受 2 个以上破折号
_TASK_CHAPTER_SEP = re.compile(r"\s*[—\-]{2,}\s*")

# 章节之间的分隔 —— 两级策略（见 agents/writer.py 的真实产物）
#
# writer 拼接多个章节用的是**带空格的**「 与 」：
#     f"{ch1} 与 {ch2}"
# 而章节名**自身**就可能含「与」和「/」，例如：
#     "控制流程：条件/循环/异常处理"、"函数与模块化编程"
# 所以绝不能裸切「与」「/」——那会把一个章节名切成两半。
#
# 一级：带空格的连词（writer 的官方格式）
_CHAPTER_SEP_LOOSE = re.compile(r"\s+(?:与|和)\s+|\s+/\s+")
# 二级：明确的列表标点（仅在单个片段内部再拆，且这些字符不会出现在章节名里）
_CHAPTER_SEP_TIGHT = re.compile(r"\s*[、，,;；]\s*")

# 天号的合理上限（10 年），超出则认为解析错误，回退到位置序号
_MAX_DAY = 3660


def _coerce_day_number(raw: str, fallback: int) -> int:
    """把正则捕获到的天号字符串转成 int，异常/越界时回退。"""
    try:
        n = int(raw)
    except Exception:
        return fallback
    if 1 <= n <= _MAX_DAY:
        return n
    return fallback


def normalize_day(day: Any, idx: int) -> dict:
    """把 plan / outline 里的一项归一化成统一 dict。

    参数：
        day: 字符串（真实 pipeline）或 dict（结构化输入）或其它任意值
        idx: 在列表中的位置（**从 1 开始**），作为天号兜底

    返回：
        {
            "day":      int,     # 天号（解析不出时 = idx）
            "title":    str,     # 任务正文（已剥离「第N天：」前缀）；永不为空
            "tasks":    list,    # 结构化输入原样保留；字符串输入为空列表
            "chapters": list,    # 「——」之后按「与」等分隔拆出的章节
        }

    示例：
        >>> normalize_day("第3天：做题——第一章 与 第二章", 1)
        {'day': 3, 'title': '做题', 'tasks': [], 'chapters': ['第一章', '第二章']}
        >>> normalize_day({"day": 2, "title": "看书"}, 1)
        {'day': 2, 'title': '看书', 'tasks': [], 'chapters': []}
    """
    # ---- 形态 2：dict 原样透传（补齐缺失字段）----
    if isinstance(day, dict):
        out = dict(day)
        if not out.get("day"):
            out["day"] = idx
        # 必须**总是**写出 title 键：调用方统一用 out["title"] 取值，
        # 只提供 name 别名时若不同步，会 KeyError。
        out["title"] = out.get("title") or out.get("name") or f"第 {idx} 天"
        if not isinstance(out.get("tasks"), list):
            out["tasks"] = [out["tasks"]] if out.get("tasks") else []
        chapters = out.get("chapters") or out.get("chapter") or []
        if not isinstance(chapters, list):
            chapters = [chapters] if chapters else []
        out["chapters"] = chapters
        return out

    # ---- 形态 1：字符串 ----
    text = "" if day is None else str(day).strip()
    day_no = idx

    # 1) 剥离「第N天：」/「Day N:」前缀，取出显式天号
    m = _DAY_PREFIX_ZH.match(text) or _DAY_PREFIX_EN.match(text)
    if m is not None:
        day_no = _coerce_day_number(m.group(1), idx)
        text = text[m.end():].strip()

    # 2) 「任务——章节」切分
    title, chapters = text, []
    parts = _TASK_CHAPTER_SEP.split(text, maxsplit=1)
    if len(parts) == 2:
        title = parts[0].strip()
        chapters = _split_chapters(parts[1])

    return {
        "day": day_no,
        "title": title or f"第 {day_no} 天",
        "tasks": [],
        "chapters": chapters,
    }


def _split_chapters(tail: str) -> list[str]:
    """把「——」之后的章节串拆成章节名列表。

    两级切分（顺序重要）：
        1. 先按**带空格的**「 与 」/「 和 」/「 / 」切 —— writer 的官方 join 格式
        2. 再对每个片段按「、，,;；」切 —— 明确的列表标点

    绝不裸切「与」和「/」，因为章节名本身就可能包含它们。

    >>> _split_chapters("环境搭建与开发工具准备 与 基础语法与数据类型")
    ['环境搭建与开发工具准备', '基础语法与数据类型']
    >>> _split_chapters("控制流程：条件/循环/异常处理 与 函数与模块化编程")
    ['控制流程：条件/循环/异常处理', '函数与模块化编程']
    """
    out = []
    for piece in _CHAPTER_SEP_LOOSE.split(tail or ""):
        for sub in _CHAPTER_SEP_TIGHT.split(piece or ""):
            sub = sub.strip()
            if sub:
                out.append(sub)
    return out


def normalize_plan(plan: Any, skip_blank: bool = True) -> list[dict]:
    """把整个 plan 列表归一化。

    参数：
        plan: 任意形态的 plan（非 list 时返回空列表）
        skip_blank: 是否跳过 None / 纯空白项（默认 True，避免产出空事件）

    返回：
        归一化后的 dict 列表
    """
    if not isinstance(plan, list):
        return []
    out = []
    for i, day in enumerate(plan, start=1):
        if skip_blank:
            if day is None:
                continue
            if isinstance(day, str) and not day.strip():
                continue
        out.append(normalize_day(day, i))
    return out


def plan_item_label(day: Any, idx: int, max_len: int = 60) -> str:
    """给 UI 清单（进度勾选 / 历史记录）生成一行可读标签。

    统一成 `Day {n} · {任务}` 形式，便于 dict / 字符串两种来源混排时对齐。

    参数：
        day: plan 里的一项
        idx: 位置（1 起）
        max_len: 超过则截断加省略号；<=0 表示不截断
    """
    norm = normalize_day(day, idx)
    label = f"Day {norm['day']} · {norm['title']}"
    if max_len > 0 and len(label) > max_len:
        label = label[: max_len - 1].rstrip() + "…"
    return label


def outline_item_title(chapter: Any, idx: int) -> str:
    """给大纲的一项生成标题（与 plan 同源的归一化思路）。"""
    if isinstance(chapter, dict):
        return chapter.get("title") or chapter.get("name") or f"第{idx}章"
    text = "" if chapter is None else str(chapter).strip()
    return text or f"第{idx}章"


# ------------------------------------------------------------
# 向后兼容别名：calendar_export 早期把 _normalize_day 当作私有函数，
# 保留别名避免外部/测试代码 import 失败。
# ------------------------------------------------------------
_normalize_day = normalize_day
_normalize_plan = normalize_plan
