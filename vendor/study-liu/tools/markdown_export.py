# markdown_export.py — 把生成的方案导出为 Markdown 文件

"""方案导出工具：把 run_plan_pipeline 返回的结构渲染成 Markdown 文本。"""

from datetime import datetime


def _fmt_outline(outline):
    """大纲每章渲染成 ## 章节名 + 项目列表。"""
    if not outline:
        return "（暂无大纲）"
    lines = []
    for idx, chapter in enumerate(outline, start=1):
        if isinstance(chapter, dict):
            title = chapter.get("title") or chapter.get("name") or f"第{idx}章"
            points = chapter.get("points") or chapter.get("items") or []
        else:
            title = str(chapter)
            points = []
        lines.append(f"## 第 {idx} 章 — {title}")
        for p in points:
            lines.append(f"- {p}")
        if not points:
            lines.append("- （暂无要点）")
    return "\n".join(lines)


def _fmt_resources(resources):
    """资源列表：每条 title | type | url。"""
    if not resources:
        return "（暂无推荐资源）"
    lines = ["| 标题 | 类型 | 链接 |", "| --- | --- | --- |"]
    for r in resources:
        title = r.get("title", "（未命名）") if isinstance(r, dict) else str(r)
        rtype = r.get("type", "—") if isinstance(r, dict) else "—"
        url = r.get("url", "") if isinstance(r, dict) else ""
        url_cell = url if url else "—"
        lines.append(f"| {title} | {rtype} | {url_cell} |")
    return "\n".join(lines)


def _fmt_plan(plan):
    """学习计划：每天一段，含任务列表。

    回归修复：早期实现对字符串 plan 输出 `### Day 1 — Day 1`，
    标题重复且看不出任务内容。现在统一走 tools/plan_normalize：
    - 标题取「第N天：」之后的正文
    - 「——」拆出的章节写成「> 关联章节：…」
    - 字符串原文完整保留为一条待办
    """
    from tools.plan_normalize import normalize_day

    if not plan:
        return "（暂无每日计划）"
    lines = []
    for idx, day in enumerate(plan, start=1):
        # 注意：必须把**真实位置 idx** 传进去（不能用 [day] 包一层，
        # 那样 idx 恒为 1，第二步之后的天号全错）
        norm = normalize_day(day, idx)
        title = norm.get("title") or f"Day {idx}"
        tasks = norm.get("tasks") or []
        chapters = norm.get("chapters") or []

        lines.append(f"### Day {norm.get('day', idx)} — {title}")

        if chapters:
            lines.append("> 关联章节：" + " / ".join(chapters))

        # 结构化输入的 tasks 优先；字符串输入则把原文作为唯一待办保留下来
        if not tasks and not isinstance(day, dict):
            raw = str(day).strip()
            if raw:
                lines.append(f"- [ ] {raw}")

        for t in tasks:
            lines.append(f"- [ ] {t}")

        if not tasks and not chapters and isinstance(day, dict):
            lines.append("- [ ] （待规划任务）")
    return "\n".join(lines)


def render_plan_markdown(result, course=None, generated_at=None):
    """
    把 run_plan_pipeline 返回的结果渲染成 Markdown 字符串。
    参数：
        result: {"course": str, "outline": [...], "resources": [...], "plan": [...]}
        course: 可选，覆盖 result["course"]
        generated_at: 可选，生成时间字符串；缺省取当前时间
    返回：
        Markdown 文本
    """
    course = course or result.get("course") or "未命名课程"
    generated_at = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outline = result.get("outline") or []
    resources = result.get("resources") or []
    plan = result.get("plan") or []

    md = []
    md.append(f"# 📘 {course} 学习方案")
    md.append("")
    md.append(f"> 由 study-liu 自动生成 · {generated_at}")
    md.append("")
    md.append(f"- 章节数：**{len(outline)}**")
    md.append(f"- 资源数：**{len(resources)}**")
    md.append(f"- 计划天数：**{len(plan)}**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("# 📑 课程大纲")
    md.append("")
    md.append(_fmt_outline(outline))
    md.append("")
    md.append("---")
    md.append("")
    md.append("# 🔗 推荐资源")
    md.append("")
    md.append(_fmt_resources(resources))
    md.append("")
    md.append("---")
    md.append("")
    md.append("# 📅 7 天学习计划")
    md.append("")
    md.append(_fmt_plan(plan))
    md.append("")
    md.append("---")
    md.append("")
    md.append("*本方案由 study-liu 学习智能助手生成。*")
    return "\n".join(md)


def export_plan_to_file(result, output_path, course=None, generated_at=None):
    """
    把方案导出到 Markdown 文件。
    参数：
        result: 方案 dict（同 render_plan_markdown）
        output_path: 目标路径
        course: 可选覆盖
        generated_at: 可选覆盖
    返回：
        写入文件的绝对路径
    """
    import os
    content = render_plan_markdown(result, course=course, generated_at=generated_at)
    # 确保父目录存在
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(output_path)


def suggest_filename(course, ext=".md"):
    """基于课程名生成安全文件名。"""
    if not course:
        course = "untitled"
    # 替换 Windows/Unix 都不允许的字符
    safe = "".join(
        c if c.isalnum() or c in (" ", "_", "-", "（", "）", "(", ")", "【", "】") else "_"
        for c in course
    ).strip()
    if not safe:
        safe = "untitled"
    return f"{safe}{ext}"