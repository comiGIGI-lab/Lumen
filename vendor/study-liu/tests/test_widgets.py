"""UI 组件冒烟测试。

验证各 widget 在真实 Tk 窗口下能正常构造 / 配置 / 销毁，不崩。
不验证视觉细节（颜色 / 字号）—— 那属于人眼测试范畴。

要求：在隔离的 Tk root 下测，每个 case 自己建 / 销毁 root。
"""

import os
import sys
import tkinter as tk

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# 在 CI 环境（无 display）下跳过 GUI 测试
_HAS_DISPLAY = True
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    _HAS_DISPLAY = False


pytestmark = pytest.mark.skipif(
    not _HAS_DISPLAY, reason="无 display，跳过 GUI 测试",
)


@pytest.fixture
def tk_root():
    """每个测试提供一个独立的 Tk root，测试结束后销毁。"""
    try:
        root = tk.Tk()
        root.withdraw()  # 不显示
    except tk.TclError as e:
        pytest.skip(f"无法创建 Tk root：{e}")
    yield root
    try:
        root.destroy()
    except Exception:
        pass


# ==========================================================
# Card
# ==========================================================
def test_card_constructs(tk_root):
    from ui.widgets import Card
    card = Card(tk_root)
    assert card is not None
    assert hasattr(card, "inner")
    # 卡片能 pack
    card.pack(fill=tk.BOTH, expand=True)
    tk_root.update_idletasks()


def test_card_with_padding_and_border_off(tk_root):
    from ui.widgets import Card
    card = Card(tk_root, padding=24, border=False)
    assert card.body.cget("highlightthickness") == 0


# ==========================================================
# PlaceholderEntry
# ==========================================================
def test_placeholder_entry_constructs(tk_root):
    from ui.widgets import PlaceholderEntry
    e = PlaceholderEntry(tk_root, placeholder="请输入…")
    assert e is not None
    assert e._ph == "请输入…"
    # 默认显示 placeholder
    assert e.get() == "请输入…"
    # get_real 返回空
    assert e.get_real() == ""


def test_placeholder_entry_real_input(tk_root):
    from ui.widgets import PlaceholderEntry
    e = PlaceholderEntry(tk_root, placeholder="ph")
    e._on_focus_in(None)
    e.insert(0, "hello")
    assert e.get() == "hello"
    assert e.get_real() == "hello"


def test_placeholder_entry_focus_out_restores_when_empty(tk_root):
    """focus_out 时若输入为空，应该恢复 placeholder。"""
    from ui.widgets import PlaceholderEntry
    e = PlaceholderEntry(tk_root, placeholder="ph")
    e._on_focus_in(None)   # 清空 placeholder，进入输入状态
    # 不输入任何字符
    e._on_focus_out(None)
    assert e.get() == "ph"
    assert e.get_real() == ""


# ==========================================================
# PrimaryButton / AccentButton
# ==========================================================
def test_primary_button_constructs(tk_root):
    from ui.widgets import PrimaryButton
    called = []

    def cmd():
        called.append(1)

    btn = PrimaryButton(tk_root, text="生成", command=cmd)
    btn.pack()
    tk_root.update_idletasks()
    btn.invoke()
    assert called == [1]


def test_accent_button_constructs(tk_root):
    from ui.widgets import AccentButton
    called = []

    def cmd():
        called.append("ok")

    btn = AccentButton(tk_root, text="导出", command=cmd)
    btn.pack()
    tk_root.update_idletasks()
    btn.invoke()
    assert called == ["ok"]


# ==========================================================
# ResultPanel
# ==========================================================
def test_result_panel_outline(tk_root):
    from ui.widgets import ResultPanel
    panel = ResultPanel(tk_root, "课程大纲")
    panel.pack(fill=tk.BOTH, expand=True)
    panel.set_outline(["第1章 入门", "第2章 进阶"])
    panel.clear()
    tk_root.update_idletasks()
    # 重新设置
    panel.set_outline(["A", "B", "C"])
    assert "3 章" in panel.count_label.cget("text")


def test_result_panel_resources(tk_root):
    from ui.widgets import ResultPanel
    panel = ResultPanel(tk_root, "推荐资源")
    panel.pack()
    panel.set_resources([
        {"title": "书", "type": "书籍", "url": ""},
        {"title": "视频", "type": "视频", "url": "https://x"},
    ])
    assert "2 项" in panel.count_label.cget("text")


def test_result_panel_plan(tk_root):
    from ui.widgets import ResultPanel
    panel = ResultPanel(tk_root, "学习计划")
    panel.pack()
    plan = [f"第{i}天 学习" for i in range(1, 8)]
    panel.set_plan(plan)
    assert "7 天" in panel.count_label.cget("text")


# ==========================================================
# GradientHeader
# ==========================================================
def test_gradient_header_constructs(tk_root):
    from ui.widgets import GradientHeader
    header = GradientHeader(
        tk_root, title="Study", subtitle="subtitle here",
    )
    header.pack(fill=tk.X)
    tk_root.update_idletasks()
    # 渐变 stripe 应该被构造
    assert len(header._gradient_steps) > 0


# ==========================================================
# 主题切换后 widgets 还能正常工作
# ==========================================================
def test_theme_switch_widgets_still_work(tk_root):
    """切换主题后 widget 构造不崩（验证 v19 apply_theme 不破坏 module globals）。"""
    from ui.theme import apply_theme, get_current_theme_name
    from ui.widgets import Card, PlaceholderEntry, PrimaryButton, ResultPanel

    before = get_current_theme_name()
    try:
        apply_theme("dark" if before == "light" else "light")
        # 在新主题下构造 widget
        Card(tk_root).pack()
        PlaceholderEntry(tk_root, placeholder="x").pack()
        PrimaryButton(tk_root, text="b").pack()
        ResultPanel(tk_root, "课程大纲").pack()
        tk_root.update_idletasks()
    finally:
        apply_theme(before)