# -*- coding: utf-8 -*-
"""方案链路引用知识库回归：生成方案必须能吃到刚导入材料，评委看得见标题。

现网漏洞（本切片要修）：
    run_plan_pipeline 只走 Planner → Searcher → Writer → Reviewer，
    不读 KnowledgeStore；缓存 key 只有 schema+课程+画像，
    导入新课件后 24h 内仍命中旧方案；build_payload / ResultsGrid
    也没有 retrieved。

硬禁止（本文件守住）：
    不改 RAG_MIN_SCORE / RAG_MIN_COVERAGE（1.0 / 0.2）
    不改 /api/chat 字段与 ChatPanel 契约
    不把空 URL 的课件塞进 resources（Reviewer 在 LLM 模式下会丢掉）
    不用 v-html 渲染知识库标题

用法（仓库根目录）：

    python tests/run_plan_kb_regression.py

退出码 0 = 全过。源文件检查不起服务；runtime 段只打 mock，不发外网。
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GRID = os.path.join(REPO_ROOT, "web", "src", "components", "ResultsGrid.vue")
CHAT = os.path.join(REPO_ROOT, "web", "src", "components", "ChatPanel.vue")
ZH = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-zh.json")
EN = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-en.json")
API = os.path.join(REPO_ROOT, "server", "api_server.py")
LOOP = os.path.join(REPO_ROOT, "vendor", "study-liu", "core", "agent_loop.py")
CACHE = os.path.join(REPO_ROOT, "vendor", "study-liu", "tools", "cache_store.py")
PLANNER = os.path.join(REPO_ROOT, "vendor", "study-liu", "agents", "planner.py")
WRITER = os.path.join(REPO_ROOT, "vendor", "study-liu", "agents", "writer.py")
REVIEWER = os.path.join(REPO_ROOT, "vendor", "study-liu", "agents", "reviewer.py")

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


def _fn(src, name):
    m = re.search(
        r"def %s\([^)]*\)(?:\s*->\s*[^:]+)?:.*?(?=\n(?:def |class )|\Z)"
        % re.escape(name),
        src,
        re.S,
    )
    return m.group(0) if m else ""


def main():
    grid = read(GRID)
    chat = read(CHAT)
    zh = read(ZH)
    en = read(EN)
    api = read(API)
    loop = read(LOOP)
    cache = read(CACHE)
    planner = read(PLANNER)
    writer = read(WRITER)
    reviewer = read(REVIEWER)

    plan_fn = _fn(loop, "run_plan_pipeline")
    chat_fn = _fn(loop, "run_chat_pipeline")
    payload_fn = _fn(api, "build_payload")
    key_fn = _fn(cache, "make_cache_key")
    outline_fn = _fn(planner, "plan_outline")
    write_fn = _fn(writer, "write_plan")

    print("pipeline must retrieve knowledge by course name")
    check("plan_fn_found", bool(plan_fn), "could not isolate run_plan_pipeline")
    check(
        "plan_imports_knowledge_store",
        "KnowledgeStore" in plan_fn or "KnowledgeStore" in loop,
        "run_plan_pipeline never touches KnowledgeStore",
    )
    check(
        "plan_calls_retrieve",
        "retrieve(" in plan_fn or ("_retrieve" in plan_fn and "retrieve(" in loop),
        "plan pipeline does not retrieve()",
    )
    check(
        "plan_reuses_rag_thresholds",
        "RAG_MIN_SCORE" in plan_fn and "RAG_MIN_COVERAGE" in plan_fn,
        "plan retrieve must reuse chat RAG gates, not a new threshold",
    )
    check(
        "plan_result_has_retrieved",
        re.search(r'["\']retrieved["\']\s*:', plan_fn) is not None,
        "run_plan_pipeline result dict has no retrieved",
    )
    check(
        "plan_citations_are_id_title_score",
        '"id": n.get("id")' in loop
        and '"title": n.get("title"' in loop
        and '"score": round(s, 2)' in loop,
        "citations shape drifted from chat contract",
    )
    check(
        "plan_passes_kb_into_planner",
        "kb_context" in plan_fn and "plan_outline" in plan_fn,
        "Planner is not given kb_context",
    )
    check(
        "plan_passes_kb_into_writer",
        "kb_context" in plan_fn and "write_plan" in plan_fn,
        "Writer is not given kb_context",
    )
    check(
        "planner_accepts_kb_context",
        "kb_context" in outline_fn,
        "plan_outline has no kb_context param",
    )
    check(
        "writer_accepts_kb_context",
        "kb_context" in write_fn,
        "write_plan has no kb_context param",
    )

    print("do not stuff empty-URL notes into resources")
    check(
        "plan_does_not_mark_课件_resource",
        '"课件"' not in plan_fn and "'课件'" not in plan_fn,
        "do not inject 课件 into resources; Reviewer drops empty URLs in LLM mode",
    )
    check(
        "reviewer_still_drops_empty_url",
        "if not url:" in reviewer,
        "reviewer empty-URL branch missing",
    )

    print("cache key must include knowledge fingerprint")
    check(
        "cache_has_knowledge_fingerprint",
        "def knowledge_fingerprint" in cache,
        "cache_store needs knowledge_fingerprint()",
    )
    check(
        "cache_key_includes_kb_fp",
        "kb_fp" in key_fn or "knowledge_fingerprint" in key_fn,
        "make_cache_key still ignores the knowledge base",
    )
    check(
        "cache_schema_bumped",
        re.search(r"CACHE_SCHEMA\s*=\s*([0-9]+)", cache) is not None
        and int(re.search(r"CACHE_SCHEMA\s*=\s*([0-9]+)", cache).group(1)) >= 3,
        "CACHE_SCHEMA must +1 because result now carries retrieved",
    )

    print("API wrapper must forward retrieved")
    check("payload_fn_found", bool(payload_fn), "could not isolate build_payload")
    check(
        "payload_forwards_retrieved",
        '"retrieved"' in payload_fn and "retrieved" in payload_fn,
        "build_payload does not forward retrieved",
    )
    check(
        "payload_defaults_empty_list",
        re.search(r'retrieved["\']?\s*.*(?:or \[\]|or \(\)|else \[\]|or list)', payload_fn)
        or 'res.get("retrieved")' in payload_fn
        or 'result.get("retrieved") or []' in payload_fn
        or 'result.get("retrieved") or []' in api,
        "missing retrieved must become []",
    )

    print("ResultsGrid must render citation titles")
    check(
        "grid_reads_retrieved",
        "retrieved" in grid,
        "ResultsGrid never reads result.retrieved",
    )
    check(
        "grid_iterates_retrieved",
        "v-for" in grid and re.search(r"retrieved", grid) is not None,
        "template does not iterate retrieved",
    )
    check(
        "grid_shows_title_text",
        re.search(r"\{\{\s*c\.title", grid) is not None
        or re.search(r"\{\{\s*cite\.title", grid) is not None,
        "citation title must use {{ }} not v-html",
    )
    check(
        "grid_shows_score",
        re.search(r"c\.score|cite\.score", grid) is not None,
        "citation score not rendered",
    )
    check(
        "grid_hides_empty_retrieved",
        re.search(r"retrieved(?:\.length| &&)", grid) is not None,
        "empty retrieved must not paint a blank 参考资料 block",
    )
    check(
        "grid_title_not_vhtml",
        not re.search(r"v-html=\".*(?:c\.title|cite\.title)", grid),
        "do not v-html knowledge-base titles",
    )

    print("i18n")
    check("zh_has_plan_sources", "resultsGridX.3" in zh, "auto-zh.json missing resultsGridX.3")
    check("en_has_plan_sources", "resultsGridX.3" in en, "auto-en.json missing resultsGridX.3")
    check("zh_plan_label_is_cites", '"resultsGridX.3": "参考资料"' in zh, "中文标签应为「参考资料」")

    print("scope guard: chat contract and RAG stay")
    check(
        "rag_thresholds_untouched",
        "RAG_MIN_SCORE = 1.0" in loop and "RAG_MIN_COVERAGE = 0.2" in loop,
        "do not retune RAG in this slice",
    )
    check(
        "chat_pipeline_still_returns_retrieved",
        '"retrieved": citations' in chat_fn or '"retrieved": citations' in loop,
        "do not break Day1 chat retrieved",
    )
    check(
        "api_chat_still_forwards_retrieved",
        '"retrieved": res.get("retrieved") or []' in api,
        "do not break /api/chat retrieved",
    )
    check(
        "chat_panel_still_reads_retrieved",
        "res.retrieved" in chat,
        "do not break ChatPanel.ask()",
    )

    print("runtime: mock pipeline retrieves an imported note")
    runtime_ok = _runtime_plan_kb()
    check(
        "runtime_plan_returns_imported_title",
        runtime_ok.get("hit") is True,
        runtime_ok.get("detail") or "pipeline did not cite the imported note",
    )
    check(
        "runtime_empty_kb_retrieved_is_empty_list",
        runtime_ok.get("empty") is True,
        runtime_ok.get("empty_detail") or "empty library must yield retrieved=[]",
    )
    check(
        "runtime_import_misses_old_cache",
        runtime_ok.get("cache_miss") is True,
        runtime_ok.get("cache_detail") or "importing a note must not reuse the old plan cache",
    )

    print()
    print("passed %d  failed %d" % (PASSED, len(FAILED)))
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print("  - %s" % name)
        return 1
    return 0


def _runtime_plan_kb():
    """隔离 tmp 知识库 + mock LLM，不打外网。失败时返回 detail，不抛给主流程。"""
    out = {"hit": False, "empty": False, "cache_miss": False, "detail": "", "empty_detail": "", "cache_detail": ""}
    vendor = os.path.join(REPO_ROOT, "vendor", "study-liu")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    os.environ["LLM_PROVIDER"] = "mock"
    if "requests" not in sys.modules:
        import types
        sys.modules["requests"] = types.ModuleType("requests")

    td = tempfile.mkdtemp(prefix="plan-kb-")
    kb_path = os.path.join(td, "knowledge.json")
    cache_path = os.path.join(td, "cache.json")
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    try:
        import tools.cache_store as cs
        import tools.knowledge_store as ks
        from core import agent_loop as al

        orig_kb = ks._KNOWLEDGE_FILE
        orig_cache = cs._get_cache_path
        orig_seed = getattr(ks, "ensure_seed_file", None)

        ks._KNOWLEDGE_FILE = kb_path
        ks.ensure_seed_file = lambda *a, **k: None
        cs._get_cache_path = lambda: cache_path

        # 空库：弱/无命中不得伪造引用
        empty_res = al.run_plan_pipeline("线性代数", use_cache=False)
        retrieved = empty_res.get("retrieved")
        if retrieved == []:
            out["empty"] = True
        else:
            out["empty_detail"] = "empty kb retrieved=%r" % (retrieved,)

        store = ks.KnowledgeStore(filepath=kb_path)
        store.add(
            "线性代数讲义·特征值与对角化",
            "特征值 λ 满足 Av=λv。可对角化当且仅当特征空间维数之和等于 n。"
            "刚导入的课件要求方案覆盖对角化判定步骤。",
            tags=["#线性代数"],
        )

        res = al.run_plan_pipeline("线性代数", use_cache=True)
        cites = res.get("retrieved") or []
        titles = " ".join(str(c.get("title") or "") for c in cites if isinstance(c, dict))
        if any("特征值" in str(c.get("title") or "") for c in cites if isinstance(c, dict)):
            out["hit"] = True
        else:
            out["detail"] = "retrieved=%r titles=%r" % (cites, titles)

        # 同课同画像先写进缓存，再导入第二条 → 必须 miss
        store.add(
            "线性代数讲义·二次型",
            "二次型可以通过正交对角化化成标准形，这是刚导入的第二份材料。",
            tags=["#线性代数"],
        )
        res2 = al.run_plan_pipeline("线性代数", use_cache=True)
        if not res2.get("_from_cache"):
            out["cache_miss"] = True
        else:
            out["cache_detail"] = "still _from_cache after importing a second note"

        ks._KNOWLEDGE_FILE = orig_kb
        cs._get_cache_path = orig_cache
        if orig_seed is not None:
            ks.ensure_seed_file = orig_seed
    except Exception as exc:
        out["detail"] = "runtime error: %s" % exc
        out["empty_detail"] = out["empty_detail"] or out["detail"]
        out["cache_detail"] = out["cache_detail"] or out["detail"]
    return out


if __name__ == "__main__":
    sys.exit(main())
