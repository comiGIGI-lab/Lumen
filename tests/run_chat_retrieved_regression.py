# -*- coding: utf-8 -*-
"""课程问答 retrieved 展示回归：前端必须把后端引用段落交给评委看见。

后端契约（已存在，本文件不改）：
    POST /api/chat → { answer, source, retrieved: [{id, title, score}, ...] }
    强相关命中最多 3 条；弱命中 retrieved=[]。

前端漏洞（本切片要修）：
    ChatPanel.ask() 原先只保存 answer/source，模板只渲染「来源：知识库」，
    评委看不到命中了哪篇资料。

用法（仓库根目录）：

    python tests/run_chat_retrieved_regression.py

退出码 0 = 全过。只读源文件，不起服务。
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
CHAT = os.path.join(REPO_ROOT, "web", "src", "components", "ChatPanel.vue")
ZH = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-zh.json")
EN = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-en.json")
API = os.path.join(REPO_ROOT, "server", "api_server.py")
LOOP = os.path.join(REPO_ROOT, "vendor", "study-liu", "core", "agent_loop.py")

FAILED = []
PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    chat = read(CHAT)
    zh = read(ZH)
    en = read(EN)
    api = read(API)
    loop = read(LOOP)

    print("backend contract (must stay)")
    check(
        "api_chat_forwards_retrieved",
        '"retrieved": res.get("retrieved") or []' in api
        or re.search(r'"retrieved"\s*:\s*res\.get\(\s*"retrieved"', api),
        "server/api_server.py /api/chat must keep forwarding retrieved",
    )
    check(
        "pipeline_citations_are_id_title_score",
        '"id": n.get("id")' in loop
        and '"title": n.get("title"' in loop
        and '"score": round(s, 2)' in loop,
        "agent_loop citations shape drifted",
    )
    check(
        "pipeline_returns_retrieved_key",
        '"retrieved": citations' in loop,
        "run_chat_pipeline must still return retrieved",
    )

    print("ChatPanel.ask() must persist retrieved")
    ask_match = re.search(
        r"async function ask\(\) \{.*?\n(?=function |\<\/script\>)",
        chat,
        re.S,
    )
    ask = ask_match.group(0) if ask_match else ""
    check("ask_function_found", bool(ask), "could not isolate ask()")
    check(
        "ask_reads_res_retrieved",
        "res.retrieved" in ask,
        "ask() never reads res.retrieved",
    )
    check(
        "ask_pushes_retrieved_on_ai_message",
        re.search(r"retrieved\s*:", ask) is not None,
        "AI message push does not include retrieved",
    )
    check(
        "ask_does_not_drop_retrieved_on_generate_only",
        "res.retrieved" in ask and "messages.value.push" in ask,
        "retrieved not wired into message list",
    )

    print("template must render citation titles")
    check(
        "template_iterates_retrieved",
        "m.retrieved" in chat and "v-for" in chat,
        "template does not iterate message.retrieved",
    )
    check(
        "template_shows_title",
        re.search(r"c\.title|cite\.title|item\.title", chat) is not None,
        "citation title not rendered",
    )
    check(
        "template_shows_score",
        re.search(r"c\.score|cite\.score|item\.score", chat) is not None,
        "citation score not rendered",
    )
    check(
        "empty_retrieved_hidden",
        re.search(
            r"m\.retrieved(?:\.length| &&)|retrieved && m\.retrieved",
            chat,
        )
        is not None,
        "empty retrieved must not paint a blank 参考资料 block",
    )

    print("i18n")
    check("zh_has_sources_label", "chatPanelX.8" in zh, "auto-zh.json missing chatPanelX.8")
    check("en_has_sources_label", "chatPanelX.8" in en, "auto-en.json missing chatPanelX.8")
    check("zh_label_is_cites", "参考资料" in zh, "中文标签应含「参考资料」")

    print("scope guard")
    check(
        "rag_thresholds_untouched",
        "RAG_MIN_SCORE = 1.0" in loop and "RAG_MIN_COVERAGE = 0.2" in loop,
        "do not retune RAG in this slice",
    )

    print()
    print("passed %d  failed %d" % (PASSED, len(FAILED)))
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print("  - %s" % name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
