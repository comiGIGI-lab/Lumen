"""📷 截图讲解弹窗 —— v19 第三梯队 #13-B 的 UI 接线。

流程：
    [选图] → OCR（后台线程）→ 识别文字（**可手工修正**）→ [让 AI 讲解] → 讲解

设计要点（针对答辩场景的稳健性）：
1. **OCR 是可选增强，不是硬依赖**：打包版为控制体积排除了 easyocr/torch，
   此时 OCR 会失败；但识别框可编辑，用户可直接粘贴文字后继续让 AI 讲解，
   功能链路依然完整可演示。
2. OCR 首次加载模型很慢（数十秒），必须放后台线程 + 界面显示「处理中…」，
   绝不能卡死 Tk 主循环。
3. 主题安全：颜色在控件创建时读取（见 calendar_dialog 的同一约定）。
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import scrolledtext

from i18n import t as _t


def _tv(name: str, default: str = "#000000") -> str:
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


class ScreenshotDialog(tk.Toplevel):
    """📷 截图讲解弹窗。"""

    W = 820
    H = 720

    def __init__(self, parent, course_context: str = "", on_done=None):
        super().__init__(parent)
        self._course = course_context or ""
        self._on_done = on_done
        self._image_path = ""
        self._ocr_result = {}
        self._busy = False

        self.title(_t("SCREENSHOT_TITLE"))
        self.configure(bg=_tv("BG_APP"))
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._calc_size()
        self._center(parent)
        self._build()
        self._check_backend()

    # ----------------------------------------------------------
    def _calc_size(self):
        """v19.1：按屏幕实际大小自适应窗口尺寸，避免小屏放不下。"""
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.W = max(560, min(820, sw - 80))
        # 预留标题栏(~40) + 任务栏(~80)
        self.H = max(460, min(720, sh - 120))

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
        self.minsize(560, 440)

    # ----------------------------------------------------------
    def _build(self):
        tk.Frame(self, bg=_tv("PRIMARY"), height=6).pack(side=tk.TOP, fill=tk.X)

        # ---- 底部按钮栏（先 pack 占住底部，保证任何屏幕下都可见）----
        bar = tk.Frame(self, bg=_tv("BG_CARD"), height=64)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=_tv("BORDER"), height=1).pack(side=tk.TOP, fill=tk.X)

        close_lbl = tk.Label(
            bar, text=_t("BTN_CANCEL"), font=_font("FONT_BUTTON"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_SECONDARY"),
            padx=20, pady=9, cursor="hand2",
            highlightthickness=1, highlightbackground=_tv("BORDER"), bd=0,
        )
        close_lbl.pack(side=tk.RIGHT, padx=(0, 20), pady=12)
        close_lbl.bind("<Button-1>", lambda e: self._on_close())

        # ---- 可滚动主体（v19.1：小屏上整个内容区可用滚轮上下划）----
        from tkinter import ttk as _ttk

        scroll_wrap = tk.Frame(self, bg=_tv("BG_APP"))
        scroll_wrap.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            scroll_wrap, bg=_tv("BG_APP"), highlightthickness=0, bd=0,
        )
        self.vbar = _ttk.Scrollbar(
            scroll_wrap, orient="vertical", command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        body = tk.Frame(
            self.canvas, bg=_tv("BG_APP"), padx=26, pady=18,
        )
        self._body_win = self.canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._body_win, width=e.width),
        )

        body.grid_columnconfigure(0, weight=1)
        # 权重只给两个文本区（可伸缩）；按钮行绝不参与压缩
        body.grid_rowconfigure(3, weight=1)
        body.grid_rowconfigure(6, weight=1)

        # ---- 顶栏：标题 + 提示 ----
        top = tk.Frame(body, bg=_tv("BG_APP"))
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(
            top, text=_t("SCREENSHOT_TITLE"),
            font=("Microsoft YaHei UI", 15, "bold"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
        ).pack(side=tk.LEFT)
        tk.Label(
            top, text=_t("SCREENSHOT_HINT"),
            font=_font("FONT_SMALL"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_MUTED"),
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(6, 0))

        # ---- 操作行 ----
        ops = tk.Frame(body, bg=_tv("BG_CARD"),
                       highlightthickness=1, highlightbackground=_tv("BORDER"))
        ops.grid(row=1, column=0, sticky="new", pady=(12, 10))
        inner = tk.Frame(ops, bg=_tv("BG_CARD"))
        inner.pack(fill=tk.X, padx=14, pady=12)

        self.load_lbl = self._mk_btn(
            inner, _t("SCREENSHOT_BTN_LOAD"), self._on_load, primary=False,
        )
        self.load_lbl.pack(side=tk.LEFT)

        self.ocr_lbl = self._mk_btn(
            inner, _t("SCREENSHOT_BTN_OCR"), self._on_ocr, primary=False,
        )
        self.ocr_lbl.pack(side=tk.LEFT, padx=(10, 0))

        self.file_lbl = tk.Label(
            inner, text="", font=_font("FONT_SMALL"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_MUTED"),
        )
        self.file_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # 附加提示输入
        hint_row = tk.Frame(ops, bg=_tv("BG_CARD"))
        hint_row.pack(fill=tk.X, padx=14, pady=(0, 12))
        self.hint_var = tk.StringVar()
        hint_entry = tk.Entry(
            hint_row, textvariable=self.hint_var,
            font=_font("FONT_BODY"), relief=tk.FLAT, bd=0, insertwidth=2,
            highlightthickness=1,
            highlightbackground=_tv("BORDER"), highlightcolor=_tv("PRIMARY"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
        )
        hint_entry.pack(fill=tk.X, ipady=7)
        _attach_placeholder(hint_entry, _t("SCREENSHOT_HINT_PH"))

        # ---- OCR 结果区 ----
        ocr_head = tk.Frame(body, bg=_tv("BG_APP"))
        ocr_head.grid(row=2, column=0, sticky="ew", pady=(4, 4))
        tk.Label(
            ocr_head, text=_t("SCREENSHOT_LABEL_OCR"),
            font=_font("FONT_BODY_BOLD"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
        ).pack(side=tk.LEFT)
        tk.Label(
            ocr_head, text=_t("SCREENSHOT_HINT_PH"),
            font=_font("FONT_TINY"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_MUTED"),
        ).pack(side=tk.LEFT, padx=(10, 0), pady=(3, 0))

        self.ocr_text = scrolledtext.ScrolledText(
            body, wrap=tk.WORD, height=7,
            font=_font("FONT_BODY"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_PRIMARY"),
            relief=tk.FLAT, bd=0, padx=10, pady=8,
            highlightthickness=1,
            highlightbackground=_tv("BORDER"), highlightcolor=_tv("PRIMARY"),
        )
        self.ocr_text.grid(row=3, column=0, sticky="nsew")

        # ---- 讲解按钮行 ----
        act = tk.Frame(body, bg=_tv("BG_APP"))
        act.grid(row=4, column=0, sticky="ew", pady=(12, 4))
        self.explain_lbl = self._mk_btn(
            act, _t("SCREENSHOT_BTN_EXPLAIN"), self._on_explain, primary=True,
        )
        self.explain_lbl.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(
            act, text="", font=_font("FONT_SMALL"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_MUTED"),
            anchor="w", justify=tk.LEFT, wraplength=self.W - 260,
        )
        self.status_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # ---- 讲解结果区 ----
        exp_head = tk.Frame(body, bg=_tv("BG_APP"))
        exp_head.grid(row=5, column=0, sticky="ew", pady=(10, 4))
        tk.Label(
            exp_head, text=_t("SCREENSHOT_LABEL_EXPLAIN"),
            font=_font("FONT_BODY_BOLD"),
            bg=_tv("BG_APP"), fg=_tv("TEXT_PRIMARY"),
        ).pack(side=tk.LEFT)

        self.answer_text = scrolledtext.ScrolledText(
            body, wrap=tk.WORD, height=9,
            font=_font("FONT_BODY"),
            bg=_tv("BG_CARD"), fg=_tv("TEXT_PRIMARY"),
            relief=tk.FLAT, bd=0, padx=10, pady=8,
            highlightthickness=1,
            highlightbackground=_tv("BORDER"), highlightcolor=_tv("PRIMARY"),
        )
        self.answer_text.grid(row=6, column=0, sticky="nsew")
        self.answer_text.config(state=tk.DISABLED)

        # ---- 滚轮支持（v19.1）：整个弹窗可上下划 ----
        self._setup_wheel()

    _WHEEL_TAG = "shotdlg_wheel"

    def _setup_wheel(self):
        """给弹窗内所有控件挂自定义 bindtag，滚轮滚动整个内容区。

        - 鼠标在文本框上：交给文本框自己滚
        - 其余位置：滚动 canvas（已到边界时吃掉事件，避免连动主窗口）
        - 关闭时只解绑自己的 tag，不影响主窗口的全局滚轮
        """

        def _on_wheel(e):
            if isinstance(e.widget, (tk.Text, tk.Listbox)):
                return
            first, last = self.canvas.yview()
            if (e.delta > 0 and first <= 0.0) or (e.delta < 0 and last >= 1.0):
                return "break"
            if abs(e.delta) >= 120:
                steps = -(e.delta // 120)
            else:
                steps = -1 if e.delta > 0 else 1
            self.canvas.yview_scroll(steps, "units")
            return "break"

        def _add_tag(widget):
            try:
                tags = list(widget.bindtags())
                if self._WHEEL_TAG not in tags:
                    tags.insert(1, self._WHEEL_TAG)
                    widget.bindtags(tuple(tags))
            except Exception:
                pass
            for child in widget.winfo_children():
                _add_tag(child)

        self.bind_class(self._WHEEL_TAG, "<MouseWheel>", _on_wheel)
        _add_tag(self)

    def _on_close(self):
        """关闭弹窗：先解绑滚轮 tag，再销毁。"""
        try:
            self.unbind_class(self._WHEEL_TAG, "<MouseWheel>")
        except Exception:
            pass
        self.destroy()

    def _mk_btn(self, parent, text, command, primary):
        bg = _tv("PRIMARY") if primary else _tv("BG_HOVER")
        fg = "white" if primary else _tv("TEXT_PRIMARY")
        # v19.1：加大按钮内边距，更好按
        lbl = tk.Label(
            parent, text=text, font=_font("FONT_BUTTON"),
            bg=bg, fg=fg, padx=26, pady=11, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        hover = _tv("PRIMARY_DARK") if primary else _tv("BORDER")
        lbl.bind("<Button-1>", lambda e: command())
        lbl.bind("<Enter>", lambda e: lbl.config(bg=hover))
        lbl.bind("<Leave>", lambda e: lbl.config(bg=bg))
        lbl._base_bg = bg
        return lbl

    # ----------------------------------------------------------
    def _check_backend(self):
        try:
            from tools.screenshot_ocr import get_backend_name, is_ocr_available
            if not is_ocr_available():
                self._set_status(_t("SCREENSHOT_NO_BACKEND"), _tv("WARNING"))
            else:
                self._set_status(f"OCR backend: {get_backend_name()}")
        except Exception as e:
            self._set_status(_t("SCREENSHOT_NO_BACKEND"), _tv("WARNING"))
            _ = e

    def _set_status(self, text, color=None):
        self.status_lbl.config(text=text, fg=color or _tv("TEXT_MUTED"))

    def _set_busy(self, busy, which=""):
        """忙碌态：禁掉两个动作按钮，避免并发/重入。"""
        self._busy = busy
        for lbl in (self.load_lbl, self.ocr_lbl, self.explain_lbl):
            lbl.config(
                bg=_tv("BG_HOVER"), fg=_tv("TEXT_MUTED"), cursor="arrow",
            )
        if not busy:
            self.load_lbl.config(bg=self.load_lbl._base_bg, fg=_tv("TEXT_PRIMARY"),
                                 cursor="hand2")
            self.ocr_lbl.config(bg=self.ocr_lbl._base_bg, fg=_tv("TEXT_PRIMARY"),
                                cursor="hand2")
            self.explain_lbl.config(bg=self.explain_lbl._base_bg, fg="white",
                                    cursor="hand2")
        elif which:
            self._set_status(which, _tv("WARNING"))

    # ----------------------------------------------------------
    # 选图
    # ----------------------------------------------------------
    def _on_load(self):
        if self._busy:
            return
        try:
            from tkinter import filedialog
            from tools.screenshot_ocr import get_supported_formats
            patterns = " ".join(f"*{e}" for e in get_supported_formats())
            path = filedialog.askopenfilename(
                parent=self,
                title=_t("SCREENSHOT_BTN_LOAD"),
                filetypes=[("Images", patterns), ("All Files", "*.*")],
            )
            if not path:
                return
            self._image_path = path
            size_txt = ""
            try:
                from PIL import Image
                with Image.open(path) as im:
                    size_txt = f"（{im.size[0]}×{im.size[1]}）"
            except Exception:
                pass
            self.file_lbl.config(text=os.path.basename(path) + size_txt)
            self._set_status(
                _t("SCREENSHOT_STATUS_LOADED",
                   filename=os.path.basename(path),
                   width=(size_txt or "?").strip("（）")),
            )
        except Exception as e:
            self._set_status(_t("SCREENSHOT_STATUS_OCR_FAIL", msg=e), _tv("ERROR"))

    # ----------------------------------------------------------
    # OCR（后台线程）
    # ----------------------------------------------------------
    def _on_ocr(self):
        if self._busy:
            return
        if not self._image_path:
            self._set_status(_t("SCREENSHOT_STATUS_NO_FILE"), _tv("WARNING"))
            return

        self._set_busy(True, _t("SCREENSHOT_RUNNING"))

        def worker(path):
            try:
                from tools.screenshot_ocr import extract_text_from_image
                res = extract_text_from_image(path)
            except Exception as e:
                res = {"text": "", "blocks": [], "backend": "error", "error": str(e)}
            self.after(0, self._on_ocr_done, res)

        threading.Thread(target=worker, args=(self._image_path,), daemon=True).start()

    def _on_ocr_done(self, res):
        self._set_busy(False)
        self._ocr_result = res if isinstance(res, dict) else {}
        text = (self._ocr_result.get("text") or "").strip()
        err = self._ocr_result.get("error")

        if text:
            self._fill_ocr(text)
            n = len([l for l in text.splitlines() if l.strip()])
            self._set_status(_t("SCREENSHOT_STATUS_OCR_DONE", n=n), _tv("SUCCESS"))
        else:
            self._set_status(
                _t("SCREENSHOT_STATUS_OCR_FAIL", msg=err or "empty"), _tv("WARNING"),
            )
            self._fill_ocr("")

    def _fill_ocr(self, text):
        self.ocr_text.delete("1.0", tk.END)
        self.ocr_text.insert("1.0", text)

    # ----------------------------------------------------------
    # AI 讲解（后台线程）
    # ----------------------------------------------------------
    def _on_explain(self):
        if self._busy:
            return
        text = self.ocr_text.get("1.0", tk.END).strip()
        if not text:
            self._set_status(_t("SCREENSHOT_STATUS_NO_FILE"), _tv("WARNING"))
            return

        # 用户可能手工改过识别结果 —— 以编辑框内容为准
        ocr_result = dict(self._ocr_result or {})
        ocr_result["text"] = text
        ocr_result.setdefault("backend", "manual")
        hint = self.hint_var.get().strip()
        course = self._course

        self._set_busy(True, _t("SCREENSHOT_STATUS_EXPLAIN"))
        self._write_answer("")

        def worker(res, h, ctx):
            try:
                from tools.screenshot_ocr import explain_with_llm
                full_hint = h
                if ctx:
                    full_hint = (h + " " if h else "") + f"（当前课程：{ctx}）"
                return explain_with_llm(res, user_hint=full_hint)
            except Exception as e:
                return {"answer": str(e), "source": "error"}

        threading.Thread(
            target=lambda: self.after(
                0, self._on_explain_done, worker(ocr_result, hint, course),
            ),
            daemon=True,
        ).start()

    def _on_explain_done(self, res):
        self._set_busy(False)
        answer = (res or {}).get("answer", "") if isinstance(res, dict) else str(res)
        src = (res or {}).get("source", "") if isinstance(res, dict) else ""
        if not answer:
            self._set_status(
                _t("SCREENSHOT_STATUS_EXPLAIN_FAIL", msg="empty"), _tv("ERROR"),
            )
            return
        self._write_answer(answer)
        if src in ("no-llm", "error"):
            self._set_status(
                _t("SCREENSHOT_STATUS_EXPLAIN_FAIL", msg=answer[:80]), _tv("WARNING"),
            )
        else:
            self._set_status(_t("SCREENSHOT_STATUS_EXPLAIN_OK"), _tv("SUCCESS"))
        if self._on_done:
            try:
                self._on_done(answer)
            except Exception:
                pass

    def _write_answer(self, text):
        self.answer_text.config(state=tk.NORMAL)
        self.answer_text.delete("1.0", tk.END)
        self.answer_text.insert("1.0", text)
        self.answer_text.config(state=tk.DISABLED)


# ============================================================
def _attach_placeholder(entry: tk.Entry, placeholder: str):
    """给 Entry 加占位符（获得焦点自动清空，失焦且为空则回填）。"""
    state = {"ph": True}

    def _show():
        if not entry.get():
            state["ph"] = True
            entry.insert(0, placeholder)
            entry.config(fg=_tv("TEXT_MUTED"))

    def _on_in(_):
        if state["ph"]:
            state["ph"] = False
            entry.delete(0, tk.END)
            entry.config(fg=_tv("TEXT_PRIMARY"))

    def _on_out(_):
        if not entry.get().strip():
            _show()

    _show()
    entry.bind("<FocusIn>", _on_in)
    entry.bind("<FocusOut>", _on_out)
    # 对外暴露读值（跳过占位符）
    entry.get_real = lambda: "" if state["ph"] else entry.get().strip()
