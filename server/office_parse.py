# -*- coding: utf-8 -*-
"""Office 课件抽字侧车：Docling CLI 可选，OOXML 标准库兜底。

硬约束
------
- 只接 .docx / .pptx。PDF 继续走 doc_parse（pypdf / MinerU），这里直接拒绝。
- 不把 docling / mineru / openai-whisper 整包拉进进程。只 subprocess 调官方 CLI。
- 官方 CLI 参考：`docling convert <file> --to md --output <dir> --no-ocr`
  https://docling-project.github.io/docling/reference/cli/
- 不要 `--pipeline vlm`，不要 GraniteDocling。Office 数字文件关 OCR。
- 缺 CLI 时 zipfile + xml 抽 OOXML 文本，服务仍能起。
- *_BIN 已设置但路径不存在 → 判缺，不再搜 PATH。

环境变量
--------
STUDY_LIU_DOCLING_BIN      可执行文件；.py 则用当前解释器（测试用）
STUDY_LIU_DOCLING_TIMEOUT  秒，默认 120
STUDY_LIU_OFFICE_ENGINE    docling | ooxml | 空（自动：有 CLI 用 CLI）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

OFFICE_EXTS = (".docx", ".pptx")
DEFAULT_TIMEOUT = 120
_SERVER_BIN = "/home/admin/asr/docling/docling"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def docling_cmd():
    """返回调用 docling 的 argv 前缀；不可用时返回空列表。"""
    raw = (os.environ.get("STUDY_LIU_DOCLING_BIN") or "").strip()
    if raw:
        if raw.lower().endswith(".py"):
            return [sys.executable, raw] if os.path.isfile(raw) else []
        return [raw] if os.path.isfile(raw) else []
    found = shutil.which("docling")
    if found:
        return [found]
    if os.path.isfile(_SERVER_BIN):
        return [_SERVER_BIN]
    local = os.path.join(_repo_root(), "vendor", "asr", "docling")
    if os.path.isfile(local):
        return [local]
    return []


def available():
    """探测 Docling CLI。(ok, reason)。ok 只表示侧车在，不表示 OOXML 回退不可用。"""
    cmd = docling_cmd()
    if not cmd:
        return False, "未安装 docling。Word / PPT 将走 OOXML 标准库抽字；复杂版式需要在服务器另装 Docling 侧车。"
    exe = cmd[-1]
    if not os.path.isfile(exe) and shutil.which(exe) is None:
        return False, "docling 路径无效：%s" % exe
    return True, ""


def capabilities():
    ok, reason = available()
    return {
        "available": ok,
        "engine": "docling" if ok else "",
        "fallback": "ooxml",
        "extensions": list(OFFICE_EXTS),
        "note": "" if ok else reason,
    }


def _local_tag(tag):
    if not tag:
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _paragraphs_docx(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    paras = []
    for el in root.iter():
        if _local_tag(el.tag) != "p":
            continue
        parts = []
        for child in el.iter():
            if _local_tag(child.tag) == "t" and child.text:
                parts.append(child.text)
        line = "".join(parts).strip()
        if line:
            paras.append(line)
    return paras


def _slide_texts(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    parts = []
    for el in root.iter():
        if _local_tag(el.tag) == "t" and el.text:
            t = el.text.strip()
            if t:
                parts.append(t)
    return parts


def parse_ooxml(path):
    """标准库抽 OOXML 文本。失败返回空串，不抛给调用方。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in OFFICE_EXTS:
        return ""
    try:
        with zipfile.ZipFile(path, "r") as z:
            names = z.namelist()
            if ext == ".docx":
                target = "word/document.xml"
                if target not in names:
                    return ""
                paras = _paragraphs_docx(z.read(target))
                return "\n".join(paras).strip()
            slides = sorted(
                n for n in names
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            )
            blocks = []
            for n in slides:
                blocks.extend(_slide_texts(z.read(n)))
            return "\n".join(blocks).strip()
    except (OSError, zipfile.BadZipFile, KeyError):
        return ""


def _collect_markdown(target, stem):
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if not os.path.isdir(target):
        return ""
    preferred = []
    others = []
    for root, _dirs, files in os.walk(target):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            p = os.path.join(root, name)
            if stem and stem.lower() in name.lower():
                preferred.append(p)
            else:
                others.append(p)
    chunks = []
    for p in preferred + others:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                chunks.append(f.read())
        except OSError:
            continue
    return "\n\n".join(c.strip() for c in chunks if c and c.strip())


def parse_with_docling(path, timeout=None):
    """调 docling convert。返回 {text, error}。"""
    cmd = docling_cmd()
    if not cmd:
        return {"text": "", "error": "docling 不可用"}
    if timeout is None:
        try:
            timeout = int(os.environ.get("STUDY_LIU_DOCLING_TIMEOUT") or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
    stem = os.path.splitext(os.path.basename(path))[0] or "doc"
    tmp = tempfile.mkdtemp(prefix="docling-")
    argv = cmd + [
        "convert", path,
        "--to", "md",
        "--no-ocr",
        "--output", tmp,
    ]
    try:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return {"text": "", "error": "找不到 docling 可执行文件"}
        except subprocess.TimeoutExpired:
            return {"text": "", "error": "Docling 解析超时（%d 秒）" % timeout}
        except Exception as e:
            return {"text": "", "error": "Docling 调用失败：%s" % e}

        text = _collect_markdown(tmp, stem)
        if not (text or "").strip():
            err = (proc.stderr or proc.stdout or b"").decode("utf-8", "ignore").strip()
            if proc.returncode:
                return {"text": "", "error": "Docling 退出码 %s：%s" % (proc.returncode, err[:300] or "无输出")}
            return {"text": "", "error": "Docling 没有写出 Markdown"}
        return {"text": text.strip(), "error": ""}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_office_text(path):
    """docx/pptx → 正文。返回 {text, engine, error}。engine 为 docling / ooxml / 空串。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in OFFICE_EXTS:
        return {
            "text": "",
            "engine": "",
            "error": "office_parse 不支持 %s。PDF 走 pypdf / MinerU。" % (ext or "无扩展名"),
        }

    force = (os.environ.get("STUDY_LIU_OFFICE_ENGINE") or "").strip().lower()
    native = parse_ooxml(path)
    cli_ok, cli_reason = available()

    use_cli = force != "ooxml" and (force == "docling" or cli_ok)
    if use_cli:
        r = parse_with_docling(path)
        if (r.get("text") or "").strip():
            return {"text": r["text"].strip(), "engine": "docling", "error": ""}
        if native:
            return {"text": native, "engine": "ooxml", "error": ""}
        return {
            "text": "",
            "engine": "",
            "error": r.get("error") or cli_reason or "Office 解析失败",
        }

    if native:
        return {"text": native, "engine": "ooxml", "error": ""}
    return {
        "text": "",
        "engine": "",
        "error": "文件里没有解析到任何文字" if not cli_ok else (cli_reason or "Office 解析失败"),
    }
