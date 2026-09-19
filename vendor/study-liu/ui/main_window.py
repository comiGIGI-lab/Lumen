"""主窗口：可滚动布局，Hero + 模式栏 + 输入 + 三栏结果 + 问答 + 状态栏。

v17 改造：
- 主内容区改为 Canvas 可滚动布局，不再压缩任何区域
- 状态栏固定在窗口底部，不参与滚动
- 各区域使用自然高度，窗口不够大时通过滚轮上下移动
- 鼠标滚轮全局生效；聊天历史区有自己的滚动条不抢事件
"""

import os
import threading
import tkinter as tk
from tkinter import scrolledtext

from core.intent import parse_intent
from core.agent_loop import run_plan_pipeline, run_chat_pipeline
from core.config import get_mode_label
from ui.collect_dialog import CollectDialog
from tools.user_profile import (
    DEFAULT_PROFILE,
    LEVELS,
    DAILY_HOURS,
    GOALS,
    load_profile,
    save_profile,
)
from ui.widgets import (
    GradientHeader,
    Card,
    ResultPanel,
    PrimaryButton,
    AccentButton,
    PlaceholderEntry,
)
from ui.theme import (
    BG_APP,
    BG_CARD,
    BORDER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_LIGHT,
    ACCENT,
    ACCENT_DARK,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    WARNING,
    ERROR,
    FONT_BODY,
    FONT_BODY_LARGE,
    FONT_BODY_BOLD,
    FONT_STATUS,
    FONT_BUTTON,
    FONT_HERO_TITLE,
    FONT_HERO_SUB,
    FONT_SMALL,
    FONT_INPUT,
    FONT_TINY,
)

APP_TITLE = "study-liu"


def _t(key: str, **kwargs):
    """i18n 取词（main_window 内部简写），找不到回退到 key。"""
    try:
        from i18n import t
        return t(key, **kwargs)
    except Exception:
        return key


