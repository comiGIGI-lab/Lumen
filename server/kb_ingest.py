# kb_ingest.py — 知识库导入：上传文件 → 解析 → 分块 → 入库
#
# 这一层是 Web 侧的「胶水」：把 server/multipart.py 解析出来的文件，
# 按扩展名分发给既有的工具模块，再把结果写进知识库。
#
# 复用的现成轮子（不要重写）：
#   tools/document_importer.py  —— 读 PDF/Markdown/txt（pypdf→PyPDF2→pdfplumber 三级降级）
#                                  以及分句 split_sentences()
#   server/doc_parse.py         —— PDF 侧车：扫描件走 mineru-kit，数字文本仍走 pypdf
#                                  MinerU 没装时静默回退，不让 api_server 起不来
#   server/office_parse.py      —— Word/PPT 侧车：docling convert，缺 CLI 回退 OOXML
#   tools/vision_ocr.py         —— 图片走多模态模型识图（替代装不下的本地 OCR）
#   tools/knowledge_store.py    —— 入库
#   server/safety_gate.py       —— 内容安全（导入也是一条写入路径，要过审核）
#
# 为什么不用 document_importer.import_file()：
#   它把整篇文件写成「1 条笔记」，而且正文**截断到前 2000 字** —— 长 PDF
#   后面的内容会直接丢掉；一条笔记塞全文也会让检索命中率下降。
#   这里改成按句子边界分块（带重叠），既保住全部内容，也让每块更聚焦，
#   检索时能精确命中到相关段落。import_file 本身保持不动，供桌面版使用。

import os
import re
import time

# ---------- 支持的格式 ----------
# .docx / .pptx 走 server/office_parse.py（docling 侧车，缺 CLI 回退 OOXML 标准库）
DOC_EXTS = [".pdf", ".md", ".markdown", ".txt", ".text", ".docx", ".pptx"]
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"]

# ---------- 分块参数 ----------
CHUNK_SIZE = 700          # 每块目标字数（中文按字符算）
CHUNK_OVERLAP = 120       # 块间重叠，避免恰好切断一个完整语义
MAX_CHUNKS = 60           # 单个文件最多切多少块（挡住超长文档一次写爆知识库）
MAX_TEXT_CHARS = 300_000  # 单个文件解析出的正文上限

# 上传文件落盘目录（相对 data/）
UPLOAD_SUBDIR = "uploads"
# 落盘文件保留时长（秒）——解析完就删，留一天防止排查时找不到
UPLOAD_KEEP_SECONDS = 24 * 3600


# ============================================================
# 能力探测（前端据此置灰不支持的入口）
# ============================================================
def _pdf_ready():
    """能否解析 PDF：pypdf / PyPDF2 / pdfplumber 任一可用即可。"""
    for mod in ("pypdf", "PyPDF2", "pdfplumber"):
        try:
            __import__(mod)
            return mod
        except ImportError:
            continue
    return None


