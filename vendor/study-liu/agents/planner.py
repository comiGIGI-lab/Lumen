# planner.py — Planner Agent：课程 → 大纲

"""Planner Agent：输入课程名，输出学习大纲（章节列表）。"""

import re

from core.llm import generate


# 课程分类：识别关键词 → 章节模板
_COURSE_TEMPLATES = {
    "programming": {
        "keywords": ["python", "java", "c++", "javascript", "js", "go", "rust",
                     "编程", "程序", "代码", "算法", "数据结构", "前端", "后端",
                     "flask", "django", "react", "vue", "spring", "swift", "kotlin",
                     "php", "ruby", "rust", "typescript", "ts"],
        "chapters": [
            "环境搭建与开发工具准备",
            "基础语法与数据类型",
            "控制流程：条件/循环/异常处理",
            "函数与模块化编程",
            "面向对象：类/继承/封装",
            "常用标准库与第三方包",
            "文件 IO 与数据持久化",
            "调试技巧与单元测试",
            "实战项目：构建一个完整应用",
            "性能优化与最佳实践",
        ],
    },
    "network": {
        "keywords": ["网络", "tcp", "http", "https", "dns", "socket", "路由",
                     "network", "运维"],
        "chapters": [
            "计算机网络发展史与分层模型（OSI / TCP-IP）",
            "物理层与数据链路层：MAC / 交换机 / VLAN",
            "网络层协议：IP 地址 / 子网划分 / 路由",
            "传输层：TCP 三次握手 / 滑动窗口 / 拥塞控制",
            "UDP 协议与实时通信",
            "应用层协议：HTTP / HTTPS / DNS",
            "网络安全：防火墙 / HTTPS 加密原理",
            "WebSocket 与 HTTP/2 / HTTP/3 演进",
            "常用网络排查工具：ping / traceroute / tcpdump",
            "动手实验：用 Wireshark 抓包分析",
        ],
    },
    "physics": {
        "keywords": ["物理", "力学", "电磁", "光学", "热力学", "量子",
                     "physics", "力学"],
        "chapters": [
            "物理学的研究方法与单位制",
            "运动学：位移 / 速度 / 加速度",
            "牛顿三定律与受力分析",
            "功与能：动能定理 / 势能 / 能量守恒",
            "动量与碰撞：守恒定律",
            "刚体转动：力矩 / 角动量",
            "振动与波动：简谐振动 / 波的叠加",
            "热力学：温度 / 熵 / 热力学三大定律",
            "电磁学：电场 / 磁场 / 麦克斯韦方程",
            "近代物理：相对论与量子力学初步",
        ],
    },
    "math": {
        "keywords": ["数学", "高数", "微积分", "线代", "概率", "统计",
                     "math", "calculus", "代数", "几何", "离散"],
        "chapters": [
            "集合 / 映射 / 函数基础",
            "极限与连续性",
            "一元微分学：导数与微分",
            "一元积分学：不定积分 / 定积分",
            "微分中值定理与导数应用",
            "多元函数微分学",
            "多元函数积分学（二重积分 / 三重积分）",
            "无穷级数：常数项级数 / 幂级数",
            "常微分方程基础",
            "向量与矩阵：线性代数初步",
        ],
    },
    "language": {
        "keywords": ["英语", "日语", "法语", "德语", "韩语", "雅思", "托福",
                     "english", "japanese", "chinese", "语文"],
        "chapters": [
            "发音基础：音标 / 声调 / 节奏",
            "高频词汇 1000 词与记忆法",
            "核心语法：时态 / 从句 / 语态",
            "日常对话场景演练",
            "听力训练：精听与泛听",
            "阅读训练：长难句拆解",
            "写作训练：四段式与模板",
            "口语表达：逻辑连接与流利度",
            "真题训练与错题复盘",
            "模拟考试与查漏补缺",
        ],
    },
    "ai": {
        "keywords": ["ai", "人工智能", "深度学习", "机器学习", "深度",
                     "llm", "大模型", "神经网络", "pytorch", "tensorflow",
                     "machine learning", "deep learning", "nlp", "cv"],
        "chapters": [
            "AI 发展史与基本概念",
            "Python 数据处理：NumPy / Pandas",
            "机器学习基础：监督 / 无监督 / 强化",
            "回归与分类：线性回归 / 逻辑回归 / 决策树",
            "模型评估与超参数调优",
            "神经网络原理：感知机 / BP / 激活函数",
            "深度学习框架：PyTorch 入门",
            "CNN 与图像识别",
            "RNN / Transformer 与序列建模",
            "大语言模型原理与 Prompt 工程",
        ],
    },
    "data": {
        "keywords": ["数据库", "sql", "mysql", "mongodb", "redis",
                     "database", "数据", "data"],
        "chapters": [
            "数据库基本概念与关系代数",
            "SQL 基础：SELECT / INSERT / UPDATE / DELETE",
            "表设计与范式（1NF / 2NF / 3NF）",
            "多表查询：JOIN / UNION / 子查询",
            "索引原理：B+ 树 / 哈希索引",
            "事务与并发控制：ACID / 隔离级别",
            "MySQL / PostgreSQL 实战",
            "NoSQL：MongoDB / Redis 适用场景",
            "数据库性能优化与慢查询分析",
            "数据备份 / 恢复与高可用",
        ],
    },
    "os": {
        "keywords": ["操作系统", "操作系统原理", "linux", "unix",
                     "operating system", "系统"],
        "chapters": [
            "操作系统概论与历史",
            "进程与线程：调度 / 通信 / 同步",
            "进程互斥与死锁",
            "内存管理：分页 / 分段 / 虚拟内存",
            "文件系统：FAT / EXT4 / 索引结构",
            "I/O 管理与设备驱动",
            "Linux 常用命令与 Shell 脚本",
            "进程间通信：管道 / 信号 / 共享内存",
            "虚拟化与容器：Docker 原理",
            "实战：手写一个简易 Shell",
        ],
    },
    "default": {
        "keywords": [],
        "chapters": [
            f"概述与发展历史",
            f"核心概念与基本原理",
            f"重要术语与定义",
            f"经典理论框架",
            f"主流方法与流派",
            f"典型应用场景",
            f"常见问题与解决方案",
            f"经典案例分析",
            f"前沿动态与发展趋势",
            f"综合实战与总结",
        ],
    },
}


