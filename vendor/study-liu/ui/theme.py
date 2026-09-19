"""主题与配色常量 —— v19 重构为多主题对象。

v19 改造：
- 引入 THEMES 字典：light / dark 两套配色
- THEME 常量直接指向当前主题（默认 light，向后兼容旧代码）
- 新增 apply_theme(root, name)：运行时切换主题
- 旧代码里的 `from ui.theme import BG_CARD` 依然能用 —— 我们在文件底部把
  THEME 的所有 key 注入到模块全局，保持 API 完全向后兼容。

v5 间距历史（保留）：spacing 仍让 Tk 自动跟随系统 DPI
"""

# ---------- 字体 ----------
FONT_FAMILY_ZH = "Microsoft YaHei UI"
FONT_FAMILY_EN = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"

# v5 字号：介于 v10(11pt base) 与 v11(15pt base) 之间
FONT_HERO_TITLE = (FONT_FAMILY_ZH, 26, "bold")
FONT_HERO_SUB = (FONT_FAMILY_EN, 12)
FONT_CARD_TITLE = (FONT_FAMILY_ZH, 15, "bold")
FONT_BODY = (FONT_FAMILY_ZH, 12)
FONT_BODY_BOLD = (FONT_FAMILY_ZH, 12, "bold")
FONT_BODY_LARGE = (FONT_FAMILY_ZH, 13)
FONT_INPUT = (FONT_FAMILY_ZH, 13)
FONT_BUTTON = (FONT_FAMILY_ZH, 13, "bold")
FONT_BUTTON_LARGE = (FONT_FAMILY_ZH, 14, "bold")
FONT_BUTTON_SMALL = (FONT_FAMILY_ZH, 12, "bold")
FONT_STATUS = (FONT_FAMILY_ZH, 11)
FONT_SMALL = (FONT_FAMILY_ZH, 11)
FONT_TINY = (FONT_FAMILY_ZH, 10)

# ---------- 间距（v5 收紧：介于 v10 和 v11 之间） ----------
RADIUS = 12
PAD_CARD = 16
PAD_OUTER = 20
GAP = 12
GAP_LARGE = 18


# ============================================================
# 主题字典 —— 浅色 / 深色
# ============================================================
THEMES = {
    "light": {
        # 基础背景
        "BG_APP": "#f6f7fb",
        "BG_CARD": "#ffffff",
        "BG_HOVER": "#eef2f7",
        "BG_DISABLED": "#f1f5f9",

        # 渐变 / 品牌
        "GRAD_TOP_FROM": "#6366f1",
        "GRAD_TOP_TO": "#8b5cf6",
        "PRIMARY": "#6366f1",
        "PRIMARY_DARK": "#4f46e5",
        "PRIMARY_LIGHT": "#a5b4fc",
        "ACCENT": "#06b6d4",
        "ACCENT_DARK": "#0891b2",

        # 文字
        "TEXT_PRIMARY": "#1e293b",
        "TEXT_SECONDARY": "#475569",
        "TEXT_MUTED": "#64748b",
        "TEXT_ON_PRIMARY": "#ffffff",

        # 边框
        "BORDER": "#e2e8f0",
        "BORDER_STRONG": "#cbd5e1",

        # 状态色
        "SUCCESS": "#10b981",
        "WARNING": "#f59e0b",
        "ERROR": "#ef4444",

        # 状态栏专用（始终深色）
        "STATUS_BG": "#1e293b",
        "STATUS_FG": "#cbd5e1",
        "STATUS_ERROR_FG": "#fca5a5",
        "STATUS_WARN_FG": "#fcd34d",
    },
    "dark": {
        # 基础背景：深色 + 微亮
        "BG_APP": "#0f172a",         # slate-900
        "BG_CARD": "#1e293b",        # slate-800
        "BG_HOVER": "#334155",       # slate-700
        "BG_DISABLED": "#1e293b",

        # 渐变 / 品牌（亮一些以在深色背景上有对比）
        "GRAD_TOP_FROM": "#818cf8",  # indigo-400
        "GRAD_TOP_TO": "#a78bfa",    # violet-400
        "PRIMARY": "#818cf8",
        "PRIMARY_DARK": "#6366f1",
        "PRIMARY_LIGHT": "#c7d2fe",
        "ACCENT": "#22d3ee",         # cyan-500
        "ACCENT_DARK": "#06b6d4",

        # 文字（亮色）
        "TEXT_PRIMARY": "#f1f5f9",   # slate-100
        "TEXT_SECONDARY": "#cbd5e1", # slate-300
        "TEXT_MUTED": "#94a3b8",     # slate-400
        "TEXT_ON_PRIMARY": "#0f172a",

        # 边框（深色）
        "BORDER": "#334155",
        "BORDER_STRONG": "#475569",

        # 状态色
        "SUCCESS": "#34d399",
        "WARNING": "#fbbf24",
        "ERROR": "#f87171",

        # 状态栏
        "STATUS_BG": "#020617",      # slate-950
        "STATUS_FG": "#cbd5e1",
        "STATUS_ERROR_FG": "#fca5a5",
        "STATUS_WARN_FG": "#fcd34d",
    },
}