def capabilities():
    """返回导入能力，供前端展示与置灰。"""
    pdf_mod = _pdf_ready()
    try:
        from tools.vision_ocr import is_ocr_available
        vision_ok = bool(is_ocr_available())
    except Exception:
        vision_ok = False

    try:
        import doc_parse
        mineru = doc_parse.capabilities()
    except Exception:
        mineru = {"available": False, "engine": "", "tier": "", "note": "doc_parse 模块不可用"}

    try:
        import office_parse
        office = office_parse.capabilities()
    except Exception:
        office = {"available": False, "engine": "", "fallback": "ooxml", "extensions": [".docx", ".pptx"], "note": "office_parse 模块不可用"}

    # 兜底层：xlsx / xls / html / epub / zip / 音频 / 视频字幕——doc_parse+office_parse 不覆盖的格式。
    # 进程级惰性 import（markitdown 缺包时静默 available=False，不让 api_server 起不来）。
    try:
        import markitdown_fallback
        markitdown = markitdown_fallback.status()
    except Exception:
        markitdown = {"available": False, "forced_disabled": False, "error": "markitdown_fallback 模块不可用", "extras": {}}

    pdf_note = ""
    if not pdf_mod and not mineru.get("available"):
        pdf_note = "未安装 pypdf，PDF 暂不可解析（Markdown / txt 正常）"
    elif mineru.get("available"):
        pdf_note = "数字 PDF 走 pypdf；扫描件 / 复杂版式走 MinerU 侧车（tier=%s）" % (mineru.get("tier") or "basic")
    elif pdf_mod:
        pdf_note = "当前只有 pypdf 文本层。扫描件几乎抽不到字时需要另装 MinerU 侧车。"
    if office.get("available"):
        pdf_note = (pdf_note + " Word / PPT 走 Docling 侧车，缺 CLI 回退 OOXML。" if pdf_note else "Word / PPT 走 Docling 侧车，缺 CLI 回退 OOXML。")
    else:
        pdf_note = (pdf_note + " Word / PPT 走 OOXML 标准库抽字。" if pdf_note else "Word / PPT 走 OOXML 标准库抽字。")

    # markitdown 接管扩展名：当 markitdown 可用时，把它们并入 document.extensions 列表，
    # 前端文件对话框即可放行这些格式（不动前端代码）。markitdown 不可用时只列 DOC_EXTS。
    md_exts = []
    if markitdown.get("available"):
        try:
            import markitdown_fallback as _mdf
            md_exts = list(_mdf.SUPPORTED_EXTS)
        except Exception:
            md_exts = []
    all_doc_exts = list(DOC_EXTS) + md_exts

    return {
        "document": {
            "extensions": all_doc_exts,
            "pdf": bool(pdf_mod) or bool(mineru.get("available")),
            "pdf_backend": ("mineru+" + (pdf_mod or "none")) if mineru.get("available") else (pdf_mod or ""),
            "mineru": mineru,
            "office": office,
            "markitdown": markitdown,
            # 没有 pypdf 时 PDF 仍会尝试导入，但会明确报错，这里给出提示
            "note": pdf_note,
        },
        "image": {
            "extensions": list(IMAGE_EXTS),
            "vision": vision_ok,
            "backend": "vision-llm",
            "note": "" if vision_ok else "未配置可用的模型，图片识图不可用",
        },
        "limits": {
            "max_file_mb": 16,
            "max_files_per_request": 10,
            "chunk_size": CHUNK_SIZE,
        },
    }


def supported_extensions():
    """所有可导入的扩展名。"""
    return list(DOC_EXTS) + list(IMAGE_EXTS)


