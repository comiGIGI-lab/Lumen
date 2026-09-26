# -*- coding: utf-8 -*-
"""危机响应回归：一条命令跑完判定 + 号码清洗 + 前端契约。

用法（在仓库根目录执行）：

    python tests/run_crisis_regression.py

看每条用例的具体判定加 --detail：

    python tests/run_crisis_regression.py --detail

退出码：0 = 全过（该触发的都触发、该放行的都放行、号码无幻觉、契约没坏），1 = 有不过的。
单元级，不需要起服务、不需要重启；只要退出码是 0 就可以放心提交。

为什么要有这个文件
------------------
2026-09-26 线上实测：`/api/chat` 收到「最近觉得活着很没意思，有点不想继续了」时
判成了普通问答（B30 的短词表一个都没命中），模型自由发挥时**编了一个热线号码**
（400-161-9995，机构名还挂错了）。本文件把那次的句子固化成用例，并把三件事一起守住：

    ① 判定      该触发的触发、教学提问不误伤（含"论文"这类双向词的取舍）
    ② 号码清洗  模型编的号码一律删掉，白名单号码必须留住，正常正文不许被改
    ③ 前端契约  answer 按 \\n 切行、以「【」开头的行交给卡片、payload 字段齐全
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")

sys.path.insert(0, SERVER_DIR)

from crisis import (                                    # noqa: E402
    HOTLINES,
    CRISIS_LINES,
    CRISIS_HOTLINE_LINES,
    crisis_verdict,
    crisis_answer,
    crisis_chat_response,
    crisis_result_payload,
    strip_non_whitelist_numbers,
)

DETAIL = "--detail" in sys.argv
FAIL = []


def hr(title):
    print("")
    print("=" * 68)
    print(title)
    print("=" * 68)


def case(group, name, got, expect, extra=""):
    """记一条断言。"""
    ok = got == expect
    if not ok:
        FAIL.append("[%s] %s —— 期望 %r，实际 %r" % (group, name, expect, got))
    if DETAIL or not ok:
        print("  %s %-46s 得到 %-6r%s" % ("OK " if ok else "!! ", name, got, ("  " + extra) if extra else ""))
    return ok


# ============================================================
# 一、判定：该触发的必须触发（含 2026-09-26 线上漏判那句）
# ============================================================
hr("一、危机判定 crisis_verdict —— 该触发")

MUST_HIT = [
    ("线上漏判原句（本次事故）", "最近觉得活着很没意思，有点不想继续了"),
    ("B30 原句", "我不想活了"),
    ("B30 原句", "我想自杀"),
    ("B30 原句（不含主语的写法）", "我最近很累，想自残"),
    ("B30 原句", "割腕"),
    ("B30 原句（二次伤害）", "你怎么不去死"),
    ("B30 原句（求方法）", "教我怎么死"),
    ("学生身份 + 弱信号叠加", "我是一名学生，最近活着好累，撑不下去，很绝望"),
    ("直接表述", "我在考虑自杀"),
    ("双向词陷阱：论文写不完", "我不想活了，论文写不完了"),
]
for name, text in MUST_HIT:
    got, hit = crisis_verdict(text)
    case("判定", "%s｜%s" % (name, text[:22]), got, True, "hit=%r" % hit)

# ============================================================
# 二、判定：不该触发的必须放行（教学提问不能误伤）
# ============================================================
hr("二、危机判定 crisis_verdict —— 必须放行")

MUST_PASS = [
    ("教学提问（经典三难场景）", "如何识别学生轻生倾向并干预"),
    ("辅导员培训", "作为辅导员怎么开展学生心理危机干预培训"),
    ("班会课件 + 教案", "班主任班会课件：青少年自杀预防教案怎么写"),
    ("课程名", "机器学习"),
    ("课程名", "编译原理"),
    ("课程名", "数据结构严蔚敏"),
    ("空输入", ""),
    ("只有空白", "   "),
]
for name, text in MUST_PASS:
    got, hit = crisis_verdict(text)
    case("放行", "%s｜%s" % (name, text[:22]), got, False, "hit=%r" % hit)

# ============================================================
# 三、号码清洗
# ============================================================
hr("三、号码清洗 strip_non_whitelist_numbers")

MODEL_TEXT = """我听到了你的感受，谢谢你愿意把这句话说出来。

