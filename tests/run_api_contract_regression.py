# -*- coding: utf-8 -*-
"""调用契约回归：api_server 传给各模块的关键字参数，必须真的在被调函数签名里。

用法（在仓库根目录执行）：

    python tests/run_api_contract_regression.py

为什么需要它（2026-10-13 线上事故）：
    `POST /api/quiz/generate` **对任何请求都返回 500**，而且和入参无关 ——
    api_server 一直在传 `include_wrong=`，但 `quiz.generate_quiz()` 的签名里
    根本没有这个参数（`iter_generate_quiz()` 有）。一个 commit 给流式路径加了
    参数、顺带在两个调用点都写上，却漏改了整卷那条 → TypeError。
    结果：整个「闯关」出题接口是死的，而单元测试全绿（它们直接调 quiz 模块，
    从不经过 api_server 的调用点）。

    这类「调用方 / 被调方签名漂移」用单元测试很难发现，用 AST 静态比对最便宜。
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER = os.path.join(REPO_ROOT, "server")
VENDOR_TOOLS = os.path.join(REPO_ROOT, "vendor", "study-liu", "tools")

API = os.path.join(SERVER, "api_server.py")

# api_server.py 里的模块别名 → 真实源码文件（只列会被它的业务调用命中的）
MODULE_FILES = {
    "quiz_mod": os.path.join(SERVER, "quiz.py"),
    "accounts": os.path.join(SERVER, "accounts.py"),
    "wrong_book_store": os.path.join(SERVER, "storage_wrongbook.py"),
    "mindmap_store": os.path.join(SERVER, "storage_mindmap.py"),
    "progress_store": os.path.join(SERVER, "storage_progress.py"),
    "storage_profiles": os.path.join(SERVER, "storage_profiles.py"),
    "storage_ratelimit": os.path.join(SERVER, "storage_ratelimit.py"),
    "cache_store": os.path.join(VENDOR_TOOLS, "cache_store.py"),
    "retrieval_hybrid": os.path.join(SERVER, "retrieval_hybrid.py"),
    "wrongbook_quiz_mod": os.path.join(SERVER, "wrongbook_quiz.py"),
}

PASS, FAIL = 0, 0


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  ok  %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s  %s" % (name, extra))


def _signatures(path):
    """{函数名: (参数名集合, 是否有 **kwargs)}"""
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            names = {x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)}
            out[node.name] = (names, a.kwarg is not None)
    return out


def test_call_contracts():
    print("[1] api_server → 各模块：关键字参数必须存在于被调函数签名")
    with open(API, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), API)

    sigs = {}
    for alias, path in MODULE_FILES.items():
        if os.path.exists(path):
            sigs[alias] = _signatures(path)

    problems, checked = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)):
            continue
        alias, fname = fn.value.id, fn.attr
        if alias not in sigs:
            continue
        table = sigs[alias]
        if fname not in table:          # 可能是动态属性，跳过
            continue
        params, has_kwargs = table[fname]
        if has_kwargs:
            continue
        checked += 1
        for kw in node.keywords:
            if kw.arg is None:          # **kwargs 展开，静态看不出来
                continue
            if kw.arg not in params:
                problems.append("%s.%s() 收到未知关键字 %s= (行%s)"
                                % (alias, fname, kw.arg, getattr(kw.value, "lineno", "?")))

    check("checked_enough_call_sites", checked >= 8, "只检查了 %d 处" % checked)
    check("no_signature_drift", not problems, "; ".join(problems[:4]))
    return problems


def test_quiz_specific():
    """把这次事故点单独钉死，避免以后又被别的重构绕过去。"""
    print("[2] 事故点护栏：generate_quiz 必须接受 include_wrong")
    sigs = _signatures(os.path.join(SERVER, "quiz.py"))
    check("generate_quiz_exists", "generate_quiz" in sigs)
    if "generate_quiz" in sigs:
        params, _ = sigs["generate_quiz"]
        check("generate_quiz_accepts_include_wrong", "include_wrong" in params,
              sorted(params))
    if "iter_generate_quiz" in sigs:
        params, _ = sigs["iter_generate_quiz"]
        check("iter_generate_quiz_accepts_include_wrong", "include_wrong" in params,
              sorted(params))


def test_quiz_stream_not_login_gated():
    """闯关流式不得再出现「未登录直接 401」——设计是游客可用 + 每日限额。"""
    print("[3] 闯关流式：不应有登录硬门槛（与方案流式保持一致）")
    with open(API, "r", encoding="utf-8") as f:
        src = f.read()
    m = src.find("def _handle_quiz_stream")
    block = src[m:m + 4000] if m >= 0 else ""
    check("quiz_stream_found", bool(block))
    check("quiz_stream_no_login_gate",
          'not self._auth(query)' not in block,
          "仍存在未登录 401 门槛")
    check("quiz_stream_keeps_anon_quota", "_enforce_anon_llm_quota(query)" in block)


if __name__ == "__main__":
    print("=" * 62)
    print("调用契约回归：api_server 与被调模块的签名一致性")
    print("=" * 62)
    test_call_contracts()
    test_quiz_specific()
    test_quiz_stream_not_login_gated()
    print()
    print("=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    print("结果：%s" % ("全部通过，可以提交" if FAIL == 0 else "有不过的，先修再提交"))
    sys.exit(1 if FAIL else 0)