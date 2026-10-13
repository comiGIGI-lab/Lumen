# -*- coding: utf-8 -*-
"""从 PDF / Word / PPT 里抽出嵌入图片，并交给现有识图模块。

只补正文抽不到的图片内容。没有视觉模型、图片太小或识图失败时，
原来抽出的文字照常入库，不把整份导入判失败。
"""
from __future__ import annotations

import io
import os
import struct
import tempfile
import zipfile

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_IMAGES = 4
MIN_IMAGE_BYTES = 12 * 1024
MIN_PNG_SIDE = 160


def _image_size(data, ext):
    """只认够大的 PNG。其他格式交给字节门槛，避免引入图片库。"""
    if ext != ".png" or len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        width, height = struct.unpack(">II", data[16:24])
    except struct.error:
        return None
    return width, height


def _keep(data, ext):
    if ext not in IMAGE_EXTS or len(data) < MIN_IMAGE_BYTES:
        return False
    size = _image_size(data, ext)
    if size and (size[0] < MIN_PNG_SIDE or size[1] < MIN_PNG_SIDE):
        return False
    return True


def extract_office_images(path):
    """读 word/media、ppt/media。失败返回空列表。"""
    found = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = sorted(
                n for n in zf.namelist()
                if n.startswith(("word/media/", "ppt/media/"))
                and os.path.splitext(n)[1].lower() in IMAGE_EXTS
            )
            for name in names:
                data = zf.read(name)
                ext = os.path.splitext(name)[1].lower()
                if _keep(data, ext):
                    found.append((name, ext, data))
                if len(found) >= MAX_IMAGES:
                    break
    except (OSError, zipfile.BadZipFile, KeyError):
        return []
    return found


def _pdf_objects(data):
    parts = data.split(b"endobj")
    out = []
    for part in parts:
        body = part.split(b"obj", 1)
        if len(body) == 2:
            out.append(body[1])
    return out


def extract_pdf_images(path):
    """抽出未压缩的内嵌 JPEG / PNG。Flate 压缩图片留给 MinerU，这里不解码。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    found = []
    for obj in _pdf_objects(data):
        start = obj.find(b"stream")
        if start < 0 or (b"DCTDecode" not in obj[:start] and b"/Image" not in obj[:start]):
            continue
        header = obj[:start]
        if b"FlateDecode" in header:
            continue
        start += len(b"stream")
        if obj[start:start + 2] == b"\r\n":
            start += 2
        elif obj[start:start + 1] == b"\n":
            start += 1
        end = obj.find(b"endstream", start)
        if end < 0:
            continue
        blob = obj[start:end].rstrip(b"\r\n")
        ext = ""
        if blob.startswith(b"\xff\xd8\xff"):
            ext = ".jpg"
        elif blob.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = ".png"
        if ext and _keep(blob, ext):
            found.append(("page-image-%d%s" % (len(found) + 1, ext), ext, blob))
        if len(found) >= MAX_IMAGES:
            break
    return found


def extract_embedded_images(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".pptx"):
        return extract_office_images(path)
    if ext == ".pdf":
        return extract_pdf_images(path)
    return []


def append_vision_text(path, text, reader):
    """识别嵌入图片，把转写追加到正文后面。

    reader(image_path) 形状与 vision_ocr.extract_text_from_image 相同。
    返回 (text, count)。reader 缺席、抛错或没识别出字时保留原文。
    """
    base = (text or "").strip()
    if reader is None:
        return base, 0
    images = extract_embedded_images(path)
    if not images:
        return base, 0
    blocks = []
    for name, ext, data in images:
        handle = None
        try:
            handle = tempfile.NamedTemporaryFile(prefix="emb-", suffix=ext, delete=False)
            handle.write(data)
            handle.close()
            result = reader(handle.name) or {}
            seen = str(result.get("text") or "").strip()
            if seen:
                blocks.append("【图片 %s】\n%s" % (os.path.basename(name), seen))
        except Exception:
            continue
        finally:
            if handle is not None:
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass
    if not blocks:
        return base, 0
    merged = "\n\n".join([p for p in (base, "\n\n".join(blocks)) if p])
    return merged, len(blocks)
