"""AI 模型设置对话框——v7。

从用户视角出发，做以下事：
1. 去掉重复的大标题（窗口标题栏已经有 AI 模型设置了，里面别再来一次）
2. 段控件两段严格等宽——用 grid weight=1，而不是塞内容撑开
3. 必填提示严格放在对应字段下面，不错位
4. 输入框左右内边距严格一致
5. 字段宽度吃满外层——只保留一个内边距常量
6. 底部按钮排版清晰，主按钮显眼但文字清楚
7. 中间内容用 Canvas + Scrollbar 包裹，永远不会出现按钮被挡
"""

import threading
import tkinter as tk
from tkinter import ttk

from ui.theme import (
    BG_APP,
    BG_CARD,
    BG_HOVER,
    BORDER,
    BORDER_STRONG,
    PRIMARY,
    PRIMARY_DARK,
    ACCENT,
    ACCENT_DARK,
    SUCCESS,
    WARNING,
    ERROR,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_INPUT,
    FONT_BUTTON,
    FONT_BUTTON_SMALL,
    FONT_HERO_SUB,
    FONT_SMALL,
)
from core.config import (
    load_settings, save_settings, get_provider, get_api_key,
    get_base_url, get_model, get_settings_raw,
)
from ui.theme import get_theme_names, get_current_theme_name

PLATFORMS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "通义千问 (Qwen)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "智谱 GLM": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "月之暗面 (Kimi)": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "自定义": {
        "base_url": "",
        "model": "",
    },
}


# =================================================================
# 段控件 — 两段严格等宽
# =================================================================
class SegmentedToggle(tk.Frame):
    """两个并排按钮，用 grid weight=1 让两段严格等宽。"""

    def __init__(self, parent, options, command=None, height=58, **kw):
        super().__init__(parent, bg=BG_APP, **kw)
        self._command = command
        self._value = None
        self._buttons = {}

        # 两段严格等宽
        self.grid_columnconfigure(0, weight=1, uniform="seg")
        self.grid_columnconfigure(1, weight=1, uniform="seg")

        for i, (val, label) in enumerate(options):
            # 外层 wrapper，保证 cell 等宽
            wrap = tk.Frame(self, bg=BG_APP)
            wrap.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0))

            btn = tk.Label(
                wrap, text=label,
                font=FONT_BUTTON,
                bg=BG_CARD, fg=TEXT_SECONDARY,
                pady=18, cursor="hand2",
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=PRIMARY,
                bd=0,
            )
            btn.pack(fill=tk.BOTH, expand=True)
            btn.bind("<Button-1>", lambda e, v=val: self._set(v))
            btn.bind("<Enter>", lambda e, b=btn: self._on_hover(b, True))
            btn.bind("<Leave>", lambda e, b=btn: self._on_hover(b, False))

            self._buttons[val] = btn

        self._render()

    def _on_hover(self, btn, entering):
        # 不高亮当前选中项，hover 只对未选中的生效
        if btn is self._buttons.get(self._value):
            return
        btn.config(bg=BG_HOVER if entering else BG_CARD)

    def _set(self, val):
        if val == self._value:
            return
        self._value = val
        self._render()
        if self._command:
            self._command(val)

    def set(self, val):
        self._value = val
        self._render()

    def get(self):
        return self._value

    def _render(self):
        for v, btn in self._buttons.items():
            if v == self._value:
                btn.config(bg=PRIMARY, fg="white", highlightbackground=PRIMARY)
            else:
                btn.config(bg=BG_CARD, fg=TEXT_SECONDARY, highlightbackground=BORDER)


