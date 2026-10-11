# -*- coding: utf-8 -*-
"""markitdown 兜底解析：xlsx / html / epub / zip 等 doc_parse+office_parse 不覆盖的格式。

硬约束
------
- 本模块只做「探测 + 调 MarkItDown.convert() + 读回 Markdown」。不在顶层 import
  markitdown，避免未装 markitdown 时把 api_server 起不来。
- doc_parse 解析 PDF、office_parse 解析 docx/pptx 是首选项；它们都拿不到文字 /
  不覆盖该扩展名时才回退到本模块，**作为补充而非替换**。
- 缺包时所有函数静默返 None / available=False，由上游 kb_ingest 决定是否报错。
- 任何 markitdown 自身抛错都被吞掉（不向上传），仅记录错误文案到 _ERROR。
- 进程级单例 _MARKITDOWN：避免每次导入文件都重新加载 mammoth/pptx 等重量级解析器。

环境变量
--------
STUDY_LIU_MARKITDOWN_DISABLED=1   测试/应急时直接禁用回退（caps 仍报 available）
"""
from __future__ import annotations

import os
import traceback
from typing import Any


_MD: Any = None                # 进程级 MarkItDown 单例（None=未初始化）
_BACKEND_OK: bool = False
_ERROR: str = ""
_FORCE_DISABLED: bool = os.environ.get("STUDY_LIU_MARKITDOWN_DISABLED", "").strip() in ("1", "true", "yes", "on")


# ============================================================
# 初始化
# ============================================================
def _init() -> None:
    """惰性 import markitdown。失败原因存到 _ERROR，caps 报给前端置灰。"""
    global _MD, _BACKEND_OK, _ERROR
    if _MD is not None or _FORCE_DISABLED:
        return
    try:
        from markitdown import MarkItDown  # type: ignore
        _MD = MarkItDown()
        _BACKEND_OK = True
        _ERROR = ""
    except Exception as e:
        _MD = None
        _BACKEND_OK = False
        _ERROR = "%s: %s" % (type(e).__name__, e)


# ============================================================
# 能力探测
# ============================================================
_EXTRAS = (
    "pdf", "docx", "pptx", "xlsx", "xls",
    "html", "audio_transcription", "youtube_transcription",
)


def _detect_extras() -> dict:
    """细粒度探测每个 extras 的依赖是否到位，给前端按格式置灰。"""
    out = {k: False for k in _EXTRAS}
    # mammoth → docx
    try:
        import mammoth  # noqa: F401
        out["docx"] = True
    except Exception:
        pass
    # python-pptx → pptx
    try:
        import pptx  # noqa: F401
        out["pptx"] = True
    except Exception:
        pass
    # openpyxl → xlsx
    try:
        import openpyxl  # noqa: F401
        out["xlsx"] = True
    except Exception:
        pass
    # xlrd → xls
    try:
        import xlrd  # noqa: F401
        out["xls"] = True
    except Exception:
        pass
    # pdfminer.six → pdf（markitdown[pdf] 走它；我们也直接验）
    try:
        import pdfminer  # noqa: F401
        out["pdf"] = True
    except Exception:
        pass
    # beautifulsoup4 → html
    try:
        import bs4  # noqa: F401
        out["html"] = True
    except Exception:
        pass
    # speechrecognition + pydub → audio
    try:
        import speech_recognition  # noqa: F401
        import pydub  # noqa: F401
        out["audio_transcription"] = True
    except Exception:
        pass
    # youtube_transcript_api → youtube
    try:
        import youtube_transcript_api  # noqa: F401
        out["youtube_transcription"] = True
    except Exception:
        pass
    return out


def is_available() -> bool:
    _init()
    return _BACKEND_OK and not _FORCE_DISABLED


def status() -> dict:
    """给 kb_ingest.capabilities() 调用，前端据此置灰。"""
    _init()
    return {
        "available": is_available(),
        "forced_disabled": _FORCE_DISABLED,
        "error": _ERROR or "",
        "extras": _detect_extras(),
    }


# ============================================================
# 转换
# ============================================================
# markitdown 支持的扩展名（除了 doc_parse/office_parse 已经覆盖的 .pdf/.docx/.pptx）
# 按 _EXTRAS 反推：xlsx / xls / html / epub / zip + 一些冷门格式
SUPPORTED_EXTS = (
    ".xlsx", ".xls",                # Excel
    ".html", ".htm",                # HTML
    ".epub",                        # 电子书
    ".zip",                         # 压缩包
    ".csv", ".json", ".xml",        # 数据
    ".mp3", ".wav", ".m4a",         # 音频
)


def supports(ext: str) -> bool:
    """kb_ingest 调度时按扩展名判定本模块是否接管。"""
    if not ext:
        return False
    return ext.lower() in SUPPORTED_EXTS


def convert(path: str) -> dict:
    """对单文件调 MarkItDown.convert()。

    返回：
        {"text": str, "engine": "markitdown", "error": None}
        失败返 {"text": "", "engine": "markitdown", "error": "<原因>"}
        不可用返 {"text": "", "engine": "", "error": "markitdown 不可用：<原因>"}
    """
    if _FORCE_DISABLED:
        return {"text": "", "engine": "", "error": "markitdown 已被环境变量禁用"}
    _init()
    if not _BACKEND_OK or _MD is None:
        return {"text": "", "engine": "", "error": "markitdown 不可用：%s" % (_ERROR or "未安装")}
    try:
        r = _MD.convert(path)
        text = (getattr(r, "text_content", "") or "").strip()
        if not text:
            return {"text": "", "engine": "markitdown", "error": "markitdown 解析后内容为空"}
        return {"text": text, "engine": "markitdown", "error": None}
    except Exception as e:
        return {"text": "", "engine": "markitdown", "error": "markitdown 解析失败：%s" % e}
