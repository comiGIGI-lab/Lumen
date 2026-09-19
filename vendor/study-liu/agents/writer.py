# writer.py — Writer Agent：大纲 → 学习计划

"""Writer Agent：根据课程和大纲生成 7 天学习计划。"""

from core.llm import generate


# 7 天不同活动模板：避免每天复读
_DAY_ACTIVITIES = [
    "通读章节内容，标记不懂的概念，预习思维导图",
    "看配套视频课程，对照笔记补全关键点",
    "动手做课后习题 + 整理知识卡片（Anki）",
    "完成实战小项目 / 案例练习",
    "回顾错题与疑难，群里讨论或查资料",
    "用 1 小时做综合训练，检验掌握程度",
    "整理笔记 + 模拟测试 + 总结薄弱环节",
]


def write_plan(course, outline, profile=None):
    """
    根据大纲为课程生成学习计划。
    参数：
        course: 课程名
        outline: 大纲列表（字符串数组）
        profile: 可选，用户画像（决定计划天数 / 活动节奏）
    返回：
        学习计划列表（字符串数组，按天排）
    """
    # 根据画像决定天数（默认 7 天）
    days = 7
    try:
        if profile:
            from tools.user_profile import suggest_plan_length
            days = suggest_plan_length(profile)
    except Exception:
        days = 7

    # 把大纲拼成列表格式
    outline_text = "\n".join(f"- {ch}" for ch in outline)

    # 1. 尝试大模型
    profile_text = ""
    if profile:
        try:
            from tools.user_profile import format_profile_text
            profile_text = format_profile_text(profile) + "\n"
        except Exception:
            profile_text = ""

    prompt = (
        profile_text
        + f"你是学习计划助手。为「{course}」生成 {days} 天学习计划，每天任务必须不同。\n"
        + f"要求每天覆盖大纲一两个章节，并加上\"预习/视频/练习/项目/复盘\"等活动。\n"
        + f"格式\"第1天：xxx\"，每天一行，只输出计划。\n"
        + f"大纲：\n{outline_text}\n"
        + "请避免每天都是\"学习第N章 xxx\"的简单重复，要体现不同的学习活动。"
    )
    result = generate(prompt)

    # 2. 解析
    if not result.startswith("[LLM 不可用]"):
        lines = []
        for ln in result.strip().split("\n"):
            ln = ln.strip()
            if not ln:
                continue
            # 去掉 markdown 列表符号
            ln = ln.lstrip("-*·•# ").strip()
            if ln:
                lines.append(ln)
        if len(lines) >= 5:
            return lines[:days]

    # 3. 兜底：每天分配不同活动（打降级标记，供 UI 警告）
    from core import llm as _llm
    _llm.mark_degraded("writer")
    return _fallback_plan(course, outline, days=days)


def _fallback_plan(course, outline, days=7):
    """兜底：days 天活动循环 + 大纲章节轮转，确保每天不同。

    参数：
        course: 课程名
        outline: 章节列表
        days: 计划天数（默认 7，可被 profile.suggest_plan_length 覆盖）
    """
    plan = []
    chapter_count = len(outline)

    for day in range(1, days + 1):
        activity = _DAY_ACTIVITIES[(day - 1) % len(_DAY_ACTIVITIES)]
        if chapter_count == 0:
            # 没有大纲
            plan.append(f"第{day}天：{course}——{activity}")
            continue

        # 每天覆盖两章（取模轮转）
        ch1 = outline[(day - 1) % chapter_count]
        ch2 = outline[day % chapter_count] if chapter_count > 1 else None

        if day <= min(3, days) and ch2:
            plan.append(
                f"第{day}天：{activity}——"
                f"{ch1} 与 {ch2}"
            )
        else:
            # 后半段是回顾与综合
            if day >= 4:
                plan.append(
                    f"第{day}天：{activity}——"
                    f"横跨前 {min(day, chapter_count)} 章"
                )
            else:
                plan.append(f"第{day}天：{activity}——{ch1}")

    return plan