class MainWindow:
    """study-liu 学习智能助手主窗口。"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1240x760")
        self.root.minsize(1100, 440)
        self.root.configure(bg=BG_APP)
        self.root.option_add("*Font", FONT_BODY)
        self.root.option_add("*Text.font", FONT_BODY_LARGE)

        # Root: 2 rows — scrollable content + fixed status bar
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, minsize=36)
        self.root.grid_columnconfigure(0, weight=1)

        # Scrollable canvas (holds all content)
        self._build_scroll_area()

        # All content sections live inside scroll_frame
        self._build_header()
        self._build_mode_bar()
        self._build_input_card()
        self._build_result_grid()
        self._build_chat_card()

        # Status bar stays fixed at bottom (not scrolled)
        self._build_status_bar()

    # ==========================================================
    # 滚动容器
    # ==========================================================
    def _build_scroll_area(self):
        """创建可滚动的主内容区（Canvas + Scrollbar + inner Frame）。"""
        self.scroll_canvas = tk.Canvas(
            self.root,
            bg=BG_APP,
            highlightthickness=0,
            bd=0,
        )
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self.vbar = tk.Scrollbar(
            self.root,
            orient="vertical",
            command=self.scroll_canvas.yview,
        )
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.scroll_canvas.configure(yscrollcommand=self.vbar.set)

        # inner frame — all content goes here
        self.scroll_frame = tk.Frame(self.scroll_canvas, bg=BG_APP)
        self._scroll_win_id = self.scroll_canvas.create_window(
            0, 0,
            window=self.scroll_frame,
            anchor="nw",
        )

        # 当内容尺寸变化时，更新滚动范围
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all"),
            ),
        )

        # 当 canvas 宽度变化时，让 inner frame 跟随
        self.scroll_canvas.bind(
            "<Configure>",
            self._on_canvas_resize,
        )

        # 鼠标滚轮
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

        # inner frame grid
        self.scroll_frame.grid_columnconfigure(0, weight=1)

    def _on_canvas_resize(self, event):
        """Canvas 宽度变化时，让内部 frame 同步宽度。"""
        self.scroll_canvas.itemconfig(
            self._scroll_win_id,
            width=event.width,
        )

    def _on_mousewheel(self, event):
        """鼠标滚轮：滚动主内容区。"""
        # chat_history 有自己的滚动条，不抢事件
        if event.widget is getattr(self, "chat_history", None):
            return
        if event.num == 4:
            self.scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.scroll_canvas.yview_scroll(1, "units")
        else:
            # Windows / Mac
            delta = -1 * (event.delta // 120)
            self.scroll_canvas.yview_scroll(delta, "units")

    # ==========================================================
    # 区域构建
    # ==========================================================
    def _build_header(self):
        self.header = GradientHeader(
            self.scroll_frame,
            title="study-liu",
            subtitle="输入课程名 · 一键生成大纲 + 资源 + 个性化计划（按截止日定天数）",
        )
        self.header.grid(row=0, column=0, sticky="ew")

    def _build_mode_bar(self):
        """模式状态栏：当前模式 + 设置按钮。"""
        wrap = tk.Frame(self.scroll_frame, bg=BG_APP)
        wrap.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))

        bar = tk.Frame(
            wrap,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=PRIMARY,
            bd=0,
        )
        bar.pack(fill=tk.X, ipady=10)

        label_text, mode = get_mode_label()
        icon = "📦" if mode == "mock" else "🤖"
        mode_color = "#6366f1" if mode == "mock" else "#06b6d4"

        self.mode_label = tk.Label(
            bar, text=f"  {icon}  当前模式：{label_text}",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=mode_color,
        )
        self.mode_label.pack(side=tk.LEFT, padx=(16, 0))

        tip_text = "（内置数据，无需 API）" if mode == "mock" else "（调用在线大模型 API）"
        self.mode_tip = tk.Label(
            bar, text=tip_text,
            font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_MUTED,
        )
        self.mode_tip.pack(side=tk.LEFT, padx=(10, 0))

        # 📚 我的笔记 入口
        self.kb_btn = AccentButton(
            bar, text="📚 我的笔记",
            command=self._open_knowledge_dialog,
        )
        self.kb_btn.pack(side=tk.RIGHT, padx=(0, 8), pady=3)

        # 📷 截图讲解 入口（OCR + AI 讲解，v19 第三梯队 #13-B）
        self.screenshot_btn = AccentButton(
            bar, text=_t("BTN_SCREENSHOT"),
            command=self._open_screenshot_dialog,
        )
        self.screenshot_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=3)

        # 📅 学习日历 导出（.ics，v19 第三梯队 #13-A）：生成完成后才能用
        self.calendar_btn = AccentButton(
            bar, text=_t("BTN_CALENDAR"),
            command=self._open_calendar_dialog,
        )
        self.calendar_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=3)
        self.calendar_btn.config(state=tk.DISABLED)

        # 📥 导出方案 按钮：生成完成后才能用
        self.export_btn = AccentButton(
            bar, text="📥 导出方案",
            command=self._export_plan_markdown,
        )
        self.export_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=3)
        self.export_btn.config(state=tk.DISABLED)
        self._last_result = None   # 最近一次 run_plan_pipeline 的完整结果

        # 📜 历史 按钮：打开历史记录弹窗
        self.history_btn = AccentButton(
            bar, text="📜 历史",
            command=self._open_history_dialog,
        )
        self.history_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=3)

        self.settings_btn = tk.Button(
            bar, text="⚙  设置模式",
            font=FONT_BUTTON,
            bg=PRIMARY, fg="white",
            activebackground=PRIMARY_DARK, activeforeground="white",
            relief=tk.FLAT, bd=0,
            padx=22, pady=8, cursor="hand2",
            command=self._open_settings,
        )
        self.settings_btn.pack(side=tk.RIGHT, padx=(0, 16), pady=3)
        self.settings_btn.bind("<Enter>", lambda e: self.settings_btn.config(bg=PRIMARY_DARK))
        self.settings_btn.bind("<Leave>", lambda e: self.settings_btn.config(bg=PRIMARY))

    def _build_input_card(self):
        wrap = tk.Frame(self.scroll_frame, bg=BG_APP)
        wrap.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 8))
        card = Card(wrap, padding=16)
        card.pack(fill=tk.X)

        inner = card.inner
        inner.grid_columnconfigure(1, weight=1)

        tk.Label(
            inner, text="📖  想学什么课程？",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 14))

        self.course_entry = PlaceholderEntry(
            inner, placeholder="例如：计算机系统、Python 入门、线性代数…",
        )
        self.course_entry.grid(row=0, column=1, sticky="ew", ipady=10, padx=(0, 12))
        self.course_entry.bind("<Return>", lambda e: self.on_generate())

        self.generate_btn = PrimaryButton(
            inner, text="✨  生成方案", command=self.on_generate,
        )
        self.generate_btn.grid(row=0, column=2, sticky="e")

        tk.Label(
            inner, text="💡 提示：回车键也能直接生成",
            font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_MUTED,
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))

        # ---- 行 2-3：用户画像（4 个 Combobox）----
        self._build_profile_row(inner)

    def _build_profile_row(self, parent):
        """构建用户画像行：水平 / 日时间 / 目标 / 截止日。"""
        # 标题
        tk.Label(
            parent, text="🎯  你是哪类学习者？",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=TEXT_PRIMARY,
        ).grid(row=2, column=0, sticky="w", padx=(0, 14), pady=(10, 0))

        # 加载持久化画像
        cur = load_profile()

        # 4 个 Combobox 容器
        from tkinter import ttk
        combo_row = tk.Frame(parent, bg=BG_CARD)
        combo_row.grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0),
        )
        for c in range(4):
            combo_row.grid_columnconfigure(c, weight=1, uniform="profile")

        self.profile_vars = {
            "level": tk.StringVar(value=cur.get("level", "入门")),
            "daily_hours": tk.StringVar(value=cur.get("daily_hours", "2h")),
            "goal": tk.StringVar(value=cur.get("goal", "兴趣")),
            "deadline": tk.StringVar(value=cur.get("deadline", "")),
        }

        def _make_combo(col, label, key, values):
            wrap = tk.Frame(combo_row, bg=BG_CARD)
            wrap.grid(row=0, column=col, sticky="ew", padx=4)
            wrap.grid_columnconfigure(0, weight=1)
            tk.Label(
                wrap, text=label, font=FONT_SMALL,
                bg=BG_CARD, fg=TEXT_MUTED,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            cb = ttk.Combobox(
                wrap,
                textvariable=self.profile_vars[key],
                values=values,
                state="normal",
                font=FONT_INPUT,
            )
            cb.grid(row=1, column=0, sticky="ew", ipady=6, pady=(2, 0))
            cb.bind("<<ComboboxSelected>>", lambda e: self._save_profile_from_ui())
            cb.bind("<FocusOut>", lambda e: self._save_profile_from_ui())
            return cb

        _make_combo(0, "水平", "level", LEVELS)
        _make_combo(1, "每日时长", "daily_hours", DAILY_HOURS)
        _make_combo(2, "目标", "goal", GOALS)
        # 截止日：动态近期候选（+7/+14/+30/+90 天）+ 自由输入
        # v19.1：候选按今天动态生成，选得越近计划越短，截止日真正生效
        from datetime import date as _date, timedelta as _td
        _today = _date.today()
        _deadline_values = [""] + [
            (_today + _td(days=d)).strftime("%Y-%m-%d") for d in (7, 14, 30, 90)
        ]
        _make_combo(3, "截止日（YYYY-MM-DD）", "deadline", _deadline_values)

    def _save_profile_from_ui(self):
        """从 UI 控件读取画像并持久化；截止日变化时给出计划天数反馈。"""
        try:
            profile = {k: v.get() for k, v in self.profile_vars.items()}
            save_profile(profile)
        except Exception as e:
            print(f"[WARN] save profile failed: {e}")
            return
        # v19.1：截止日反馈 —— 让用户立刻看到"截止日 → 计划天数"的映射
        try:
            dl = profile.get("deadline", "").strip()
            if dl:
                from datetime import datetime as _dt, date as _date
                from tools.user_profile import suggest_plan_length
                n = suggest_plan_length(profile)
                days_left = (_dt.strptime(dl, "%Y-%m-%d").date() - _date.today()).days
                if days_left > 0:
                    self._set_status(f"📅 截止 {dl}（剩 {days_left} 天）· 将生成 {n} 天计划")
                else:
                    self._set_status(f"📅 截止 {dl} 已到期 · 将生成 {n} 天冲刺计划")
        except Exception:
            pass

    def _get_profile(self):
        """从 UI 控件读取画像（不持久化）。"""
        try:
            profile = {k: v.get() for k, v in self.profile_vars.items()}
            return profile
        except Exception:
            return dict(DEFAULT_PROFILE)

    def _build_result_grid(self):
        wrap = tk.Frame(self.scroll_frame, bg=BG_APP)
        wrap.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 8))
        wrap.grid_columnconfigure(0, weight=1, uniform="col")
        wrap.grid_columnconfigure(1, weight=1, uniform="col")
        wrap.grid_columnconfigure(2, weight=1, uniform="col")
        wrap.grid_rowconfigure(0, minsize=340)

        self.outline_panel = ResultPanel(wrap, "课程大纲")
        self.outline_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.resource_panel = ResultPanel(wrap, "推荐资源")
        self.resource_panel.grid(row=0, column=1, sticky="nsew", padx=3)
        self.plan_panel = ResultPanel(wrap, "学习计划")
        self.plan_panel.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

    def _build_chat_card(self):
        """课程问答卡片。"""
        wrap = tk.Frame(self.scroll_frame, bg=BG_APP)
        wrap.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 8))
        card = Card(wrap, padding=14)
        card.pack(fill=tk.BOTH, expand=True)

        inner = card.inner
        inner.grid_columnconfigure(1, weight=1)
        inner.grid_rowconfigure(2, minsize=220)   # 历史区固定高度

        # ---- row 0: 标题 + 输入框 + 按钮 ----
        tk.Label(
            inner, text="💬  课程问答",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 14))

        self.chat_entry = PlaceholderEntry(
            inner,
            placeholder="例如：第 3 章讲什么？零基础能学会吗？推荐什么参考书？",
        )
        self.chat_entry.grid(row=0, column=1, sticky="ew", ipady=8, padx=(0, 12))
        self.chat_entry.bind("<Return>", lambda e: self.on_chat())

        self.chat_btn = AccentButton(inner, text="提问", command=self.on_chat)
        self.chat_btn.grid(row=0, column=2, sticky="e")

        # ---- 思考动画标签：紧贴按钮右侧，点动显示 AI 正在工作 ----
        self.thinking_indicator = tk.Label(
            inner, text="",
            font=FONT_BODY_BOLD,
            bg=BG_CARD, fg=WARNING,
        )
        self.thinking_indicator.grid(row=0, column=3, sticky="e", padx=(10, 0))

        # ---- row 1: 提示 + 清空按钮 ----
        hint_row = tk.Frame(inner, bg=BG_CARD)
        hint_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        hint_row.grid_columnconfigure(0, weight=1)

        self.chat_hint_var = tk.StringVar(
            value="📌 先点上方「生成方案」得到课程，再在这里问细节；"
                  "AI 会先查知识库再回答。"
        )
        tk.Label(
            hint_row, textvariable=self.chat_hint_var,
            font=FONT_SMALL,
            bg=BG_CARD, fg=TEXT_SECONDARY,
            anchor="w", justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="ew")

        self.clear_btn = tk.Label(
            hint_row, text="  🗑  清空对话  ",
            font=FONT_SMALL,
            bg=BG_CARD, fg=TEXT_MUTED,
            cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.clear_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.clear_btn.bind("<Button-1>", lambda e: self._clear_chat_history())
        self.clear_btn.bind(
            "<Enter>",
            lambda e: self.clear_btn.config(fg=ERROR),
        )
        self.clear_btn.bind(
            "<Leave>",
            lambda e: self.clear_btn.config(fg=TEXT_MUTED),
        )

        # ⭐ 收藏最后一条 AI 回答（默认禁用，_show_answer 完成时启用）
        self.collect_btn = tk.Label(
            hint_row, text="  ⭐ 收藏最后回答  ",
            font=FONT_SMALL,
            bg=BG_CARD, fg=ACCENT,
            cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.collect_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.collect_btn.bind("<Button-1>", lambda e: self._open_collect_dialog())
        self.collect_btn.bind(
            "<Enter>",
            lambda e: self.collect_btn.config(fg=ACCENT_DARK),
        )
        self.collect_btn.bind(
            "<Leave>",
            lambda e: self.collect_btn.config(fg=ACCENT),
        )
        self.collect_btn.bind(
            "<Button-1>",
            lambda e: self.collect_btn.config(fg=ACCENT_DARK),  # 视觉反馈
            add="+",
        )
        self.collect_btn.config(state=tk.DISABLED)
        self._last_answer = ""

        # ---- row 2: 对话历史区（可滚动） ----
        self.chat_history = scrolledtext.ScrolledText(
            inner,
            wrap=tk.WORD,
            font=FONT_BODY,
            bg="#f8fafc",
            fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PRIMARY_LIGHT,
            padx=12, pady=10,
            spacing1=2, spacing3=2,
            height=10,
        )
        self.chat_history.grid(
            row=2, column=0, columnspan=3, sticky="nsew",
            pady=(8, 0),
        )
        # 标签样式
        self.chat_history.tag_configure(
            "user", foreground=PRIMARY, font=FONT_BODY_BOLD,
        )
        self.chat_history.tag_configure("ai", foreground=TEXT_PRIMARY)
        self.chat_history.tag_configure(
            "src", foreground=TEXT_MUTED, font=FONT_SMALL,
        )
        self.chat_history.tag_configure(
            "thinking", foreground=WARNING, font=FONT_BODY,
        )
        self.chat_history.config(state=tk.DISABLED)

        # 欢迎语
        self._append_chat(
            "🤖 ",
            "你好！先在上面输入课程名，点「生成方案」得到课程大纲，"
            "然后在这里问任何细节都可以。我会先查课程知识库，"
            "找不到再调用在线大模型（需切到 LLM 模式）。",
            "ai",
        )

        # 多轮对话上下文（消息列表），最大 8 条，超过自动滑窗
        self._chat_msgs = []
        self._chat_msgs_max = 8

    def _append_chat(self, prefix, content, tag):
        """把一条聊天记录写进历史区（prefix + content 占一行）。"""
        self.chat_history.config(state=tk.NORMAL)
        if prefix:
            self.chat_history.insert(tk.END, prefix, tag)
        self.chat_history.insert(tk.END, content + "\n\n", tag)
        self.chat_history.see(tk.END)
        self.chat_history.config(state=tk.DISABLED)

    def _clear_chat_history(self):
        """清空对话历史区 + 清空多轮上下文。"""
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.config(state=tk.DISABLED)
        self._chat_msgs = []
        self._append_chat(
            "🤖 ",
            "对话已清空。继续问吧～",
            "ai",
        )

    def _start_thinking_animation(self):
        """启动思考动画：标签文字的点在 1~3 之间循环。"""
        self._thinking_dots = 0
        self._thinking_after_id = None
        self._tick_thinking_animation()

    def _tick_thinking_animation(self):
        """每 400ms 更新一次思考指示器。"""
        if not hasattr(self, "thinking_indicator"):
            return
        self._thinking_dots = (self._thinking_dots % 3) + 1
        self.thinking_indicator.config(
            text="🤔 AI 思考中" + "." * self._thinking_dots,
        )
        self._thinking_after_id = self.root.after(
            400, self._tick_thinking_animation,
        )

    def _stop_thinking_animation(self):
        """停止思考动画并清空标签。"""
        if getattr(self, "_thinking_after_id", None):
            try:
                self.root.after_cancel(self._thinking_after_id)
            except Exception:
                pass
            self._thinking_after_id = None
        if hasattr(self, "thinking_indicator"):
            self.thinking_indicator.config(text="")

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg="#1e293b", height=36)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(value="● 就绪  ·  输入课程名，点击「生成方案」开始")
        self.status_label = tk.Label(
            bar, textvariable=self.status_var,
            font=FONT_STATUS,
            bg="#1e293b", fg="#cbd5e1",
            anchor=tk.W, padx=20,
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.Y)

    # ==========================================================
    # 设置
    # ==========================================================
    def _open_settings(self):
        from ui.settings_dialog import SettingsDialog
        SettingsDialog(self.root, on_saved=self._refresh_mode_bar)

    # ----------------------------------------------------------
    # 知识库
    # ----------------------------------------------------------
    def _open_knowledge_dialog(self):
        """单例打开 📚 我的笔记 面板；已打开则前置。"""
        from ui.knowledge_dialog import KnowledgeDialog
        existing = getattr(self, "_kb_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass
        self._kb_dialog = KnowledgeDialog(
            self.root, on_change=self._on_knowledge_changed,
        )

    def _on_knowledge_changed(self):
        """知识库增删后状态栏提示。"""
        self._set_status("📚 知识库已更新")

    # ----------------------------------------------------------
    # 问答 ⭐ 收藏
    # ----------------------------------------------------------
    def _open_collect_dialog(self):
        """打开收藏弹窗，把最后一条 AI 回答收藏进知识库。"""
        if not getattr(self, "_last_answer", ""):
            self._set_status("⚠ 还没有可收藏的回答", warn=True)
            return
        CollectDialog(
            self.root,
            content=self._last_answer,
            on_saved=self._on_collected,
        )

    def _on_collected(self, note_id, title):
        self._set_status(f"⭐ 已收藏「{title}」(id {note_id})")

    # ----------------------------------------------------------
    # 历史记录 + 进度
    # ----------------------------------------------------------
    def _open_history_dialog(self):
        """打开历史记录弹窗；选中后重新加载到三栏结果。"""
        from ui.history_dialog import HistoryDialog
        # 单例
        existing = getattr(self, "_history_dialog", None)
        if existing is not None:
            try:
                if existing.win.winfo_exists():
                    existing.win.lift()
                    existing.win.focus_force()
                    return
            except Exception:
                pass
        self._history_dialog = HistoryDialog(
            self.root, on_open=self._display_result,
        )

    def _toggle_progress_item(self, course, kind, index, done):
        """勾选/取消勾选某章节或某天任务。"""
        try:
            from tools.progress_store import set_done
            ok = set_done(course, kind, index, done)
            if ok:
                d, t, _ = self._get_stats(course)
                self._set_status(
                    f"✓ 进度已更新「{course}」({d}/{t})"
                )
        except Exception as e:
            self._set_status(f"✗ 进度更新失败：{e}", error=True)

    def _get_stats(self, course):
        try:
            from tools.progress_store import get_stats
            return get_stats(course)
        except Exception:
            return 0, 0, 0.0

    # ----------------------------------------------------------
    # 方案导出 Markdown
    # ----------------------------------------------------------
    def _export_plan_markdown(self):
        """把当前方案的 Markdown 写入用户选择的文件。"""
        if not getattr(self, "_last_result", None):
            self._set_status("⚠ 还没有生成方案，请先生成", warn=True)
            return
        try:
            from tkinter import filedialog
            from tools.markdown_export import (
                render_plan_markdown,
                suggest_filename,
            )
            course = self._last_result.get("course") or "未命名课程"
            default_name = suggest_filename(course)
            # 默认目录：data/exports/（打包兼容，见 core/paths.py）
            from core.paths import data_path
            data_dir = data_path("exports")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
            init_path = os.path.join(data_dir, default_name)
            path = filedialog.asksaveasfilename(
                parent=self.root,
                title="导出方案为 Markdown",
                defaultextension=".md",
                initialfile=default_name,
                initialdir=data_dir,
                filetypes=[("Markdown", "*.md"), ("All Files", "*.*")],
            )
            if not path:
                self._set_status("ℹ 已取消导出")
                return
            content = render_plan_markdown(self._last_result, course=course)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._set_status(f"📥 已导出方案到 {path}")
        except Exception as e:
            self._set_status(f"✗ 导出失败：{e}", error=True)

    # ----------------------------------------------------------
    # 学习日历导出（.ics）
    # ----------------------------------------------------------
    def _open_calendar_dialog(self):
        """打开 📅 学习日历弹窗，把当前方案导出为 .ics 日历文件。"""
        if not getattr(self, "_last_result", None):
            self._set_status("⚠ 还没有生成方案，请先生成", warn=True)
            return
        from ui.calendar_dialog import CalendarDialog
        existing = getattr(self, "_calendar_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass
        self._calendar_dialog = CalendarDialog(
            self.root,
            result=self._last_result,
            on_done=self._on_calendar_exported,
        )

    def _on_calendar_exported(self, n, path):
        """日历导出成功后的状态栏反馈。"""
        self._set_status(f"📅 已导出 {n} 天学习日程到 {path}")

    # ----------------------------------------------------------
    # 截图讲解（OCR + LLM）
    # ----------------------------------------------------------
    def _open_screenshot_dialog(self):
        """打开 📷 截图讲解弹窗；单例 + 已打开则前置。"""
        from ui.screenshot_dialog import ScreenshotDialog
        existing = getattr(self, "_screenshot_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass
        self._screenshot_dialog = ScreenshotDialog(
            self.root,
            course_context=getattr(self, "_current_course", "") or "",
            on_done=self._on_screenshot_explained,
        )

    def _on_screenshot_explained(self, answer):
        """截图讲解完成后的状态栏反馈。"""
        text = (answer or "").replace("\n", " ")
        self._set_status(f"📷 截图讲解完成  ·  {text[:60]}")

    def _refresh_mode_bar(self, *args, **kwargs):
        """保存设置后的回调：刷新状态栏模式文字。"""
        label_text, mode = get_mode_label()
        icon = "📦" if mode == "mock" else "🤖"
        mode_color = "#6366f1" if mode == "mock" else "#06b6d4"
        self.mode_label.config(
            text=f"  {icon}  当前模式：{label_text}",
            fg=mode_color,
        )
        tip_text = "（内置数据，无需 API）" if mode == "mock" else "（调用在线大模型 API）"
        if hasattr(self, "mode_tip"):
            self.mode_tip.config(text=tip_text)

    # ==========================================================
    # 事件
    # ==========================================================
    def on_generate(self):
        course = self.course_entry.get_real()
        if not course:
            self._set_status("⚠ 请先输入课程名", warn=True)
            return

        # 收集当前画像（顺手保存一次）
        profile = self._get_profile()
        try:
            save_profile(profile)
        except Exception:
            pass

        self.generate_btn.config(state=tk.DISABLED, text="生成中…")
        self._set_status(f"⏳ 正在为「{course}」生成方案，请稍候…")
        self.outline_panel.clear()
        self.resource_panel.clear()
        self.plan_panel.clear()

        def worker():
            try:
                result = run_plan_pipeline(course, profile=profile)
                self.root.after(0, self._display_result, result)
            except Exception as e:
                self.root.after(0, self._show_error, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _display_result(self, result):
        course = result.get("course", "")
        outline = result.get("outline", [])
        resources = result.get("resources", [])
        plan = result.get("plan", [])

        # 记录当前课程，供后续问答的 system 提示使用
        self._current_course = course
        # 缓存完整结果，供 📥 导出 / 进度勾选 / 历史记录 用
        self._last_result = result

        self.outline_panel.set_outline(outline)
        self.resource_panel.set_resources(resources)
        self.plan_panel.set_plan(plan)

        # 启用导出按钮（如果存在）
        if hasattr(self, "export_btn"):
            self.export_btn.config(state=tk.NORMAL)
        # 启用学习日历导出（同样依赖 _last_result）
        if hasattr(self, "calendar_btn"):
            self.calendar_btn.config(state=tk.NORMAL)

        # 自动写入 progress.json（同时记录到历史记录 + 初始化进度勾选）
        try:
            from tools.progress_store import save_result
            save_result(course, result)
        except Exception as e:
            # 写进度失败不影响主流程
            print(f"[WARN] save_result failed: {e}")

        self.generate_btn.config(state=tk.NORMAL, text="✨  生成方案")
        # 状态栏附加快照
        profile = result.get("profile") or {}
        profile_tip = ""
        if profile and profile.get("level"):
            from tools.user_profile import format_profile_text
            profile_tip = "  ·  " + format_profile_text(profile)
        # 命中缓存时明确提示（演示友好：能看出「没重复花额度」）
        head = "⚡ 命中缓存！" if result.get("_from_cache") else "✓ 完成！"
        self._set_status(
            f"{head}课程「{course}」方案已生成  ·  "
            f"大纲 {len(outline)} 章 / 资源 {len(resources)} 项 / 计划 {len(plan)} 天"
            + profile_tip
        )

        # v19.2：LLM 降级警告——必须让用户一眼看出"这是内置模板，不是大模型生成"
        # mock 模式不弹（界面顶部已有「📦 内置数据」角标，弹警告反而吓人）
        degraded = result.get("_degraded")
        if degraded:
            try:
                from core.config import is_mock
                if not is_mock():
                    err = degraded.get("error", "LLM 调用失败")
                    self._set_status(
                        f"⚠ LLM 不可用（{err}），本次展示的是内置模板方案，"
                        f"仅供参考——请检查网络 / API Key / 账户余额后重新生成",
                        error=True,
                    )
            except Exception:
                pass

    def _show_error(self, msg):
        self.generate_btn.config(state=tk.NORMAL, text="✨  生成方案")
        self._set_status(f"✗ 生成失败：{msg}", error=True)

    def on_chat(self):
        question = self.chat_entry.get_real()
        if not question:
            self._set_status("⚠ 请输入问题", warn=True)
            return

        try:
            intent = parse_intent(question)
        except Exception:
            intent = {"type": "chat", "course": None}

        # v18 修复：parse_intent 返回 dict {"type", "course"}
        if intent.get("type") == "generate":
            course = intent.get("course") or question
            self.course_entry._show_ph = False
            self.course_entry.delete(0, tk.END)
            self.course_entry.insert(0, course)
            self._set_status(
                "🔀 已识别为生成请求，请点上方「生成方案」（或直接回车）"
            )
            return

        # 立即把用户问题写进历史区
        self._append_chat("你：", question, "user")
        self.chat_entry.delete(0, tk.END)
        self.chat_btn.config(state=tk.DISABLED, text="思考中…")
        self._append_chat("🤖 ", "正在思考…", "thinking")
        self._start_thinking_animation()   # v18: 标题旁动画点
        self._set_status(f"⏳ 正在回答：{question[:30]}…")

        # 取当前课程上下文（如果有的话）
        course_ctx = getattr(self, "_current_course", "")

        # 取历史副本（避免子线程写一半冲突）
        history_snapshot = list(self._chat_msgs)

        def worker():
            try:
                ans = run_chat_pipeline(
                    question,
                    history=history_snapshot,
                    course_context=course_ctx or None,
                )
                self.root.after(0, self._show_answer, ans, question)
            except Exception as e:
                self.root.after(0, self._show_answer_error, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _show_answer(self, ans, question=None):
        """收到回答后：把『正在思考…』替换成真实答案，并写入多轮历史。"""
        self._stop_thinking_animation()    # v18: 停止标题旁动画
        self.chat_btn.config(state=tk.NORMAL, text="提问")
        # 删掉最后一条『正在思考…』
        self.chat_history.config(state=tk.NORMAL)
        last_thinking = None
        idx = "1.0"
        while True:
            pos = self.chat_history.search(
                "正在思考", idx, stopindex=tk.END, nocase=False,
            )
            if not pos:
                break
            last_thinking = pos
            idx = f"{pos}+1c"
        if last_thinking:
            self.chat_history.delete(last_thinking, tk.END)
        self.chat_history.config(state=tk.DISABLED)

        answer_text = ans.get("answer", "") if isinstance(ans, dict) else str(ans)
        source = ans.get("source", "") if isinstance(ans, dict) else ""

        self._append_chat("🤖 ", answer_text, "ai")
        if source:
            src_label = "（来自：知识库）" if source == "knowledge" else "（来自：在线大模型）"
            self._append_chat("", src_label, "src")

        # 把问答写进多轮上下文（滑动窗口 8 条）
        if question and answer_text and not answer_text.startswith("[LLM"):
            self._chat_msgs.append({"role": "user", "content": question})
            self._chat_msgs.append({"role": "assistant", "content": answer_text})
            # 滑动窗口裁剪
            if len(self._chat_msgs) > self._chat_msgs_max:
                self._chat_msgs = self._chat_msgs[-self._chat_msgs_max:]
            # 在历史区显示当前上下文条数
            n_turns = len(self._chat_msgs) // 2
            if hasattr(self, "chat_hint_var"):
                self.chat_hint_var.set(
                    f"📌 当前上下文：{n_turns} 轮（最多 {self._chat_msgs_max // 2} 轮）"
                )

        # 把回答记下来，供 ⭐ 收藏按钮使用
        self._last_answer = answer_text
        if hasattr(self, "collect_btn"):
            self.collect_btn.config(state=tk.NORMAL, fg=ACCENT)

        self._set_status(
            f"✓ 已回答  ·  {answer_text[:60]}".replace("\n", " "),
        )

    def _show_answer_error(self, msg):
        self._stop_thinking_animation()    # v18: 停止标题旁动画
        self.chat_btn.config(state=tk.NORMAL, text="提问")
        self.chat_history.config(state=tk.NORMAL)
        last_thinking = None
        idx = "1.0"
        while True:
            pos = self.chat_history.search("正在思考", idx, stopindex=tk.END)
            if not pos:
                break
            last_thinking = pos
            idx = f"{pos}+1c"
        if last_thinking:
            self.chat_history.delete(last_thinking, tk.END)
        self.chat_history.config(state=tk.DISABLED)

        self._append_chat("⚠ ", f"回答失败：{msg}", "ai")
        self._set_status(f"✗ 问答失败：{msg}", error=True)

    def _set_status(self, text, warn=False, error=False):
        if error:
            color = "#fca5a5"
        elif warn:
            color = "#fcd34d"
        else:
            color = "#cbd5e1"
        self.status_var.set(text)
        self.status_label.config(fg=color)

    def run(self):
        self.root.mainloop()
