# crisis.py — 心理危机响应：命中后由代码注入热线，号码绝不交给模型生成

"""心理危机响应层（Crisis Layer）。

为什么必须有这一层
------------------
2026-09-26 线上实测取证：往 `/api/chat` 打一句
「最近觉得活着很没意思，有点不想继续了」，返回 `type="chat" / source="llm"`，
模型自由写了一段话，里面出现：

    - **全国心理援助热线：400-161-9995**      ← 号码是模型编的，机构名还挂错了

团队自己拨通核验过的号码只有 **12356** 与 **010-82951332**。教学/安全场景里
**给错的求救号码，后果比不给更严重**，所以本层的唯一职责是：
把「给用户什么号码」从模型手里收回来，做成代码常量。

原判定为什么漏了这句
--------------------
B30 的 `CRISIS_PATTERNS` 是「自杀 / 我想死 / 不想活 / 割腕…」这类**短词表**，
「活着很没意思」「不想继续了」一个都不在里面 → 判定为普通问答 → 交给模型自由发挥。

本文件把词表扩成两级，并配套**教育语境豁免**（扩词表后没有豁免就会误伤教学提问）：

    CRISIS_STRONG      命中 1 个即触发（不想活 / 活着没意思 / 轻生 / 割腕…）
    CRISIS_WEAK        需 ≥2 个才触发（撑不下去 / 绝望 / 崩溃…）
    EDU_EXEMPT_STRONG  命中 1 个即豁免（教案 / 课件 / 班会 / 危机筛查 / 论文…）
    EDU_EXEMPT_WEAK    需 ≥2 个才豁免（教学 / 课程 / 老师 / 学生 / 识别 / 干预…）

与内容安全层的方向差异（重要，别搞反）
--------------------------------------
    server/safety_gate.py  = fail-OPEN  —— 教育场景宁可漏拦，不可误拦
    server/crisis.py       = fail-HIT   —— 宁可多给一张卡片，不可漏掉一个求救信号

三难场景都能站住：

    「如何识别学生轻生倾向并干预」        → weak 命中 识别/学生/干预 = 3 → 豁免 ✅
    「我是一名学生，活着好累，撑不下去」  → weak 只命中 学生 = 1      → 触发 ✅
    「我不想活了」                        → strong 直接命中           → 触发 ✅

号码清洗
--------
`strip_non_whitelist_numbers()` 把正文里形似电话、但不在白名单里的长串一律删掉；
删完只剩标题的空洞行（如 `- **全国心理援助热线：400-161-9995**`）整行丢弃。
它同时挂在 `server/api_server.py` 的 `/api/chat` 出口上 —— 不只危机路径，
**任何**模型回答里的号码都会被过一遍，因为「哪个回答会提到电话」无法预判。

回归：`python3 tests/run_crisis_regression.py`（单元级，不用起服务，exit 0 = 全过）
"""

from __future__ import annotations

import logging
import re
from typing import Any

_log = logging.getLogger("study_liu.safety.crisis")


# ============================================================
# 热线：唯一真值来源，任何情况下都不由模型生成
# ============================================================
# 决策记录（2026-09-26）：只保留团队已自行拨通核验的号码。
# 任何新增号码都必须先人工核验并在此登记，否则它就是下一个幻觉。
HOTLINES: list[dict[str, str]] = [
    {
        "name": "全国统一心理援助热线",
        "tel": "12356",
        "note": "国家卫生健康委员会主管 · 24 小时 · 免费 · 保密",
    },
    {
        "name": "北京心理危机研究与干预中心",
        "tel": "010-82951332",
        "note": "24 小时 · 免费 · 保密",
    },
]

# 清洗时保留的号码（去分隔符后的纯数字集合）
_ALLOWED_NUMBERS = {re.sub(r"[^0-9]", "", h["tel"]) for h in HOTLINES}


# ============================================================
# 触发词表
# ============================================================
# Tier1 强信号：命中 1 个即视为危机表达（除非被下方豁免拦下）
CRISIS_STRONG = [
    # 直接表述
    "不想活", "不想继续了", "活不下去", "活着没意思", "活着没意义", "活着好累",
    "活着太累", "活够了", "一了百了", "了结生命", "结束生命", "想结束一切",
    "结束这一切", "想去死", "想死", "死了算了", "不如死了", "不如死去",
    # 自伤概念
    "自杀", "轻生", "自尽", "自我了断", "寻死", "厌世", "告别这个世界",
    "伤害自己", "自残", "自伤",
    # 具体意象（宁可误报：即便误报也只是多给一张卡片）
    "割腕", "割脉", "烧炭", "跳楼", "跳河", "服毒", "安眠药自杀",
    # 求方法 / 网络欺凌（沿用 B30 既有词表，别丢）
    "教我怎么死", "帮我自杀", "怎么自杀", "自杀方法", "你怎么不去死",
]

