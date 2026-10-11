# -*- coding: utf-8 -*-
# wrongbook_quiz.py — 闯关错题 → 错题本 的题型适配
#
# 为什么要有这个文件
# ------------------
# 出题侧（server/quiz.py）三种题型的**答案编码互不相同**，_norm_answer_* 已经定死：
#
#     single  -> ["A"]            归一化后仍是列表，长度 1
#     multi   -> ["A", "C"]       已排序，长度 >= 2
#     judge   -> int 0 / 1        0=正确 1=错误（不是选项 key！）
#
# 而前端「我的答案」侧又不一样：judge 传的是选项 key（"A"/"B"），
# single/multi 传的是 key 数组。两侧的形态对不上，必须各自按自己的规则格式化，一旦用错一种
# 格式化，多选题就只会剩下第一个选项的文字（真踩过：选了 A、C 却只显示 A 的文本）。
#
# 错题本侧不能加字段：vendor/study-liu/tools/wrong_book_store.py 的 add_item
# 是**封闭契约**（多余入参直接丢弃），且本仓库约定 vendor 零改动；
# 出题闯关 OpenSpec 也白纸黑字写着「Ask first：改 wrong_book_store」。
# 所以题型只能落在**本来就有**的字段里：
#
#     source   = "quiz"          该字段本来就存在，OpenSpec 也承认它兼容 'quiz'
#     tags     含 "题型:多选"     承载题型（顺便可在错题本里被关键词搜到）
#     question 渲染为文本          "[多选] 题干\nA. ...\nB. ..."
#     qtype    不入存储，由服务端从 tags 派生后挂在响应上给前端读
#
# 本模块**只做纯转换**，不 import 任何 store / 不发网络请求，方便回归直接单测。

QUIZ_SOURCE = "quiz"

# 题型标签前缀。标签同时充当错因的关键字（list_items 的 keyword 会扫 tags），
# 所以用中文名而不是英文 key —— 用户搜"多选"能搜到。
TYPE_TAG_PREFIX = "题型:"

Q_TYPES = ("single", "multi", "judge")
QTYPE_LABELS = {"single": "单选", "multi": "多选", "judge": "判断"}
_LABEL_TO_TYPE = {v: k for k, v in QTYPE_LABELS.items()}

JUDGE_RIGHT = "正确"
JUDGE_WRONG = "错误"

# 与 wrong_book_store 的上限对齐（它内部还会再裁一次，这里先裁是为了保证
# 选项不被截在半句、且渲染出的题干整体不会超限）
MAX_QUESTION = 4000
MAX_ANSWER = 6000
MAX_REASON = 1000
MAX_OPTION_TEXT = 400


def _clip(text, limit):
    s = ("" if text is None else str(text)).strip()
    return s[:limit]


def normalize_qtype(t):
    """把任意输入收敛到 single / multi / judge；认不出来按单选处理。"""
    s = str(t or "").strip().lower()
    return s if s in Q_TYPES else "single"


def qtype_label(t):
    """题型中文名，用于渲染到题干头部。"""
    return QTYPE_LABELS[normalize_qtype(t)]


def type_tag(t):
    """写进 tags 的题型标记，形如 "题型:多选"。"""
    return TYPE_TAG_PREFIX + qtype_label(t)


def _coerce_qtype(raw):
    """把 "multi" / "多选" / "MULTI" 都收敛成 canonical key；认不出返回 None。"""
    s = str(raw or "").strip()
    if s.lower() in Q_TYPES:
        return s.lower()
    return _LABEL_TO_TYPE.get(s)


def parse_qtype(item):
    """从一个错题条目里还原题型；不是闯关题（没有题型标签）则返回 None。

    历史上可能写进 tags 的形态都得认：
        "题型:multi"   早期草稿、或别的调用方直接拼了英文 key
        "题型:多选"   现在的写法
        "多选"         没带前缀的裸标签
    """
    tags = (item or {}).get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    for t in tags:
        s = str(t or "").strip()
        if not s:
            continue
        raw = s[len(TYPE_TAG_PREFIX):].strip() if s.startswith(TYPE_TAG_PREFIX) else s
        key = _coerce_qtype(raw)
        if key:
            return key
    return None


