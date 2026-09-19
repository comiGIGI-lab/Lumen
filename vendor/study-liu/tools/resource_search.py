# resource_search.py — 资源搜索：内置资源库，不接搜索 API

"""资源搜索模块：内置 20 个常见课程的资源库，不联网。"""

# 内置资源库：key 是课程名，value 是资源数组
# 每条资源格式：{"title": "标题", "type": "教程/书籍/视频", "url": "网址或空"}
_RESOURCE_DB = {
    "机器学习": [
        {"title": "吴恩达机器学习课程", "type": "视频", "url": "https://www.bilibili.com/video/BV1Pa411W76i"},
        {"title": "机器学习（周志华）", "type": "书籍", "url": ""},
        {"title": "李宏毅机器学习教程", "type": "视频", "url": "https://www.bilibili.com/video/BV1Ht411g7Ef"},
        {"title": "Hands-On Machine Learning", "type": "书籍", "url": ""},
    ],
    "Python": [
        {"title": "Python 官方文档", "type": "教程", "url": "https://docs.python.org/zh-cn/3/"},
        {"title": "Python编程：从入门到实践", "type": "书籍", "url": ""},
        {"title": "廖雪峰 Python 教程", "type": "教程", "url": "https://liaoxuefeng.com/books/python/"},
        {"title": "小甲鱼 Python 零基础入门", "type": "视频", "url": "https://www.bilibili.com/video/BV1Lb411W7Ld"},
    ],
    "数据结构": [
        {"title": "数据结构（严蔚敏）", "type": "书籍", "url": ""},
        {"title": "数据结构与算法基础（青岛大学王卓）", "type": "视频", "url": "https://www.bilibili.com/video/BV1nJ411V7bd"},
        {"title": "LeetCode 在线刷题", "type": "教程", "url": "https://leetcode.cn/"},
    ],
    "数据库": [
        {"title": "数据库系统概论（王珊）", "type": "书籍", "url": ""},
        {"title": "MySQL 必知必会", "type": "书籍", "url": ""},
        {"title": "菜鸟教程 MySQL", "type": "教程", "url": "https://www.runoob.com/mysql/mysql-tutorial.html"},
    ],
    "操作系统": [
        {"title": "操作系统概念（Silberschatz）", "type": "书籍", "url": ""},
        {"title": "清华大学操作系统课程（陈渝）", "type": "视频", "url": "https://www.bilibili.com/video/BV1uW411f72n"},
        {"title": "操作系统之餐桌订餐模型", "type": "教程", "url": ""},
    ],
    "计算机网络": [
        {"title": "计算机网络（谢希仁）", "type": "书籍", "url": ""},
        {"title": "中科大计算机网络课程", "type": "视频", "url": "https://www.bilibili.com/video/BV1JV411t7ow"},
        {"title": "小林 coding 图解网络", "type": "教程", "url": "https://xiaolincoding.com/network/"},
    ],
    "Java": [
        {"title": "Java 核心技术卷一", "type": "书籍", "url": ""},
        {"title": "尚硅谷 Java 基础教程", "type": "视频", "url": "https://www.bilibili.com/video/BV1Kb411W75N"},
        {"title": "菜鸟教程 Java", "type": "教程", "url": "https://www.runoob.com/java/java-tutorial.html"},
    ],
    "C语言": [
        {"title": "C程序设计（谭浩强）", "type": "书籍", "url": ""},
        {"title": "翁恺 C 语言程序设计", "type": "视频", "url": "https://www.bilibili.com/video/BV1dr4y1c7Hj"},
        {"title": "菜鸟教程 C 语言", "type": "教程", "url": "https://www.runoob.com/cprogramming/c-tutorial.html"},
    ],
    "算法": [
        {"title": "算法导论（CLRS）", "type": "书籍", "url": ""},
        {"title": "算法（第四版）Sedgewick", "type": "书籍", "url": ""},
        {"title": "代码随想录", "type": "教程", "url": "https://programmercarl.com/"},
        {"title": "左程云算法课", "type": "视频", "url": ""},
    ],
    "数学分析": [
        {"title": "数学分析（华师大）", "type": "书籍", "url": ""},
        {"title": "陈纪修数学分析", "type": "视频", "url": "https://www.bilibili.com/video/BV1ut411Y7BR"},
        {"title": "3Blue1Brown 微积分本质", "type": "视频", "url": "https://www.bilibili.com/video/BV1qW411N7B5"},
    ],
    "线性代数": [
        {"title": "线性代数（同济版）", "type": "书籍", "url": ""},
        {"title": "3Blue1Brown 线性代数本质", "type": "视频", "url": "https://www.bilibili.com/video/BV1ys411472E"},
        {"title": "MIT 18.06 线性代数", "type": "视频", "url": "https://www.bilibili.com/video/BV16Z4y1U7oU"},
    ],
    "概率论": [
        {"title": "概率论与数理统计（浙大版）", "type": "书籍", "url": ""},
        {"title": "宋浩概率论与数理统计", "type": "视频", "url": "https://www.bilibili.com/video/BV1ot411Y7tU"},
        {"title": "可汗学院概率论", "type": "视频", "url": ""},
    ],
    "深度学习": [
        {"title": "深度学习（花书）", "type": "书籍", "url": ""},
        {"title": "李宏毅深度学习课程", "type": "视频", "url": "https://www.bilibili.com/video/BV1J94y1f7u5"},
        {"title": "动手学深度学习（李沐）", "type": "教程", "url": "https://zh.d2l.ai/"},
    ],
    "高等数学": [
        {"title": "高等数学（同济版）", "type": "书籍", "url": ""},
        {"title": "宋浩高等数学", "type": "视频", "url": "https://www.bilibili.com/video/BV1Eb411u7Fw"},
        {"title": "3Blue1Brown 微积分", "type": "视频", "url": ""},
    ],
    "离散数学": [
        {"title": "离散数学（左孝凌）", "type": "书籍", "url": ""},
        {"title": "北京大学离散数学", "type": "视频", "url": ""},
        {"title": "离散数学教程（屈婉玲）", "type": "书籍", "url": ""},
    ],
    "编译原理": [
        {"title": "编译原理（龙书）", "type": "书籍", "url": ""},
        {"title": "哈工大编译原理课程", "type": "视频", "url": "https://www.bilibili.com/video/BV1zW411t7qJ"},
        {"title": "编译原理（陈火旺）", "type": "书籍", "url": ""},
    ],
    "软件工程": [
        {"title": "软件工程（张海藩）", "type": "书籍", "url": ""},
        {"title": "黑马程序员软件工程", "type": "视频", "url": ""},
        {"title": "构建之法（邹欣）", "type": "书籍", "url": ""},
    ],
    "人工智能": [
        {"title": "人工智能（鲍军鹏）", "type": "书籍", "url": ""},
        {"title": "吴恩达 AI for Everyone", "type": "视频", "url": "https://www.bilibili.com/video/BV1KQ4y1P7Vg"},
        {"title": "CS188 人工智能导论", "type": "教程", "url": "https://ai.berkeley.edu/"},
    ],
    "统计学": [
        {"title": "统计学（贾俊平）", "type": "书籍", "url": ""},
        {"title": "可汗学院统计学", "type": "视频", "url": ""},
        {"title": "统计学习方法（李航）", "type": "书籍", "url": ""},
    ],
    "计算机组成原理": [
        {"title": "计算机组成原理（唐朔飞）", "type": "书籍", "url": ""},
        {"title": "哈工大计算机组成原理", "type": "视频", "url": "https://www.bilibili.com/video/BV1WW411Q7PF"},
        {"title": "Crash Course 计算机科学", "type": "视频", "url": "https://www.bilibili.com/video/BV1EW411u7th"},
    ],
}


