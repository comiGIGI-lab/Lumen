"""历史记录弹窗：列出所有已生成方案，点击可重新打开。"""

import tkinter as tk
from tkinter import ttk, messagebox

from tools.progress_store import (
    list_courses,
    load_result,
    delete_course,
    get_stats,
)


class HistoryDialog:
    """历史课程列表 + 双击打开 + 删除按钮。"""

    def __init__(self, parent, on_open=None):
        """
        参数：
            parent: 父窗口
            on_open: 选中一个课程后的回调，签名 on_open(result: dict)
        """
        self.on_open = on_open
        self.win = tk.Toplevel(parent)
        self.win.title("📜 历史记录")
        self.win.geometry("640x440")
        self.win.transient(parent)
        self.win.grab_set()

        self._build()
        self._refresh()

    def _build(self):
        # 标题
        head = tk.Frame(self.win, bg="#1e293b", height=46)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        tk.Label(
            head, text="📜  历史记录",
            font=("Microsoft YaHei", 14, "bold"),
            bg="#1e293b", fg="white",
        ).pack(side=tk.LEFT, padx=16)

        # 主体：Treeview
        wrap = tk.Frame(self.win, bg="#f8fafc")
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cols = ("course", "outline", "plan", "created", "seen")
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", height=12,
        )
        self.tree.heading("course", text="课程")
        self.tree.heading("outline", text="章节进度")
        self.tree.heading("plan", text="计划进度")
        self.tree.heading("created", text="创建时间")
        self.tree.heading("seen", text="最近查看")
        self.tree.column("course", width=180, anchor="w")
        self.tree.column("outline", width=80, anchor="center")
        self.tree.column("plan", width=80, anchor="center")
        self.tree.column("created", width=130, anchor="center")
        self.tree.column("seen", width=130, anchor="center")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vbar.set)

        self.tree.bind("<Double-1>", self._on_double_click)

        # 底部按钮
        btn_row = tk.Frame(self.win, bg="#f1f5f9")
        btn_row.pack(fill=tk.X)

        tk.Button(
            btn_row, text="📂 打开", font=("Microsoft YaHei", 10),
            bg="#3b82f6", fg="white",
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", command=self._on_open_clicked,
        ).pack(side=tk.LEFT, padx=(10, 6), pady=8)

        tk.Button(
            btn_row, text="🗑 删除", font=("Microsoft YaHei", 10),
            bg="#ef4444", fg="white",
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", command=self._on_delete_clicked,
        ).pack(side=tk.LEFT, padx=6, pady=8)

        tk.Button(
            btn_row, text="🔄 刷新", font=("Microsoft YaHei", 10),
            bg="#64748b", fg="white",
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", command=self._refresh,
        ).pack(side=tk.LEFT, padx=6, pady=8)

        tk.Button(
            btn_row, text="关闭", font=("Microsoft YaHei", 10),
            bg="#94a3b8", fg="white",
            relief=tk.FLAT, padx=14, pady=6,
            cursor="hand2", command=self.win.destroy,
        ).pack(side=tk.RIGHT, padx=10, pady=8)

    def _refresh(self):
        """刷新列表。"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in list_courses():
            done, total, ratio = get_stats(row["course"])
            outline_pct = (
                f"{sum(1 for x in get_progress(row['course'])['outline'] if x['done'])}"
                f"/{len(get_progress(row['course'])['outline'])}"
            )
            plan_pct = (
                f"{sum(1 for x in get_progress(row['course'])['plan'] if x['done'])}"
                f"/{len(get_progress(row['course'])['plan'])}"
            )
            self.tree.insert(
                "", tk.END,
                values=(
                    row["course"],
                    outline_pct,
                    plan_pct,
                    row["created_at"],
                    row["last_seen_at"],
                ),
            )

    def _on_double_click(self, event):
        self._on_open_clicked()

    def _on_open_clicked(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一门课程", parent=self.win)
            return
        course = self.tree.item(sel[0], "values")[0]
        result = load_result(course)
        if not result:
            messagebox.showerror("错误", f"无法加载「{course}」的方案", parent=self.win)
            return
        self.win.destroy()
        if self.on_open:
            self.on_open(result)

    def _on_delete_clicked(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一门课程", parent=self.win)
            return
        course = self.tree.item(sel[0], "values")[0]
        if not messagebox.askyesno(
            "确认删除",
            f"确定从历史记录中删除「{course}」？\n（不会删除导出的 Markdown 文件）",
            parent=self.win,
        ):
            return
        delete_course(course)
        self._refresh()


# 工具函数：拿进度信息避免循环 import
def get_progress(course):
    from tools.progress_store import get_progress as _gp
    return _gp(course)