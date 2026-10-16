# planner.py — Planner Agent：课程 → 大纲

"""Planner Agent：输入课程名，输出学习大纲。

输出契约（v20 起）：**每章是一个对象** `{"title": str, "points": [str, ...]}`。
- title：章节名
- points：该章要点，至少 3 条，必须具体到概念或操作（不写「要点待补充」这类空话）

为什么改成对象：此前只返回章节名字符串，导出预览里每章下面只能显示「要点待补充」，
Markdown / Word 里也只能写「暂无要点」—— 大纲等于没有内容。
"""

import json
import re

from core.llm import generate


def _ch(title, points):
    """构造一个章节对象（内部用，省去重复的 dict 字面量）。"""
    return {"title": title, "points": list(points)}


# 课程分类：识别关键词 → 章节模板（每章含 title + 至少 3 条具体要点）
_COURSE_TEMPLATES = {
    "programming": {
        "keywords": ["python", "java", "c++", "javascript", "js", "go", "rust",
                     "编程", "程序", "代码", "算法", "数据结构", "前端", "后端",
                     "flask", "django", "react", "vue", "spring", "swift", "kotlin",
                     "php", "ruby", "rust", "typescript", "ts"],
        "chapters": [
            _ch("环境搭建与开发工具准备", [
                "安装语言运行时并配置 PATH 环境变量",
                "选一个编辑器/IDE，配好语法高亮与断点调试",
                "用包管理器创建虚拟环境并锁定依赖版本",
            ]),
            _ch("基础语法与数据类型", [
                "变量、常量与命名规范",
                "基本数据类型：整数 / 浮点 / 字符串 / 布尔",
                "类型转换与常见坑（精度、隐式转换）",
            ]),
            _ch("控制流程：条件/循环/异常处理", [
                "if / elif / else 分支的写法与嵌套",
                "for / while 循环与 break、continue",
                "try / except / finally 捕获运行时错误",
            ]),
            _ch("函数与模块化编程", [
                "函数定义、参数传递与返回值",
                "作用域、闭包与装饰器",
                "拆模块与 import 的组织方式",
            ]),
            _ch("面向对象：类/继承/封装", [
                "类与实例、构造与析构",
                "继承、多态与抽象基类",
                "封装与访问控制（public / private）",
            ]),
            _ch("常用标准库与第三方包", [
                "字符串 / 时间 / 文件等高频标准库",
                "用包管理器安装并使用第三方库",
                "读懂官方文档与版本变更说明",
            ]),
            _ch("文件 IO 与数据持久化", [
                "文本 / 二进制文件的读写与编码",
                "JSON / CSV 等格式的序列化与反序列化",
                "用文件或数据库做简单持久化",
            ]),
            _ch("调试技巧与单元测试", [
                "断点调试与日志排查的基本套路",
                "写单元测试：断言、用例组织与隔离",
                "覆盖边界值与异常分支",
            ]),
            _ch("实战项目：构建一个完整应用", [
                "拆解需求并做模块与接口设计",
                "编码实现与前后端联调",
                "打包 / 部署并补一份使用说明",
            ]),
            _ch("性能优化与最佳实践", [
                "用计时与剖析定位性能瓶颈",
                "常见优化手段：缓存、算法、并发",
                "代码风格与可维护性规范",
            ]),
        ],
    },
    "network": {
        "keywords": ["网络", "tcp", "http", "https", "dns", "socket", "路由",
                     "network", "运维"],
        "chapters": [
            _ch("计算机网络发展史与分层模型（OSI / TCP-IP）", [
                "分组交换与互联网的由来",
                "OSI 七层与 TCP/IP 四层的对应关系",
                "数据封装与解封装的完整过程",
            ]),
            _ch("物理层与数据链路层：MAC / 交换机 / VLAN", [
                "双绞线 / 光纤与信号编码",
                "MAC 地址与以太网帧结构",
                "交换机转发原理与 VLAN 划分",
            ]),
            _ch("网络层协议：IP 地址 / 子网划分 / 路由", [
                "IPv4 地址分类与 CIDR 表示法",
                "子网掩码与子网划分计算",
                "路由表与静态 / 动态路由选择",
            ]),
            _ch("传输层：TCP 三次握手 / 滑动窗口 / 拥塞控制", [
                "三次握手与四次挥手的完整流程",
                "可靠传输：序号、确认与超时重传",
                "滑动窗口与拥塞控制算法",
            ]),
            _ch("UDP 协议与实时通信", [
                "UDP 报文结构与无连接特性",
                "TCP 与 UDP 的选型对比",
                "基于 UDP 的实时音视频场景",
            ]),
            _ch("应用层协议：HTTP / HTTPS / DNS", [
                "HTTP 请求响应报文与常见状态码",
                "HTTPS 加密过程与证书链",
                "DNS 解析过程与缓存层级",
            ]),
            _ch("网络安全：防火墙 / HTTPS 加密原理", [
                "对称加密与非对称加密的分工",
                "防火墙规则与 NAT 的作用",
                "常见攻击与防护（中间人、DDoS）",
            ]),
            _ch("WebSocket 与 HTTP/2 / HTTP/3 演进", [
                "WebSocket 的全双工通信机制",
                "HTTP/2 多路复用与头部压缩",
                "QUIC 与 HTTP/3 带来的改进",
            ]),
            _ch("常用网络排查工具：ping / traceroute / tcpdump", [
                "用 ping / traceroute 定位连通性",
                "用 netstat / ss 查看端口与连接",
                "tcpdump 抓包与过滤表达式",
            ]),
            _ch("动手实验：用 Wireshark 抓包分析", [
                "安装 Wireshark 并选择抓包网卡",
                "过滤三次握手与 HTTP 流量",
                "从抓包结果定位一次真实故障",
            ]),
        ],
    },
    "physics": {
        "keywords": ["物理", "力学", "电磁", "光学", "热力学", "量子",
                     "physics", "力学"],
        "chapters": [
            _ch("物理学的研究方法与单位制", [
                "量纲分析与单位换算",
                "有效数字与误差处理",
                "建模与近似的基本思想",
            ]),
            _ch("运动学：位移 / 速度 / 加速度", [
                "位移、路程与速度的定义与区别",
                "匀变速直线运动的三个基本公式",
                "用 v-t / x-t 图像分析运动",
            ]),
            _ch("牛顿三定律与受力分析", [
                "牛顿三定律的表述与物理含义",
                "受力分析与隔离法",
                "常见力：重力、弹力、摩擦力",
            ]),
            _ch("功与能：动能定理 / 势能 / 能量守恒", [
                "功与功率的计算",
                "动能定理与重力势能表达式",
                "机械能守恒的条件与能量转化",
            ]),
            _ch("动量与碰撞：守恒定律", [
                "冲量与动量定理",
                "动量守恒的成立条件",
                "弹性与非弹性碰撞的求解",
            ]),
            _ch("刚体转动：力矩 / 角动量", [
                "力矩与转动惯量",
                "角动量守恒的应用",
                "定轴转动的动力学方程",
            ]),
            _ch("振动与波动：简谐振动 / 波的叠加", [
                "简谐振动的运动学方程与相位",
                "机械波的产生、传播与波函数",
                "波的叠加、干涉与驻波",
            ]),
            _ch("热力学：温度 / 熵 / 热力学三大定律", [
                "温度与理想气体状态方程",
                "热力学第一定律与第二定律",
                "熵的物理意义与简单计算",
            ]),
            _ch("电磁学：电场 / 磁场 / 麦克斯韦方程", [
                "库仑定律与电场强度、电势",
                "磁场、安培力与洛伦兹力",
                "电磁感应与楞次定律",
            ]),
            _ch("近代物理：相对论与量子力学初步", [
                "狭义相对论的两条基本假设",
                "光电效应与光子说",
                "波粒二象性与不确定关系",
            ]),
        ],
    },
    "math": {
        "keywords": ["数学", "高数", "微积分", "线代", "概率", "统计",
                     "math", "calculus", "代数", "几何", "离散"],
        "chapters": [
            _ch("集合 / 映射 / 函数基础", [
                "集合运算与区间表示",
                "映射与函数的定义",
                "常见初等函数的图像与性质",
            ]),
            _ch("极限与连续性", [
                "数列极限与函数极限的定义",
                "两个重要极限",
                "连续性与间断点的分类",
            ]),
            _ch("一元微分学：导数与微分", [
                "导数的定义与几何意义",
                "求导法则与复合函数求导",
                "微分的概念与近似计算",
            ]),
            _ch("一元积分学：不定积分 / 定积分", [
                "不定积分与基本积分表",
                "换元积分法与分部积分法",
                "定积分定义与牛顿-莱布尼茨公式",
            ]),
            _ch("微分中值定理与导数应用", [
                "罗尔 / 拉格朗日 / 柯西中值定理",
                "用洛必达法则求未定式极限",
                "单调性、极值与最值的判定",
            ]),
            _ch("多元函数微分学", [
                "偏导数与全微分",
                "多元复合函数与隐函数求导",
                "极值判定与拉格朗日乘数法",
            ]),
            _ch("多元函数积分学（二重积分 / 三重积分）", [
                "二重积分的定义与直角坐标计算",
                "极坐标与一般换元法",
                "三重积分及其几何 / 物理应用",
            ]),
            _ch("无穷级数：常数项级数 / 幂级数", [
                "正项级数与交错级数的收敛判别法",
                "幂级数与收敛半径的求法",
                "泰勒级数与麦克劳林展开",
            ]),
            _ch("常微分方程基础", [
                "可分离变量方程的解法",
                "一阶线性微分方程与积分因子",
                "二阶常系数线性方程的通解结构",
            ]),
            _ch("向量与矩阵：线性代数初步", [
                "向量运算与线性相关性",
                "矩阵运算与行列式",
                "用高斯消元法解线性方程组",
            ]),
        ],
    },
    "language": {
        "keywords": ["英语", "日语", "法语", "德语", "韩语", "雅思", "托福",
                     "english", "japanese", "chinese", "语文"],
        "chapters": [
            _ch("发音基础：音标 / 声调 / 节奏", [
                "元音与辅音音标的发音要点",
                "重音与语调的基本规律",
                "连读与弱读的听辨",
            ]),
            _ch("高频词汇 1000 词与记忆法", [
                "词根词缀拆解记忆",
                "按艾宾浩斯曲线安排复习",
                "把单词放进例句与语境记忆",
            ]),
            _ch("核心语法：时态 / 从句 / 语态", [
                "常用时态与时间标志词",
                "定语、状语与名词性从句",
                "主动语态与被动语态的转换",
            ]),
            _ch("日常对话场景演练", [
                "问候 / 点餐 / 问路等高频场景表达",
                "常用口语短语与礼貌用语",
                "影子跟读与角色扮演练习",
            ]),
            _ch("听力训练：精听与泛听", [
                "精听：逐句听写与复述",
                "泛听：大量输入培养语感",
                "抓关键词与逻辑信号词",
            ]),
            _ch("阅读训练：长难句拆解", [
                "先找主干再拆修饰成分",
                "略读与扫读的定位技巧",
                "生词猜测的上下文策略",
            ]),
            _ch("写作训练：四段式与模板", [
                "四段式结构：引入-论证-例证-结论",
                "常用连接词与高分句型",
                "自评批改与重写",
            ]),
            _ch("口语表达：逻辑连接与流利度", [
                "用连接词组织观点",
                "减少停顿与自我修正",
                "就熟悉话题做 1 分钟陈述",
            ]),
            _ch("真题训练与错题复盘", [
                "限时做题熟悉题型与节奏",
                "整理错题并归因到知识点",
                "针对薄弱项做专项练习",
            ]),
            _ch("模拟考试与查漏补缺", [
                "按考试节奏做全真模考",
                "分析分数构成与失分点",
                "制定冲刺补漏清单",
            ]),
        ],
    },
    "ai": {
        "keywords": ["ai", "人工智能", "深度学习", "机器学习", "深度",
                     "llm", "大模型", "神经网络", "pytorch", "tensorflow",
                     "machine learning", "deep learning", "nlp", "cv"],
        "chapters": [
            _ch("AI 发展史与基本概念", [
                "符号主义与连接主义两条路线",
                "机器学习与深度学习的关系",
                "常见任务：分类 / 回归 / 生成",
            ]),
            _ch("Python 数据处理：NumPy / Pandas", [
                "NumPy 数组与向量化运算",
                "Pandas 读写数据与表格操作",
                "缺失值与重复值的清洗",
            ]),
            _ch("机器学习基础：监督 / 无监督 / 强化", [
                "三类学习范式的区别与代表算法",
                "训练集 / 验证集 / 测试集的划分",
                "过拟合与欠拟合的识别",
            ]),
            _ch("回归与分类：线性回归 / 逻辑回归 / 决策树", [
                "线性回归与最小二乘求解",
                "逻辑回归与概率输出、阈值选择",
                "决策树的分裂准则与剪枝",
            ]),
            _ch("模型评估与超参数调优", [
                "准确率 / 精确率 / 召回率 / F1",
                "交叉验证与网格搜索",
                "用学习曲线诊断模型",
            ]),
            _ch("神经网络原理：感知机 / BP / 激活函数", [
                "感知机与前向传播",
                "反向传播与梯度下降",
                "常用激活函数及其选择",
            ]),
            _ch("深度学习框架：PyTorch 入门", [
                "Tensor 与自动求导机制",
                "定义模型、损失函数与优化器",
                "训练循环与模型保存 / 加载",
            ]),
            _ch("CNN 与图像识别", [
                "卷积、池化与感受野",
                "经典网络结构（LeNet / ResNet）",
                "图像分类实战与数据增强",
            ]),
            _ch("RNN / Transformer 与序列建模", [
                "RNN 与梯度消失问题",
                "LSTM / GRU 的门控机制",
                "注意力机制与 Transformer 结构",
            ]),
            _ch("大语言模型原理与 Prompt 工程", [
                "预训练与微调（SFT / RLHF）",
                "Tokenization 与上下文窗口",
                "Prompt 设计与效果评测",
            ]),
        ],
    },
    "data": {
        "keywords": ["数据库", "sql", "mysql", "mongodb", "redis",
                     "database", "数据", "data"],
        "chapters": [
            _ch("数据库基本概念与关系代数", [
                "关系模型与表 / 行 / 列",
                "主键、外键与完整性约束",
                "关系代数的基本运算",
            ]),
            _ch("SQL 基础：SELECT / INSERT / UPDATE / DELETE", [
                "SELECT 与 WHERE 条件过滤",
                "增删改语句与事务提交",
                "ORDER BY / LIMIT / 聚合函数",
            ]),
            _ch("表设计与范式（1NF / 2NF / 3NF）", [
                "函数依赖与候选键",
                "三大范式的判定方法",
                "反范式的适用场景与权衡",
            ]),
            _ch("多表查询：JOIN / UNION / 子查询", [
                "内连接、左连接与自连接",
                "子查询与 EXISTS 的用法",
                "UNION 与结果去重",
            ]),
            _ch("索引原理：B+ 树 / 哈希索引", [
                "B+ 树结构与查询过程",
                "聚簇索引与非聚簇索引",
                "索引失效的常见场景",
            ]),
            _ch("事务与并发控制：ACID / 隔离级别", [
                "ACID 四个特性的含义",
                "四种隔离级别与脏读 / 幻读",
                "锁机制与 MVCC 多版本并发控制",
            ]),
            _ch("MySQL / PostgreSQL 实战", [
                "建库建表与用户权限管理",
                "备份与恢复操作",
                "常用运维与监控命令",
            ]),
            _ch("NoSQL：MongoDB / Redis 适用场景", [
                "文档型数据库与集合模型",
                "Redis 常用数据结构与缓存用法",
                "与关系型数据库的选型对比",
            ]),
            _ch("数据库性能优化与慢查询分析", [
                "开启慢查询日志并看 EXPLAIN",
                "SQL 改写与索引优化",
                "分库分表的初步思路",
            ]),
            _ch("数据备份 / 恢复与高可用", [
                "逻辑备份与物理备份的区别",
                "主从复制与读写分离",
                "故障切换演练",
            ]),
        ],
    },
    "os": {
        "keywords": ["操作系统", "操作系统原理", "linux", "unix",
                     "operating system", "系统"],
        "chapters": [
            _ch("操作系统概论与历史", [
                "操作系统的作用与设计目标",
                "批处理 / 分时 / 实时系统的区别",
                "内核态与用户态、系统调用",
            ]),
            _ch("进程与线程：调度 / 通信 / 同步", [
                "进程与线程的区别与联系",
                "调度算法（FCFS / SJF / 时间片轮转）",
                "进程间通信的主要方式",
            ]),
            _ch("进程互斥与死锁", [
                "临界区与互斥锁",
                "信号量的 PV 操作",
                "死锁的四个必要条件与预防",
            ]),
            _ch("内存管理：分页 / 分段 / 虚拟内存", [
                "连续分配与内存碎片",
                "分页机制与地址转换",
                "页面置换算法（LRU / FIFO）",
            ]),
            _ch("文件系统：FAT / EXT4 / 索引结构", [
                "文件与目录的组织结构",
                "inode 与索引节点",
                "磁盘空间分配与回收",
            ]),
            _ch("I/O 管理与设备驱动", [
                "中断与 DMA 的工作方式",
                "缓冲技术与假脱机",
                "设备驱动模型",
            ]),
            _ch("Linux 常用命令与 Shell 脚本", [
                "文件与权限命令（ls / chmod / chown）",
                "进程与文本处理（ps / grep / sed / awk）",
                "编写 Shell 脚本与定时任务",
            ]),
            _ch("进程间通信：管道 / 信号 / 共享内存", [
                "匿名管道与命名管道",
                "信号机制与 signal 处理",
                "共享内存与消息队列",
            ]),
            _ch("虚拟化与容器：Docker 原理", [
                "namespace 与 cgroup 的隔离与限制",
                "镜像分层与容器生命周期",
                "容器网络与数据卷",
            ]),
            _ch("实战：手写一个简易 Shell", [
                "解析命令行与参数",
                "用 fork / exec 执行外部命令",
                "支持管道与输入输出重定向",
            ]),
        ],
    },
    "default": {
        "keywords": [],
        "chapters": [
            _ch("概述与发展历史", [
                "本学科的研究对象与范围",
                "发展脉络与关键节点",
                "与相邻学科的关系",
            ]),
            _ch("核心概念与基本原理", [
                "基本术语的定义与区别",
                "核心原理的表述",
                "原理成立的适用条件",
            ]),
            _ch("重要术语与定义", [
                "整理本学科术语表",
                "辨析易混概念",
                "术语的中英文对应",
            ]),
            _ch("经典理论框架", [
                "主要理论模型",
                "模型的假设与局限",
                "用模型解释典型现象",
            ]),
            _ch("主流方法与流派", [
                "主要方法论的对比",
                "代表流派与核心主张",
                "各方法的适用场景",
            ]),
            _ch("典型应用场景", [
                "行业中的实际应用",
                "从问题到方案的映射过程",
                "应用时的约束条件",
            ]),
            _ch("常见问题与解决方案", [
                "高频问题清单",
                "排错与解决的思路",
                "案例复盘的标准步骤",
            ]),
            _ch("经典案例分析", [
                "案例背景与目标",
                "分析过程与结论",
                "可迁移的经验",
            ]),
            _ch("前沿动态与发展趋势", [
                "近年研究热点",
                "技术与产业趋势",
                "值得持续关注的方向",
            ]),
            _ch("综合实战与总结", [
                "设计一个综合练习",
                "用思维导图梳理知识体系",
                "复盘学习路线并做后续规划",
            ]),
        ],
    },
}

