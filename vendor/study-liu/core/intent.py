# intent.py — 意图识别：parse_intent(text) -> dict

"""意图识别模块：判断用户输入是生成方案还是普通提问。

v18 修复：
- 返回 dict {"type": "generate"|"chat", "course": str|None}，
  之前返回字符串导致调用方 .get("type") AttributeError 崩了
- 默认行为改 chat：聊天区输入默认当作问答，不再静默重定向到生成方案
"""

# 触发"生成方案"意图的关键词（明确表达想学一门课）
_PLAN_KEYWORDS = [
    "计划", "方案", "大纲", "学习路线", "怎么学", "如何学",
    "想学", "学一下", "入门", "帮我学", "教我",
]

# 触发"问答"意图的关键词（问句特征）
_CHAT_KEYWORDS = [
    "什么是", "为什么", "怎么理解", "解释一下", "区别",
    "是什么", "如何理解", "的意思", "有哪些", "怎么用",
    "吗", "呢", "？", "?",
]


def parse_intent(text):
    """
    判断用户输入的意图。

    参数：
        text: 用户输入文本

    返回：
        dict: {"type": "generate"|"chat", "course": str|None}
        - type == "generate"：生成学习方案（course 为文本本身）
        - type == "chat"：普通问答（course 固定 None）
    """
    if not text or not text.strip():
        return {"type": "chat", "course": None}

    text = text.strip()

    # 包含方案/计划/大纲等关键词 → generate
    for kw in _PLAN_KEYWORDS:
        if kw in text:
            return {"type": "generate", "course": text}

    # 问句特征或默认 → chat（让用户在课程问答区正常提问）
    return {"type": "chat", "course": None}