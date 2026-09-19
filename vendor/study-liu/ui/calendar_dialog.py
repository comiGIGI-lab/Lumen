"""学习日历导出弹窗 —— v19 第三梯队 #13-A 的 UI 接线。

把主窗口刚生成的方案（self._last_result）导出成 .ics 文件，
可直接导入 Google Calendar / 苹果日历 / Outlook。

设计要点：
- 主题安全：颜色在**创建控件时**从 ui.theme 读取，而不是模块导入时快照，
  这样用户切换深色模式后新开的弹窗配色是正确的（settings_dialog 的旧写法会拿旧色）
- 零网络、零后台线程：纯本地文件写入，毫秒级完成，不需要进度条
- 失败不崩：任何异常都落到状态行提示
"""

from __future__ import annotations

import datetime as _dt
import os
import tkinter as tk

from i18n import t as _t


def _tv(name: str, default: str = "#000000") -> str:
    """运行时读取主题色（跟随主题切换，避免导入期快照）。"""
    try:
        from ui import theme
        return getattr(theme, name, default)
    except Exception:
        return default


def _font(name: str, default=None):
    try:
        from ui import theme
        return getattr(theme, name, default or ("Microsoft YaHei UI", 12))
    except Exception:
        return default or ("Microsoft YaHei UI", 12)


