"""UI 组件：渐变 Header、卡片、按钮、结果面板等。

v2 重写：
- GradientHeader 改用 Frame + Label（Canvas 文本在高 DPI 下会歪）
- 渐变用 tk.Frame 的背景色分段实现（用 Canvas 只画装饰，不画文本）
"""

import tkinter as tk

from ui.theme import (
    BG_APP,
    BG_CARD,
    BORDER,
    BORDER_STRONG,
    PRIMARY,
    PRIMARY_LIGHT,
    PRIMARY_DARK,
    ACCENT,
    ACCENT_DARK,
    SUCCESS,
    ERROR,
    GRAD_TOP_FROM,
    GRAD_TOP_TO,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    TEXT_ON_PRIMARY,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_BODY_LARGE,
    FONT_CARD_TITLE,
    FONT_INPUT,
    FONT_BUTTON,
    FONT_HERO_TITLE,
    FONT_HERO_SUB,
    FONT_SMALL,
    PAD_CARD,
    RADIUS,
)


# ============================================================
# 卡片容器
# ============================================================
class Card(tk.Frame):
    """白底圆角卡片（tkinter 无真阴影，省略以避免尺寸计算坑）。"""

    def __init__(self, parent, padding=PAD_CARD, border=True, **kwargs):
        super().__init__(
            parent, bg=BG_APP,
            highlightthickness=0, bd=0, **kwargs,
        )
        self.body = tk.Frame(
            self,
            bg=BG_CARD,
            highlightthickness=1 if border else 0,
            highlightbackground=BORDER,
            bd=0,
        )
        self.body.pack(fill=tk.BOTH, expand=True)
        self.inner = tk.Frame(self.body, bg=BG_CARD)
        self.inner.pack(fill=tk.BOTH, expand=True, padx=padding, pady=padding)

    def pack(self, **kwargs):
        super().pack(**kwargs)

    def grid(self, **kwargs):
        super().grid(**kwargs)