def search_resources(course):
    """
    搜索课程资源。
    参数：
        course: 课程名
    返回：
        资源列表，每项 {"title", "type", "url"}
    """
    # 精确匹配
    if course in _RESOURCE_DB:
        return _RESOURCE_DB[course]

    # 模糊匹配：课程名包含或被包含
    for key, resources in _RESOURCE_DB.items():
        if course in key or key in course:
            return resources

    # 没匹配到，返回通用学习平台（不再用 XXX入门教程 占位符）
    return [
        {"title": "知乎 - 搜索学科相关问答", "type": "社区", "url": "https://www.zhihu.com/search?type=content&q=" + course},
        {"title": "B站 - 搜索课程视频", "type": "视频", "url": "https://search.bilibili.com/all?keyword=" + course},
        {"title": "中国大学MOOC - 搜索课程", "type": "平台", "url": "https://www.icourse163.org/search.htm?search=" + course},
        {"title": "Coursera - 搜索国际课程", "type": "平台", "url": "https://www.coursera.org/search?query=" + course},
        {"title": "菜鸟教程 - 编程与技术", "type": "教程", "url": "https://www.runoob.com/"},
        {"title": "掘金 - 技术文章", "type": "社区", "url": "https://juejin.cn/search?query=" + course},
        {"title": "豆瓣读书 - 搜索教材", "type": "书籍", "url": "https://book.douban.com/subject_search?search_text=" + course},
    ]
