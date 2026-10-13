# -*- coding: utf-8 -*-
"""接口健壮性回归：畸形入参不许把接口打成 500。

用法（在仓库根目录执行）：

    python tests/run_api_robustness_regression.py

背景（2026-10-13 线上实测）：
    历史写法 `(body.get("course") or "").strip()` 只在客户端老实传字符串时成立，
    任何非字符串（数字 / 列表 / 对象）都会在 .strip() 上抛 AttributeError，
    被 do_POST 的兜底 except 吞成 500「服务暂时不可用」。实测三个活例子：
        GET  /api/trace?limit=abc          → 500
        POST /api/plan   {"course":123}     → 500
        POST /api/login  {"username":123}   → 500
    也就是说任何访客都能用一个数字把公开接口打成 500。
    修复是引入 `_as_text()` / `_as_int()` 两个安全取值助手并全量替换。

本脚本做两件事：
  1) 源检查：安全助手在、危险的裸 strip 写法不在了；
  2) 功能检查：把这两个助手**从真实源码里抠出来 exec**，直接验证取值行为——
     不 import api_server（那会拉起 MySQL / 建 schema / 建默认管理员）。
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
API = os.path.join(REPO_ROOT, "server", "api_server.py")

PASS, FAIL = 0, 0


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  ok  %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s  %s" % (name, extra))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_helpers(src):
    """从 api_server.py 里抽出 _as_text / _as_int 的定义并执行。"""
    ns = {}
    for fn in ("_as_text", "_as_int"):
        m = re.search(r"^def %s\(.*?(?=^\S|\Z)" % fn, src, re.M | re.S)
        if not m:
            raise AssertionError("找不到 %s 的定义" % fn)
        exec(compile(m.group(0), fn, "exec"), ns)
    return ns


def test_source_guards():
    print("[1] 源检查：助手存在 + 危险写法已清除")
    if not os.path.exists(API):
        check("api_server_exists", False, API)
        return None
    src = read(API)
    check("helper_as_text_defined", "def _as_text(" in src)
    check("helper_as_int_defined", "def _as_int(" in src)
    # 先去掉整行注释（说明文字里会引用这个旧写法，不能算命中），
    # 再排除 str(...) 包裹的安全写法——那三种本来就防得住非字符串。
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    bad = re.findall(r'(?<!str)\(body\.get\([^)]*\)[^)]*\)\s*\.strip\(\)', code)
    check("no_unsafe_body_strip", not bad, bad[:3])
    # limit 那行必须走 _as_int，不能再是裸 int(...)
    trace_line = next((ln for ln in src.splitlines() if 'query.get("limit")' in ln), "")
    check("trace_limit_guarded", "_as_int(" in trace_line, trace_line.strip())
    # _as_int 必须带上限，避免 ?limit=99999999 把整个日志吐出去
    check("trace_limit_capped", "high=1000" in trace_line, trace_line.strip())
    return src


def test_helper_behaviour(src):
    print("[2] 功能检查：_as_text / _as_int 的取值行为")
    ns = load_helpers(src)
    as_text, as_int = ns["_as_text"], ns["_as_int"]

    # _as_text：标量照收，容器/bool/None 当没传
    check("text_str_strips", as_text("  离散数学  ") == "离散数学")
    check("text_int_accepted", as_text(123) == "123")
    check("text_float_accepted", as_text(1.5) == "1.5")
    check("text_none_is_empty", as_text(None) == "")
    check("text_bool_is_empty", as_text(True) == "")
    check("text_list_is_empty", as_text(["a", "b"]) == "")
    check("text_dict_is_empty", as_text({"a": 1}) == "")

    # 这些正是当年打出 500 的入参，现在必须安全收敛
    check("text_no_crash_on_int", as_text(123) == "123")
    check("text_no_crash_on_list", as_text([1, 2, 3]) == "")

    # _as_int：非法回落 default，越界夹紧
    check("int_parses", as_int("50", 120) == 50)
    check("int_bad_falls_back", as_int("abc", 120) == 120)
    check("int_none_falls_back", as_int(None, 120) == 120)
    check("int_empty_falls_back", as_int("", 120) == 120)
    check("int_clamped_high", as_int("999999999", 120, low=1, high=1000) == 1000)
    check("int_clamped_low", as_int("-5", 120, low=1, high=1000) == 1)
    check("int_float_string_rejected", as_int("1e5", 120, low=1, high=1000) == 120)
    return ns


def test_call_sites_cover_every_endpoint():
    print("[3] 覆盖检查：主要写接口都改用了安全取值")
    src = read(API)
    for name, path in (
        ("plan", '"/api/plan"'),
        ("chat", '"/api/chat"'),
        ("login", '"/api/login"'),
        ("register", '"/api/register"'),
        ("profile", '"/api/profile"'),
        ("mindmap", '"/api/mindmap"'),
        ("quiz_grade", '"/api/quiz/grade"'),
        ("export", '"/api/export"'),
    ):
        # 同名路径在 do_GET / do_POST 里各有一处，所以「任意一块」用上安全取值即可。
        pat = (r'if path == %s:(.*?)(?=\n {12}if path|\n {8}return self\._send_json\(\{"ok": False, "error": f")'
               % re.escape(path))
        blocks = [m.group(1) for m in re.finditer(pat, src, re.S)]
        ok = any("_as_text(" in b or "_require_" in b or "_auth()" in b for b in blocks)
        check("write_endpoint_uses_helper:%s" % name, ok,
              "%s 命中 %d 块" % (path, len(blocks)))


def test_quiz_container_params_guarded():
    """[4] quiz.generate_quiz 的 topics / avoid_stems 必须是列表。

    传标量会 `for t in (topics or [])` → TypeError → 500
    （2026-10-13 线上实测 POST /api/quiz/generate
     {"course":"Python入门","topics":5} → TypeError: 'int' object is not iterable，
     quiz.py:1051）。

    与 run_api_contract_regression.py 互补：那个查「调用方关键字 vs 被调方签名」
    漂移（6ea66c0 事故），这个查「本该是列表的字段被塞了标量」。
    """
    print("[4] 类型收敛：quiz 的 topics / avoid_stems 必须是列表")
    quiz = read(os.path.join(REPO_ROOT, "server", "quiz.py"))
    check("quiz_topics_guarded",
          "isinstance(topics, (list, tuple))" in quiz,
          "topics 未做 isinstance 收敛")
    check("quiz_avoid_guarded",
          "isinstance(avoid_stems, (list, tuple))" in quiz,
          "avoid_stems 未做 isinstance 收敛")


if __name__ == "__main__":
    print("=" * 62)
    print("接口健壮性回归：畸形入参不得打成 500")
    print("=" * 62)
    src = test_source_guards()
    if src:
        test_helper_behaviour(src)
        test_call_sites_cover_every_endpoint()
    test_quiz_container_params_guarded()
    print()
    print("=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    print("结果：%s" % ("全部通过，可以提交" if FAIL == 0 else "有不过的，先修再提交"))
    sys.exit(1 if FAIL else 0)