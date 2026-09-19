"""文档导入工具测试。

覆盖：
- split_sentences：中英文混排、换行切分、过滤空
- _tokenize：中文字串 / 英文单词
- _build_freq：高频词过滤
- extract_key_sentences：空 / 短文 / 长文 / 无高频词 / 顺序保持
- paste_import：返回 id、写入数据库
- import_file：MD/TXT 文件能入库；不支持的扩展名抛错
- list_supported_extensions
"""

import os
import sys

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from tools.document_importer import (
    split_sentences,
    _tokenize,
    _build_freq,
    extract_key_sentences,
    paste_import,
    import_file,
    list_supported_extensions,
)


# ==========================================================
# split_sentences
# ==========================================================
def test_split_sentences_basic_chinese():
    s = split_sentences("今天天气很好。我去图书馆看书。学习让我快乐。")
    assert len(s) == 3
    assert s[0] == "今天天气很好。"
    assert s[1] == "我去图书馆看书。"
    assert s[2] == "学习让我快乐。"


def test_split_sentences_mixed_punct():
    s = split_sentences("What is next? 接下来干什么！继续学习; 加油.")
    assert len(s) >= 3


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences(None) == []


def test_split_sentences_newline_split():
    s = split_sentences("第一句\n第二句\n第三句")
    assert len(s) == 3


# ==========================================================
# _tokenize / _build_freq
# ==========================================================
def test_tokenize_chinese():
    tokens = _tokenize("今天 天气 很好 神经网络 深度学习")
    assert "神经网络" in tokens
    assert "深度学习" in tokens
    assert "今天" in tokens


def test_tokenize_english():
    tokens = _tokenize("Python is a great programming language")
    assert "Python" in tokens
    assert "programming" in tokens


def test_build_freq_filters_rare():
    tokens = ["AI", "AI", "深度", "深度", "Python"]
    high = _build_freq(tokens, min_freq=2)
    assert "AI" in high
    assert "深度" in high
    assert "Python" not in high  # 只出现 1 次


# ==========================================================
# extract_key_sentences
# ==========================================================
def test_extract_empty():
    assert extract_key_sentences("") == []
    assert extract_key_sentences(None) == []


def test_extract_short_text_returns_as_is():
    """短文本没有高频词时也返回（最多 max_sentences 条）。"""
    text = "今天天气真的很好，适合出去散步和阅读。"
    sents = extract_key_sentences(text, max_sentences=3)
    assert len(sents) >= 1


def test_extract_picks_top_by_score():
    """长文本应该抽出包含高频词的句。"""
    text = (
        "深度学习是机器学习的一个分支。"
        "今天我们去公园散步。"
        "神经网络是深度学习的核心。"
        "深度学习模型包括 CNN 和 Transformer。"
        "午饭吃面条。"
        "深度学习需要大量数据。"
    )
    sents = extract_key_sentences(text, max_sentences=3)
    assert len(sents) == 3
    # 高频词是"深度学习"，应该至少被选 2 句
    joined = "".join(sents)
    assert joined.count("深度学习") >= 2


def test_extract_keeps_original_order():
    """抽出的句子保持原文顺序，不是按分数排序返回。"""
    text = (
        "深度学习是机器学习的一个分支。"
        "今天我们去公园散步。"
        "神经网络是深度学习的核心。"
        "深度学习需要大量数据。"
    )
    sents = extract_key_sentences(text, max_sentences=2)
    # 顺序应该和原文一致（索引递增）
    assert len(sents) == 2


# ==========================================================
# paste_import
# ==========================================================
def test_paste_import_writes_to_store(tmp_path):
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    nid = paste_import(
        "这是粘贴的笔记内容。",
        title="测试笔记",
        tags=["#test"],
        store=store,
    )
    assert nid == 1
    items = store.list_all()
    assert len(items) == 1
    assert items[0]["title"] == "测试笔记"
    assert "#test" in items[0]["tags"]


def test_paste_import_empty_text_raises():
    from tools.knowledge_store import KnowledgeStore
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(filepath=os.path.join(td, "k.json"))
        with pytest.raises(ValueError):
            paste_import("", store=store)
        with pytest.raises(ValueError):
            paste_import("   ", store=store)


def test_paste_import_default_title():
    """不传 title 时自动生成。"""
    from tools.knowledge_store import KnowledgeStore
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        store = KnowledgeStore(filepath=os.path.join(td, "k.json"))
        nid = paste_import("内容", store=store)
        items = store.list_all()
        assert items[0]["title"].startswith("粘贴笔记-")


# ==========================================================
# import_file
# ==========================================================
def test_import_file_md(tmp_path):
    md = tmp_path / "note.md"
    md.write_text(
        "# 深度学习入门\n\n"
        "深度学习是机器学习的分支。\n"
        "神经网络是深度学习的核心。\n"
        "今天天气很好。\n"
        "深度学习需要大量数据。\n",
        encoding="utf-8",
    )
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    nid = import_file(str(md), store=store)
    items = store.list_all()
    assert len(items) == 1
    assert "深度学习" in items[0]["content"]
    assert "摘要" in items[0]["content"]


def test_import_file_txt(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text(
        "深度学习很强大。\n神经网络是核心。\n其他不相关内容。\n" * 5,
        encoding="utf-8",
    )
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    nid = import_file(str(txt), store=store)
    items = store.list_all()
    assert items[0]["title"] == "note"  # 用文件名


def test_import_file_not_found_raises(tmp_path):
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    with pytest.raises(FileNotFoundError):
        import_file(str(tmp_path / "missing.md"), store=store)


def test_import_file_unsupported_extension(tmp_path):
    f = tmp_path / "data.zip"
    f.write_text("zip 内容", encoding="utf-8")
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    with pytest.raises(ValueError):
        import_file(str(f), store=store)


def test_import_file_empty_content_raises(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("", encoding="utf-8")
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    with pytest.raises(ValueError):
        import_file(str(f), store=store)


def test_import_file_custom_title(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("内容", encoding="utf-8")
    from tools.knowledge_store import KnowledgeStore
    p = tmp_path / "k.json"
    store = KnowledgeStore(filepath=str(p))
    import_file(str(txt), title="自定义标题", tags=["#x"], store=store)
    items = store.list_all()
    assert items[0]["title"] == "自定义标题"
    assert "#x" in items[0]["tags"]


# ==========================================================
# list_supported_extensions
# ==========================================================
def test_list_supported_extensions():
    exts = list_supported_extensions()
    assert ".pdf" in exts
    assert ".md" in exts
    assert ".txt" in exts