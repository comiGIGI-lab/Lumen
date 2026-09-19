"""知识库 GUI 面板：列表 / 搜索 / 新增 / 删除 / 详情编辑。

对接 tools/knowledge_store.py 的 KnowledgeStore：add / search / list_all / delete。
新增的 KnowledgeAddDialog 用于录入新笔记。
"""

import os
import tkinter as tk
from tkinter import messagebox

from tools.knowledge_store import KnowledgeStore
from ui.theme import (
    BG_APP,
    BG_CARD,
    BORDER,
    BORDER_STRONG,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_LIGHT,
    ACCENT,
    ACCENT_DARK,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    TEXT_ON_PRIMARY,
    SUCCESS,
    ERROR,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_BUTTON,
    FONT_INPUT,
    FONT_SMALL,
    FONT_TINY,
)
from ui.widgets import Card, PrimaryButton, AccentButton


# 标签 chip 底色：复用 PRIMARY_LIGHT
_TAG_BG = PRIMARY_LIGHT
_TAG_FG = "#312e81"


def _normalize_tags(raw):
    """把 'a, b、c,d' 切分成干净的 tag 列表。"""
    if not raw:
        return []
    # 中文 / 英文逗号、顿号都视作分隔符
    parts = []
    buf = ""
    for ch in raw:
        if ch in (",", "，", "、"):
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    # 去重 + 去空
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


