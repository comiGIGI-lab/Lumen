"""i18n UI 接入测试 —— v19 第三梯队 #7 验证。

验证 i18n 字符串能正确驱动 main_window / settings_dialog 的文案。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from i18n import t, set_language, get_language


@pytest.fixture(autouse=True)
def _reset_lang():
    set_language("zh")
    yield
    set_language("zh")


class TestI18nUI:
    """i18n 字符串能驱动 UI 文案（无需启动 tkinter）。"""

    def test_app_title_zh(self):
        set_language("zh")
        title = t("APP_TITLE")
        assert title == "study-liu"

    def test_app_title_en(self):
        set_language("en")
        title = t("APP_TITLE")
        assert title == "study-liu"

    def test_main_buttons_zh(self):
        set_language("zh")
        for key in (
            "BTN_GENERATE", "BTN_CHAT", "BTN_SETTINGS",
            "BTN_KNOWLEDGE", "BTN_EXPORT", "BTN_HISTORY",
            "BTN_CALENDAR", "BTN_SCREENSHOT",
        ):
            text = t(key)
            assert len(text) > 0
            assert text != key   # 不能回退到 key

    def test_main_buttons_en(self):
        set_language("en")
        for key in (
            "BTN_GENERATE", "BTN_CHAT", "BTN_SETTINGS",
            "BTN_KNOWLEDGE", "BTN_EXPORT", "BTN_HISTORY",
        ):
            text = t(key)
            assert len(text) > 0

    def test_status_messages_have_placeholders(self):
        set_language("zh")
        # 这些都需要格式化
        msg = t("STATUS_DONE", course="Python", n_outline=3, n_resource=5, n_plan=7)
        assert "Python" in msg
        assert "3" in msg
        assert "5" in msg
        assert "7" in msg

    def test_status_messages_en(self):
        set_language("en")
        msg = t("STATUS_DONE", course="Python", n_outline=3, n_resource=5, n_plan=7)
        assert "Python" in msg
        assert "3" in msg

    def test_three_columns(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in ("COL_OUTLINE", "COL_RESOURCES", "COL_PLAN"):
                text = t(key)
                assert len(text) > 0

    def test_profile_labels(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in ("PROFILE_TITLE", "PROFILE_LEVEL", "PROFILE_DAILY",
                        "PROFILE_GOAL", "PROFILE_DEADLINE"):
                text = t(key)
                assert len(text) > 0

    def test_settings_dialog_labels(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in ("SETTINGS_TITLE", "SETTINGS_MODE_LABEL",
                        "SETTINGS_LLM_LABEL", "SETTINGS_APPEARANCE",
                        "SETTINGS_LANG"):
                text = t(key)
                assert len(text) > 0

    def test_knowledge_base_labels(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in ("KB_TITLE", "KB_NEW", "KB_IMPORT", "KB_SEARCH_PH"):
                text = t(key)
                assert len(text) > 0

    def test_calendar_labels(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in ("CALENDAR_TITLE", "CALENDAR_TIP", "CALENDAR_BTN_EXPORT"):
                text = t(key)
                assert len(text) > 0

    def test_screenshot_labels(self):
        for lang in ("zh", "en"):
            set_language(lang)
            for key in (
                "SCREENSHOT_TITLE", "SCREENSHOT_BTN_LOAD",
                "SCREENSHOT_BTN_OCR", "SCREENSHOT_BTN_EXPLAIN",
            ):
                text = t(key)
                assert len(text) > 0


class TestLanguageSwitch:
    """语言切换对 UI 字符串的影响。"""

    def test_switch_changes_output(self):
        set_language("zh")
        zh_text = t("BTN_GENERATE")

        set_language("en")
        en_text = t("BTN_GENERATE")

        assert zh_text != en_text

    def test_switch_back(self):
        set_language("en")
        en = t("BTN_GENERATE")
        set_language("zh")
        zh = t("BTN_GENERATE")
        assert en != zh
        # 再次切换应回到一致
        set_language("en")
        en2 = t("BTN_GENERATE")
        assert en2 == en