def _detect_course_type(course):
    """根据课程名判断属于哪一类。"""
    course_lower = course.lower()
    for type_name, info in _COURSE_TEMPLATES.items():
        if type_name == "default":
            continue
        for kw in info["keywords"]:
            if kw in course_lower:
                return type_name
    return "default"


def _personalize_chapter(chapter, course):
    """把章节标题加上课程前缀（首章除外）。"""
    # 章节里已经包含专业词就跳过
    generic_words = ["基础", "核心", "进阶", "入门", "概述", "概览",
                     "基础概念", "基础原理", "相关"]
    if any(w in chapter for w in generic_words) and course in chapter:
        return chapter
    # 第一章通常包含课程名
    if "课程" not in chapter and "章" not in chapter[:3]:
        return f"{course}——{chapter}"
    return chapter


def plan_outline(course, profile=None):
    """
    为课程生成学习大纲。
    参数：
        course: 课程名
        profile: 可选，用户画像（注入 prompt 让章节深度 / 数量更贴合）
    返回：
        章节列表（字符串数组，每项一章）
    """
    # 1. 先尝试调大模型
    profile_text = ""
    if profile:
        try:
            from tools.user_profile import format_profile_text
            profile_text = format_profile_text(profile) + "\n"
        except Exception:
            profile_text = ""

    # 根据水平调整章节数量
    chapter_count = "8-10 章"
    if profile:
        level = profile.get("level", "入门")
        if level == "入门":
            chapter_count = "10-12 章（循序渐进）"
        elif level == "冲刺":
            chapter_count = "6-8 章（聚焦重难点）"

    prompt = (
        profile_text
        + f"你是课程规划助手。请为课程「{course}」输出一个学习大纲，"
        + f"共 {chapter_count}，每章一行，开头用\"第N章 xxx\"的格式，只输出章节列表，不要其他内容。"
        + "每章标题要具体（包含关键概念），不要\"基础/进阶\"这种泛词。"
    )
    result = generate(prompt)

    # 2. 大模型可用且格式对
    if not result.startswith("[LLM 不可用]"):
        lines = [ln.strip() for ln in result.strip().split("\n") if ln.strip()]
        # 过滤掉说明性文字（保留含"第"或含"章"的行）
        clean = []
        for ln in lines:
            ln_clean = re.sub(r"^第[一二三四五六七八九十0-9]+章[：:\s]*", "", ln)
            ln_clean = ln_clean.strip().strip("-*·•#")
            if ln_clean and len(ln_clean) > 3:
                clean.append(ln_clean)
        if len(clean) >= 3:
            return clean[:12]

    # 3. 兜底：按课程类型匹配模板（打降级标记，供 UI 警告）
    from core import llm as _llm
    _llm.mark_degraded("planner")
    return _fallback_outline(course)


def _fallback_outline(course):
    """兜底大纲：按课程类型给出具体章节。"""
    type_name = _detect_course_type(course)
    template_chapters = _COURSE_TEMPLATES[type_name]["chapters"]
    # 第一章添加课程前缀
    chapters = [f"{course}——{template_chapters[0]}"]
    chapters.extend(template_chapters[1:])
    return chapters
