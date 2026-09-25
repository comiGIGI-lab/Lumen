# reviewer.py — Reviewer Agent：质量检查

"""Reviewer Agent：检查生成结果是否满足质量要求。"""

from tools.plan_normalize import outline_item_points

# 每章至少要有多少条非空要点（v20 新增检查）
MIN_POINTS_PER_CHAPTER = 2


def review(result):
    """
    检查生成方案的质量。
    检查四项：
        1. outline 至少有 3 章
        2. outline 每一章至少 2 条非空要点
        3. resources 至少有 2 条
        4. plan 至少有 5 天
    参数：
        result: 包含 outline / resources / plan 的字典
    返回：
        (ok: bool, comments: list[str])
        ok 为 True 表示通过，comments 为空列表
        ok 为 False 表示不通过，comments 列出未满足的项
    """
    comments = []

    outline = result.get("outline", []) or []
    resources = result.get("resources", [])
    plan = result.get("plan", [])

    if len(outline) < 3:
        comments.append("大纲不足 3 章")

    # 每章至少 2 条非空要点 —— 否则大纲只有标题、导出里全是「要点待补充」
    thin = [
        idx for idx, ch in enumerate(outline, start=1)
        if len(outline_item_points(ch)) < MIN_POINTS_PER_CHAPTER
    ]
    if thin:
        shown = "、".join(str(i) for i in thin[:6])
        suffix = " 等" if len(thin) > 6 else ""
        comments.append(f"大纲第 {shown}{suffix} 章要点不足 {MIN_POINTS_PER_CHAPTER} 条")

    if len(resources) < 2:
        comments.append("资源不足 2 条")

    if len(plan) < 5:
        comments.append("计划不足 5 天")

    ok = len(comments) == 0
    return (ok, comments)