# 兜底要点：LLM 只给了章节名、没给要点时，用标题生成具体一点的要点，
# 保证 Reviewer 的「每章 ≥2 条要点」能过，而不是写「要点待补充」。
def _points_from_title(title):
    return [
        f"{title}：核心概念与定义",
        f"{title}：典型方法与操作步骤",
        f"{title}：常见问题与练习",
    ]


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


def _chapter_title(ch):
    """从章节项里取标题（兼容 dict / str）。"""
    if isinstance(ch, dict):
        return str(ch.get("title") or ch.get("name") or "").strip()
    return str(ch or "").strip()


def _chapter_points(ch):
    """从章节项里取要点列表（兼容 points / items / sections，且过滤空串）。"""
    if not isinstance(ch, dict):
        return []
    pts = ch.get("points") or ch.get("items") or ch.get("sections") or []
    if isinstance(pts, str):
        pts = [pts]
    if not isinstance(pts, list):
        return []
    return [str(p).strip() for p in pts if str(p).strip()]


def _parse_outline_from_llm(text):
    """从大模型文本里解析大纲（章节对象列表）。

    支持两种形态：
      1. JSON（首选）：{"chapters": [{"title": "...", "points": [...]}, ...]}
      2. 逐行列表（旧格式 / 模型不听话时）：每行一个章节名 → 要点由标题生成
    解析不出或章节不足 3 条时返回空列表，由调用方走模板兜底。
    """
    if not text:
        return []

    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)

    # ---- 形态 1：JSON ----
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:
            data = None
        items = None
        if isinstance(data, dict):
            for k in ("chapters", "outline", "sections", "items", "data", "list"):
                if k in data and isinstance(data[k], list):
                    items = data[k]
                    break
            if items is None:
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
        elif isinstance(data, list):
            items = data
        if items:
            chapters = []
            for it in items:
                if isinstance(it, dict):
                    title = _chapter_title(it)
                    if not title:
                        continue
                    points = _chapter_points(it)
                    if not points:
                        points = _points_from_title(title)
                    chapters.append(_ch(title, points))
                elif isinstance(it, str) and it.strip():
                    title = it.strip()
                    chapters.append(_ch(title, _points_from_title(title)))
            if len(chapters) >= 3:
                return chapters[:12]

    # ---- 形态 2：逐行章节名 ----
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    chapters = []
    for ln in lines:
        clean = re.sub(r"^第[一二三四五六七八九十0-9]+章[：:\s]*", "", ln)
        clean = clean.strip().strip("-*·•#").strip()
        if clean and len(clean) > 3:
            chapters.append(_ch(clean, _points_from_title(clean)))
    if len(chapters) >= 3:
        return chapters[:12]

    return []


