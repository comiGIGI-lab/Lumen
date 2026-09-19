# document_importer.py — 文档导入：粘贴文本 / 文件 → 关键句抽取 → 知识库

"""文档导入工具：把外部材料变成知识库条目。

支持：
1. paste_import(text, title=None, tags=None) — 直接粘贴一段文字
2. import_file(path, title=None, tags=None) — 读 PDF / MD / TXT 文件
3. extract_key_sentences(text, max_sentences=5) — 从长文本里抽关键句

关键句抽取算法（v1，简单但稳定）：
- 按中文 / 英文句号切句（。！？.!?；\n）
- 跳过长度 < 8 或 > 120 的句（多半是噪声或段落标题）
- 按"关键词集中度"打分：
  - 高频词 = 全文词频 ≥ 2 的实词（中文长度 ≥ 2、英文长度 ≥ 4）
  - 得分 = 句中高频词数 / 句长（归一化）
- 取分数最高的 N 句，保持原文本顺序

未来可扩展：
- TF-IDF / TextRank（要装 jieba / networkx）
- LLM 二次提炼（要在线模式）
"""

import os
import re


# ---------- 句切分 ----------
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?；;])\s*|\n+")


def split_sentences(text):
    """把文本切成句子列表（保留原顺序、过滤空字符串）。"""
    if not text:
        return []
    # 中文/英文标点 + 换行 都作为切分点
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


# ---------- 关键词集中度评分 ----------
def _tokenize(s):
    """简单分词：中文按字（连续 ≥ 2 字的串算"词"），英文按单词。"""
    # 英文 / 数字
    en_tokens = re.findall(r"[A-Za-z0-9]+", s)
    # 中文 ≥ 2 字串
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", s)
    return en_tokens + zh_tokens


def _build_freq(tokens_list, min_freq=2):
    """从一批 tokens 里统计高频词（出现 ≥ min_freq）。"""
    from collections import Counter
    c = Counter()
    for t in tokens_list:
        c[t] += 1
    return {w for w, n in c.items() if n >= min_freq}


def _score_sentence(sent, high_freq):
    """句子得分 = 高频词数 / max(句长, 1)。"""
    if not sent:
        return 0.0
    tokens = _tokenize(sent)
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in high_freq)
    return hits / max(len(tokens), 1)


def extract_key_sentences(text, max_sentences=5):
    """
    从文本里抽取关键句。
    参数：
        text: 原文
        max_sentences: 最多抽几句（默认 5）
    返回：
        关键句列表（按原文本顺序）
    """
    if not text or not text.strip():
        return []

    sents = split_sentences(text)
    # 过滤太短 / 太长的句
    sents = [s for s in sents if 8 <= len(s) <= 200]
    if not sents:
        return []

    # 统计全文高频词
    all_tokens = []
    for s in sents:
        all_tokens.extend(_tokenize(s))
    high_freq = _build_freq(all_tokens, min_freq=2)

    if not high_freq:
        # 没有高频词 → 取前 max_sentences 个非空句
        return sents[:max_sentences]

    # 评分排序
    scored = [(s, _score_sentence(s, high_freq)) for s in sents]
    # 按分数从高到低排序；同分按原顺序（用 enumerate 当 tiebreaker）
    indexed = [(i, s, sc) for i, (s, sc) in enumerate(scored)]
    indexed.sort(key=lambda x: (-x[2], x[0]))

    top = indexed[:max_sentences]
    # 恢复原文本顺序
    top.sort(key=lambda x: x[0])
    return [s for _, s, _ in top]


# ---------- 文件读取 ----------
def _read_text_file(path):
    """读 .md / .txt 文件，按 UTF-8。"""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _read_pdf_file(path):
    """读 PDF 文件。优先用 pypdf；失败回退到 pdfplumber；都失败抛 ImportError。"""
    text = ""
    try:
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader  # noqa: F401
        reader = PdfReader(path)
        chunks = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                chunks.append("")
        text = "\n".join(chunks)
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        pass

    # 尝试 pdfplumber
    try:
        import pdfplumber  # type: ignore
        chunks = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
        text = "\n".join(chunks)
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception:
        pass

    raise ImportError(
        "读取 PDF 需要 pypdf 或 pdfplumber，请 `pip install pypdf`"
    )


def _read_file_auto(path):
    """根据扩展名自动选择读取方式。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".markdown", ".txt", ".text"):
        return _read_text_file(path)
    if ext == ".pdf":
        return _read_pdf_file(path)
    raise ValueError(f"不支持的文件类型：{ext}（仅支持 .pdf / .md / .txt）")


def _suggest_title(path, content):
    """从文件路径或内容推断标题。"""
    if path:
        base = os.path.basename(path)
        stem = os.path.splitext(base)[0]
        if stem:
            return stem
    # 用内容第一行
    if content:
        first = content.strip().split("\n", 1)[0]
        return first[:30] if first else "导入的笔记"
    return "导入的笔记"


# ---------- 高层 API ----------
def paste_import(text, title=None, tags=None, store=None):
    """
    把一段粘贴的文本入库。
    参数：
        text: 文本内容
        title: 标题（默认 "粘贴笔记-时间戳"）
        tags: 标签列表（默认 ["#import", "#paste"]）
        store: KnowledgeStore 实例（None 则用默认 data/knowledge.json）
    返回：
        新增笔记的 id
    """
    from datetime import datetime
    from tools.knowledge_store import KnowledgeStore
    if store is None:
        store = KnowledgeStore()
    content = (text or "").strip()
    if not content:
        raise ValueError("粘贴内容为空")
    if title is None or not title.strip():
        title = f"粘贴笔记-{datetime.now().strftime('%m-%d %H:%M')}"
    if tags is None:
        tags = ["#import", "#paste"]
    return store.add(title=title, content=content, tags=tags)


def import_file(path, title=None, tags=None, store=None, max_key_sentences=8):
    """
    导入文件：抽取关键句 + 全文 → 写入知识库（生成 1 条摘要笔记）。
    参数：
        path: 文件路径（.pdf / .md / .txt）
        title: 标题（默认用文件名）
        tags: 标签列表（默认 ["#import", "#<ext>"]）
        store: KnowledgeStore 实例
        max_key_sentences: 关键句条数
    返回：
        新增笔记的 id
    """
    from datetime import datetime
    from tools.knowledge_store import KnowledgeStore
    if store is None:
        store = KnowledgeStore()
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在：{path}")
    text = _read_file_auto(path).strip()
    if not text:
        raise ValueError(f"文件内容为空：{path}")
    if title is None or not title.strip():
        title = _suggest_title(path, text)
    if tags is None:
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        tags = ["#import", f"#{ext or 'file'}"]

    # 抽关键句 + 全文摘要
    key_sents = extract_key_sentences(text, max_sentences=max_key_sentences)
    key_part = "".join(f"• {s}\n" for s in key_sents) if key_sents else ""
    summary = (
        f"## 摘要（关键句）\n{key_part}\n"
        f"## 全文（{len(text)} 字）\n{text[:2000]}"
    )
    # 把元数据放在内容开头
    header = (
        f"[导入] {path}\n"
        f"[时间] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"[字数] {len(text)}\n"
        f"---\n\n"
    )
    content = header + summary
    return store.add(title=title, content=content, tags=tags)


def list_supported_extensions():
    """返回支持的扩展名列表（供 UI 文件对话框过滤用）。"""
    return [".pdf", ".md", ".markdown", ".txt"]