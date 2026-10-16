# -*- coding: utf-8 -*-
"""run_dependency_facts.py — 依赖事实核查回归（2026-10-16 事故复盘后新增）。

背景：此前对外口径「不依赖 LangChain 框架」只查了源码 import 层，而
langchain-tavily 的传递依赖（requires_dist）里就包含完整 langchain>=1.0.0,<2
——判据错配导致口径失实。同批修复见 server/web_tools.py（缺依赖补 warning
日志）与 server/quiz.py（_run_tool_agent 构造工具包 try，兑现降级注释承诺）。

本脚本把「用了哪些依赖」从人肉 grep 变成机器可复验的三层证据：
  1. 声明层：server/requirements.txt 登记了什么（必须钉版本，上下界）；
  2. 闭包层：importlib.metadata 解析每个已装依赖的传递闭包，禁止出现
     未登记的框架（FastAPI / Flask / Chroma / MySQL 系）；
  3. 源码层：降级路径存在性（quiz / web_tools 缺依赖时不冒 500、留日志）。

三层证据判据（同步写入 README 依赖策略一节）：
  - 凡「是否用了 X」的结论，三层齐全才能下判断；闭包层缺证据（依赖未安装）
    只能记 WARN，不得计 PASS——skip 不许伪装成 pass（2026-10-16 前车之鉴：
    run_quiz_regression 的 construction_skipped 长期以绿灯掩盖从未实测）。

用法：python tests/run_dependency_facts.py
退出码：0 = 无 FAIL（WARN 不阻塞，但报告末尾会列出「本轮未实测项」）。
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "server")
REQ_FILE = os.path.join(SERVER, "requirements.txt")
QUIZ = os.path.join(SERVER, "quiz.py")
WEB_TOOLS = os.path.join(SERVER, "web_tools.py")

# 闭包内禁止出现的未登记框架（规范化包名）。langchain / langgraph 不在禁列：
# 2026-10-15 队长已确认引入 LangChain 生态（见 requirements.txt 注释与 README 依赖策略）。
FORBIDDEN = {
    "fastapi", "flask", "chromadb", "pymysql", "mysqlclient",
    "mysql-connector-python", "sqlalchemy", "django",
}

_results = []  # (status, name, msg)  status ∈ PASS/FAIL/WARN


def check(name, ok, msg="", warn_only=False):
    status = ("WARN" if warn_only else "FAIL") if not ok else "PASS"
    _results.append((status, name, msg))
    suffix = (" — " + msg) if (msg and not ok) else ""
    print("  [%s] %s%s" % (status, name, suffix))
    return ok


def _norm(name):
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _req_name(spec):
    """'langchain-tavily>=0.2.18,<0.3' → 'langchain-tavily'。"""
    return re.split(r"[<>=!~\[\s;]", spec.strip(), 1)[0].strip().lower()


def _closure(dist_name):
    """BFS 解析传递依赖闭包（只算运行时 requires，跳过 extras）。"""
    seen, queue = set(), [_norm(dist_name)]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for req in (dist.requires or []):
            base, _, env = req.partition(";")
            if "extra" in env:
                continue
            dep = _req_name(base)
            if dep:
                queue.append(dep)
    return seen


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    print("== 依赖事实核查（三层证据：声明 / 闭包 / 源码）==\n")

    # ---------- 第 1 层：声明层 ----------
    print("[声明层] server/requirements.txt")
    declared = []
    for line in read(REQ_FILE).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        declared.append(s)
    if not check("req_nonempty", bool(declared), "requirements.txt 无任何依赖登记"):
        declared = []
    unpinned = [d for d in declared if not re.search(r"[<>=~!]", d)]
    check("req_version_pinned", not unpinned,
          "未钉版本（将无法复现闭包）: %s" % ", ".join(unpinned) if unpinned else "全部已钉版本")

    # ---------- 第 2 层：闭包层 ----------
    print("\n[闭包层] importlib.metadata 传递闭包")
    untested = []
    for spec in declared:
        name = _req_name(spec)
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            untested.append(name)
            continue
        closure = _closure(name)
        bad = sorted(closure & FORBIDDEN)
        check("closure_clean_%s" % name, not bad,
              "闭包含未登记框架: %s" % ", ".join(bad) if bad else
              "闭包 %d 包，无禁用项" % len(closure))
        # 事实记录：langchain-tavily 的闭包含 langchain（事故复现锚点）
        if name == "langchain-tavily":
            if "langchain" in closure:
                print("  [FACT] langchain-tavily 传递闭包内含 langchain —— "
                      "「不依赖 LangChain」的说法自此作废（2026-10-15 核实）")
            else:
                check("closure_contains_langchain", False,
                      "闭包未解析出 langchain，闭包计算可能失效", warn_only=True)
    if untested:
        for n in untested:
            check("closure_untested_%s" % n, False,
                  "本环境未安装，闭包未实测（记 WARN，不许计 PASS）", warn_only=True)

    # ---------- 第 3 层：源码层（降级路径存在性） ----------
    print("\n[源码层] 降级路径（缺依赖不冒 500、留日志）")
    quiz_src = read(QUIZ)
    web_src = read(WEB_TOOLS)
    check("quiz_tool_build_guarded",
          "Tavily 工具构造失败" in quiz_src and "try:" in quiz_src.split("_run_tool_agent", 1)[1][:600],
          "quiz._run_tool_agent 必须把 _build_tavily_tools 包 try（否则 ImportError 冒泡成 500）")
    check("webtools_degrade_logged",
          "langchain_tavily 不可导入" in web_src,
          "web_tools 两处 except 必须留 warning 日志（静默降级会掩盖依赖缺失）")

    # ---------- 汇总 ----------
    n_pass = sum(1 for s, _, _ in _results if s == "PASS")
    n_fail = sum(1 for s, _, _ in _results if s == "FAIL")
    n_warn = sum(1 for s, _, _ in _results if s == "WARN")
    print("\n== 汇总：PASS %d / FAIL %d / WARN %d ==" % (n_pass, n_fail, n_warn))
    if untested:
        print("本轮 %d 项未实测（依赖未安装）：%s" % (len(untested), ", ".join(untested)))
        print("→ 结论只能写「未实测」，不得写「未使用」。装齐后重跑本脚本再下结论。")
    if n_fail:
        print("存在 FAIL，退出码 1")
        sys.exit(1)
    print("无 FAIL，退出码 0")


if __name__ == "__main__":
    main()
