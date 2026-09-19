"""⭐ 收藏到知识库 的小弹窗。

复用 KnowledgeStore.add，默认填入 AI 回答全文，让用户编辑标题与标签。
"""

import tkinter as tk
from tkinter import messagebox

from tools.knowledge_store import KnowledgeStore
from ui.theme import (
    BG_APP,
    BG_CARD,
    BORDER,
    PRIMARY,
    PRIMARY_LIGHT,
    TEXT_PRIMARY,
    TEXT_MUTED,
    ERROR,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_BUTTON,
    FONT_INPUT,
)


def _default_title_from_content(content):
    """从内容里抽出第一句话作为默认标题（去标点）。"""
    if not content:
        return ""
    # 取首行
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    # 截前 24 个字符
    head = first_line[:24].strip()
    return head or "未命名笔记"


def _normalize_tags(raw):
    if not raw:
        return []
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
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


class CollectDialog(tk.Toplevel):
    """把 AI 回答一键收藏到知识库的弹窗。"""

    def __init__(self, master, content="", default_title="", default_tags="#chat, #ai", on_saved=None):
        super().__init__(master)
        self.title("⭐ 收藏到知识库")
        self.geometry("560x440")
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=BG_APP)

        self._on_saved = on_saved

        # 标题（默认从 content 抽取）
        tk.Label(
            self, text="标题：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY, anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(16, 4))

        self.title_var = tk.StringVar(value=default_title or _default_title_from_content(content))
        tk.Entry(
            self, textvariable=self.title_var, font=FONT_INPUT,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
        ).pack(fill=tk.X, padx=18, ipady=6)

        # 标签
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

        # 内容
        tk.Label(
            self, text="内容（可编辑）：", font=FONT_BODY_BOLD,
            bg=BG_APP, fg=TEXT_PRIMARY, anchor="w",
        ).pack(fill=tk.X, padx=18, pady=(12, 4))

        self.content_text = tk.Text(
            self, wrap=tk.WORD, font=FONT_BODY,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=PRIMARY,
            padx=8, pady=8, height=10,
        )
        self.content_text.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 8))
        if content:
            self.content_text.insert("1.0", content)

        # 按钮
        btn_bar = tk.Frame(self, bg=BG_APP)
        btn_bar.pack(fill=tk.X, padx=18, pady=(0, 14))

        tk.Button(
            btn_bar, text="取消",
            font=FONT_BUTTON, bg=BG_CARD, fg=TEXT_PRIMARY,
            activebackground=BG_APP, activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT, bd=0, padx=14, pady=8, cursor="hand2",
            command=self.destroy,
        ).pack(side=tk.RIGHT)
        tk.Button(
            btn_bar, text="⭐ 收藏",
            font=FONT_BUTTON, bg=PRIMARY, fg="white",
            activebackground=PRIMARY_LIGHT, activeforeground="white",
            relief=tk.FLAT, bd=0, padx=18, pady=8, cursor="hand2",
            command=self._save,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.grab_set()
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
            new_id = KnowledgeStore().add(title, content, tags=tags)
        except Exception as e:
            messagebox.showerror("收藏失败", str(e), parent=self)
            return

        if self._on_saved:
            try:
                self._on_saved(new_id, title)
            except Exception:
                pass
        self.destroy()


__all__ = ["CollectDialog"]