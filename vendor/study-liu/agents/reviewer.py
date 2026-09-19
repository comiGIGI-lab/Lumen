# reviewer.py — Reviewer Agent：质量检查

"""Reviewer Agent：检查生成结果是否满足质量要求。"""


def review(result):
    """
    检查生成方案的质量。
    检查三项：
        1. outline 至少有 3 章
        2. resources 至少有 2 条
        3. plan 至少有 5 天
    参数：
        result: 包含 outline / resources / plan 的字典
    返回：
        (ok: bool, comments: list[str])
        ok 为 True 表示通过，comments 为空列表
        ok 为 False 表示不通过，comments 列出未满足的项
    """
    comments = []

    outline = result.get("outline", [])
    resources = result.get("resources", [])
    plan = result.get("plan", [])

    if len(outline) < 3:
        comments.append("大纲不足 3 章")

    if len(resources) < 2:
        comments.append("资源不足 2 条")

    if len(plan) < 5:
        comments.append("计划不足 5 天")

    ok = len(comments) == 0
    return (ok, comments)