class CalendarDialog(tk.Toplevel):
    """📅 学习日历导出弹窗。"""

    W = 620
    H = 430

    def __init__(self, parent, result=None, on_done=None):
        super().__init__(parent)
        self._result = result or {}
        self._on_done = on_done

        self.title(_t("CALENDAR_TITLE"))
        self.configure(bg=_tv("BG_APP"))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._center(parent)
        self._build()
        self._refresh_preview()

    # ----------------------------------------------------------
    def _center(self, parent):
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px, py, pw, ph = 200, 200, 1100, 760
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(max(0, px + (pw - self.W) // 2), max(0, sw - self.W))
        y = min(max(0, py + (ph - self.H) // 2), max(0, sh - self.H))
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

    # ----------------------------------------------------------
    def _build(self):
        tk.Frame(self, bg=_tv("PRIMARY"), height=6).pack(side=tk.TOP, fill=tk.X)

        body = tk.Frame(self, bg=_tv("BG_APP"))
        body.pack(fill=tk.BOTH, expand=True, padx=28, pady=(20, 8))

        tk.Label(
            body, text=_t("CALENDAR_TITLE"),
            font=("Microsoft YaHei UI", 15, "bold"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
            anchor="w",
        ).pack(fill=tk.X)

        tk.Label(
            body, text=_t("CALENDAR_TIP"),
            font=_font("FONT_BODY"), justify=tk.LEFT, wraplength=self.W - 70,
            bg=_tv("BG_APP"), fg=_tv("TEXT_SECONDARY"),
            anchor="w",
        ).pack(fill=tk.X, pady=(8, 16))

        # ---- 开始日期 ----
        row = tk.Frame(body, bg=_tv("BG_APP"))
        row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            row, text=_t("CALENDAR_START_DATE"),
            font=_font("FONT_BODY"), width=10, anchor="w",
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
        ).pack(side=tk.LEFT)

        self.start_var = tk.StringVar(value=_dt.date.today().isoformat())
        entry = tk.Entry(
            row, textvariable=self.start_var,
            font=_font("FONT_INPUT"),
            relief=tk.FLAT, bd=0, insertwidth=2,
            highlightthickness=1,
            highlightbackground=_tv("BORDER"),
            highlightcolor=_tv("PRIMARY"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_PRIMARY"),
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        entry.bind("<KeyRelease>", lambda e: self._refresh_preview())

        tk.Label(
            row, text="YYYY-MM-DD",
            font=_font("FONT_SMALL"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_MUTED"),
        ).pack(side=tk.LEFT)

        # ---- 预览卡片 ----
        card = tk.Frame(
            body, bg=_tv("BG_CARD"),
            highlightthickness=1, highlightbackground=_tv("BORDER"),
        )
        card.pack(fill=tk.X, pady=(6, 0))
        self.preview_lbl = tk.Label(
            card, text="", font=_font("FONT_BODY"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_SECONDARY"),
            anchor="w", justify=tk.LEFT, wraplength=self.W - 100,
            padx=16, pady=14,
        )
        self.preview_lbl.pack(fill=tk.X)

        # ---- 状态行 ----
        self.status_lbl = tk.Label(
            body, text="", font=_font("FONT_SMALL"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_MUTED"),
            anchor="w", justify=tk.LEFT, wraplength=self.W - 70,
        )
        self.status_lbl.pack(fill=tk.X, pady=(12, 0))

        # ---- 底部按钮栏 ----
        bar = tk.Frame(self, bg=_tv("BG_CARD"), height=72)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=_tv("BORDER"), height=1).pack(side=tk.TOP, fill=tk.X)

        close_lbl = tk.Label(
            bar, text=_t("BTN_CANCEL"), font=_font("FONT_BUTTON"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_SECONDARY"),
            padx=20, pady=9, cursor="hand2",
            highlightthickness=1, highlightbackground=_tv("BORDER"), bd=0,
        )
        close_lbl.pack(side=tk.RIGHT, padx=(0, 20), pady=14)
        close_lbl.bind("<Button-1>", lambda e: self.destroy())

        self.export_lbl = tk.Label(
            bar, text=_t("CALENDAR_BTN_EXPORT"), font=_font("FONT_BUTTON"),
            bg=_tv("PRIMARY"), fg="white",
            padx=20, pady=9, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.export_lbl.pack(side=tk.RIGHT, padx=(0, 12), pady=14)
        self.export_lbl.bind("<Button-1>", lambda e: self._on_export())
        self.export_lbl.bind(
            "<Enter>", lambda e: self.export_lbl.config(bg=_tv("PRIMARY_DARK")),
        )
        self.export_lbl.bind(
            "<Leave>", lambda e: self.export_lbl.config(bg=_tv("PRIMARY")),
        )

    # ----------------------------------------------------------
    # 预览 / 导出
    # ----------------------------------------------------------
    def _plan(self):
        plan = self._result.get("plan") if isinstance(self._result, dict) else None
        return plan if isinstance(plan, list) else []

    def _refresh_preview(self):
        n = len(self._plan())
        start = (self.start_var.get() or "").strip()
        if not self._result or n == 0:
            self.preview_lbl.config(
                text=_t("CALENDAR_NO_PLAN"), fg=_tv("WARNING"),
            )
            self.export_lbl.config(bg=_tv("BG_HOVER"), fg=_tv("TEXT_MUTED"),
                                   cursor="arrow")
            return
        self.preview_lbl.config(
            text=_t("CALENDAR_PREVIEW", n=n, start=start or _dt.date.today().isoformat()),
            fg=_tv("TEXT_SECONDARY"),
        )
        self.export_lbl.config(bg=_tv("PRIMARY"), fg="white", cursor="hand2")

    def _set_status(self, text, color=None):
        self.status_lbl.config(text=text, fg=color or _tv("TEXT_MUTED"))

    def _on_export(self):
        if not self._plan():
            self._set_status(_t("CALENDAR_NO_PLAN"), _tv("WARNING"))
            return
        try:
            from tkinter import filedialog
            from core.paths import data_path
            from tools.calendar_export import (
                export_plan_to_ics,
                suggest_ics_filename,
            )

            course = (self._result.get("course") or "").strip() or "study"
            default_name = suggest_ics_filename(course)
            out_dir = data_path("exports")
            os.makedirs(out_dir, exist_ok=True)

            path = filedialog.asksaveasfilename(
                parent=self,
                title=_t("CALENDAR_TITLE"),
                defaultextension=".ics",
                initialfile=default_name,
                initialdir=out_dir,
                filetypes=[("iCalendar", "*.ics"), ("All Files", "*.*")],
            )
            if not path:
                self._set_status(_t("CALENDAR_STATUS_CANCEL"))
                return

            start = (self.start_var.get() or "").strip() or None
            written = export_plan_to_ics(self._result, path, start_date=start)
            n = len(self._plan())
            self._set_status(
                _t("CALENDAR_STATUS_OK", n=n, path=written), _tv("SUCCESS"),
            )
            if self._on_done:
                try:
                    self._on_done(n, written)
                except Exception:
                    pass
        except Exception as e:
            self._set_status(_t("CALENDAR_STATUS_FAIL", msg=e), _tv("ERROR"))