# 当前主题（默认 light）
CURRENT_THEME_NAME = "light"
THEME = THEMES[CURRENT_THEME_NAME]


# ---------- 主题管理 ----------
def get_theme_names():
    """返回所有可用主题名。"""
    return list(THEMES.keys())


def get_current_theme_name():
    return CURRENT_THEME_NAME


def _set_module_globals(theme_dict):
    """把主题字典的 key 注入到模块全局变量（向后兼容旧 from ui.theme import X）。"""
    import sys
    mod = sys.modules[__name__]
    for k, v in theme_dict.items():
        setattr(mod, k, v)


def apply_theme(name):
    """
    切换主题，并更新模块全局变量。
    返回旧主题名（用于回调比对）。
    """
    global CURRENT_THEME_NAME, THEME
    if name not in THEMES:
        raise ValueError(f"未知主题：{name}（可选：{list(THEMES.keys())}）")
    old = CURRENT_THEME_NAME
    CURRENT_THEME_NAME = name
    THEME = THEMES[name]
    _set_module_globals(THEME)
    return old


def apply_global_style(root):
    """把 tk 的 optiondatabase 设为现代化默认值（颜色随当前主题）。"""
    try:
        from tkinter import ttk
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    root.option_add("*Font", FONT_BODY)
    root.option_add("*TCombobox*Font", FONT_INPUT)
    root.option_add("*Text.font", FONT_BODY)
    root.option_add("*Entry.font", FONT_INPUT)
    root.option_add("*Button.font", FONT_BUTTON)
    root.option_add("*Label.font", FONT_BODY)
    root.configure(bg=BG_APP)


# 初始化：让旧代码 `from ui.theme import BG_CARD` 仍然能拿到 light 主题的值
_set_module_globals(THEME)


# ============================================================
# 旧版常量别名（保持向后兼容）
# ============================================================
# 注意：下面这些是 v18 及更早的固定值。
# v19 起，每次 apply_theme() 会重新写入同名属性，因此下面的赋值只在首次
# import 时生效，作为兜底默认。运行中的代码请通过 THEME[...] 读取最新值。
BG_APP = THEMES["light"]["BG_APP"]
BG_CARD = THEMES["light"]["BG_CARD"]
BG_HOVER = THEMES["light"]["BG_HOVER"]
BG_DISABLED = THEMES["light"]["BG_DISABLED"]
GRAD_TOP_FROM = THEMES["light"]["GRAD_TOP_FROM"]
GRAD_TOP_TO = THEMES["light"]["GRAD_TOP_TO"]
PRIMARY = THEMES["light"]["PRIMARY"]
PRIMARY_DARK = THEMES["light"]["PRIMARY_DARK"]
PRIMARY_LIGHT = THEMES["light"]["PRIMARY_LIGHT"]
ACCENT = THEMES["light"]["ACCENT"]
ACCENT_DARK = THEMES["light"]["ACCENT_DARK"]
TEXT_PRIMARY = THEMES["light"]["TEXT_PRIMARY"]
TEXT_SECONDARY = THEMES["light"]["TEXT_SECONDARY"]
TEXT_MUTED = THEMES["light"]["TEXT_MUTED"]
TEXT_ON_PRIMARY = THEMES["light"]["TEXT_ON_PRIMARY"]
BORDER = THEMES["light"]["BORDER"]
BORDER_STRONG = THEMES["light"]["BORDER_STRONG"]
SUCCESS = THEMES["light"]["SUCCESS"]
WARNING = THEMES["light"]["WARNING"]
ERROR = THEMES["light"]["ERROR"]