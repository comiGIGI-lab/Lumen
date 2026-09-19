"""知识库 GUI 改造相关的测试。

覆盖：
- KnowledgeStore 核心 API（add / search / list_all / delete）
- 边界：空文件、损坏 JSON、空关键词
- _normalize_tags 行为（中文 / 英文 / 顿号 / 去重 / 去空）
"""

import json
import os
import sys

import pytest

# 确保项目根目录在 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from tools.knowledge_store import KnowledgeStore


# ==========================================================
# KnowledgeStore API
# ==========================================================
def test_list_all_empty(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    assert s.list_all() == []


def test_add_returns_id_and_persists(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    nid = s.add("深度学习", "神经网络基础", tags=["AI"])
    assert nid == 1

    # 重新加载验证持久化
    s2 = KnowledgeStore(filepath=str(p))
    items = s2.list_all()
    assert len(items) == 1
    assert items[0]["title"] == "深度学习"
    assert items[0]["content"] == "神经网络基础"
    assert items[0]["tags"] == ["AI"]
    assert "created_at" in items[0]


def test_add_multiple_increments_id(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    assert s.add("A", "a") == 1
    assert s.add("B", "b") == 2
    assert s.add("C", "c") == 3


def test_search_case_insensitive(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    s.add("深度学习", "神经网络基础", tags=["AI"])
    s.add("线性代数", "矩阵求逆", tags=["数学"])
    r = s.search("ai")
    assert len(r) == 1
    assert r[0]["title"] == "深度学习"

    r2 = s.search("AI")
    assert len(r2) == 1

    r3 = s.search("矩阵")
    assert len(r3) == 1
    assert r3[0]["title"] == "线性代数"


def test_search_matches_in_content(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    s.add("标题A", "正文里包含 Python 这个关键词")
    r = s.search("python")
    assert len(r) == 1
    assert r[0]["title"] == "标题A"


def test_search_empty_keyword_returns_all(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    s.add("A", "a")
    s.add("B", "b")
    # 空关键词：在 KnowledgeStore 实现里 kw="" 一定 in 字符串，所以返回全部
    r = s.search("")
    assert len(r) == 2


def test_delete_returns_bool(tmp_path):
    p = tmp_path / "k.json"
    s = KnowledgeStore(filepath=str(p))
    nid = s.add("t", "c")
    assert s.delete(nid) is True
    assert s.list_all() == []
    # 删除不存在的 id
    assert s.delete(99999) is False


def test_corrupted_json_recovers(tmp_path):
    p = tmp_path / "k.json"
    p.write_text("{not valid json", encoding="utf-8")
    s = KnowledgeStore(filepath=str(p))
    # 不崩，回退空列表
    assert s.list_all() == []


def test_search_corrupted_json_recovers(tmp_path):
    p = tmp_path / "k.json"
    p.write_text("{not valid json", encoding="utf-8")
    s = KnowledgeStore(filepath=str(p))
    assert s.search("anything") == []


def test_add_after_corrupted_json_recovers(tmp_path):
    p = tmp_path / "k.json"
    p.write_text("garbage", encoding="utf-8")
    s = KnowledgeStore(filepath=str(p))
    # 加一条新笔记后应能正常持久化
    nid = s.add("重建", "新建笔记")
    assert nid == 1
    s2 = KnowledgeStore(filepath=str(p))
    assert len(s2.list_all()) == 1


def test_default_filepath_creates_data_dir():
    """默认路径（data/knowledge.json）应能创建目录。"""
    s = KnowledgeStore()
    # 不崩即可（_ensure_dir 已跑过）
    assert isinstance(s.list_all(), list)


# ==========================================================
# _normalize_tags：GUI 用到的标签规范化
# ==========================================================
def _normalize_tags(raw):
    """镜像 ui/knowledge_dialog.py 与 ui/collect_dialog.py 中的实现。"""
    if not raw:
        return []
    parts = []
    buf = ""
    for ch in raw:
        if ch in (",", "，", "、"):
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def test_normalize_tags_english_comma():
    assert _normalize_tags("a, b, c") == ["a", "b", "c"]


def test_normalize_tags_chinese_comma():
    assert _normalize_tags("a，b，c") == ["a", "b", "c"]


def test_normalize_tags_dunhao():
    assert _normalize_tags("a、b、c") == ["a", "b", "c"]


def test_normalize_tags_mixed():
    assert _normalize_tags("a, b、c，d") == ["a", "b", "c", "d"]


def test_normalize_tags_dedup():
    assert _normalize_tags("a, a, b") == ["a", "b"]


def test_normalize_tags_strip_whitespace():
    assert _normalize_tags("  a  ,  b  ") == ["a", "b"]


def test_normalize_tags_empty():
    assert _normalize_tags("") == []
    assert _normalize_tags(None) == []


def test_normalize_tags_no_separator():
    assert _normalize_tags("single") == ["single"]


# ==========================================================
# 默认标题抽取（collect_dialog 用）
# ==========================================================
def _default_title_from_content(content):
    if not content:
        return ""
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    head = first_line[:24].strip()
    return head or "未命名笔记"


def test_default_title_short_content():
    assert _default_title_from_content("这是第一行\n第二行") == "这是第一行"


def test_default_title_truncate_to_24():
    long = "a" * 50
    t = _default_title_from_content(long)
    assert len(t) == 24


def test_default_title_empty():
    assert _default_title_from_content("") == ""
    assert _default_title_from_content(None) == ""