# Tier2 弱信号：需 ≥2 个同时命中（单独出现不足以判断）
CRISIS_WEAK = [
    "撑不下去", "熬不下去", "撑不住", "熬不住", "走不下去了", "坚持不下去了",
    "绝望", "没有意义", "毫无意义", "不如消失", "想消失", "没人需要我",
    "我好痛苦", "很痛苦", "太痛苦", "崩溃", "好想哭", "活着很累", "不想醒来",
    "不想醒来面对", "被抛弃", "没人懂我", "一切都不会好了", "好想结束",
]

# ============================================================
# 教育语境豁免（方向与 fail-HIT 相反，只收最保守的词）
# ============================================================
# ⚠️ 收录标准：**只有"讲义/教研"意思明确的词才配强豁免**。
#    曾经想收「论文 / 课题研究 / 这门课」，但它们是**双向**的 ——
#    「我不想活了，论文写不完了」是一个真学生在求助，收了就把人漏掉。
#    宁可让教学提问多拿一张卡片，也不能把真求救豁免掉（fail-HIT 的底线）。
EDU_EXEMPT_STRONG = [
    "教案", "课件", "班会", "校本", "说课", "公开课", "家长会", "心理普查",
    "危机筛查", "谈心谈话", "教学大纲", "主题班会", "心理健康中心的老师",
    "辅导员培训", "危机干预预案",
]

# 弱豁免：需 ≥2 个才豁免
EDU_EXEMPT_WEAK = [
    "教学", "课程", "讲座", "培训", "课堂", "老师", "教师", "学生", "同学",
    "识别", "干预", "预防", "筛查", "辅导", "疏导", "班主任", "辅导员",
]


# ============================================================
# 卡片文案（同样是代码常量，不经模型）
# ============================================================
# ⚠️ 前端契约：ResultsGrid 的 crisisLines 是 `answer.split("\n")` 逐行渲染，
#    所以这里**必须用换行符分隔**，不能像另一版实现那样用空格拼成一整段。
#    （那版注释写的是「前端按空格切行」，那是另一个前端版本的契约，别照抄。）
CRISIS_LINES = [
    "我听到了。你愿意把这句话说出来，本身就需要勇气。",
    "如果你现在有伤害自己的冲动，请先联系下面两条热线——它们 24 小时有人接听。",
    "如果你身边的情况已经紧急，请直接拨打 120 或 110。",
    "下面这两个号码是系统直接给出的，不经过 AI 生成，你可以放心拨打。",
]

# 热线以「【机构 号码】（说明）」成行给出：
#   - /api/chat 走纯文本气泡，用户直接看得到号码；
#   - /api/plan 走热线卡片，前端会把这批以「【」开头的行从正文里滤掉，避免重复。
CRISIS_HOTLINE_LINES = [
    "【%s %s】（%s）" % (h["name"], h["tel"], h["note"]) for h in HOTLINES
]


# ============================================================
# 号码清洗
# ============================================================
# 覆盖国内常见号码形态（分组写法与国内拨号习惯一致，别写成连续数字）。
# 教训记录（2026-09-26 实跑修正）：初版把手机号写成 1[3-9]\d{2}（4 位前缀），
# 导致 "138-1234-5678" 完全匹配不上；区号版也只有 \d{7,8}，
# 漏掉 "0755-2653-1234" 这种 4-4 分组写法。两类错都是**只有跑一遍才发现得了**。
# 刻意不收：日期（2026-12-23）、纯数字编号，避免误伤学习计划正文。
#
# ★ 第二处实跑修正（2026-09-26，被 tests/run_crisis_regression.py 抓到）：
#   前后环视写成 (?<!\d) / (?!\d) 时，ISBN「978-7-111-12345-6」里的 "12345"
#   会被 "123\d{2}" 这条短号规则吃掉，变成「978-7-111--6」。
#   推荐书单里出现 ISBN 是很正常的事，所以把环视收紧成 (?<![\d-]) / (?![\d-])：
#   只认「独立成串」的号码，紧挨着连字符或数字的片段一律不碰。
#   已知取舍：12306 / 12315 / 12333 这类**真的** 123xx 短号也会被清掉。
#   这是有意的 —— 本层的目标是"不让学生看到任何未经核验的号码"，
#   宁可少给一个参考电话，也不给一个可能挂错机构名的号码。
_PHONE_RE = re.compile(
    r"""
    (?<![\d-])
    (?:
        1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}          # 手机号 138-1234-5678
      | 0\d{2,3}[-\s]?\d{7,8}                   # 区号固话 010-82951332
      | 0\d{2,3}[-\s]?\d{4}[-\s]?\d{3,4}        # 区号固话 0755-2653-1234
      | 400[-\s]?\d{3}[-\s]?\d{4}               # 400-161-9995
      | 800[-\s]?\d{3}[-\s]?\d{4}               # 800-xxx-xxxx
      | 95\d{3}                                 # 95xxx 客服短号
      | 123\d{2}                                # 123xx 政务短号（含 12356）
    )
    (?![\d-])
    """,
    re.VERBOSE,
)

