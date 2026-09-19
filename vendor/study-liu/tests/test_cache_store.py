"""cache_store 模块测试 —— v19 第三梯队 #12。

覆盖：
- cache key 派生
- 命中 / 未命中
- TTL 过期
- LRU 淘汰
- list/clear/stats
- 持久化往返
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import tools.cache_store as cs


@pytest.fixture(autouse=True)
def _use_tmp_cache(monkeypatch, tmp_path):
    """所有用例都跑在 tmp 目录。"""
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(cs, "_get_cache_path", lambda: str(cache_path))
    yield


class TestCacheKey:
    """cache key 派生测试。"""

    def test_same_course_same_key(self):
        k1 = cs.make_cache_key("机器学习")
        k2 = cs.make_cache_key("机器学习")
        assert k1 == k2
        assert len(k1) == 16

    def test_case_insensitive(self):
        k1 = cs.make_cache_key("Python")
        k2 = cs.make_cache_key("python")
        assert k1 == k2

    def test_whitespace_trimmed(self):
        k1 = cs.make_cache_key("  Python  ")
        k2 = cs.make_cache_key("Python")
        assert k1 == k2

    def test_different_profile_different_key(self):
        p1 = {"level": "入门"}
        p2 = {"level": "进阶"}
        k1 = cs.make_cache_key("Python", p1)
        k2 = cs.make_cache_key("Python", p2)
        assert k1 != k2

    def test_same_profile_dict_different_order_same_key(self):
        """profile dict 顺序不影响 key（因为 sort_keys=True）。"""
        p1 = {"a": 1, "b": 2}
        p2 = {"b": 2, "a": 1}
        k1 = cs.make_cache_key("X", p1)
        k2 = cs.make_cache_key("X", p2)
        assert k1 == k2


class TestPutAndGet:
    """put + get 测试。"""

    def test_basic(self):
        result = {"course": "Python", "outline": ["a"], "plan": []}
        cs.put_cache("Python", result)
        got = cs.get_cached("Python")
        assert got == result

    def test_different_courses(self):
        cs.put_cache("Python", {"course": "Python"})
        cs.put_cache("Java", {"course": "Java"})
        assert cs.get_cached("Python")["course"] == "Python"
        assert cs.get_cached("Java")["course"] == "Java"

    def test_cache_miss(self):
        assert cs.get_cached("nonexistent") is None

    def test_put_empty_result_ignored(self):
        """空结果不入缓存。"""
        cs.put_cache("", {"course": ""})
        assert cs.get_cached("") is None
        cs.put_cache("X", None)
        assert cs.get_cached("X") is None

    def test_profile_affects_key(self):
        cs.put_cache("Python", {"v": "A"}, profile={"level": "入门"})
        # 同课程但不同画像应不命中
        assert cs.get_cached("Python", profile={"level": "进阶"}) is None
        # 同画像应命中
        assert cs.get_cached("Python", profile={"level": "入门"})["v"] == "A"

    def test_get_updates_last_used(self):
        cs.put_cache("X", {"v": 1})
        entries1 = cs.list_cached()
        time.sleep(0.05)
        cs.get_cached("X")
        entries2 = cs.list_cached()
        assert entries2[0]["last_used"] >= entries1[0]["last_used"]


class TestTTL:
    """TTL 过期测试。"""

    def test_expired_returns_none(self):
        cs.put_cache("X", {"v": 1})
        # 用 ttl=0 立即过期
        assert cs.get_cached("X", ttl=0) is None

    def test_expired_removes_entry(self):
        cs.put_cache("X", {"v": 1})
        cs.get_cached("X", ttl=0)
        # 即便不传 ttl 也应拿不到
        assert cs.get_cached("X") is None


class TestLRUEviction:
    """LRU 淘汰测试。"""

    def test_evicts_oldest_when_full(self, monkeypatch):
        monkeypatch.setattr(cs, "MAX_ENTRIES", 3)
        for i in range(5):
            cs.put_cache(f"C{i}", {"n": i})
        # 应只保留最后 3 条
        cached = cs.list_cached()
        assert len(cached) == 3
        # 后入的应该都在
        courses = {c["course"] for c in cached}
        assert "C2" in courses
        assert "C3" in courses
        assert "C4" in courses


class TestListAndClear:
    """list / clear / stats 测试。"""

    def test_list_sorted_by_last_used(self):
        # Windows time.time() 精度 ~15ms，sleep 50ms 保证时间戳可区分
        cs.put_cache("A", {"course": "A"})
        time.sleep(0.05)
        cs.put_cache("B", {"course": "B"})
        time.sleep(0.05)
        cs.put_cache("C", {"course": "C"})
        # C 应该是 last_used 最大的
        lst = cs.list_cached()
        assert lst[0]["course"] == "C"

    def test_clear_all(self):
        cs.put_cache("A", {"course": "A"})
        cs.put_cache("B", {"course": "B"})
        n = cs.clear_cache()
        assert n == 2
        assert cs.list_cached() == []

    def test_clear_specific_course(self):
        cs.put_cache("A", {"course": "A"})
        cs.put_cache("B", {"course": "B"})
        cs.put_cache("A", {"course": "A", "v": 2})   # 重新写 A
        n = cs.clear_cache(course="A")
        assert n == 1
        lst = cs.list_cached()
        assert len(lst) == 1
        assert lst[0]["course"] == "B"

    def test_stats(self):
        cs.put_cache("A", {"course": "A"})
        cs.put_cache("B", {"course": "B"})
        s = cs.cache_stats()
        assert s["count"] == 2
        assert s["oldest"] > 0
        assert s["newest"] >= s["oldest"]

    def test_stats_empty(self):
        s = cs.cache_stats()
        assert s["count"] == 0


class TestPersistence:
    """持久化往返测试。"""

    def test_reload_returns_same(self, tmp_path, monkeypatch):
        path = tmp_path / "cache.json"
        monkeypatch.setattr(cs, "_get_cache_path", lambda: str(path))
        cs.put_cache("Python", {"v": "hello"})
        # 模拟重新读
        data = cs._load_raw()
        assert len(data["entries"]) == 1
        # 直接拿
        assert cs.get_cached("Python")["v"] == "hello"

    def test_corrupted_file_does_not_crash(self, tmp_path, monkeypatch):
        path = tmp_path / "cache.json"
        path.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(cs, "_get_cache_path", lambda: str(path))
        # 损坏时不崩
        assert cs.get_cached("X") is None
        # 写入应能修复
        cs.put_cache("X", {"v": 1})
        assert cs.get_cached("X") == {"v": 1}


class TestCachePath:
    """路径测试。"""

    def test_cache_path_returns_string(self):
        p = cs.get_cache_path()
        assert isinstance(p, str)
        assert p.endswith("cache.json")