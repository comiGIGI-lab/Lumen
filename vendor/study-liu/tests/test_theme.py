"""主题切换测试（v19）。

覆盖：
- THEMES 字典结构
- get_theme_names / get_current_theme_name
- apply_theme 切换 + 全局变量更新
- apply_theme 校验非法主题
- 字体 / 间距常量不依赖主题（保持稳定）
"""

import os
import sys

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


import ui.theme as theme


@pytest.fixture(autouse=True)
def _restore_theme():
    """每个测试后还原默认主题（避免污染其他测试）。"""
    original = theme.get_current_theme_name()
    yield
    theme.apply_theme(original)


# ==========================================================
# THEMES 结构
# ==========================================================
def test_themes_has_light_and_dark():
    assert "light" in theme.THEMES
    assert "dark" in theme.THEMES


def test_light_and_dark_have_same_keys():
    """两套主题必须有完全相同的 key（确保切换时不会 KeyError）。"""
    assert set(theme.THEMES["light"].keys()) == set(theme.THEMES["dark"].keys())


def test_required_color_keys():
    required = {
        "BG_APP", "BG_CARD", "BG_HOVER", "BG_DISABLED",
        "PRIMARY", "PRIMARY_DARK", "PRIMARY_LIGHT",
        "ACCENT", "ACCENT_DARK",
        "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED", "TEXT_ON_PRIMARY",
        "BORDER", "BORDER_STRONG",
        "SUCCESS", "WARNING", "ERROR",
        "STATUS_BG", "STATUS_FG",
    }
    for key in required:
        assert key in theme.THEMES["light"], f"light 缺 {key}"
        assert key in theme.THEMES["dark"], f"dark 缺 {key}"


def test_color_values_are_hex():
    for name, d in theme.THEMES.items():
        for k, v in d.items():
            if not k.startswith("STATUS_") and not k.startswith("BG_"):
                continue
            if isinstance(v, str) and v.startswith("#"):
                assert len(v) == 7, f"{name}.{k} = {hex(v)!r} 长度不是 7"


def test_dark_bg_is_darker_than_light():
    """暗色主题的 BG_APP 应该是深色，浅色主题应该是亮色。"""
    def luminance(hex_color):
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return 0.299 * r + 0.587 * g + 0.114 * b

    l_light = luminance(theme.THEMES["light"]["BG_APP"])
    l_dark = luminance(theme.THEMES["dark"]["BG_APP"])
    assert l_dark < l_light, "暗色背景应该比浅色暗"


# ==========================================================
# get_theme_names / get_current_theme_name
# ==========================================================
def test_get_theme_names_includes_light_and_dark():
    names = theme.get_theme_names()
    assert "light" in names
    assert "dark" in names


def test_get_current_theme_name_default():
    # 测试启动时可能因为 pytest 顺序，主题已被切换；只断言返回在合法集合里
    name = theme.get_current_theme_name()
    assert name in theme.get_theme_names()


# ==========================================================
# apply_theme
# ==========================================================
def test_apply_theme_returns_old_name():
    cur = theme.get_current_theme_name()
    other = "dark" if cur == "light" else "light"
    old = theme.apply_theme(other)
    assert old == cur
    assert theme.get_current_theme_name() == other


def test_apply_theme_updates_module_globals():
    """切换主题后，模块全局变量应该被更新。"""
    bg_light = theme.THEMES["light"]["BG_APP"]
    bg_dark = theme.THEMES["dark"]["BG_APP"]
    # 确保 light / dark 不同
    assert bg_light != bg_dark

    # 切到 dark
    theme.apply_theme("dark")
    assert theme.BG_APP == bg_dark
    assert theme.PRIMARY == theme.THEMES["dark"]["PRIMARY"]

    # 切回 light
    theme.apply_theme("light")
    assert theme.BG_APP == bg_light


def test_apply_theme_invalid_raises():
    with pytest.raises(ValueError):
        theme.apply_theme("neon-pink")


def test_apply_theme_is_idempotent():
    """重复切同一主题不报错。"""
    cur = theme.get_current_theme_name()
    theme.apply_theme(cur)
    assert theme.get_current_theme_name() == cur


# ==========================================================
# 字体 / 间距常量（不依赖主题）
# ==========================================================
def test_font_constants_stable():
    """切换主题不应该影响字体常量。"""
    before = theme.FONT_BODY
    theme.apply_theme("dark")
    assert theme.FONT_BODY == before
    theme.apply_theme("light")
    assert theme.FONT_BODY == before


def test_spacing_constants_stable():
    before = theme.PAD_CARD
    theme.apply_theme("dark")
    assert theme.PAD_CARD == before


# ==========================================================
# 向后兼容：旧常量名依然可用
# ==========================================================
def test_backward_compat_constants_exist():
    """v18 及更早的常量名（BG_APP / BG_CARD 等）依然能 import。"""
    for name in [
        "BG_APP", "BG_CARD", "PRIMARY", "ACCENT",
        "TEXT_PRIMARY", "BORDER", "SUCCESS", "ERROR",
    ]:
        assert hasattr(theme, name), f"缺少 {name}"
        assert isinstance(getattr(theme, name), str)


def test_backward_compat_values_match_current_theme():
    """BG_APP 等应该等于当前主题的 BG_APP。"""
    cur = theme.get_current_theme_name()
    assert theme.BG_APP == theme.THEMES[cur]["BG_APP"]
    assert theme.BG_CARD == theme.THEMES[cur]["BG_CARD"]
    assert theme.PRIMARY == theme.THEMES[cur]["PRIMARY"]