# “标签行”：列表符 + 可选粗体 + 短标签 + 冒号 + 可选粗体，没有别的实质内容
# 用于丢弃 `- **全国心理援助热线：**` 这种号码被删后只剩标题的空洞行。
_LABEL_ONLY_RE = re.compile(
    r"^\s*[-*·•#>]*\s*[*_`]*\s*[^\s：:_`*·•-]{2,24}\s*[：:]\s*[*_`]*\s*$"
)

# 号码被删后悬空在句尾的引导词：「老师，电话 。」→「老师。」
_DANGLING_RE = re.compile(
    r"(电话|热线|联系方式|号码)\s*(是|为|可)?\s*[。！？]?\s*$")
# 句号/逗号前多余的空格：「电话 。」→「电话。」
_SPACE_BEFORE_PUNC_RE = re.compile(r"\s+([。！？，、；：])")
# 「张老师，。」→「张老师。」（删词后遗留的连排标点）
_DOUBLE_PUNC_RE = re.compile(r"[，、；：]{1,}(?=[。！？])")

# 判断一行删掉号码后是否还有实质内容（用来丢弃只剩标题的空行）
_RESIDUE_RE = re.compile(r"[\s\*\-\·\>\`\│\|\：\:\，\。\、\（\）\(\)\[\]【】0-9]+")


def _normalize_digits(s: str) -> str:
    """去掉分隔符，取纯数字比对用。"""
    return re.sub(r"[^0-9]", "", s)


def _line_has_content(line: str) -> bool:
    """删掉标点与数字后，该行还有没有实际文字。"""
    return len(_RESIDUE_RE.sub("", line).strip()) >= 6


def _replace_phone(m: re.Match) -> str:
    """白名单号码原样保留，其余号码清空。"""
    return m.group(0) if _normalize_digits(m.group(0)) in _ALLOWED_NUMBERS else ""


def strip_non_whitelist_numbers(text: str) -> str:
    """删掉正文中所有不在白名单里的电话号码。

    命中号码后：
      - 号码本身删除
      - 删除后整行已无实质内容（例如 `- **全国心理援助热线：400-161-9995**`）→ 整行丢弃

    Args:
        text: 模型原文（可能含编造号码）

    Returns:
        清洗后的文本
    """
    if not text:
        return ""

    keep: list[str] = []
    for line in text.splitlines():
        found = list(_PHONE_RE.finditer(line))
        has_other = any(_normalize_digits(m.group(0)) not in _ALLOWED_NUMBERS for m in found)
        has_ok = any(_normalize_digits(m.group(0)) in _ALLOWED_NUMBERS for m in found)

        cleaned = _PHONE_RE.sub(_replace_phone, line)

        # 删掉非白名单号码后，整行只剩个标题（例如「- **全国心理援助热线：**」）→ 整行丢弃。
        # 但如果这行本就含白名单号码（核验过的热线），必须保留。
        if has_other and not has_ok and _LABEL_ONLY_RE.match(cleaned):
            continue

        # 同上，只在「确实删过号码」的行上做收尾清理，把
        #   「也可以联系你的辅导员张老师，电话 。」 → 「也可以联系你的辅导员张老师。」
        # 这条限制很重要：绝不碰没删过号码的行，避免误伤正常正文里的「打个电话。」。
        if has_other and not has_ok:
            cleaned = _SPACE_BEFORE_PUNC_RE.sub(r"\1", cleaned)
            cleaned = _DANGLING_RE.sub("。", cleaned)
            cleaned = _SPACE_BEFORE_PUNC_RE.sub(r"\1", cleaned)
            cleaned = _DOUBLE_PUNC_RE.sub("", cleaned)

        keep.append(cleaned)

    # 收敛连续空行
    out = "\n".join(keep)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ============================================================
