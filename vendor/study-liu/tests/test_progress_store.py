"""progress_store.py 单元测试。

通过临时目录隔离测试环境，避免污染真实 data/progress.json。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 把 progress_store 内部的 _PROGRESS_FILE 重定向到临时文件
import tools.progress_store as ps


def _use_tmp_progress(tmpdir):
    """把 progress_store 的存储路径改到临时目录。"""
    target = os.path.join(tmpdir, "progress.json")
    ps._PROGRESS_FILE = target
    ps._DATA_DIR = tmpdir


SAMPLE = {
    "course": "测试课程-进度",
    "outline": [
        {"title": "第 1 章 入门", "points": ["a", "b"]},
        {"title": "第 2 章 进阶"},
        "第 3 章 综合",
    ],
    "resources": [
        {"title": "R1", "type": "教程", "url": ""},
    ],
    "plan": [
        {"title": "Day 1 环境搭建", "tasks": ["安装"]},
        {"title": "Day 2 写代码"},
    ],
}


class TestSaveAndList:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_creates_entry(self):
        ps.save_result(SAMPLE["course"], SAMPLE)
        items = ps.list_courses()
        assert len(items) == 1
        assert items[0]["course"] == SAMPLE["course"]

    def test_save_initializes_progress_all_undone(self):
        ps.save_result(SAMPLE["course"], SAMPLE)
        info = ps.get_progress(SAMPLE["course"])
        assert len(info["outline"]) == 3
        assert len(info["plan"]) == 2
        for o in info["outline"]:
            assert o["done"] is False
        for p in info["plan"]:
            assert p["done"] is False

    def test_save_twice_updates_last_seen(self):
        ps.save_result(SAMPLE["course"], SAMPLE)
        first = ps.list_courses()[0]
        ps.save_result(SAMPLE["course"], SAMPLE)
        second = ps.list_courses()[0]
        # last_seen_at 应 >= created_at
        assert second["last_seen_at"] >= first["created_at"]


class TestSetDone:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)
        ps.save_result(SAMPLE["course"], SAMPLE)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_outline(self):
        ok = ps.set_done(SAMPLE["course"], "outline", 0, True)
        assert ok is True
        info = ps.get_progress(SAMPLE["course"])
        assert info["outline"][0]["done"] is True
        assert info["outline"][1]["done"] is False

    def test_check_plan(self):
        ok = ps.set_done(SAMPLE["course"], "plan", 1, True)
        assert ok is True
        info = ps.get_progress(SAMPLE["course"])
        assert info["plan"][1]["done"] is True

    def test_uncheck(self):
        ps.set_done(SAMPLE["course"], "outline", 0, True)
        ps.set_done(SAMPLE["course"], "outline", 0, False)
        info = ps.get_progress(SAMPLE["course"])
        assert info["outline"][0]["done"] is False

    def test_invalid_index_returns_false(self):
        assert ps.set_done(SAMPLE["course"], "outline", 99, True) is False
        assert ps.set_done(SAMPLE["course"], "plan", -1, True) is False

    def test_unknown_course_returns_false(self):
        assert ps.set_done("不存在的课程", "outline", 0, True) is False


class TestStats:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)
        ps.save_result(SAMPLE["course"], SAMPLE)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initial_stats_zero(self):
        d, t, r = ps.get_stats(SAMPLE["course"])
        assert d == 0
        assert t == 5   # 3 outline + 2 plan
        assert r == 0.0

    def test_after_check(self):
        ps.set_done(SAMPLE["course"], "outline", 0, True)
        ps.set_done(SAMPLE["course"], "plan", 1, True)
        d, t, r = ps.get_stats(SAMPLE["course"])
        assert d == 2
        assert t == 5
        assert abs(r - 0.4) < 1e-6


class TestLoadResult:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_existing(self):
        ps.save_result(SAMPLE["course"], SAMPLE)
        loaded = ps.load_result(SAMPLE["course"])
        assert loaded is not None
        assert loaded["course"] == SAMPLE["course"]
        assert len(loaded["outline"]) == 3

    def test_load_missing_returns_none(self):
        assert ps.load_result("不存在的课程") is None


class TestDeleteCourse:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)
        ps.save_result(SAMPLE["course"], SAMPLE)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delete_existing(self):
        assert ps.delete_course(SAMPLE["course"]) is True
        assert ps.load_result(SAMPLE["course"]) is None
        assert ps.list_courses() == []

    def test_delete_missing(self):
        assert ps.delete_course("不存在的课程") is False


class TestReSavePreservesProgress:
    """覆盖：第二次 save_result 时进度状态不应被重置。"""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        _use_tmp_progress(self.tmp)
        ps.save_result(SAMPLE["course"], SAMPLE)
        ps.set_done(SAMPLE["course"], "outline", 0, True)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_progress_preserved_after_resave(self):
        # 第二次保存同样的方案
        ps.save_result(SAMPLE["course"], SAMPLE)
        info = ps.get_progress(SAMPLE["course"])
        assert info["outline"][0]["done"] is True   # 已勾选状态保留