def _diagnosis_for(course):
    """取本课程最近一次摸底诊断记录；没有 / 读失败 → None（按"没做诊断"处理）。

    单一事实来源是 data/diagnosis.json（见 tools/diagnosis_store.py）。
    与 profile.json 一样按课程/部署粒度共享：本应用画像本来就是全局一份，
    诊断沿用同一口径；将来若要严格按账号隔离，调用方把 record 直接传进
    plan_outline(diagnosis=...) 覆盖即可。
    """
    try:
        from tools import diagnosis_store
        return diagnosis_store.latest_for_course(course)
    except Exception:                                        # noqa: BLE001
        return None


def plan_outline(course, profile=None, kb_context=None, diagnosis=None):
    """
    为课程生成学习大纲。
    参数：
        course: 课程名
        profile: 可选，用户画像（注入 prompt 让章节深度 / 数量更贴合）
        kb_context: 可选，知识库检索到的资料文本（已截断），注入 prompt
        diagnosis: 可选，摸底诊断记录。**不传**时自动按课程取最近一次
            （data/diagnosis.json）；显式传 None 想表达"本次不要诊断"请用
            `diagnosis=False`。没有诊断时 prompt 与加诊断之前逐字节一致。
    返回：
        章节列表，每项 {"title": str, "points": [str, ...]}
    """
    # 1. 先尝试调大模型
    profile_text = ""
    if profile:
        try:
            from tools.user_profile import format_profile_text
            # 诊断段的价值就在这里兑现：让大纲对**弱项章节**加厚、对已掌握的压缩。
            if diagnosis is None:
                diagnosis = _diagnosis_for(course)
            elif diagnosis is False:
                diagnosis = None
            profile_text = format_profile_text(profile, diagnosis) + "\n"
        except Exception:
            profile_text = ""

    # 根据水平调整章节数量（水平三档：入门 / 进阶 / 冲刺）
    chapter_count = "8-10 章"
    if profile:
        level = profile.get("level", "入门")
        if level == "入门":
            chapter_count = "10-12 章（循序渐进）"
        elif level == "冲刺":
            chapter_count = "6-8 章（聚焦重难点）"

    kb_text = ""
    if kb_context:
        kb_text = (
            "下面是本课程知识库中检索到的资料。规划章节时请优先覆盖这些材料里出现的概念；"
            "资料不足以构成章节时按常识补全。不要复述「资料1/资料2」这种编号。\n\n"
            + str(kb_context)
            + "\n\n"
        )

    prompt = (
        profile_text
        + kb_text
        + f"你是课程规划助手。请为课程「{course}」输出学习大纲，共 {chapter_count}。\n"
        + "要求：\n"
        + "1. 每章一个标题 + 至少 3 条要点；要点必须具体到概念或操作"
        + "（例如「用 venv 创建独立环境并锁定依赖版本」），"
        + "禁止「基础」「进阶」「要点待补充」这类空话。\n"
        + "2. 章节标题要包含关键概念。\n"
        + "3. 禁止 markdown 代码块，不要任何额外说明文字。\n"
        + "4. 严格按下面 JSON 格式输出：\n"
        + '{"chapters": ['
        + '{"title": "第1章 环境搭建", "points": ["安装运行时并配置 PATH", "创建虚拟环境", "跑通 Hello World"]},'
        + '{"title": "第2章 基础语法", "points": ["变量与命名规范", "基本数据类型", "类型转换与常见坑"]}'
        + "]}"
    )
    result = generate(prompt)

    # 2. 大模型可用且格式对
    if not _is_llm_unavailable(result):
        chapters = _parse_outline_from_llm(result)
        if len(chapters) >= 3:
            return chapters[:12]

    # 3. 兜底：按课程类型匹配模板（打降级标记，供 UI 警告）
    from core import llm as _llm
    _llm.mark_degraded("planner")
    return _fallback_outline(course)


def _is_llm_unavailable(result):
    """判断 generate() 返回是否失败。"""
    if not result:
        return True
    return result.startswith("[LLM 不可用]")


def _fallback_outline(course):
    """兜底大纲：按课程类型给出具体章节（每章含至少 3 条要点）。"""
    type_name = _detect_course_type(course)
    template_chapters = _COURSE_TEMPLATES[type_name]["chapters"]
    # 第一章带上课程前缀，便于识别「这是哪门课的大纲」
    first = template_chapters[0]
    chapters = [_ch(f"{course}——{first['title']}", first["points"])]
    for ch in template_chapters[1:]:
        chapters.append(_ch(ch["title"], ch["points"]))
    return chapters