# ============================================================
# 渐变 Hero 头部（v2：用 Frame + Label，放弃 Canvas 文本）
# ============================================================
class GradientHeader(tk.Frame):
    """顶部 Hero。

    v2 重写：之前用 Canvas 画渐变 + 文本，高 DPI 下文本会歪。
    现在用纯 Frame + Label，渐变效果用 background 渐变模拟（分段 Frame）。
    """

    def __init__(self, parent, title, subtitle, height=108):
        super().__init__(parent, bg=GRAD_TOP_FROM, height=height)
        self.pack_propagate(False)
        self._height = height

        # 渐变背景：用 8 个等宽竖条 Frame，颜色从 GRAD_TOP_FROM 线性插值到 GRAD_TOP_TO
        steps = 16
        self._gradient_steps = []
        frm_rgb = self._hex_to_rgb(GRAD_TOP_FROM)
        to_rgb = self._hex_to_rgb(GRAD_TOP_TO)
        for i in range(steps):
            t = i / (steps - 1)
            r = int(frm_rgb[0] + (to_rgb[0] - frm_rgb[0]) * t)
            g = int(frm_rgb[1] + (to_rgb[1] - frm_rgb[1]) * t)
            b = int(frm_rgb[2] + (to_rgb[2] - frm_rgb[2]) * t)
            stripe = tk.Frame(self, bg=f"#{r:02x}{g:02x}{b:02x}", bd=0, width=1)
            stripe.pack(side=tk.LEFT, fill=tk.Y)
            self._gradient_steps.append(stripe)

        # 内容层（用 place 浮在渐变上）
        content = tk.Frame(self, bg=GRAD_TOP_FROM, bd=0)
        content.place(x=0, y=0, relwidth=1, relheight=1)

        # 让内容层透明——把渐变色重新填上去
        # 上面 gradient 已经画了，我们用 place 覆盖一个透明 Frame
        # tkinter 不支持真透明，用与底部同色的 Frame 即可
        # 简化：把 content 背景设为平均色（视觉上看不出区别）
        avg_rgb = (
            (frm_rgb[0] + to_rgb[0]) // 2,
            (frm_rgb[1] + to_rgb[1]) // 2,
            (frm_rgb[2] + to_rgb[2]) // 2,
        )
        avg_hex = f"#{avg_rgb[0]:02x}{avg_rgb[1]:02x}{avg_rgb[2]:02x}"
        content.config(bg=avg_hex)
        # 重新画渐变 stripe 在 content 之上
        # 太复杂，改方案：渐变 stripe 直接画，content 用 absolute positioning 浮在最上层

        # ---- 左侧：LOGO 圆 + 标题 + 副标题 ----
        left = tk.Frame(content, bg=avg_hex, bd=0)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=(20, 0), pady=12)

        # LOGO 圆（v5 缩小）
        logo_circle = tk.Frame(
            left, bg="white", width=48, height=48,
            highlightthickness=0, bd=0,
        )
        logo_circle.pack(side=tk.LEFT, padx=(0, 14))
        logo_circle.pack_propagate(False)
        tk.Label(
            logo_circle, text="S",
            font=("Segoe UI", 24, "bold"),
            bg="white", fg=PRIMARY,
        ).pack(expand=True)

        # 标题 + 副标题（竖排）
        text_col = tk.Frame(left, bg=avg_hex, bd=0)
        text_col.pack(side=tk.LEFT, fill=tk.BOTH)

        tk.Label(
            text_col, text=title,
            font=FONT_HERO_TITLE,
            bg=avg_hex, fg="white",
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            text_col, text=subtitle,
            font=FONT_HERO_SUB,
            bg=avg_hex, fg="#e0e7ff",
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        # ---- 右侧：徽章 ----
        right = tk.Frame(content, bg=avg_hex, bd=0)
        right.pack(side=tk.RIGHT, padx=(0, 20), pady=0)
        # 让 right 垂直居中
        right.place(relx=1.0, x=-20, rely=0.5, anchor="e")

        badge = tk.Label(
            right, text="  AI · 学习助手  ",
            font=FONT_BODY_BOLD,
            bg="#312e81", fg="#e0e7ff",
            padx=12, pady=6,
        )
        badge.pack()

    @staticmethod
    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ============================================================
# 按钮
# ============================================================
class PrimaryButton(tk.Button):
    def __init__(self, parent, text, command=None, **kw):
        super().__init__(
            parent, text=text, command=command,
            font=FONT_BUTTON,
            bg=PRIMARY, fg="white",
            activebackground=PRIMARY_DARK, activeforeground="white",
            relief=tk.FLAT, bd=0,
            padx=20, pady=8, cursor="hand2", **kw,  # v5 调回适中
        )
        self.bind("<Enter>", lambda e: self.config(bg=PRIMARY_DARK))
        self.bind("<Leave>", lambda e: self.config(bg=PRIMARY))


class AccentButton(tk.Button):
    def __init__(self, parent, text, command=None, **kw):
        super().__init__(
            parent, text=text, command=command,
            font=FONT_BUTTON,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_DARK, activeforeground="white",
            relief=tk.FLAT, bd=0,
            padx=18, pady=8, cursor="hand2", **kw,  # v5 调回适中
        )
        self.bind("<Enter>", lambda e: self.config(bg=ACCENT_DARK))
        self.bind("<Leave>", lambda e: self.config(bg=ACCENT))


# ============================================================
# 输入框（带 placeholder）
# ============================================================
class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder="请输入…", **kw):
        kw.setdefault("font", FONT_INPUT)
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("bd", 0)
        super().__init__(parent, **kw)
        self._ph = placeholder
        self._show_ph = True
        self._show_ph_text()
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

    def _show_ph_text(self):
        self.config(fg=TEXT_MUTED)
        self.delete(0, tk.END)
        self.insert(0, self._ph)
        self._show_ph = True

    def _on_focus_in(self, _):
        if self._show_ph:
            self.delete(0, tk.END)
            self.config(fg=TEXT_PRIMARY)
            self._show_ph = False

    def _on_focus_out(self, _):
        if not self.get():
            self._show_ph_text()

    def get_real(self):
        if self._show_ph:
            return ""
        return self.get().strip()