class KnowledgeAddDialog(tk.Toplevel):
    """新增笔记的录入弹窗（标题、标签、内容）。"""

    def __init__(self, master, default_title="", default_tags="", default_content="", on_saved=None):
        super().__init__(master)
        self.title("➕ 新增笔记")
        self.geometry("560x420")
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=BG_APP)

        self._on_saved = on_saved
        self._result_saved = False

        # ---- 标题 ----
        tk.Label(
            self, text="标题（必填）：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY, anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(16, 4))

        self.title_var = tk.StringVar(value=default_title)
        tk.Entry(
            self, textvariable=self.title_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(fill=tk.X, padx=18, ipady=6)

        # ---- 标签 ----
        tk.Label(
            self, text="标签（逗号或顿号分隔）：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY, anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(12, 4))

        self.tags_var = tk.StringVar(value=default_tags)
        tk.Entry(
            self, textvariable=self.tags_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(fill=tk.X, padx=18, ipady=6)

        # ---- 内容 ----
        tk.Label(
            self, text="内容（必填）：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY, anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(12, 4))

        self.content_text = tk.Text(
            self, wrap=tk.WORD, font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            padx=8, pady=8, height=8,
        )
        self.content_text.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 8))
        if default_content:
            self.content_text.insert("1.0", default_content)

        # ---- 按钮栏 ----
        btn_bar = tk.Frame(self, bg=BG_APP)
        btn_bar.pack(fill=tk.X, padx=18, pady=(0, 14))

        AccentButton(btn_bar, text="保存", command=self._save).pack(side=tk.RIGHT)
        tk.Button(
            btn_bar, text="取消",
            font=FONT_BUTTON, bg=BG_CARD, fg=TEXT_SECONDARY,
            activebackground=BG_APP, activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, padx=14, pady=8, cursor="hand2",
            command=self.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.grab_set()
        self.title_var.set(default_title or "")
        self.focus_force()

    def _save(self):
        title = self.title_var.get().strip()
        content = self.content_text.get("1.0", tk.END).strip()
        tags = _normalize_tags(self.tags_var.get())

        if not title:
            messagebox.showwarning("提示", "标题不能为空", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "内容不能为空", parent=self)
            return

        try:
            KnowledgeStore().add(title, content, tags=tags)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return

        self._result_saved = True
        if self._on_saved:
            try:
                self._on_saved()
            except Exception:
                pass
        self.destroy()


class KnowledgeDialog(tk.Toplevel):
    """📚 我的笔记 主面板：列表 + 搜索 + 详情编辑 + 新增 + 删除。"""

    SEARCH_DEBOUNCE_MS = 200

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.title("📚 我的笔记 — study-liu")
        self.geometry("780x540")
        self.minsize(640, 420)
        self.transient(master)
        self.configure(bg=BG_APP)

        self._on_change = on_change
        self._items = []
        self._current_note = None
        self._dirty = False
        self._search_after_id = None

        self._build()
        self._reload()

    # ----------------------------------------------------------
    # 构建
    # ----------------------------------------------------------
    def _build(self):
        # ---- 顶部：标题 + 关闭 ----
        top = tk.Frame(self, bg=BG_APP)
        top.pack(fill=tk.X, padx=16, pady=(12, 6))

        tk.Label(
            top, text="📚 我的笔记",
            font=("Microsoft YaHei UI", 15, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(side=tk.LEFT)

        tk.Button(
            top, text="✕",
            font=FONT_BUTTON, bg=BG_APP, fg=TEXT_MUTED,
            activebackground=BG_APP, activeforeground=ERROR,
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_close,
        ).pack(side=tk.RIGHT)

        # ---- 工具栏：搜索 + 新增 ----
        toolbar = tk.Frame(self, bg=BG_APP)
        toolbar.pack(fill=tk.X, padx=16, pady=(0, 8))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_search())
        tk.Entry(
            toolbar, textvariable=self.search_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

        tk.Label(
            toolbar, text="🔍",
            font=FONT_BODY, bg=BG_APP, fg=TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(6, 0))

        PrimaryButton(
            toolbar, text="+ 新增",
            command=self._open_add_dialog,
        ).pack(side=tk.LEFT, padx=(10, 0))

        # 📥 导入 按钮（文件 + 粘贴）
        import_btn = tk.Label(
            toolbar, text="  📥 导入  ",
            font=FONT_BUTTON, bg=ACCENT, fg="white",
            padx=14, pady=6, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        import_btn.pack(side=tk.LEFT, padx=(8, 0))
        import_btn.bind("<Button-1>", lambda e: self._open_import_dialog())
        import_btn.bind(
            "<Enter>", lambda e: import_btn.config(bg=ACCENT_DARK),
        )
        import_btn.bind(
            "<Leave>", lambda e: import_btn.config(bg=ACCENT),
        )
        self._import_btn = import_btn

        # ---- 主体：左 Listbox + 右 详情 ----
        body = tk.Frame(self, bg=BG_APP)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        # 左
        left = tk.Frame(body, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER, bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)
        left.configure(width=240)

        self.listbox = tk.Listbox(
            left, font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            selectbackground=PRIMARY_LIGHT, selectforeground=TEXT_PRIMARY,
            highlightthickness=0, bd=0,
            activestyle="none",
            relief="flat",
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # 右：详情卡片
        self.detail_card = Card(body, padding=14)
        self.detail_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_detail(self.detail_card.inner)

        # ---- 状态栏 ----
        self.status_var = tk.StringVar(value="共 0 条")
        tk.Label(
            self, textvariable=self.status_var,
            font=FONT_STATUS, bg=BG_APP, fg=TEXT_MUTED, anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_detail(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # 标题编辑框
        self.dtitle_var = tk.StringVar()
        tk.Entry(
            parent, textvariable=self.dtitle_var, font=("Microsoft YaHei UI", 13, "bold"),
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).grid(row=0, column=0, sticky="ew", ipady=4)
        self.dtitle_var.trace_add("write", lambda *_: self._mark_dirty())

        # 标签 chips 区
        tags_frame = tk.Frame(parent, bg=BG_CARD)
        tags_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._tags_frame = tags_frame
        self._tag_widgets = []

        # 时间戳
        self.dtime_var = tk.StringVar(value="")
        tk.Label(
            parent, textvariable=self.dtime_var,
            font=FONT_TINY, bg=BG_CARD, fg=TEXT_MUTED, anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(4, 0))

        # 内容区
        self.dcontent_text = tk.Text(
            parent, wrap=tk.WORD, font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            padx=10, pady=10, height=8,
        )
        self.dcontent_text.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.dcontent_text.bind("<<Modified>>", self._on_content_modified)

        # 按钮栏
        btn_bar = tk.Frame(parent, bg=BG_CARD)
        btn_bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))

        self.delete_btn = tk.Button(
            btn_bar, text="🗑 删除",
            font=FONT_BUTTON, bg=BG_CARD, fg=ERROR,
            activebackground=BG_APP, activeforeground=ERROR,
            relief=tk.FLAT, bd=0, padx=14, pady=6, cursor="hand2",
            command=self._delete_current,
        )
        self.delete_btn.pack(side=tk.LEFT)

        self.save_btn = AccentButton(
            btn_bar, text="💾 保存修改", command=self._save_current,
        )
        self.save_btn.pack(side=tk.RIGHT)
        self.save_btn.config(state=tk.DISABLED)

        self._set_detail_enabled(False)

    # ----------------------------------------------------------
    # 数据加载
    # ----------------------------------------------------------
    def _reload(self, items=None):
        if items is None:
            items = KnowledgeStore().list_all()
        # 按 id 倒序（最新在前）
        self._items = sorted(items, key=lambda x: x.get("id", 0), reverse=True)

        self.listbox.delete(0, tk.END)
        for item in self._items:
            tags = " ".join(f"#{t}" for t in item.get("tags", []))
            title = item.get("title", "(无标题)")
            display = f"{title}  {tags}".strip() if tags else title
            self.listbox.insert(tk.END, display)

        self.status_var.set(f"共 {len(self._items)} 条")
        self._set_detail_enabled(False)
        self._current_note = None

        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    def _schedule_search(self):
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(
            self.SEARCH_DEBOUNCE_MS, self._run_search,
        )

    def _run_search(self):
        self._search_after_id = None
        kw = self.search_var.get().strip()
        if not kw:
            self._reload()
            return
        try:
            results = KnowledgeStore().search(kw)
        except Exception as e:
            messagebox.showerror("搜索失败", str(e), parent=self)
            results = []
        self._reload(items=results)

    # ----------------------------------------------------------
    # 详情渲染
    # ----------------------------------------------------------
    def _on_select(self, _evt=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._items):
            return
        self._current_note = self._items[idx]
        self._dirty = False
        self._fill_detail(self._current_note)
        self._set_detail_enabled(True)
        self.save_btn.config(state=tk.DISABLED)

    def _fill_detail(self, note):
        self.dtitle_var.set(note.get("title", ""))
        self.dtime_var.set(
            f"创建：{note.get('created_at', '-')}  ·  id: {note.get('id', '-')}"
        )

        # 渲染 chips
        for w in self._tag_widgets:
            w.destroy()
        self._tag_widgets = []
        for tag in note.get("tags", []):
            chip = tk.Label(
                self._tags_frame, text=f" #{tag} ",
                font=FONT_SMALL, bg=_TAG_BG, fg=_TAG_FG,
                padx=6, pady=2,
            )
            chip.pack(side=tk.LEFT, padx=(0, 6), pady=(4, 4))
            self._tag_widgets.append(chip)

        # 内容：填到 Text，禁用 modified 触发
        self.dcontent_text.config(state=tk.NORMAL)
        self.dcontent_text.delete("1.0", tk.END)
        self.dcontent_text.insert("1.0", note.get("content", ""))
        self.dcontent_text.edit_modified(False)

    def _set_detail_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for w in (
            self.dtitle_var,
        ):
            # StringVar 不需要 set state；Entry 通过配置 disabledforeground 处理
            pass
        # 真正起作用：把 Entry / Text 的 state 切到 normal/disabled
        # 但我们要让 title 可编辑，所以重新拉一遍
        try:
            self._title_entry = self.dtitle_var
            # Entry 是通过 self.dtitle_var 关联的，无法直接 state 切换；
            # 我们用 children() 找到对应 Entry
            for child in self.detail_card.inner.winfo_children():
                if isinstance(child, tk.Entry):
                    child.config(state=state)
        except Exception:
            pass

        self.dcontent_text.config(state=state)
        self.delete_btn.config(state=state)
        self.save_btn.config(state=tk.DISABLED if not enabled else tk.DISABLED)

    def _on_content_modified(self, _evt=None):
        if self.dcontent_text.edit_modified():
            self._mark_dirty()
            self.dcontent_text.edit_modified(False)

    def _mark_dirty(self):
        if self._current_note is None:
            return
        self._dirty = True
        self.save_btn.config(state=tk.NORMAL)

    # ----------------------------------------------------------
    # 新增 / 删除 / 保存
    # ----------------------------------------------------------
    def _open_add_dialog(self):
        def on_saved():
            self._reload()
            self._set_status(f"✓ 已新增笔记")

        KnowledgeAddDialog(self, on_saved=on_saved)

    def _open_import_dialog(self):
        """打开导入弹窗：粘贴文本 / 选文件 → 自动抽取关键句入知识库。"""
        def on_done(note_id, summary):
            self._reload()
            self._set_status(f"📥 已导入：{summary}（id {note_id}）")

        ImportDialog(self, on_done=on_done)

    def _delete_current(self):
        if not self._current_note:
            return
        nid = self._current_note.get("id")
        title = self._current_note.get("title", "")
        if not messagebox.askyesno("确认删除", f"确定删除「{title}」？此操作不可恢复。", parent=self):
            return
        try:
            ok = KnowledgeStore().delete(nid)
        except Exception as e:
            messagebox.showerror("删除失败", str(e), parent=self)
            return
        if not ok:
            messagebox.showwarning("删除失败", "笔记不存在或已被删除", parent=self)
            return
        self._set_status(f"🗑 已删除「{title}」")
        # 删完后按当前关键词再搜一次，保持过滤状态
        kw = self.search_var.get().strip()
        if kw:
            self._run_search()
        else:
            self._reload()

    def _save_current(self):
        if not self._current_note:
            return
        nid = self._current_note.get("id")
        # 直接重写文件：KnowledgeStore 没有 update API，朴素方案：删+加
        title = self.dtitle_var.get().strip()
        content = self.dcontent_text.get("1.0", tk.END).strip()
        tags = _normalize_tags(
            # 从当前 chips 拿不到原始字符串，改为从 self._current_note 读 tags，不让 UI 改 tags
            # tags 在详情面板是只读展示，编辑 tags 走新增/单独接口
            ",".join(self._current_note.get("tags", []))
        )

        if not title:
            messagebox.showwarning("提示", "标题不能为空", parent=self)
            return
        if not content:
            messagebox.showwarning("提示", "内容不能为空", parent=self)
            return

        try:
            store = KnowledgeStore()
            store.delete(nid)
            new_id = store.add(title, content, tags=tags)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return

        self._set_status(f"💾 已保存「{title}」(id {new_id})")
        # 重新加载
        kw = self.search_var.get().strip()
        if kw:
            self._run_search()
        else:
            self._reload()

    # ----------------------------------------------------------
    # 关闭
    # ----------------------------------------------------------
    def _on_close(self):
        if self._dirty and self._current_note:
            if not messagebox.askyesno("未保存的修改", "当前笔记有未保存的修改，是否关闭？", parent=self):
                return
        self.destroy()

    def _set_status(self, text):
        self.status_var.set(text)


__all__ = ["KnowledgeDialog", "KnowledgeAddDialog", "ImportDialog"]


# ==========================================================
# 导入弹窗（粘贴文本 / 选文件 → 自动入知识库）
# ==========================================================
class ImportDialog(tk.Toplevel):
    """📥 导入弹窗：选文件 或 粘贴文本 → 自动抽取关键句入知识库。"""

    W = 640
    H = 540

    def __init__(self, master, on_done=None):
        super().__init__(master)
        self.title("📥 导入笔记 — study-liu")
        self.configure(bg=BG_APP)
        self.transient(master)
        self.resizable(False, False)

        self._on_done = on_done

        # 居中
        self.update_idletasks()
        try:
            px, py = master.winfo_rootx(), master.winfo_rooty()
            pw, ph = master.winfo_width(), master.winfo_height()
        except Exception:
            px, py, pw, ph = 200, 200, 800, 600
        x = px + max(0, (pw - self.W) // 2)
        y = py + max(0, (ph - self.H) // 2)
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self._build()

        self.grab_set()
        self.focus_force()

    def _build(self):
        # 顶部装饰条
        tk.Frame(self, bg=ACCENT, height=4).pack(side=tk.TOP, fill=tk.X)

        # 标题
        tk.Label(
            self, text="📥 导入笔记到知识库",
            font=("Microsoft YaHei UI", 15, "bold"),
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).pack(pady=(14, 4))

        # 副标题
        tk.Label(
            self,
            text=(
                "方式 1：选文件（.pdf / .md / .txt）\n"
                "方式 2：在文本框粘贴一段文字\n"
                "系统会自动抽取关键句作为摘要入库。"
            ),
            font=FONT_BODY, bg=BG_APP, fg=TEXT_SECONDARY,
            justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, padx=24, pady=(0, 10))

        # ---- 选项卡：文件 / 粘贴 ----
        tab_row = tk.Frame(self, bg=BG_APP)
        tab_row.pack(fill=tk.X, padx=24, pady=(0, 8))

        self._tab_var = tk.StringVar(value="file")
        self._tabs = {}
        for key, label in [("file", "📁 选文件"), ("paste", "📝 粘贴文本")]:
            btn = tk.Label(
                tab_row, text=f"  {label}  ",
                font=FONT_BODY_BOLD,
                bg=BG_CARD, fg=TEXT_SECONDARY,
                padx=14, pady=6, cursor="hand2",
                highlightthickness=1, highlightbackground=BORDER, bd=0,
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda e, b=btn: self._on_tab_hover(b, True))
            btn.bind("<Leave>", lambda e, b=btn: self._on_tab_hover(b, False))
            self._tabs[key] = btn

        # ---- 文件面板 ----
        self.file_panel = tk.Frame(self, bg=BG_APP)
        self.file_panel.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 6))

        file_row = tk.Frame(self.file_panel, bg=BG_APP)
        file_row.pack(fill=tk.X, pady=(8, 8))

        self.file_path_var = tk.StringVar(value="（未选文件）")
        tk.Label(
            file_row, textvariable=self.file_path_var,
            font=FONT_BODY, bg=BG_APP, fg=TEXT_MUTED,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        AccentButton(
            file_row, text="📂 选择文件",
            command=self._choose_file,
        ).pack(side=tk.RIGHT, padx=(10, 0))

        # 提示
        tk.Label(
            self.file_panel,
            text="支持 .pdf / .md / .markdown / .txt\n"
                 "PDF 需要安装 pypdf 或 pdfplumber。",
            font=FONT_SMALL, bg=BG_APP, fg=TEXT_MUTED,
            justify=tk.LEFT, anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        # ---- 粘贴面板 ----
        self.paste_panel = tk.Frame(self, bg=BG_APP)
        # 不 pack，默认隐藏

        self.paste_text = tk.Text(
            self.paste_panel, font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            padx=10, pady=8, height=10, wrap=tk.WORD,
        )
        self.paste_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # ---- 通用：标题 + 标签 ----
        meta_row = tk.Frame(self, bg=BG_APP)
        meta_row.pack(fill=tk.X, padx=24, pady=(8, 4))
        meta_row.grid_columnconfigure(1, weight=1)

        tk.Label(
            meta_row, text="标题：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.title_var = tk.StringVar()
        tk.Entry(
            meta_row, textvariable=self.title_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).grid(row=0, column=1, sticky="ew", ipady=4)

        tk.Label(
            meta_row, text="标签：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY,
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self.tags_var = tk.StringVar(value="#import")
        tk.Entry(
            meta_row, textvariable=self.tags_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).grid(row=1, column=1, sticky="ew", ipady=4, pady=(6, 0))

        # ---- 底部按钮 ----
        btn_bar = tk.Frame(self, bg=BG_APP)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=(0, 14))

        tk.Label(
            btn_bar, text="  取消  ",
            font=FONT_BUTTON, bg=BG_CARD, fg=TEXT_SECONDARY,
            padx=22, pady=8, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        ).pack(side=tk.RIGHT)
        cancel_btn = btn_bar.winfo_children()[-1]
        cancel_btn.bind("<Button-1>", lambda e: self.destroy())
        cancel_btn.bind(
            "<Enter>", lambda e: cancel_btn.config(bg=BG_HOVER),
        )
        cancel_btn.bind(
            "<Leave>", lambda e: cancel_btn.config(bg=BG_CARD),
        )

        self.import_btn = tk.Label(
            btn_bar, text="    导入并入库    ",
            font=FONT_BUTTON, bg=PRIMARY, fg="white",
            padx=20, pady=8, cursor="hand2",
            highlightthickness=0, bd=0,
        )
        self.import_btn.pack(side=tk.RIGHT, padx=(0, 10))
        self.import_btn.bind("<Button-1>", lambda e: self._do_import())
        self.import_btn.bind(
            "<Enter>", lambda e: self.import_btn.config(bg=PRIMARY_DARK),
        )
        self.import_btn.bind(
            "<Leave>", lambda e: self.import_btn.config(bg=PRIMARY),
        )

        # 默认显示文件面板
        self._switch_tab("file")

    def _switch_tab(self, key):
        self._tab_var.set(key)
        for k, btn in self._tabs.items():
            if k == key:
                btn.config(bg=PRIMARY, fg="white", highlightbackground=PRIMARY)
            else:
                btn.config(bg=BG_CARD, fg=TEXT_SECONDARY, highlightbackground=BORDER)
        if key == "file":
            self.paste_panel.pack_forget()
            self.file_panel.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 6))
        else:
            self.file_panel.pack_forget()
            self.paste_panel.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 6))

    def _on_tab_hover(self, btn, entering):
        # 不高亮当前选中的 tab
        if btn is self._tabs.get(self._tab_var.get()):
            return
        btn.config(bg=BG_HOVER if entering else BG_CARD)

    def _choose_file(self):
        from tkinter import filedialog
        from tools.document_importer import list_supported_extensions
        exts = list_supported_extensions()
        filetypes = [
            ("支持格式", " ".join(f"*{e}" for e in exts)),
            ("PDF", "*.pdf"),
            ("Markdown", "*.md *.markdown"),
            ("文本", "*.txt"),
            ("所有文件", "*.*"),
        ]
        path = filedialog.askopenfilename(
            parent=self,
            title="选择要导入的文件",
            filetypes=filetypes,
        )
        if path:
            self.file_path_var.set(path)
            # 自动用文件名做默认标题
            if not self.title_var.get().strip():
                import os
                stem = os.path.splitext(os.path.basename(path))[0]
                self.title_var.set(stem)

    def _do_import(self):
        """根据当前 tab 执行粘贴导入 / 文件导入。"""
        from tools.document_importer import paste_import, import_file
        tags = _normalize_tags(self.tags_var.get())
        title = self.title_var.get().strip() or None

        try:
            if self._tab_var.get() == "paste":
                text = self.paste_text.get("1.0", tk.END).strip()
                if not text:
                    messagebox.showwarning(
                        "提示", "请先粘贴一段文字", parent=self,
                    )
                    return
                note_id = paste_import(text, title=title, tags=tags)
                summary = f"粘贴 {len(text)} 字"
            else:
                path = self.file_path_var.get()
                if not path or path == "（未选文件）":
                    messagebox.showwarning(
                        "提示", "请先选择文件", parent=self,
                    )
                    return
                note_id = import_file(path, title=title, tags=tags)
                summary = os.path.basename(path) if hasattr(os, "path") else path
        except FileNotFoundError as e:
            messagebox.showerror("文件不存在", str(e), parent=self)
            return
        except ValueError as e:
            messagebox.showerror("内容无效", str(e), parent=self)
            return
        except ImportError as e:
            messagebox.showerror(
                "缺少依赖",
                f"{e}\n\n请在终端运行：pip install PyPDF2",
                parent=self,
            )
            return
        except Exception as e:
            messagebox.showerror("导入失败", str(e), parent=self)
            return

        if self._on_done:
            try:
                self._on_done(note_id, summary)
            except Exception:
                pass
        self.destroy()