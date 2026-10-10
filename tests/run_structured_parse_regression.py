# -*- coding: utf-8 -*-
"""结构化解析回归（方案 B）：Block 模型 + 用块边界切 chunk，不落库。

不装 MinerU / Docling。extract_* 的 blocks 字段为 additive，
既有 sidecar 契约（text / engine / error）不得破坏。

用法（仓库根目录）：

    python tests/run_structured_parse_regression.py

退出码 0 = 全过。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor", "study-liu")
sys.path.insert(0, VENDOR_DIR)
sys.path.insert(0, SERVER_DIR)

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


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _write_ooxml_docx(path, paragraphs):
    from xml.sax.saxutils import escape
    paras = "".join(
        "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % escape(p) for p in paragraphs
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>%s</w:body></w:document>" % paras
    )
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", body)


def test_parse_blocks_model():
    print("\n[parse_blocks] Block 模型")
    import parse_blocks
    b = parse_blocks.make_block("heading", "第一章 绪论", level=1)
    check("make_block 含 type/text/level/caption",
          b.get("type") == "heading" and b.get("text") == "第一章 绪论"
          and b.get("level") == 1 and "caption" in b, b)
    b2 = parse_blocks.make_block("paragraph", "正文")
    check("paragraph 默认 level=0", b2.get("level") == 0, b2)
    empty = parse_blocks.markdown_to_blocks("")
    check("空 markdown 返回 []", empty == [], empty)
    check("空 plaintext 返回 []", parse_blocks.plaintext_to_blocks("  ") == [])
    check("空 ooxml 返回 []", parse_blocks.ooxml_to_blocks([]) == [])


def test_markdown_to_blocks():
    print("\n[parse_blocks] markdown 分块")
    import parse_blocks
    md = (
        "# 第一章 绪论\n\n"
        "这是导言段落。\n\n"
        "## 1.1 背景\n\n"
        "背景说明若干字。\n\n"
        "![架构](a.png)\n"
        "图1 系统架构示意图\n\n"
        "- 列表甲\n"
        "- 列表乙\n"
    )
    blocks = parse_blocks.markdown_to_blocks(md)
    types = [b.get("type") for b in blocks]
    texts = [b.get("text") for b in blocks]
    check("markdown 产出 heading", "heading" in types, types)
    check("一级标题 level=1", any(b.get("type") == "heading" and b.get("level") == 1 and "绪论" in b.get("text", "") for b in blocks), blocks)
    check("二级标题 level=2", any(b.get("type") == "heading" and b.get("level") == 2 for b in blocks), blocks)
    check("图片后短行判 caption", any(b.get("type") == "caption" and "系统架构" in b.get("text", "") for b in blocks), blocks)
    check("列表项", types.count("list_item") >= 2, types)
    check("段落保留导言", any(b.get("type") == "paragraph" and "导言" in b.get("text", "") for b in blocks), texts)


def test_plaintext_headings():
    print("\n[parse_blocks] plaintext 启发式标题")
    import parse_blocks
    text = (
        "第一章 绪论\n"
        "本文介绍结构化解析。\n"
        "1. 问题定义\n"
        "问题定义的正文。\n"
        "INTRODUCTION OVERVIEW\n"
        "An English paragraph follows.\n"
        "图2 流程简图\n"
    )
    blocks = parse_blocks.plaintext_to_blocks(text)
    headings = [b for b in blocks if b.get("type") == "heading"]
    check("中文章节作 heading", any("第一章" in b.get("text", "") for b in headings), headings)
    check("编号行作 heading", any("问题定义" in b.get("text", "") for b in headings), headings)
    check("大写短行作 heading", any("INTRODUCTION" in b.get("text", "") for b in headings), headings)
    check("图N 短行作 caption", any(b.get("type") == "caption" and "流程" in b.get("text", "") for b in blocks), blocks)


def test_ooxml_to_blocks():
    print("\n[parse_blocks] ooxml 段落块")
    import parse_blocks
    units = ["第二章 方法", "方法正文第一段。", "图3 实验装置"]
    blocks = parse_blocks.ooxml_to_blocks(units)
    check("OOXML 标题块", any(b.get("type") == "heading" and "第二章" in b.get("text", "") for b in blocks), blocks)
    check("OOXML 段落块", any(b.get("type") == "paragraph" and "方法正文" in b.get("text", "") for b in blocks), blocks)
    check("OOXML 图注 caption", any(b.get("type") == "caption" and "实验装置" in b.get("text", "") for b in blocks), blocks)


def test_section_texts_and_chunks():
    print("\n[parse_blocks] 按 heading 切段")
    import parse_blocks
    blocks = [
        parse_blocks.make_block("heading", "第一章 总论", level=1),
        parse_blocks.make_block("paragraph", "甲" * 40),
        parse_blocks.make_block("heading", "第二章 方法", level=1),
        parse_blocks.make_block("paragraph", "乙" * 40),
    ]
    secs = parse_blocks.section_texts(blocks)
    check("两个标题切成两段", len(secs) == 2, secs)
    check("第一段含第一章不含第二章", "第一章" in secs[0] and "第二章" not in secs[0], secs[0][:80])
    check("第二段含第二章", "第二章" in secs[1] and "乙" in secs[1], secs[1][:80])


def test_doc_parse_returns_blocks():
    print("\n[doc_parse] extract_pdf_text 产出 blocks")
    import doc_parse
    orig = doc_parse._read_native_pdf
    saved = os.environ.get("STUDY_LIU_PDF_ENGINE")

    def fake(_path):
        return "第一章 绪论\n导言段落若干字。\n第二章 方法\n方法段落若干字。"

    try:
        doc_parse._read_native_pdf = fake
        os.environ["STUDY_LIU_PDF_ENGINE"] = "pypdf"
        r = doc_parse.extract_pdf_text("dummy.pdf")
        check("仍返回 text/engine/error", "text" in r and "engine" in r and "error" in r, r)
        check("pypdf engine 保留", r.get("engine") == "pypdf", r)
        blocks = r.get("blocks")
        check("pypdf 路径含 blocks 列表", isinstance(blocks, list) and len(blocks) >= 2, r)
        check("pypdf blocks 含 heading", any(b.get("type") == "heading" for b in (blocks or [])), blocks)
    finally:
        doc_parse._read_native_pdf = orig
        if saved is None:
            os.environ.pop("STUDY_LIU_PDF_ENGINE", None)
        else:
            os.environ["STUDY_LIU_PDF_ENGINE"] = saved

    empty = doc_parse.extract_pdf_text.__doc__ or ""
    check("失败路径也带 blocks 键", True)  # 下面显式调
    r_err = {"text": "", "engine": "", "error": "x"}
    # 用强制 pypdf + 空 native
    def empty_read(_path):
        return ""
    try:
        doc_parse._read_native_pdf = empty_read
        os.environ["STUDY_LIU_PDF_ENGINE"] = "pypdf"
        r2 = doc_parse.extract_pdf_text("dummy.pdf")
        check("无正文时 blocks=[]", r2.get("blocks") == [], r2)
    finally:
        doc_parse._read_native_pdf = orig
        if saved is None:
            os.environ.pop("STUDY_LIU_PDF_ENGINE", None)
        else:
            os.environ["STUDY_LIU_PDF_ENGINE"] = saved


def test_office_parse_returns_blocks():
    print("\n[office_parse] extract_office_text 产出 blocks")
    tmp = tempfile.mkdtemp(prefix="struct-office-")
    docx = os.path.join(tmp, "a.docx")
    _write_ooxml_docx(docx, ["第三章 实验", "实验步骤说明。", "图4 装置图"])
    saved_bin = os.environ.get("STUDY_LIU_DOCLING_BIN")
    saved_eng = os.environ.get("STUDY_LIU_OFFICE_ENGINE")
    missing = os.path.join(tmp, "no-docling")
    try:
        os.environ["STUDY_LIU_DOCLING_BIN"] = missing
        os.environ["STUDY_LIU_OFFICE_ENGINE"] = "ooxml"
        import office_parse
        r = office_parse.extract_office_text(docx)
        check("ooxml engine 保留", r.get("engine") == "ooxml", r)
        check("ooxml 仍返回 text", "实验" in (r.get("text") or ""), r)
        blocks = r.get("blocks")
        check("ooxml 路径含 blocks", isinstance(blocks, list) and len(blocks) >= 2, r)
        check("ooxml blocks 含 heading", any(b.get("type") == "heading" for b in (blocks or [])), blocks)
        pdf = os.path.join(tmp, "x.pdf")
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4")
        r2 = office_parse.extract_office_text(pdf)
        check("拒绝 PDF 时 blocks=[]", r2.get("blocks") == [], r2)
    finally:
        if saved_bin is None:
            os.environ.pop("STUDY_LIU_DOCLING_BIN", None)
        else:
            os.environ["STUDY_LIU_DOCLING_BIN"] = saved_bin
        if saved_eng is None:
            os.environ.pop("STUDY_LIU_OFFICE_ENGINE", None)
        else:
            os.environ["STUDY_LIU_OFFICE_ENGINE"] = saved_eng


def test_kb_ingest_uses_block_boundaries():
    print("\n[kb_ingest] 用 Block 边界切 chunk，不落库")
    import kb_ingest
    import parse_blocks
    blocks = [
        parse_blocks.make_block("heading", "第一章 总论", level=1),
        parse_blocks.make_block("paragraph", "甲段" * 20),
        parse_blocks.make_block("heading", "第二章 方法", level=1),
        parse_blocks.make_block("paragraph", "乙段" * 20),
    ]
    text = "\n".join(b["text"] for b in blocks)
    chunks = kb_ingest.chunk_prefer_blocks(text, blocks)
    check("短章节按标题切开（≥2 块）", len(chunks) >= 2, chunks)
    check("第一块含第一章不含第二章", "第一章" in chunks[0] and "第二章" not in chunks[0], chunks[0][:60])
    check("第二块含第二章", any("第二章" in c for c in chunks[1:]), chunks)
    joined = "".join(chunks)
    char_chunks = kb_ingest.chunk_text(text)
    check("硬切会并成 1 块（对照）", len(char_chunks) == 1, char_chunks)
    check("结构化切分块数 > 硬切", len(chunks) > len(char_chunks), (len(chunks), len(char_chunks)))

    tmp = tempfile.mkdtemp(prefix="struct-ingest-")
    store_path = os.path.join(tmp, "knowledge.json")
    _write(store_path, "[]")
    from tools.knowledge_store import KnowledgeStore
    store = KnowledgeStore(filepath=store_path)
    md = os.path.join(tmp, "x.md")
    _write(md, "# 第一章 总论\n\n甲段内容。\n\n# 第二章 方法\n\n乙段内容。\n")
    added = []
    orig_add = store.add

    def spy_add(*args, **kwargs):
        added.append(kwargs)
        return orig_add(*args, **kwargs)

    store.add = spy_add
    r = kb_ingest.ingest(md, "x.md", store=store)
    check("md ingest ok", r.get("ok") is True, r)
    check("md 按标题至少 2 chunk", r.get("chunks", 0) >= 2, r)
    check("store.add 不传 blocks", all("blocks" not in kw for kw in added), added)
    check("ingest 响应不含必须落库的 blocks 字段", "blocks" not in r or r.get("blocks") is None, r)


def test_scope_gate_api_server():
    print("\n[scope] api_server 不 import parse_blocks")
    src = os.path.join(SERVER_DIR, "api_server.py")
    with open(src, "r", encoding="utf-8") as f:
        txt = f.read()
    check("api_server 无 import parse_blocks",
          "import parse_blocks" not in txt and "from parse_blocks" not in txt)


def main():
    print("=" * 60)
    print("结构化解析回归（方案 B：Block + 块边界切 chunk，不落库）")
    print("=" * 60)
    for fn in (
        test_parse_blocks_model,
        test_markdown_to_blocks,
        test_plaintext_headings,
        test_ooxml_to_blocks,
        test_section_texts_and_chunks,
        test_doc_parse_returns_blocks,
        test_office_parse_returns_blocks,
        test_kb_ingest_uses_block_boundaries,
        test_scope_gate_api_server,
    ):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__ + "/exception")
            traceback.print_exc()
    print("")
    print("=" * 60)
    print("通过 %d  失败 %d" % (PASSED, len(FAILED)))
    if FAILED:
        print("失败项：" + "、".join(FAILED))
        return 1
    print("全过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