# ============================================================
# 分块
# ============================================================
def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, max_chunks=MAX_CHUNKS):
    """把长正文按**句子边界**切成若干块，块间带重叠。

    做法：先用 document_importer.split_sentences() 断句（它按 。！？；\n 切），
    再贪心地把句子拼到接近 size；下一块以尾部约 overlap 字的句子作开头，
    这样跨块的语义不会被硬切断。

    为什么要分块而不是整篇一条：
      1. document_importer.import_file 会把正文截断到 2000 字，长文会丢内容；
      2. 检索时一块 ≈ 一个主题，命中更精确；整篇一条会把无关内容也带进 prompt。
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= size:
        return [text]

    try:
        from tools.document_importer import split_sentences
        sents = split_sentences(text)
    except Exception:
        sents = []
    if not sents:
        # 断句失败就退化成按固定长度硬切（仍然带重叠）
        step = max(1, size - overlap)
        return [text[i:i + size] for i in range(0, len(text), step)][:max_chunks]

    chunks = []
    cur = []
    cur_len = 0
    for s in sents:
        s_len = len(s)
        if cur_len + s_len > size and cur:
            chunks.append("".join(cur).strip())
            if len(chunks) >= max_chunks:
                break
            # 用尾部句子作为下一块的开头（重叠）
            tail = []
            tail_len = 0
            for prev in reversed(cur):
                if tail_len + len(prev) > overlap:
                    break
                tail.insert(0, prev)
                tail_len += len(prev)
            cur = tail
            cur_len = tail_len
        cur.append(s)
        cur_len += s_len
    if cur and len(chunks) < max_chunks:
        tail_text = "".join(cur).strip()
        if tail_text:
            chunks.append(tail_text)
    return [c for c in chunks if c]


def chunk_prefer_blocks(text, blocks, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, max_chunks=MAX_CHUNKS):
    """有 heading 时按块边界切；无 heading 或切不出多段则回退 chunk_text。

    blocks 不落库，只影响切分边界。
    """
    if not (text or "").strip():
        return []
    try:
        import parse_blocks
        secs = parse_blocks.section_texts(blocks or [])
    except Exception:
        secs = []
    if len(secs) >= 2:
        out = []
        for sec in secs:
            if len(out) >= max_chunks:
                break
            pieces = chunk_text(sec, size=size, overlap=overlap, max_chunks=max_chunks - len(out))
            out.extend(pieces)
        return out[:max_chunks] if out else chunk_text(text, size=size, overlap=overlap, max_chunks=max_chunks)
    return chunk_text(text, size=size, overlap=overlap, max_chunks=max_chunks)


# ============================================================
# 内容安全：导入是一条写入路径，也要过审核
# ============================================================
def _safety_reject(text):
    """检查导入文本。返回拒绝原因字符串，通过则返回 None。

    只拦 **A1 层（无豁免的硬拦截词）**，不拦 A2 议题词 ——
    因为合法课件里出现「赌博」「武器」这类**议题词**是正常的
    （「枪械设计原理」这类课程本来就是被显式设计为放行的），
    而 A1 是「开盒 / 自制枪 / ddos」这种毫无正当用法的操作性词组。
    """
    try:
        from safety_gate import check_detail
    except ImportError:
        try:
            from server.safety_gate import check_detail
        except ImportError:
            return None  # 安全层不可用时放行，避免把导入功能整个卡死
    try:
        detail = check_detail(text)
    except Exception:
        return None
    if detail.get("action") == "BLOCK" and detail.get("layer") == "A1":
        return "内容命中硬拦截词：%s" % "、".join(detail.get("hits") or [])
    return None


# ============================================================
# 落盘
# ============================================================
def save_upload(data, filename, data_dir):
    """把上传的字节写到 data/uploads/ 下，返回落盘路径。

    文件名会用 form_parser.safe_name() 清洗过（去掉路径分隔符），
    再加时间戳前缀避免同名覆盖。
    """
    from form_parser import safe_name

    updir = os.path.join(data_dir, UPLOAD_SUBDIR)
    os.makedirs(updir, exist_ok=True)
    clean = safe_name(filename, fallback="upload")
    path = os.path.join(updir, "%d_%s" % (int(time.time() * 1000), clean))
    with open(path, "wb") as f:
        f.write(data)
    return path


def cleanup_uploads(data_dir, keep_seconds=UPLOAD_KEEP_SECONDS):
    """清掉过期的上传临时文件（每次导入时顺手做，不需要定时任务）。"""
    updir = os.path.join(data_dir, UPLOAD_SUBDIR)
    if not os.path.isdir(updir):
        return 0
    now = time.time()
    removed = 0
    for name in os.listdir(updir):
        p = os.path.join(updir, name)
        try:
            if os.path.isfile(p) and (now - os.path.getmtime(p)) > keep_seconds:
                os.remove(p)
                removed += 1
        except OSError:
            pass
    return removed


# ============================================================
# 向量化挂钩（向量 RAG 切片，2026-10-10）
# ============================================================
def _vectorize_notes(notes, chunks, owner, scope, category):
    """分块入库后把各块写入向量库。

    设计要点：
      1. 任何失败都不抛、不阻塞导入 —— 笔记已落 JSON，仅词法可检，
         向量层可由 embed_backfill.py 事后补建；
      2. 惰性 import（函数内），未装 chromadb / 无 key 时秒退；
      3. 一个笔记一块（与当前入库结构一一对应），向量文本用「标题\\n正文」，
         让标题信号也参与语义匹配（词法层标题权重 6.0，语义层同样受益）。
    """
    try:
        if os.environ.get("STUDY_LIU_VECTOR", "1").strip() in ("0", "false", "no"):
            return
        import embeddings
        import vector_store
        if not vector_store.AVAILABLE:
            return
        texts = ["%s\\n%s" % (n.get("title") or "", ck)
                 for n, ck in zip(notes, chunks)]
        vecs = embeddings.embed_texts(texts)
        if not vecs:
            return   # 无 key / 断网：回退词法，不影响导入结果
        for (note, _ck), vec in zip(zip(notes, chunks), vecs):
            if vec:
                vector_store.upsert_chunk(
                    note["id"], 0, note.get("title", ""), vec,
                    owner=owner, scope=scope, category=category)
    except Exception:
        pass   # 向量化是增强路径，绝不能把导入接口打挂


# ============================================================
# 主入口
# ============================================================
def ingest(path, filename, tags=None, store=None, data_dir=None, title=None,
           owner="", scope="public", category=""):
    """把一个已落盘的文件导入知识库。

    参数：
        title: 可选，「归入的笔记名」。界面上允许把多个文件归到同一条笔记下 ——
               传了就以它作为所有块的前缀（分组时自然聚在一起），不传则用文件名。
               它不覆盖来源信息：块标题仍是「<归入名> · i/n」，tags 里保留 #pdf / #image 等。
    返回：
        {
          "ok": bool,
          "kind": "document" | "image",
          "notes": [{"id", "title"}],   # 成功写入的条目
          "chunks": int,
          "chars": int,
          "engine": str,                # 文档解析引擎（pypdf / mineru / docling / ooxml，可能为空）
          "error": str | None,
        }
    不抛异常（除编程错误）—— 上传接口需要把失败原因原样返回给前端。
    """
    from tools.knowledge_store import KnowledgeStore

    if store is None:
        store = KnowledgeStore()

    ext = os.path.splitext(filename)[1].lower()
    out = {"ok": False, "kind": "", "notes": [], "chunks": 0, "chars": 0, "error": None}
    parse_blocks_list = []

    # ---- 1. 取出正文（文档直接读，图片先识图）----
    if ext in IMAGE_EXTS:
        out["kind"] = "image"
        try:
            from tools.vision_ocr import extract_text_from_image
        except ImportError as e:
            out["error"] = "视觉识图模块不可用：%s" % e
            return out
        r = extract_text_from_image(path)
        if r.get("error"):
            out["error"] = r["error"]
            return out
        text = (r.get("text") or "").strip()
        base_title = os.path.splitext(os.path.basename(filename))[0] or "图片笔记"
        default_tags = ["#import", "#image", "#ocr"]
    elif ext in DOC_EXTS:
        out["kind"] = "document"
        parse_engine = ""
        parse_blocks_list = []
        if ext == ".pdf":
            # PDF 走 doc_parse：数字文本 pypdf，扫描件 / 复杂版式尝试 MinerU 侧车
            try:
                import doc_parse
                parsed = doc_parse.extract_pdf_text(path)
            except ImportError as e:
                parsed = {"text": "", "engine": "", "error": "PDF 解析模块不可用：%s" % e}
            except Exception as e:
                parsed = {"text": "", "engine": "", "error": "解析失败：%s" % e}
            text = (parsed.get("text") or "").strip()
            parse_engine = parsed.get("engine") or ""
            parse_blocks_list = list(parsed.get("blocks") or [])
            if not text:
                err = (parsed.get("error") or "").strip() or "文件里没有解析到任何文字"
                low = err.lower()
                if "pypdf" in low or "pdfplumber" in low:
                    # PDF 但没装 pypdf —— 把话说明白，别只说"导入失败"
                    out["error"] = (
                        "解析失败：%s。PDF 需要服务器安装 pypdf（纯 Python 库，约 1MB）；"
                        "复杂版式可另装 MinerU 侧车。Markdown / txt 无需任何依赖。" % err
                    )
                elif err.startswith("解析") or "失败" in err or "未安装" in err or "没有解析" in err:
                    out["error"] = err
                else:
                    out["error"] = "解析失败：%s" % err
                return out
        elif ext in (".docx", ".pptx"):
            # Word / PPT 走 office_parse：docling 侧车，缺 CLI 回退 OOXML 标准库
            try:
                import office_parse
                parsed = office_parse.extract_office_text(path)
            except ImportError as e:
                parsed = {"text": "", "engine": "", "error": "Office 解析模块不可用：%s" % e}
            except Exception as e:
                parsed = {"text": "", "engine": "", "error": "解析失败：%s" % e}
            text = (parsed.get("text") or "").strip()
            parse_engine = parsed.get("engine") or ""
            parse_blocks_list = list(parsed.get("blocks") or [])
            if not text:
                err = (parsed.get("error") or "").strip() or "文件里没有解析到任何文字"
                out["error"] = err if ("失败" in err or "没有解析" in err or "不支持" in err) else ("解析失败：%s" % err)
                return out
        else:
            try:
                from tools.document_importer import read_text
            except ImportError as e:
                out["error"] = "文档解析模块不可用：%s" % e
                return out
            try:
                text = (read_text(path) or "").strip()
                try:
                    import parse_blocks as _pb
                    if ext in (".md", ".markdown"):
                        parse_blocks_list = _pb.markdown_to_blocks(text)
                    else:
                        parse_blocks_list = _pb.plaintext_to_blocks(text)
                except Exception:
                    parse_blocks_list = []
            except ImportError as e:
                out["error"] = "解析失败：%s" % e
                return out
            except Exception as e:
                out["error"] = "解析失败：%s" % e
                return out
        base_title = os.path.splitext(os.path.basename(filename))[0] or "导入的笔记"
        default_tags = ["#import", "#%s" % (ext.lstrip(".") or "file")]
        if parse_engine:
            default_tags.append("#%s" % parse_engine)
        out["engine"] = parse_engine
    else:
        # 兜底层：xlsx / xls / html / epub / zip / 音频 等 doc_parse+office_parse 不覆盖的格式走 markitdown。
        # 它是补盲，不替换任何现网解析器；缺包时静默回落到 unsupported 提示。
        out["kind"] = "document"
        parse_engine = ""
        parse_blocks_list = []
        try:
            import markitdown_fallback
            if markitdown_fallback.supports(ext):
                parsed = markitdown_fallback.convert(path)
                if parsed.get("text"):
                    text = parsed["text"]
                    parse_engine = parsed.get("engine") or "markitdown"
                elif parsed.get("error"):
                    out["error"] = parsed["error"]
                    return out
            else:
                out["error"] = "不支持的文件类型：%s（支持 %s）" % (
                    ext or "无扩展名", " / ".join(supported_extensions()))
                return out
        except Exception as e:
            out["error"] = "markitdown 兜底层不可用：%s" % e
            return out
        base_title = os.path.splitext(os.path.basename(filename))[0] or "导入的笔记"
        default_tags = ["#import", "#%s" % (ext.lstrip(".") or "file"), "#markitdown"]
        out["engine"] = parse_engine

    if not text:
        out["error"] = "文件里没有解析到任何文字"
        return out

    # 调用方指定了「归入的笔记名」就以其为准（界面上的「归入笔记」），
    # 这样多个文件能聚到同一条笔记下；不指定才退回用文件名。
    if title and str(title).strip():
        base_title = str(title).strip()

    # ---- 2. 内容安全 ----
    reject = _safety_reject(text)
    if reject:
        out["error"] = reject
        return out

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    # ---- 3. 分块（有 heading 时按 Block 边界切，不落库）----
    if ext in IMAGE_EXTS:
        parse_blocks_list = []
    chunks = chunk_prefer_blocks(text, parse_blocks_list if ext in DOC_EXTS else [])
    if not chunks:
        out["error"] = "分块后没有内容"
        return out

    # ---- 4. 入库 ----
    tags = list(tags) if tags else list(default_tags)
    # 图片识图出来的内容标记来源，便于事后区分
    if out["kind"] == "image":
        tags.append("#vision")

    total = len(chunks)
    for i, ck in enumerate(chunks, 1):
        title = base_title if total == 1 else "%s · %d/%d" % (base_title, i, total)
        try:
            note_id = store.add(
                title=title, content=ck, tags=tags,
                owner=owner, scope=scope, category=category)
        except Exception as e:
            out["error"] = "写入知识库失败（已写入 %d 条）：%s" % (len(out["notes"]), e)
            return out
        out["notes"].append({"id": note_id, "title": title})

    out["ok"] = True
    out["chunks"] = total
    out["chars"] = len(text)

    # ---- 5. 向量化（失败不阻塞：见 _vectorize_notes 注释）----
    _vectorize_notes(out["notes"], chunks, owner, scope, category)
    return out


def ingest_text(text, title=None, tags=None, store=None,
                owner="", scope="public", category=""):
    """直接导入一段文本（粘贴导入 / 接口用）。"""
    from tools.knowledge_store import KnowledgeStore
    if store is None:
        store = KnowledgeStore()

    text = (text or "").strip()
    if not text:
        return {"ok": False, "kind": "text", "notes": [], "chunks": 0,
                "chars": 0, "error": "内容为空"}
    reject = _safety_reject(text)
    if reject:
        return {"ok": False, "kind": "text", "notes": [], "chunks": 0,
                "chars": 0, "error": reject}

    title = (title or "").strip() or ("粘贴笔记 %s" % time.strftime("%m-%d %H:%M"))
    try:
        import parse_blocks as _pb
        paste_blocks = _pb.plaintext_to_blocks(text)
    except Exception:
        paste_blocks = []
    chunks = chunk_prefer_blocks(text, paste_blocks)
    total = len(chunks)
    notes = []
    chunks_kept = []
    for i, ck in enumerate(chunks, 1):
        t = title if total == 1 else "%s · %d/%d" % (title, i, total)
        notes.append({"id": store.add(
                          title=t, content=ck,
                          tags=list(tags) if tags else ["#import", "#paste"],
                          owner=owner, scope=scope, category=category),
                      "title": t})
        chunks_kept.append(ck)
    # 向量化（失败不阻塞，同 ingest）
    _vectorize_notes(notes, chunks_kept, owner, scope, category)
    return {"ok": True, "kind": "text", "notes": notes,
            "chunks": total, "chars": len(text), "error": None}