# ============================================================
# 三栏结果面板
# ============================================================
class ResultPanel:
    HEADERS = {
        "课程大纲": ("📘", PRIMARY),
        "推荐资源": ("📚", ACCENT),
        "学习计划": ("📅", SUCCESS),
    }

    def __init__(self, parent, title):
        self.title = title
        self.card = Card(parent)
        inner = self.card.inner

        head = tk.Frame(inner, bg=BG_CARD)
        head.pack(fill=tk.X, pady=(0, 6))
        head.grid_columnconfigure(1, weight=1)

        icon_char, icon_color = self.HEADERS.get(title, ("📄", PRIMARY))
        icon_bg = tk.Frame(head, bg=icon_color, width=36, height=36)  # 46→36
        icon_bg.grid(row=0, column=0, padx=(0, 10))
        icon_bg.grid_propagate(False)
        icon_bg.grid_columnconfigure(0, weight=1)
        icon_bg.grid_rowconfigure(0, weight=1)
        tk.Label(
            icon_bg, text=icon_char,
            font=("Segoe UI Emoji", 17),  # 22→17
            bg=icon_color, fg="white",
        ).grid(row=0, column=0, sticky="nsew")

        title_frame = tk.Frame(head, bg=BG_CARD)
        title_frame.grid(row=0, column=1, sticky="w")
        tk.Label(
            title_frame, text=title,
            font=FONT_CARD_TITLE, bg=BG_CARD, fg=TEXT_PRIMARY,
        ).pack(anchor="w")

        self.count_label = tk.Label(
            head, text="",
            font=FONT_SMALL, bg=BG_CARD, fg=TEXT_MUTED,
        )
        self.count_label.grid(row=0, column=2, sticky="e")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill=tk.X, pady=(0, 8))

        self.text = tk.Text(
            inner, wrap=tk.WORD,
            font=FONT_BODY_LARGE,
            bg=BG_CARD, fg=TEXT_PRIMARY,
            relief=tk.FLAT, padx=4, pady=4, bd=0,
            highlightthickness=0, spacing1=2, spacing3=4,
            height=12,
            state=tk.DISABLED,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        self.text.tag_configure("accent", font=FONT_BODY_BOLD, foreground=PRIMARY)
        self.text.tag_configure("meta", foreground=TEXT_SECONDARY)
        self.text.tag_configure("url", foreground=ACCENT_DARK)
        self.text.tag_configure("muted", foreground=TEXT_MUTED)

    def pack(self, **kwargs):
        self.card.pack(**kwargs)

    def grid(self, **kwargs):
        self.card.grid(**kwargs)

    def set_outline(self, outline):
        self._reset()
        self.count_label.config(text=f"{len(outline)} 章")
        for line in outline:
            self._ins("●  ", "accent")
            self._ins(line + "\n")

    def set_resources(self, resources):
        self._reset()
        self.count_label.config(text=f"{len(resources)} 项")
        for res in resources:
            title = res.get("title", "")
            rtype = res.get("type", "")
            url = res.get("url", "")
            self._ins("◆  ", "accent")
            self._ins(title + "\n", "accent")
            self._ins(f"    {rtype}\n", "meta")
            if url:
                self._ins(f"    ↗ {url}\n", "url")
            self._ins("\n")

    def set_plan(self, plan):
        self._reset()
        self.count_label.config(text=f"{len(plan)} 天")
        for i, line in enumerate(plan):
            if i > 0:
                self._ins("\n")
            self._ins("▸  ", "accent")
            self._ins(line + "\n")

    def clear(self):
        self._reset()
        self.count_label.config(text="")

    def _reset(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)

    def _ins(self, text, tag=None):
        if tag:
            self.text.insert(tk.END, text, tag)
        else:
            self.text.insert(tk.END, text)


# ============================================================
# 格式化函数（兼容旧调用）
# ============================================================
def format_outline(outline):
    return list(outline)


def format_resources(resources):
    lines = []
    for res in resources:
        title = res.get("title", "")
        rtype = res.get("type", "")
        url = res.get("url", "")
        lines.append(f"{title}（{rtype}）")
        if url:
            lines.append(f"  链接：{url}")
    return lines


def format_plan(plan):
    return list(plan)