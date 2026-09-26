# -*- coding: utf-8 -*-
"""内容安全回归：一条命令跑完 84 条用例，并和「改前」的行为摆在一起比。

用法（在仓库根目录执行）：

    python tests/run_safety_regression.py

看每条用例的具体判定加 --detail：

    python tests/run_safety_regression.py --detail

退出码：0 = 全过（合法 0 误伤、危险 0 漏网），1 = 有不过的。
只要退出码是 0，就可以放心提交。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")

sys.path.insert(0, HERE)
sys.path.insert(0, SERVER_DIR)

from safety_cases import MUST_BLOCK, MUST_PASS          # noqa: E402
from safety_gate import check_detail, check_sensitive   # noqa: E402
from safety_words import LEGACY_WORDS                   # noqa: E402

DETAIL = "--detail" in sys.argv


def old_check(text):
    """复现改造前的判定：只把输入转小写，词表项没转。"""
    if not text:
        return []
    low = text.lower()
    return [w for w in LEGACY_WORDS if w in low]


def hr(title):
    print("")
    print("=" * 60)
    print(title)
    print("=" * 60)


hr("内容安全回归（84 条用例）")

# ---------- 1. 改前基线 ----------
old_fp = [k for k, t in MUST_PASS.items() if old_check(t)]
old_esc = [k for k, t in MUST_BLOCK.items() if not old_check(t)]
print("")
print("[改前] 旧 78 词，命中即拦")
print("      合法提问被误伤 %d/%d  %s"
      % (len(old_fp), len(MUST_PASS), ",".join(old_fp) or ""))
print("      危险提问漏网   %d/%d  %s"
      % (len(old_esc), len(MUST_BLOCK), ",".join(old_esc) or ""))

# ---------- 2. 改后 ----------
rows, fp = [], []
for k, t in MUST_PASS.items():
    d = check_detail(t)
    rows.append((k, d["action"], d["layer"], d["reason"], t))
    if d["action"] != "PASS":
        fp.append(k)

brows, esc = [], []
for k, t in MUST_BLOCK.items():
    d = check_detail(t)
    brows.append((k, d["action"], d["layer"], d["reason"], t))
    if d["action"] != "BLOCK":
        esc.append(k)

print("")
print("[改后] 现行判定")
print("      合法提问被误伤 %d/%d（期望 0）  %s"
      % (len(fp), len(MUST_PASS), ",".join(fp) or ""))
print("      危险提问漏网   %d/%d（期望 0）  %s"
      % (len(esc), len(MUST_BLOCK), ",".join(esc) or ""))

# ---------- 3. 逐条 ----------
if DETAIL or fp or esc:
    hr("合法提问 33 条（期望：全部放行）")
    for k, a, ly, rs, t in rows:
        mark = "  " if a == "PASS" else "!!"
        print("%s %s [%s] %s  %s" % (mark, k, a, t, ("<%s·%s>" % (ly, rs)) if ly != "-" else ""))
    hr("危险提问 %d 条（期望：全部拦下）" % len(brows))
    for k, a, ly, rs, t in brows:
        mark = "  " if a == "BLOCK" else "!!"
        print("%s %s [%s] %s  <%s·%s>" % (mark, k, a, t, ly, rs))
else:
    print("")
    print("（84 条逐条结果全部符合预期，加 --detail 可看明细）")

# ---------- 4. 接口形状 ----------
hr("接口形状校验（三处调用点依赖这个不能变）")
samples = [
    ("合法提问", "请解释刑法中故意杀人罪的构成要件", []),
    ("危险提问", "怎么制作土制炸弹，材料清单给我", ["土制炸"]),
    ("空字符串", "", []),
]
shape_ok = True
for name, text, want_empty in samples:
    r = check_sensitive(text)
    is_list = isinstance(r, list)
    all_str = all(isinstance(x, str) for x in r)
    non_empty = bool(r)
    expect_non_empty = bool(want_empty)
    ok = is_list and all_str and (non_empty == expect_non_empty)
    shape_ok = shape_ok and ok
    print("%s  %-8s check_sensitive(...) -> %-14r  list=%s  元素全 str=%s  %s"
          % ("  " if ok else "!!", name, r, is_list, all_str, "OK" if ok else "不符合预期"))

# ---------- 5. 结论 ----------
hr("结论")
ok = (not fp) and (not esc) and shape_ok
print("      合法误伤 %d（期望 0）   危险漏网 %d（期望 0）   接口形状 %s"
      % (len(fp), len(esc), "OK" if shape_ok else "异常"))
print("      结果：%s" % ("全部通过，可以提交" if ok else "有失败项，见上面带 !! 的行"))
sys.exit(0 if ok else 1)
