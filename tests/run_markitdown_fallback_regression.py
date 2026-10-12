# -*- coding: utf-8 -*-
"""MarkItDown 兜底回归。

契约：
    PDF / Word / PPT / 图片 / Markdown / txt 不进 markitdown。
    xlsx / xls / html / epub / zip / csv / json / xml 才进兜底。
    音频（.mp3 / .wav / .m4a）不进兜底：缺 speech_recognition 且本机无 ffmpeg，语音走 /api/asr。
    markitdown 未安装或被环境变量禁用时，导入接口返回明确错误，不能抛异常。

用法：

    python tests/run_markitdown_fallback_regression.py
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor", "study-liu")
sys.path.insert(0, VENDOR_DIR)
sys.path.insert(0, SERVER_DIR)

FAILED = []
PASSED = 0
SKIPPED = []


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def skip(name, why):
    SKIPPED.append(name)
    print("  --  %s  %s" % (name, why))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _function_body(src, name):
    marker = "def %s(" % name
    start = src.index(marker)
    nxt = src.find("\ndef ", start + len(marker))
    return src[start:] if nxt < 0 else src[start:nxt]


def test_source_contract():
    print("\n[source] 分流契约")
    kb = read(os.path.join(SERVER_DIR, "kb_ingest.py"))
    ingest = _function_body(kb, "ingest")
    fallback = read(os.path.join(SERVER_DIR, "markitdown_fallback.py"))
    req = read(os.path.join(VENDOR_DIR, "requirements.txt"))

    check("kb_routes_pdf_before_fallback",
          ingest.index('ext == ".pdf"') < ingest.index("import markitdown_fallback"),
          "PDF 必须先走 doc_parse")
    check("kb_routes_office_before_fallback",
          'ext in (".docx", ".pptx")' in ingest
          and ingest.index('".pptx")') < ingest.index("import markitdown_fallback"),
          "Office 必须先走 office_parse")
    check("kb_routes_images_separately",
          "IMAGE_EXTS" in ingest and "extract_text_from_image" in ingest,
          "图片必须走 vision_ocr")
    check("fallback_is_lazy",
          "from markitdown import" in fallback and "def _init" in fallback,
          "markitdown 只能惰性导入")
    check("requirements_keeps_fallback_optional",
          "markitdown[" in req and "缺包" in req,
          "requirements 需声明兜底及缺包降级")


def test_extension_boundary():
    print("\n[boundary] 扩展名边界")
    import markitdown_fallback as m
    primary = (".pdf", ".docx", ".pptx", ".png", ".jpg", ".md", ".txt")
    for ext in primary:
        check("primary_not_supported_%s" % ext.lstrip("."), not m.supports(ext), ext)
    fallback = (".xlsx", ".xls", ".html", ".htm", ".epub", ".zip",
                ".csv", ".json", ".xml")
    for ext in fallback:
        check("fallback_supported_%s" % ext.lstrip("."), m.supports(ext), ext)
    # 音频刻意不接管：缺 speech_recognition、本机无 ffmpeg，转了只有空内容（2026-10-12 线上实测）
    for ext in (".mp3", ".wav", ".m4a"):
        check("audio_not_routed_%s" % ext.lstrip("."), not m.supports(ext), ext)
    check("blank_extension_rejected", not m.supports(""))
    check("uppercase_normalized", m.supports(".XLSX"))


class _Store:
    def __init__(self):
        self.rows = []

    def add(self, title, content, tags, owner="", scope="public", category=""):
        self.rows.append({
            "title": title, "content": content, "tags": list(tags),
            "owner": owner, "scope": scope, "category": category,
        })
        return "n%d" % len(self.rows)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_missing_and_disabled(tmp):
    print("\n[degrade] 缺包与禁用")
    import kb_ingest
    import markitdown_fallback as m

    path = os.path.join(tmp, "plain.csv")
    _write(path, "知识点,答案\n迭代协议,列表\n")
    original = m._BACKEND_OK
    original_md = m._MD
    original_error = m._ERROR
    original_init = m._init
    try:
        # convert() 开头会调 _init()。只改标志而不拦住初始化，
        # 已装包的解释器会把单例重新拉起来，测不到缺包分支。
        m._init = lambda: None
        m._BACKEND_OK = False
        m._MD = None
        m._ERROR = "未安装"
        out = kb_ingest.ingest(path, "plain.csv", store=_Store())
        check("missing_returns_error", out.get("ok") is False and "未安装" in (out.get("error") or ""),
              out.get("error"))
    finally:
        m._init = original_init
        m._BACKEND_OK = original
        m._MD = original_md
        m._ERROR = original_error

    old = m._FORCE_DISABLED
    try:
        m._FORCE_DISABLED = True
        result = m.convert(path)
        check("disabled_returns_error", "禁用" in (result.get("error") or ""), result)
    finally:
        m._FORCE_DISABLED = old


def test_real_conversion(tmp):
    print("\n[convert] 真实转换")
    import kb_ingest
    import markitdown_fallback as m

    if not m.is_available():
        skip("html_real_convert", "当前解释器没有可用 markitdown")
        skip("xlsx_real_convert", "当前解释器没有可用 markitdown")
        skip("ingest_html_and_tag", "当前解释器没有可用 markitdown")
        return

    html = os.path.join(tmp, "course.html")
    _write(html, "<html><body><h1>导入标题</h1><p>兜底正文</p></body></html>")
    parsed = m.convert(html)
    check("html_real_convert",
          parsed.get("engine") == "markitdown"
          and "导入标题" in parsed.get("text", "")
          and "兜底正文" in parsed.get("text", ""),
          parsed.get("error"))

    try:
        from openpyxl import Workbook
    except ImportError:
        skip("xlsx_real_convert", "当前解释器没有 openpyxl")
        return
    xlsx = os.path.join(tmp, "course.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["知识点", "答案"])
    ws.append(["迭代协议", "列表和生成器"])
    wb.save(xlsx)
    parsed = m.convert(xlsx)
    check("xlsx_real_convert",
          parsed.get("engine") == "markitdown"
          and "知识点" in parsed.get("text", "")
          and "迭代协议" in parsed.get("text", ""),
          parsed.get("error"))

    store = _Store()
    out = kb_ingest.ingest(html, "course.html", store=store)
    check("ingest_html_and_tag",
          out.get("ok") is True and out.get("engine") == "markitdown"
          and store.rows and "#markitdown" in store.rows[0]["tags"],
          out.get("error"))


def test_primary_paths_not_called(tmp):
    print("\n[routing] 主路径隔离")
    import kb_ingest
    import markitdown_fallback as m

    called = {"n": 0}
    original = m.convert

    def spy(path):
        called["n"] += 1
        return original(path)

    m.convert = spy
    try:
        kb_ingest.ingest(os.path.join(tmp, "missing.pdf"), "missing.pdf", store=_Store())
        kb_ingest.ingest(os.path.join(tmp, "missing.docx"), "missing.docx", store=_Store())
        kb_ingest.ingest(os.path.join(tmp, "missing.png"), "missing.png", store=_Store())
        txt = os.path.join(tmp, "plain.txt")
        _write(txt, "普通文本")
        kb_ingest.ingest(txt, "plain.txt", store=_Store())
    finally:
        m.convert = original
    check("primary_paths_do_not_call_markitdown", called["n"] == 0, called["n"])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    test_source_contract()
    test_extension_boundary()
    with tempfile.TemporaryDirectory(prefix="md-fallback-") as tmp:
        test_missing_and_disabled(tmp)
        test_real_conversion(tmp)
        test_primary_paths_not_called(tmp)
    print("\n%d passed, %d failed, %d skipped" % (PASSED, len(FAILED), len(SKIPPED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