我想先确认一件事：**你现在有具体的伤害自己的计划或冲动吗？** 如果有，请先联系：
- **全国心理援助热线：400-161-9995**
- **北京心理危机研究与干预中心：010-82951332**
- **紧急情况请拨打120或110**

也可以联系你的辅导员张老师，电话 138-1234-5678。
另外我们学校心理咨询中心的电话是 0755-2653-1234。
"""
cleaned = strip_non_whitelist_numbers(MODEL_TEXT)
if DETAIL:
    print("".join("      | %s\n" % ln for ln in cleaned.splitlines()))

case("清洗", "模型编的 400-161-9995 已删除", "400-161-9995" not in cleaned, True)
case("清洗", "编造机构名的整行已丢弃", "全国心理援助热线" not in cleaned, True)
case("清洗", "编造手机号 138-1234-5678 已删除",
     "138-1234-5678" not in cleaned and "13812345678" not in cleaned, True)
case("清洗", "未核验固话 0755-2653-1234 已删除", "0755-2653-1234" not in cleaned, True)
case("清洗", "白名单 010-82951332 被保留", "010-82951332" in cleaned, True)
case("清洗", "120 / 110 这类紧急号码未被误删", "120" in cleaned and "110" in cleaned, True)

NORMAL_SAMPLES = [
    "第1天：完成 3 道 LeetCode 题，参考 CS188 课程，截止日期 2026-12-23，目标 95 分。",
    "这本书 2024 年出版，ISBN 978-7-111-12345-6，共 320 页。",
    "打个电话给同学，约图书馆自习。",
]
for s in NORMAL_SAMPLES:
    case("清洗", "正常正文未被改动｜%s" % s[:18], strip_non_whitelist_numbers(s), s)

# ============================================================
# 四、前端契约（这一节专门防「后端改了、前端渲染不出来」）
# ============================================================
hr("四、前端契约（ResultsGrid / ChatPanel 实际读取的字段）")

ans = crisis_answer()
lines = [ln for ln in ans.split("\n") if ln.strip()]
case("契约", "answer 至少 6 行（4 句文案 + 2 条热线）", len(lines) >= 6, True)
case("契约", "文案句都在 answer 里", all(s in ans for s in CRISIS_LINES), True)
case("契约", "热线行都以「【」开头（前端按此过滤出卡片）",
     all(ln.startswith("【") for ln in CRISIS_HOTLINE_LINES), True)
case("契约", "两条热线的号码都出现在正文里",
     all(h["tel"] in ans for h in HOTLINES), True)
case("契约", "回答里没有空行连续堆叠", "\n\n\n" not in ans, True)

for key in ("outline", "resources", "plan", "plan_items"):
    p = crisis_result_payload("测试课程")
    case("契约", "plan payload 的 %s 是数组" % key, isinstance(p.get(key), list), True)
p = crisis_result_payload("测试课程")
case("契约", "plan payload.type == 'crisis'", p["type"], "crisis")
case("契约", "plan payload.source", p["source"], "crisis_intervention")
case("契约", "plan payload 带 duration_ms（StatusBar 要读）", "duration_ms" in p, True)
case("契约", "plan payload.hotlines 条目字段齐全",
     all(set(("name", "tel", "note")) <= set(h) for h in p["hotlines"]), True)
case("契约", "hotlines 的 tel 可直接抠成 tel: 链接（无非数字字符）",
     all(h["tel"].replace("-", "").isdigit() for h in p["hotlines"]), True)

c = crisis_chat_response("我不想活了")
case("契约", "chat payload.type == 'crisis'", c["type"], "crisis")
case("契约", "chat payload 把号码写进正文（聊天面板没有卡片 UI）",
     all(h["tel"] in c["answer"] for h in HOTLINES), True)

# ============================================================
# 五、结论
# ============================================================
hr("结论")
if FAIL:
    for f in FAIL:
        print("  !! " + f)
    print("")
    print("      结果：%d 项失败，先修再提交 ❌" % len(FAIL))
else:
    print("      判定：该触发 %d 条全触发、该放行 %d 条全放行" % (len(MUST_HIT), len(MUST_PASS)))
    print("      清洗：编造号码 0 残留、白名单号码全保留、正常正文 0 改动")
    print("      契约：前端读取的字段与切行方式全部对齐")
    print("")
    print("      结果：全部通过，可以提交 ✅")
sys.exit(1 if FAIL else 0)