def is_quiz_item(item):
    """是不是闯关来的错题。"""
    return str((item or {}).get("source") or "") == QUIZ_SOURCE


def _keys_of(ans):
    """把答案/选中值统一拆成选项 key 列表。"""
    if isinstance(ans, (list, tuple)):
        raw = [x for x in ans if str(x).strip() != ""]
    else:
        raw = [] if ans is None else [ans]
    return [str(x).strip().upper() for x in raw]


def render_question(stem, options, qtype):
    """渲染进 question 字段：[题型] 题干 + 逐条选项。"""
    qtype = normalize_qtype(qtype)
    head = "[%s] %s" % (qtype_label(qtype), _clip(stem, MAX_QUESTION))
    lines = []
    for o in options or []:
        if not isinstance(o, dict):
            continue
        key = str(o.get("key") or "").strip()
        text = _clip(o.get("text") or "", MAX_OPTION_TEXT)
        if key and text:
            lines.append("%s. %s" % (key, text))
    return _clip("\n".join([head] + lines), MAX_QUESTION)


def human_answer(ans, qtype, options=None):
    """把答案（或作答）格式化成人能读的一句话，三种题型各走各的路。

    judge 尤其要注意：正解是 int 0/1，而前端选中值是选项 key "A"/"B"，
    两种形态都得认，否则错题本里会显示成裸的 "0"/"A"。
    """
    qtype = normalize_qtype(qtype)
    opts = options or []
    text_of = {}
    for o in opts:
        if isinstance(o, dict):
            k = str(o.get("key") or "").strip().upper()
            if k:
                text_of[k] = str(o.get("text") or "").strip()

    if qtype == "judge":
        raw = ans[0] if isinstance(ans, (list, tuple)) and ans else ans
        if isinstance(raw, bool):
            return JUDGE_WRONG if raw else JUDGE_RIGHT
        if isinstance(raw, int) and raw in (0, 1):
            return JUDGE_WRONG if raw == 1 else JUDGE_RIGHT
        s = str(raw or "").strip()
        if s in ("0", "1"):
            return JUDGE_WRONG if s == "1" else JUDGE_RIGHT
        # 当成选项 key 查它的文本（一般是"正确"/"错误"）
        if s.upper() in text_of and text_of[s.upper()]:
            return text_of[s.upper()]
        return _clip(s, MAX_ANSWER)

    keys = _keys_of(ans)
    if not keys:
        return ""

    if qtype == "single":
        k = keys[0]
        return ("%s. %s" % (k, text_of[k]))[:MAX_ANSWER] if k in text_of else k

    ks = sorted(set(keys))
    pairs = ["%s. %s" % (k, text_of[k]) if k in text_of else k for k in ks]
    return "、".join(ks) + "（" + "；".join(pairs) + "）"


def build_quiz_wrong(course, question, selected, answer, explanation,
                     knowledge_point="", extra_tags=None):
    """把一道闯关错题整理成 wrong_book_store.add_item 直接能吃的字段。

    返回的键刻意与 add_item 的入参一一对应（course/question/my_answer/
    answer/reason/tags/source），多一个键 add_item 都会 TypeError。
    """
    q = question if isinstance(question, dict) else {}
    qtype = normalize_qtype(q.get("type"))
    stem = str(q.get("stem") or "").strip()
    options = q.get("options") or []

    my = human_answer(selected, qtype, options)
    right = human_answer(answer, qtype, options)
    kp = str(knowledge_point or "").strip()

    answer_text = "正确答案：%s" % right
    exp = str(explanation or "").strip()
    if exp:
        answer_text += "。" + exp

    tags = []
    for t in ([kp] if kp else []) + ["闯关"] + list(extra_tags or []) + [type_tag(qtype)]:
        s = str(t or "").strip()
        if s and s not in tags:
            tags.append(s)

    return {
        "course": _clip(course, 80),
        "question": render_question(stem, options, qtype),
        "my_answer": _clip(my, MAX_ANSWER),
        "answer": _clip(answer_text, MAX_ANSWER),
        "reason": _clip(("知识点：%s" % kp) if kp else "", MAX_REASON),
        "tags": tags,
        "source": QUIZ_SOURCE,
    }