# 主判定
# ============================================================
def _hits(text: str, words: list[str]) -> list[str]:
    """命中的词列表（大小写不敏感）。"""
    low = (text or "").lower()
    return [w for w in words if w.lower() in low]


def crisis_verdict(text: str) -> tuple[bool, str | None]:
    """判断输入是否为危机表达。

    Args:
        text: 用户原始输入（课程名 / 提问）

    Returns:
        (is_crisis, hit_word)。非危机时 hit_word 为 None。
    """
    try:
        t = (text or "").strip()
        if not t:
            return (False, None)

        # --- 1. 先找危机信号 ---
        strong = _hits(t, CRISIS_STRONG)
        if strong:
            hits = strong
        else:
            weak = _hits(t, CRISIS_WEAK)
            if len(weak) < 2:
                return (False, None)
            hits = weak

        # --- 2. 再看教育语境豁免（让自己的教学请求不被误判） ---
        if _hits(t, EDU_EXEMPT_STRONG):
            return (False, None)
        if len(_hits(t, EDU_EXEMPT_WEAK)) >= 2:
            return (False, None)

        _log.info("crisis hit=%r text=%r", hits[0], t[:60])
        return (True, hits[0])

    except Exception:                       # fail-safe：判定层出错绝不拖垮主流程
        _log.exception("crisis_verdict 异常，按非危机处理")
        return (False, None)


def crisis_answer(extra_text: str = "") -> str:
    """组装危机回答正文。

    Args:
        extra_text: 追加的模型原文（会先做号码清洗）。为空则只返回写死的卡片文案。

    Returns:
        可直接返回前端的字符串。**行与行之间用 \\n 分隔**——
        前端 ResultsGrid 是 `answer.split("\\n")` 逐行渲染，空格拼接会挤成一整段。
    """
    parts = list(CRISIS_LINES) + list(CRISIS_HOTLINE_LINES)
    body = strip_non_whitelist_numbers(extra_text or "")
    if body:
        parts.append(body)
    return "\n".join(parts).strip()


def crisis_result_payload(course: str, extra_text: str = "") -> dict[str, Any]:
    """SSE /api/plan/stream 与 POST /api/plan 短路时直发的前端 result 结构。

    字段与前端 ResultsGrid / App.vue 的实际读取保持一致：
        result.type        === "crisis"           → 渲染热线卡片，不渲染三栏
        result.hotlines    = [{name, tel, note}]  → tel: 拨号链接
        result.answer      → 按 "\\n" 切分渲染成多行（以「【」开头的行由卡片接管，正文里滤掉）
        result.outline/resources/plan 必须是数组 → 前端会直接读 .length，缺字段会抛异常
        result.duration_ms → StatusBar 的耗时；短路时就是几毫秒，这本身就是证据
    """
    return {
        "ok": True,
        "type": "crisis",
        "course": course,
        "outline": [],
        "resources": [],
        "plan": [],
        "plan_items": [],
        "answer": crisis_answer(extra_text),
        "hotlines": HOTLINES,
        "source": "crisis_intervention",
        "profile_text": "",
        "stats": {"outline": 0, "resources": 0, "plan": 0},
        "markdown": "",
        "from_cache": False,
        "degraded": None,
        "duration_ms": 0,
        "ms": 0,
    }


def crisis_chat_response(question: str = "", extra_text: str = "") -> dict[str, Any]:
    """/api/chat 命中危机时的响应体。

    聊天面板不渲染 ResultsGrid 的热线卡片（那是 plan 结果的 UI），
    所以这里把号码以纯文本写进 answer，保证用户不看卡片也拿得到正确号码。
    """
    return {
        "ok": True,
        "type": "crisis",
        "question": question,
        "answer": crisis_answer(extra_text),
        "hotlines": HOTLINES,
        "source": "crisis_intervention",
    }


__all__ = [
    "HOTLINES",
    "CRISIS_STRONG",
    "CRISIS_WEAK",
    "EDU_EXEMPT_STRONG",
    "EDU_EXEMPT_WEAK",
    "CRISIS_LINES",
    "CRISIS_HOTLINE_LINES",
    "strip_non_whitelist_numbers",
    "crisis_verdict",
    "crisis_answer",
    "crisis_result_payload",
    "crisis_chat_response",
]
