# -*- coding: utf-8 -*-
"""文档结构块：标题 / 段落 / 列表 / 图注。

供 doc_parse / office_parse 产出 blocks，kb_ingest 用 heading 边界切 chunk。
不落知识库、不进 api_server。
"""
from __future__ import annotations

import re

_CAPTION = re.compile(
    r"^(图|表|Figure|Table|Fig\.?)\s*[\d一二三四五六七八九十]+",
    re.I,
)
_CHAPTER = re.compile(r"^第[一二三四五六七八九十百千0-9]+[章节篇部]")
_NUMBERED = re.compile(r"^\d+(?:\.\d+)*[\s.、]")
_UPPER = re.compile(r"^[A-Z][A-Z0-9 \-]{4,40}$")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST = re.compile(r"^([-*+]|\d+\.)\s+(.*)$")


def make_block(type_, text, level=0, caption=""):
    """统一 Block 形状：{type, text, level, caption}。"""
    return {
        "type": type_,
        "text": (text or "").strip(),
        "level": int(level or 0),
        "caption": caption or "",
    }


def _is_heading_line(line):
    s = (line or "").strip()
    if not s or len(s) > 40:
        return False
    if _CHAPTER.match(s):
        return True
    if _NUMBERED.match(s):
        return True
    if _UPPER.match(s):
        return True
    return False


def _is_caption_line(line):
    s = (line or "").strip()
    return bool(s) and len(s) <= 60 and bool(_CAPTION.match(s))


def markdown_to_blocks(md):
    """MinerU / Docling Markdown → blocks。"""
    if not (md or "").strip():
        return []
    lines = md.replace("\r\n", "\n").split("\n")
    blocks = []
    para = []

    def flush_para():
        if para:
            t = "\n".join(para).strip()
            if t:
                blocks.append(make_block("paragraph", t))
            para.clear()

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        m_h = _MD_HEADING.match(stripped)
        if m_h:
            flush_para()
            title = (m_h.group(2) or "").strip()
            if title:
                blocks.append(make_block("heading", title, level=len(m_h.group(1))))
            i += 1
            continue
        if stripped.startswith("!["):
            flush_para()
            blocks.append(make_block("image", stripped))
            if i + 1 < n:
                nxt = lines[i + 1].strip()
                if nxt and len(nxt) <= 60 and not nxt.startswith("#") and not nxt.startswith("!["):
                    blocks.append(make_block("caption", nxt))
                    i += 2
                    continue
            i += 1
            continue
        m_l = _LIST.match(stripped)
        if m_l:
            flush_para()
            item = (m_l.group(2) or "").strip()
            if item:
                blocks.append(make_block("list_item", item))
            i += 1
            continue
        if not stripped:
            flush_para()
            i += 1
            continue
        para.append(stripped)
        i += 1
    flush_para()
    return blocks


def plaintext_to_blocks(text):
    """pypdf 等纯文本：启发式标题 + 图注。"""
    if not (text or "").strip():
        return []
    blocks = []
    para = []

    def flush():
        if para:
            t = "\n".join(para).strip()
            if t:
                blocks.append(make_block("paragraph", t))
            para.clear()

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        if _is_caption_line(line):
            flush()
            blocks.append(make_block("caption", line))
            continue
        if _is_heading_line(line):
            flush()
            blocks.append(make_block("heading", line, level=1))
            continue
        para.append(line)
    flush()
    return blocks


def ooxml_to_blocks(units):
    """OOXML 段落/幻灯文本单元 → blocks。"""
    out = []
    for raw in units or []:
        u = str(raw).strip()
        if not u:
            continue
        if _is_caption_line(u):
            out.append(make_block("caption", u))
        elif _is_heading_line(u):
            out.append(make_block("heading", u, level=1))
        else:
            out.append(make_block("paragraph", u))
    return out


def section_texts(blocks):
    """按 heading 切开，每段含标题 + 后续非标题块文本。无 heading 则整篇一段。"""
    if not blocks:
        return []
    secs = []
    cur = []
    saw_heading = False
    for b in blocks:
        t = (b.get("text") or "").strip()
        if not t:
            continue
        if b.get("type") == "heading":
            if cur:
                secs.append("\n".join(cur).strip())
            cur = [t]
            saw_heading = True
        else:
            cur.append(t)
    if cur:
        secs.append("\n".join(cur).strip())
    return [s for s in secs if s]
