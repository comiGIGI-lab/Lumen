"""i18n 模块测试 —— v19 第三梯队 #9。

覆盖：
- 中英切换
- 占位符格式化
- 未知 key 回退
- 缓存清理
- 多语言模块存在性
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest
from i18n import t, set_language, get_language, get_available_languages, clear_cache


@pytest.fixture(autouse=True)
def _reset_lang():
    """每个用例前后都回到中文（避免污染）。"""
    clear_cache()
    set_language("zh")
    yield
    clear_cache()
    set_language("zh")


class TestBasic:
    """基础 API 测试。"""

    def test_default_is_zh(self):
        assert get_language() == "zh"

    def test_available_languages(self):
        langs = get_available_languages()
        assert "zh" in langs
        assert "en" in langs

    def test_unknown_language_silently_keeps_current(self):
        set_language("zh")
        set_language("xx")   # 未知
        assert get_language() == "zh"

    def test_set_and_get(self):
        set_language("en")
        assert get_language() == "en"
        set_language("zh")
        assert get_language() == "zh"


class TestTranslation:
    """翻译正确性测试。"""

    def test_chinese_btn_generate(self):
        set_language("zh")
        assert "生成" in t("BTN_GENERATE")

    def test_english_btn_generate(self):
        set_language("en")
        assert "Generate" in t("BTN_GENERATE")

    def test_english_status_with_placeholder(self):
        set_language("en")
        msg = t("STATUS_GENERATING", course="Python")
        assert "Python" in msg
        assert "Generating" in msg.lower() or "⏳" in msg

    def test_chinese_status_with_placeholder(self):
        set_language("zh")
        msg = t("STATUS_GENERATING", course="Python")
        assert "Python" in msg
        assert "生成" in msg or "⏳" in msg

    def test_help_sections_is_list(self):
        for lang in ("zh", "en"):
            set_language(lang)
            secs = t("HELP_SECTIONS")
            assert isinstance(secs, list)
            assert len(secs) >= 3
            for title, body in secs:
                assert isinstance(title, str) and len(title) > 0
                assert isinstance(body, str) and len(body) > 0

    def test_settings_tips_is_list(self):
        for lang in ("zh", "en"):
            set_language(lang)
            tips = t("SETTINGS_TIPS")
            assert isinstance(tips, list)
            assert len(tips) >= 2


class TestFallback:
    """兜底测试。"""

    def test_unknown_key_returns_itself(self):
        set_language("zh")
        # 未知 key 应原样返回，便于发现漏翻译
        assert t("NONEXISTENT_KEY") == "NONEXISTENT_KEY"

    def test_unknown_key_in_en_returns_key(self):
        set_language("en")
        # 未知 key 仍然返回原 key（不会炸）
        assert t("STILL_NONEXISTENT") == "STILL_NONEXISTENT"

    def test_fallback_to_zh_when_en_key_missing(self):
        """如果某个 key 只在中文有，英文模式下也应兜底返回中文。"""
        from i18n import _CACHE, _load
        clear_cache()
        _CACHE["en"] = _load("en")
        if "BTN_GENERATE" in _CACHE["en"]:
            del _CACHE["en"]["BTN_GENERATE"]
        set_language("en")
        result = t("BTN_GENERATE")
        # 中文兜底必须包含"生成"
        assert "生成" in result


class TestPlaceholderSafety:
    """占位符异常安全。"""

    def test_missing_placeholder_returns_unformatted(self):
        set_language("zh")
        # 模板是 "课程「{course}」"，不传 course 时不应崩
        result = t("STATUS_GENERATING")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extra_kwargs_ignored(self):
        set_language("zh")
        result = t("STATUS_GENERATING", course="X", extra="Y")
        assert "X" in result
        assert "extra" not in result


class TestThreadSafety:
    """线程安全测试（轻量）。"""

    def test_concurrent_set_language(self):
        import threading
        errors = []

        def switcher(lang, n):
            try:
                for _ in range(n):
                    set_language(lang)
                    t("BTN_GENERATE")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=switcher, args=("zh", 50)),
            threading.Thread(target=switcher, args=("en", 50)),
        ]
        for t_ in threads:
            t_.start()
        for t_ in threads:
            t_.join(timeout=10)

        assert errors == []


class TestParity:
    """中英文案应保持 key 一致（手动同步的守护）。"""

    def test_zh_en_keys_parity(self):
        """zh.py 和 en.py 的文案 key 应该完全相同。"""
        from i18n import _load
        zh_keys = set(_load("zh").keys())
        en_keys = set(_load("en").keys())
        missing_in_en = zh_keys - en_keys
        missing_in_zh = en_keys - zh_keys
        assert missing_in_en == set(), f"英译缺失：{sorted(missing_in_en)}"
        assert missing_in_zh == set(), f"中文缺失：{sorted(missing_in_zh)}"

    def test_all_values_are_strings(self):
        from i18n import _load
        for lang in ("zh", "en"):
            d = _load(lang)
            for k, v in d.items():
                assert isinstance(v, (str, list)), \
                    f"{lang}.{k} 应该是 str 或 list，实际是 {type(v).__name__}"