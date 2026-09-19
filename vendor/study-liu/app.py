# app.py — 学习智能助手入口：启动窗口

"""study-liu 学习智能助手 入口文件，启动主窗口。"""

import os
import sys


def _enable_high_dpi():
    """启用 Windows 高 DPI 感知，让 Tkinter 字体显示清晰。

    必须在创建任何 Tk 控件之前调用。
    """
    if sys.platform != "win32":
        return
    try:
        # Per-monitor V2 awareness，Win10 1903+ 推荐
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            # 旧版 Win 没有 shcore，回退到 V1
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass


# 必须在 import tkinter 之前开启 DPI awareness
_enable_high_dpi()

# 确保项目根目录在 Python 路径中（仅源码运行需要；打包后由 PyInstaller 处理）
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """启动应用主窗口。"""
    from ui.main_window import MainWindow

    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