# =================================================================
# 帮助对话框
# =================================================================
class HelpDialog(tk.Toplevel):
    """使用说明弹窗——v7：紧凑、列宽一致、不绕字。"""

    W = 760
    H = 720

    def __init__(self, parent):
        super().__init__(parent)
        self.title("使用说明")
        self.configure(bg=BG_APP)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # 居中
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 200, 200, 900, 700
        x = px + (pw - self.W) // 2
        y = py + (ph - self.H) // 2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # 顶部装饰条
        tk.Frame(self, bg=PRIMARY, height=6).pack(side=tk.TOP, fill=tk.X)

        # 标题
        tk.Label(
            self, text="使用说明",
            font=("Microsoft YaHei UI", 18, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.TOP, pady=(18, 10))

        # 内容
        body = tk.Frame(self, bg=BG_APP)
        body.pack(fill=tk.BOTH, expand=True, padx=36, pady=(0, 8))

        sections = [
            ("两种模式",
             "【离线 Mock】无需联网、无需 Key，使用内置的课程数据快速生成计划，适合先看效果。\n"
             "【在线 LLM】需要联网 + API Key，会调用真实大模型生成更个性化的方案。"),
            ("怎么用",
             "1. 选择运行模式（默认 Mock，可随时切换）\n"
             "2. LLM 模式下选平台、填 API Key（点\"显示\"看明文）\n"
             "3. 默认 URL 和模型会自动填好，一般不用改\n"
             "4. 点\"测试连接\"验证 Key 是否可用（可选）\n"
             "5. 点\"保存设置\"完成"),
            ("关于 API Key",
             "只保存在本机配置文件 settings.json，不会上传到任何地方。\n"
             "DeepSeek 注册送额度，新用户够用一段时间；详细价格看各平台官网。"),
            ("关于学习计划",
             "根据你输入的目标（学什么、花多久、每天几小时）生成大纲 + 日历。\n"
             "可以多次生成对比，挑一个最合适的保存。"),
        ]
        for title, body_text in sections:
            tk.Label(
                body, text=title, anchor="w",
                font=("Microsoft YaHei UI", 13, "bold"),
                bg=BG_APP, fg=PRIMARY,
            ).pack(fill=tk.X, pady=(8, 4))
            tk.Label(
                body, text=body_text, anchor="w", justify="left",
                font=FONT_BODY,
                bg=BG_APP, fg=TEXT_SECONDARY,
                wraplength=self.W - 72,
            ).pack(fill=tk.X)

        # 底部固定按钮
        btn_bar = tk.Frame(self, bg=BG_CARD, height=68)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        btn_bar.pack_propagate(False)
        tk.Frame(btn_bar, bg=BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            btn_bar, text="    知道了    ",
            font=FONT_BUTTON,
            bg=PRIMARY, fg="white",
            padx=18, pady=10, cursor="hand2",
            highlightthickness=0, bd=0,
        ).pack(side=tk.RIGHT, padx=(0, 20), pady=10)
        ok_lbl = btn_bar.winfo_children()[-1]
        ok_lbl.bind("<Button-1>", lambda e: self.destroy())
        ok_lbl.bind("<Enter>", lambda e: ok_lbl.config(bg=PRIMARY_DARK))
        ok_lbl.bind("<Leave>", lambda e: ok_lbl.config(bg=PRIMARY))


# =================================================================
# 主对话框
# =================================================================
class SettingsDialog(tk.Toplevel):
    """AI 模型设置弹窗——v7。

    改进点（人视角）：
    - **窗口更大了** (920 x 920)，URL 字段能完整显示
    - 中间内容用 **Canvas + 滚动条** 包裹，永远不会被底部按钮栏遮住
    - 「测试连接」按钮和状态文字必显示完整
    - 顶部只放细分隔线 + 左上图标 + 右上说明，不再放重复的大标题
    - 段控件两段严格等宽
    - 标签占固定宽度，输入框吃满剩余空间，左右都对齐
    - 必填提示紧贴字段下方，不错位
    - 字段之间间距统一（24px），不忽大忽小
    - 底部按钮固定可见
    """

    # 对话框尺寸：保证所有内容自然显示，不挤不空
    W = 1040
    H = 1040

    # 标签列宽度，让所有标签对齐
    LABEL_W = 160
    SIDE_PAD = 56  # 左右内边距统一

    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.title("AI 模型设置")
        self.configure(bg=BG_APP)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_saved = on_saved
        self._current = load_settings()
        self._init_ttk_style()

        # 居中（如果父窗口更小，居中到屏幕）
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 200, 200, 1100, 800
        # 防止计算后位置超出屏幕
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = px + max(0, (pw - self.W) // 2)
        y = py + max(0, (ph - self.H) // 2)
        x = min(x, max(0, sw - self.W))
        y = min(y, max(0, sh - self.H))
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.minsize(self.W, self.H)
        self.maxsize(self.W, self.H)  # 因为里面已经滚动，不允许拉伸乱布局

        self._build_ui()
        self._load_values()

    def _init_ttk_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Modern.TCombobox",
            fieldbackground=BG_CARD, background=BG_CARD,
            foreground=TEXT_PRIMARY, borderwidth=0,
            relief="flat", arrowsize=18,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", BG_CARD), ("disabled", BG_HOVER)],
            foreground=[("readonly", TEXT_PRIMARY), ("disabled", TEXT_MUTED)],
            selectbackground=[("readonly", BG_CARD)],
            selectforeground=[("readonly", TEXT_PRIMARY)],
        )

    # ==========================================================
    def _build_ui(self):
        # ---- 1. 底部固定按钮栏（先 pack 最底）----
        btn_bar = tk.Frame(self, bg=BG_CARD, height=80)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        btn_bar.pack_propagate(False)

        tk.Frame(btn_bar, bg=BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        btn_row = tk.Frame(btn_bar, bg=BG_CARD)
        btn_row.pack(side=tk.TOP, fill=tk.X, padx=self.SIDE_PAD, pady=14)

        # 左侧：使用说明
        help_lbl = tk.Label(
            btn_row, text="  ?  使用说明  ",
            font=FONT_BODY,
            bg=BG_HOVER, fg=TEXT_PRIMARY,
            padx=18, pady=8, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        help_lbl.pack(side=tk.LEFT)
        help_lbl.bind("<Button-1>", lambda e: HelpDialog(self))
        help_lbl.bind("<Enter>", lambda e: help_lbl.config(bg=BORDER))
        help_lbl.bind("<Leave>", lambda e: help_lbl.config(bg=BG_HOVER))

        # 右侧：取消 + 保存
        cancel_lbl = tk.Label(
            btn_row, text="  取消  ",
            font=FONT_BUTTON,
            bg=BG_CARD, fg=TEXT_SECONDARY,
            padx=22, pady=8, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        cancel_lbl.pack(side=tk.RIGHT)
        cancel_lbl.bind("<Button-1>", lambda e: self.destroy())
        cancel_lbl.bind("<Enter>", lambda e: cancel_lbl.config(bg=BG_HOVER))
        cancel_lbl.bind("<Leave>", lambda e: cancel_lbl.config(bg=BG_CARD))

        self.save_lbl = tk.Label(
            btn_row, text="    保存设置    ",
            font=FONT_BUTTON,
            bg=PRIMARY, fg="white",
            padx=20, pady=8, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.save_lbl.pack(side=tk.RIGHT, padx=(0, 14))
        self.save_lbl.bind("<Button-1>", lambda e: self._on_save())
        self.save_lbl.bind("<Enter>", lambda e: self.save_lbl.config(bg=PRIMARY_DARK))
        self.save_lbl.bind("<Leave>", lambda e: self.save_lbl.config(bg=PRIMARY))

        # ---- 2. 顶部条：简洁，不放重复标题 ----
        top_bar = tk.Frame(self, bg=PRIMARY, height=6)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        # ---- 3. 中间内容区：Canvas + Scrollbar ----
        body_holder = tk.Frame(self, bg=BG_APP)
        body_holder.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(
            body_holder,
            bg=BG_APP, highlightthickness=0, bd=0,
        )
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(
            body_holder,
            orient="vertical",
            command=canvas.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        # 内嵌 frame
        content = tk.Frame(canvas, bg=BG_APP)
        canvas_window = canvas.create_window(
            (0, 0), window=content, anchor="nw",
        )

        # 更新 scrollregion
        def _on_content_config(_):
            canvas.configure(scrollregion=canvas.bbox("all"))

        content.bind("<Configure>", _on_content_config)

        # 让内嵌 frame 跟 canvas 同宽
        def _on_canvas_config(e):
            canvas.itemconfigure(canvas_window, width=e.width)

        canvas.bind("<Configure>", _on_canvas_config)

        # 鼠标滚轮
        def _on_mousewheel(e):
            # Windows / macOS
            delta = -1 if e.delta > 0 else 1
            if e.delta == 0:
                # Linux (Button-4 / Button-5)
                if e.num == 4:
                    delta = -1
                elif e.num == 5:
                    delta = 1
            canvas.yview_scroll(delta, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        # 内部 padding
        pad = tk.Frame(content, bg=BG_APP)
        pad.pack(fill=tk.X, padx=self.SIDE_PAD, pady=(32, 32))

        # --- 分组 1：运行模式 ---
        mode_block = tk.Frame(pad, bg=BG_APP)
        mode_block.pack(fill=tk.X, pady=(0, 8))

        # 标签 + 副标题（一列）
        mode_title = tk.Frame(mode_block, bg=BG_APP)
        mode_title.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            mode_title, text="运行模式",
            font=("Microsoft YaHei UI", 14, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        self.mode_tip = tk.Label(
            mode_title, text="",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_MUTED,
        )
        self.mode_tip.pack(side=tk.LEFT, padx=(18, 0), pady=(6, 0))

        # 段控件全宽
        self.mode_toggle = SegmentedToggle(
            mode_block,
            options=[("mock", "离线 Mock 模式"), ("llm", "在线 LLM 模式")],
            command=self._on_mode_change,
        )
        self.mode_toggle.pack(fill=tk.X, pady=(0, 6))

        # --- 分隔条 ---
        tk.Frame(pad, bg=BORDER, height=1).pack(fill=tk.X, pady=24)

        # --- 分组 2：LLM 配置 ---
        self.llm_block = tk.Frame(pad, bg=BG_APP)
        self.llm_block.pack(fill=tk.X)

        # 标题
        llm_title_row = tk.Frame(self.llm_block, bg=BG_APP)
        llm_title_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            llm_title_row, text="模型配置",
            font=("Microsoft YaHei UI", 14, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)
        tk.Label(
            llm_title_row, text="（可提前配置；切到 LLM 模式后生效）",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(14, 0), pady=(8, 0))

        # ---- 表单 ----
        form = tk.Frame(self.llm_block, bg=BG_APP)
        form.pack(fill=tk.X)
        # 列 0 标签固定宽度；列 1 字段吃满剩余宽度
        form.grid_columnconfigure(0, minsize=self.LABEL_W)
        form.grid_columnconfigure(1, weight=1)

        # 行高统一
        ROW_PAD = 14

        # 平台
        tk.Label(
            form, text="平台",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(8, ROW_PAD))
        self.platform_var = tk.StringVar()
        self.platform_combo = ttk.Combobox(
            form,
            textvariable=self.platform_var,
            values=list(PLATFORMS.keys()),
            state="readonly",
            style="Modern.TCombobox",
            font=FONT_INPUT,
            height=10,
        )
        self.platform_combo.grid(row=0, column=1, sticky="ew", pady=(0, ROW_PAD), ipady=10)
        self.platform_combo.bind("<<ComboboxSelected>>", self._on_platform_change)

        # API Key
        tk.Label(
            form, text="API Key",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(8, 4))
        key_row = tk.Frame(form, bg=BG_APP)
        key_row.grid(row=1, column=1, sticky="ew", pady=(0, 4))
        key_row.grid_columnconfigure(0, weight=1)
        self.key_entry = tk.Entry(
            key_row, font=FONT_INPUT, show="·",
            relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=PRIMARY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            disabledbackground=BG_HOVER, disabledforeground=TEXT_MUTED,
            insertwidth=2,
        )
        self.key_entry.grid(row=0, column=0, sticky="ew", ipady=10, padx=(0, 8))
        self.show_var = tk.BooleanVar(value=False)
        self.show_btn = tk.Label(
            key_row, text=" 显示 ",
            font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            padx=18, pady=8, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        self.show_btn.grid(row=0, column=1)
        self.show_btn.bind("<Button-1>", lambda e: self._toggle_key_visibility())
        self.show_btn.bind("<Enter>", lambda e: self.show_btn.config(bg=BG_HOVER))
        self.show_btn.bind("<Leave>", lambda e: self.show_btn.config(bg=BG_CARD))

        # 必填提示（紧贴 API Key 下方，不错位）
        self.required_label = tk.Label(
            form, text="* 必填（LLM 模式下需要）",
            font=FONT_SMALL,
            bg=BG_APP, fg=ERROR, anchor="w",
        )
        self.required_label.grid(row=2, column=1, sticky="w", pady=(0, ROW_PAD))

        # Base URL
        tk.Label(
            form, text="API Base URL",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=3, column=0, sticky="w", padx=(0, 16), pady=(8, ROW_PAD))
        self.url_entry = tk.Entry(
            form, font=FONT_INPUT,
            relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=PRIMARY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            disabledbackground=BG_HOVER, disabledforeground=TEXT_MUTED,
            insertwidth=2,
        )
        self.url_entry.grid(row=3, column=1, sticky="ew", pady=(0, ROW_PAD), ipady=10)

        # 模型名称
        tk.Label(
            form, text="模型名称",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=4, column=0, sticky="w", padx=(0, 16), pady=(8, ROW_PAD))
        self.model_entry = tk.Entry(
            form, font=FONT_INPUT,
            relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=PRIMARY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            disabledbackground=BG_HOVER, disabledforeground=TEXT_MUTED,
            insertwidth=2,
        )
        self.model_entry.grid(row=4, column=1, sticky="ew", pady=(0, ROW_PAD), ipady=10)

        # 测试行（独立一行 + 状态文字）—— 一定不会被遮
        test_row = tk.Frame(form, bg=BG_APP)
        test_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(20, 0))

        self.test_btn = tk.Label(
            test_row, text="  测试连接  ",
            font=FONT_BUTTON,
            bg=ACCENT, fg="white",
            padx=18, pady=8, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.test_btn.pack(side=tk.LEFT)
        self.test_btn.bind("<Button-1>", lambda e: self._on_test())
        self.test_btn.bind("<Enter>", lambda e: self._on_test_hover(True))
        self.test_btn.bind("<Leave>", lambda e: self._on_test_hover(False))

        self.test_label = tk.Label(
            test_row, text="",
            font=FONT_BODY, bg=BG_APP, fg=TEXT_MUTED,
        )
        self.test_label.pack(side=tk.LEFT, padx=(18, 0), pady=(14, 14))

        # ---- 分隔条 ----
        tk.Frame(pad, bg=BORDER, height=1).pack(fill=tk.X, pady=24)

        # --- 分组 3：外观 ---
        self._build_appearance_block(pad)

        # ---- 分隔条 ---
        tk.Frame(pad, bg=BORDER, height=1).pack(fill=tk.X, pady=24)

        # --- 分组 4：安全与存储（v19 第三梯队 #10 / #12 的可视化）---
        self._build_security_block(pad)

        # ---- 预留底部说明卡 ----
        tip_card = tk.Frame(pad, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        tip_card.pack(fill=tk.X, pady=(28, 0))

        tk.Label(
            tip_card, text="💡 小提示",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(14, 4))

        tips = [
            "DeepSeek / OpenAI / 通义千问 / 智谱 GLM / 月之暗面都兼容 OpenAI 格式",
            "选「自定义」可以填自己的 URL 和模型名",
            "API Key 只保存在本机 settings.json，不联网传输",
        ]
        for t in tips:
            tk.Label(
                tip_card, text=f"  •  {t}",
                font=FONT_BODY,
                bg=BG_CARD, fg=TEXT_SECONDARY,
                anchor="w", justify="left",
            ).pack(fill=tk.X, padx=18, pady=2)

        tk.Frame(tip_card, bg=BG_CARD, height=14).pack()  # 底部留白

    # ==========================================================
    # 安全与存储（v19 第三梯队 #10 加密 / #12 缓存与节流）
    # ==========================================================
    def _build_security_block(self, parent):
        """把「看不见的安全」变成看得见的状态，答辩时可以当场指出来。

        展示三件事：
        1. API Key 是否已用 AES-GCM 加密落盘（tools/keypad.py）
        2. 请求节流还剩多少次额度（tools/rate_limiter.py）
        3. 结果缓存有多少条，可一键清空（tools/cache_store.py）
        """
        block = tk.Frame(parent, bg=BG_APP)
        block.pack(fill=tk.X, pady=(0, 8))

        title_row = tk.Frame(block, bg=BG_APP)
        title_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            title_row, text="🔐 安全与存储",
            font=("Microsoft YaHei UI", 14, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)
        tk.Label(
            title_row, text="（本机生效，不上传云端）",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(14, 0), pady=(8, 0))

        card = tk.Frame(
            block, bg=BG_CARD,
            highlightthickness=1, highlightbackground=BORDER,
        )
        card.pack(fill=tk.X)

        inner = tk.Frame(card, bg=BG_CARD)
        inner.pack(fill=tk.X, padx=18, pady=14)
        inner.grid_columnconfigure(1, weight=1)

        self.sec_values = {}
        rows = [
            ("api_key_storage", "API Key 存储"),
            ("api_key_masked", "当前 Key"),
            ("rate_limit", "请求节流"),
            ("cache", "结果缓存"),
        ]
        for i, (key, label) in enumerate(rows):
            tk.Label(
                inner, text=label,
                font=FONT_BODY,
                bg=BG_CARD, fg=TEXT_SECONDARY,
                anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=(0, 20), pady=4)

            val = tk.Label(
                inner, text="…",
                font=FONT_BODY_BOLD,
                bg=BG_CARD, fg=TEXT_PRIMARY,
                anchor="w", justify=tk.LEFT,
            )
            val.grid(row=i, column=1, sticky="ew", pady=4)
            self.sec_values[key] = val

        # 操作行：刷新 + 清空缓存
        ops = tk.Frame(card, bg=BG_CARD)
        ops.pack(fill=tk.X, padx=18, pady=(0, 14))

        self.refresh_sec_lbl = tk.Label(
            ops, text="  刷新状态  ",
            font=FONT_BODY,
            bg=BG_HOVER, fg=TEXT_PRIMARY,
            padx=16, pady=7, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        self.refresh_sec_lbl.pack(side=tk.LEFT)
        self.refresh_sec_lbl.bind("<Button-1>", lambda e: self._refresh_security())
        self.refresh_sec_lbl.bind(
            "<Enter>", lambda e: self.refresh_sec_lbl.config(bg=BORDER),
        )
        self.refresh_sec_lbl.bind(
            "<Leave>", lambda e: self.refresh_sec_lbl.config(bg=BG_HOVER),
        )

        self.clear_cache_lbl = tk.Label(
            ops, text="  🗑 清空缓存  ",
            font=FONT_BODY,
            bg=BG_HOVER, fg=WARNING,
            padx=16, pady=7, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        self.clear_cache_lbl.pack(side=tk.LEFT, padx=(10, 0))
        self.clear_cache_lbl.bind("<Button-1>", lambda e: self._on_clear_cache())
        self.clear_cache_lbl.bind(
            "<Enter>", lambda e: self.clear_cache_lbl.config(bg=BORDER),
        )
        self.clear_cache_lbl.bind(
            "<Leave>", lambda e: self.clear_cache_lbl.config(bg=BG_HOVER),
        )

        self.sec_hint = tk.Label(
            ops, text="",
            font=FONT_SMALL,
            bg=BG_CARD, fg=TEXT_MUTED,
            anchor="w",
        )
        self.sec_hint.pack(side=tk.LEFT, padx=(14, 0))

        self._refresh_security()

    def _refresh_security(self):
        """刷新安全与存储面板的实时状态。每一项都独立兜底，互不影响。"""
        vals = getattr(self, "sec_values", None)
        if not vals:
            return

        # ---- 1. 加密能力 + Key 落盘形态 ----
        crypto_ok = False
        encrypted = False
        masked = ""
        try:
            from tools.keypad import has_crypto_lib, is_encrypted, mask_key
            crypto_ok = bool(has_crypto_lib())
            stored = (get_settings_raw() or {}).get("api_key", "") or ""
            encrypted = bool(stored) and bool(is_encrypted(stored))
            plain = (self._current or {}).get("api_key", "") or ""
            from_env = False
            if not plain:
                # 设置里没有，可能来自环境变量 LLM_API_KEY
                try:
                    from core.config import get_api_key as _get_key
                    plain = _get_key() or ""
                    from_env = bool(plain)
                except Exception:
                    plain = ""
            masked = mask_key(plain) if plain else ""
            if from_env:
                masked = f"{masked}（来自环境变量）"
        except Exception:
            pass

        if not stored and not plain:
            vals["api_key_storage"].config(text="— 尚未设置 API Key", fg=TEXT_MUTED)
        elif encrypted and crypto_ok:
            vals["api_key_storage"].config(text="✅ AES-GCM 加密存储", fg=SUCCESS)
        elif encrypted:
            vals["api_key_storage"].config(
                text="⚠ 已加密（当前环境缺少加密库，无法校验）", fg=WARNING,
            )
        elif crypto_ok:
            vals["api_key_storage"].config(text="⚠ 明文存储（保存后自动加密）", fg=WARNING)
        else:
            vals["api_key_storage"].config(
                text="⚠ 未安装 cryptography，使用兜底模式", fg=WARNING,
            )

        vals["api_key_masked"].config(text=masked or "（未设置）")

        # ---- 2. 限流状态 ----
        try:
            from tools.rate_limiter import status as _rl_status
            st = _rl_status() or {}
            used = st.get("used", 0)
            mx = st.get("max", 10)
            win = st.get("window_sec", 60)
            if used >= mx:
                wait = st.get("retry_after", 0)
                vals["rate_limit"].config(
                    text=f"⛔ 已达上限 {used}/{mx}，需等 {wait:.0f}s", fg=WARNING,
                )
            else:
                vals["rate_limit"].config(
                    text=f"✅ {used}/{mx} 次（{win:.0f} 秒滑动窗口）", fg=SUCCESS,
                )
        except Exception as e:
            vals["rate_limit"].config(text=f"（不可用：{e}）", fg=TEXT_MUTED)

        # ---- 3. 缓存状态 ----
        try:
            import time as _time
            from tools.cache_store import cache_stats, DEFAULT_TTL, MAX_ENTRIES
            stats = cache_stats() or {}
            n = int(stats.get("count", 0) or 0)
            ttl_h = max(1, int(round(DEFAULT_TTL / 3600.0)))
            if n == 0:
                vals["cache"].config(
                    text=f"📦 空（上限 {MAX_ENTRIES} 条，{ttl_h}h 过期）",
                    fg=TEXT_MUTED,
                )
            else:
                newest = stats.get("newest", 0) or 0
                age = max(0.0, _time.time() - newest) if newest else 0.0
                if age < 60:
                    age_txt = "刚刚"
                elif age < 3600:
                    age_txt = f"{age / 60:.0f} 分钟前"
                else:
                    age_txt = f"{age / 3600:.1f} 小时前"
                vals["cache"].config(
                    text=f"📦 {n}/{MAX_ENTRIES} 条 · {ttl_h}h 过期 · 最近 {age_txt}",
                    fg=SUCCESS if n < MAX_ENTRIES else WARNING,
                )
        except Exception as e:
            vals["cache"].config(text=f"（不可用：{e}）", fg=TEXT_MUTED)

    def _on_clear_cache(self):
        """清空方案缓存（不影响历史记录与进度）。"""
        try:
            from tools.cache_store import clear_cache
            n = clear_cache()
            if hasattr(self, "sec_hint"):
                self.sec_hint.config(text=f"已清空 {n} 条缓存", fg=SUCCESS)
        except Exception as e:
            if hasattr(self, "sec_hint"):
                self.sec_hint.config(text=f"清空失败：{e}", fg=ERROR)
        self._refresh_security()

    # ==========================================================
    def _on_test_hover(self, entering):
        # mock 模式下，测试按钮被禁用为灰色
        is_llm = self.mode_toggle.get() == "llm"
        if not is_llm:
            self.test_btn.config(bg=BG_HOVER, fg=TEXT_MUTED)
            return
        self.test_btn.config(bg=ACCENT_DARK if entering else ACCENT)

    # ==========================================================
    # 外观（主题）
    # ==========================================================
    def _build_appearance_block(self, parent):
        block = tk.Frame(parent, bg=BG_APP)
        block.pack(fill=tk.X, pady=(0, 8))

        title_row = tk.Frame(block, bg=BG_APP)
        title_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            title_row, text="外观",
            font=("Microsoft YaHei UI", 14, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        self.theme_tip = tk.Label(
            title_row, text="",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_MUTED,
        )
        self.theme_tip.pack(side=tk.LEFT, padx=(18, 0), pady=(6, 0))

        # 主题段控件（浅色 / 深色）
        self.theme_toggle = SegmentedToggle(
            block,
            options=[
                ("light", "☀️  浅色"),
                ("dark", "🌙  深色"),
            ],
            command=self._on_theme_change,
        )
        self.theme_toggle.pack(fill=tk.X, pady=(0, 6))

        # 当前显示一行（实时预览）
        self.theme_preview = tk.Frame(
            block, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER,
        )
        self.theme_preview.pack(fill=tk.X, pady=(8, 0))
        self.theme_preview_lbl = tk.Label(
            self.theme_preview, text="",
            font=FONT_BODY, bg=BG_CARD, fg=TEXT_SECONDARY,
            anchor="w", padx=14, pady=10,
        )
        self.theme_preview_lbl.pack(fill=tk.X)

        self._refresh_theme_preview()

        # ---- 分隔条 ----
        tk.Frame(block, bg=BORDER, height=1).pack(fill=tk.X, pady=(20, 16))

        # ---- 语言切换（v19 第三梯队） ----
        self._build_language_row(block)

    def _build_language_row(self, parent):
        """构建语言切换段控件。"""
        try:
            from i18n import set_language as i18n_set, get_available_languages
            langs = get_available_languages()
        except Exception:
            i18n_set = None
            langs = ["zh", "en"]

        # 当前语言
        try:
            from i18n import get_language
            cur_lang = get_language()
        except Exception:
            cur_lang = "zh"

        # 行：标签 + 段控件
        title_row = tk.Frame(parent, bg=BG_APP)
        title_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            title_row, text="🌐 语言",
            font=("Microsoft YaHei UI", 13, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        self.lang_tip = tk.Label(
            title_row, text="（切换后立即生效）",
            font=FONT_BODY,
            bg=BG_APP, fg=TEXT_MUTED,
        )
        self.lang_tip.pack(side=tk.LEFT, padx=(14, 0), pady=(6, 6))

        # 段控件：中文 / English
        self.lang_toggle = SegmentedToggle(
            parent,
            options=[
                ("zh", "中文"),
                ("en", "English"),
            ],
            command=self._on_language_change,
        )
        self.lang_toggle.pack(fill=tk.X, pady=(0, 6))
        if cur_lang in langs:
            self.lang_toggle.set(cur_lang)

    def _on_language_change(self, lang):
        """语言切换：调用 i18n.set_language。"""
        try:
            from i18n import set_language
            set_language(lang)
        except Exception as e:
            if hasattr(self, "lang_tip"):
                self.lang_tip.config(text=f"切换失败：{e}", fg=ERROR)
            return
        if hasattr(self, "lang_tip"):
            self.lang_tip.config(text="✓ 语言已切换，部分文字需重启后完全生效", fg=TEXT_MUTED)

    def _on_theme_change(self, name):
        """主题切换：实时应用 + 更新预览。"""
        try:
            from ui.theme import apply_theme
            apply_theme(name)
        except Exception as e:
            self.theme_tip.config(text=f"切换失败：{e}", fg=ERROR)
            return
        # 同步刷新本弹窗的颜色（标签 / 卡片背景）
        self._refresh_settings_colors()
        self._refresh_theme_preview()
        self.theme_tip.config(
            text="✓ 已切换，重启生效（部分组件需重建）", fg=TEXT_MUTED,
        )

    def _refresh_theme_preview(self):
        """刷新外观预览条。"""
        from ui.theme import THEMES, CURRENT_THEME_NAME
        cur = CURRENT_THEME_NAME
        d = THEMES.get(cur, {})
        # 文字说明
        sample = (
            f"当前：{cur}    "
            f"背景 #{d.get('BG_APP', '')[1:]}    "
            f"卡片 #{d.get('BG_CARD', '')[1:]}    "
            f"主色 #{d.get('PRIMARY', '')[1:]}"
        )
        self.theme_preview_lbl.config(text=sample)

    def _refresh_settings_colors(self):
        """把本弹窗的关键组件颜色切到新主题。"""
        # 设置弹窗的核心容器颜色
        try:
            self.configure(bg=BG_APP)
        except Exception:
            pass
        # 如果你已经构建过 self._build_ui，那 pad 还没引用，只能用 winfo_children 递归
        # 简化处理：刷新 label 上的 fg
        for lbl in self.winfo_children():
            try:
                if isinstance(lbl, tk.Label):
                    lbl.config(bg=BG_APP)
            except Exception:
                pass
        # 刷新 Card / Frame 等子组件（在 mainloop 时才生效）

    # ==========================================================
    def _load_values(self):
        # 关键：用统一的 getter（settings.json > .env > 环境变量）
        # 而不是直接 load_settings —— 否则 .env 配的 LLM 模式会被忽略
        provider = get_provider()
        api_key = get_api_key()
        base_url = get_base_url()
        model = get_model()

        self.mode_toggle.set(provider)
        self.key_entry.delete(0, tk.END)
        self.key_entry.insert(0, api_key)
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, base_url)
        self.model_entry.delete(0, tk.END)
        self.model_entry.insert(0, model)

        # 默认匹配平台
        matched = "自定义"
        for name, preset in PLATFORMS.items():
            if preset["base_url"] == base_url and preset["model"] == model:
                matched = name
                break
            # 部分匹配 base_url 也能识别
            if preset["base_url"] and preset["base_url"] in base_url:
                matched = name
        self.platform_var.set(matched)

        # 重要：先 set 平台再触发 mode_change，否则 Combo 还没匹配上
        self._on_mode_change()

    def _on_mode_change(self):
        mode = self.mode_toggle.get()
        is_llm = mode == "llm"

        # 模式提示
        if is_llm:
            self.mode_tip.config(text="调用在线大模型 API")
        else:
            self.mode_tip.config(text="使用内置示例数据，离线可用")

        # 字段在两种模式下都可编辑（方便提前配置 LLM 信息）
        # 只有"测试连接"按钮在 mock 模式下禁用（需要真发请求）
        self.platform_combo.config(state="readonly")
        for entry in (self.key_entry, self.url_entry, self.model_entry):
            entry.config(state=tk.NORMAL)
        # show_btn（显示/隐藏 Key）始终可用
        self.show_btn.config(fg=TEXT_PRIMARY, cursor="hand2")
        # test_btn 在 mock 模式下禁用
        if is_llm:
            self.test_btn.config(bg=ACCENT, fg="white", cursor="hand2")
        else:
            self.test_btn.config(bg=BG_HOVER, fg=TEXT_MUTED, cursor="arrow")

    def _on_platform_change(self, _=None):
        name = self.platform_var.get()
        preset = PLATFORMS.get(name, {})
        if name != "自定义":
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, preset.get("base_url", ""))
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, preset.get("model", ""))

    def _toggle_key_visibility(self):
        # 显示/隐藏 Key 在任何模式下都可用（mock 模式也可以查看/隐藏 Key）
        self.show_var.set(not self.show_var.get())
        if self.show_var.get():
            self.key_entry.config(show="")
            self.show_btn.config(text=" 隐藏 ")
        else:
            self.key_entry.config(show="·")
            self.show_btn.config(text=" 显示 ")

    # ==========================================================
    def _on_test(self):
        if self.mode_toggle.get() != "llm":
            self.test_label.config(text="Mock 模式下无需测试连接", fg=TEXT_MUTED)
            return
        api_key = self.key_entry.get().strip()
        base_url = self.url_entry.get().strip()
        model = self.model_entry.get().strip()

        if not api_key:
            self.test_label.config(text="请先填 API Key", fg=ERROR)
            return
        if not base_url:
            self.test_label.config(text="请先填 Base URL", fg=ERROR)
            return

        self.test_btn.config(bg=BG_HOVER, fg=TEXT_MUTED, text=" 测试中… ", cursor="arrow")
        self.test_label.config(text="连接中…", fg=TEXT_MUTED)

        def worker():
            try:
                import requests
                url = f"{base_url.rstrip('/')}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    self.after(0, lambda: self.test_label.config(
                        text="✓ 连接成功", fg=SUCCESS,
                    ))
                else:
                    err = resp.text[:100]
                    self.after(0, lambda: self.test_label.config(
                        text=f"✗ 失败 {resp.status_code}: {err}",
                        fg=ERROR,
                    ))
            except Exception as exc:
                self.after(0, lambda: self.test_label.config(
                    text=f"✗ {exc}",
                    fg=ERROR,
                ))
            finally:
                self.after(0, lambda: self.test_btn.config(
                    bg=ACCENT, fg="white", text="  测试连接  ", cursor="hand2",
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_save(self):
        provider = self.mode_toggle.get()
        api_key = self.key_entry.get().strip()
        base_url = self.url_entry.get().strip()
        model = self.model_entry.get().strip()
        data = {
            "provider": provider,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
        }
        try:
            save_settings(provider=provider, api_key=api_key, base_url=base_url, model=model)
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        if self._on_saved:
            try:
                self._on_saved(data)
            except Exception:
                pass
        self.destroy()
