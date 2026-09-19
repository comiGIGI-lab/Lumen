# paths.py — 统一的资源路径解析（PyInstaller 打包兼容）

"""路径模块：集中解决"源码运行 / 打包成 exe"两种模式下的路径差异。

背景问题：
    项目里原先各模块都用 `os.path.dirname(os.path.abspath(__file__))` 推算项目根，
    这在源码运行时没问题；但 PyInstaller --onefile 打包后，`__file__` 指向的是
    临时解压目录（sys._MEIPASS），程序退出即被清理 —— 导致：
        - 知识库 / 进度 / 画像 / 缓存 写进去就丢
        - 用户下次打开发现数据全没了

解决方案（两类路径分开处理）：

    1. 只读资源 resource_path()
       - 随程序分发、不修改的文件（如种子 knowledge.json）
       - 打包后：sys._MEIPASS 下
       - 源码运行：项目根目录

    2. 可写数据 data_dir()
       - settings.json / progress.json / cache.json / trace.log / exports/
       - 打包后：优先 exe 同目录的 data/（便携式，用户看得到自己的数据）
       - 若 exe 目录不可写（放在 Program Files、只读介质等）：
         自动回退到 ~/.study-liu/data/
       - 源码运行：项目根的 data/

使用方式：
    from core.paths import data_dir, data_path, resource_path

    path = data_path("progress.json")          # 可写文件
    seed = resource_path("data", "knowledge.json")   # 只读种子
"""

from __future__ import annotations

import os
import sys

# 缓存：避免每次都做一次写权限探测
_CACHED_DATA_DIR: str | None = None


# ============================================================
# 运行模式判断
# ============================================================
def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出来的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


def is_windows() -> bool:
    return sys.platform == "win32"


# ============================================================
# 应用基准目录
# ============================================================
def app_root() -> str:
    """应用的"基准目录"。

    - 打包后：exe 所在目录（用户能看到、可写）
    - 源码运行：项目根目录（core/ 的上一级）
    """
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # core/paths.py → core/ → 项目根
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundle_dir() -> str:
    """打包后的临时解压目录（只读资源都在这里）；源码运行时 = 项目根。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", app_root())
    return app_root()


# ============================================================
# 只读资源路径
# ============================================================
def resource_path(*parts: str) -> str:
    """拼出只读资源的绝对路径（打包后指向 _MEIPASS）。

    Args:
        *parts: 相对路径片段，如 resource_path("data", "knowledge.json")

    Returns:
        绝对路径字符串
    """
    return os.path.join(bundle_dir(), *parts)


# ============================================================
# 可写数据目录
# ============================================================
def _is_writable(path: str) -> bool:
    """探测目录是否可写（不存在则尝试创建）。"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def data_dir() -> str:
    """可写数据目录（带不可写回退），结果会被缓存。

    优先级：
        1. <exe 同目录>/data      （便携式，源码运行 = 项目/data）
        2. ~/.study-liu/data      （exe 目录不可写时的回退）
    """
    global _CACHED_DATA_DIR
    if _CACHED_DATA_DIR:
        return _CACHED_DATA_DIR

    primary = os.path.join(app_root(), "data")
    if _is_writable(primary):
        _CACHED_DATA_DIR = primary
        return primary

    # 回退：用户主目录
    fallback = os.path.join(os.path.expanduser("~"), ".study-liu", "data")
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    _CACHED_DATA_DIR = fallback
    return fallback


def data_path(*parts: str) -> str:
    """拼出可写数据文件的绝对路径。

    用法：
        data_path("progress.json")
        data_path("exports", "我的课程.md")
    """
    return os.path.join(data_dir(), *parts)


def reset_cache() -> None:
    """清空路径缓存（主要为测试服务）。"""
    global _CACHED_DATA_DIR
    _CACHED_DATA_DIR = None


# ============================================================
# 种子资源：首次运行时把打包进来的初始数据拷到可写目录
# ============================================================
def ensure_seed_file(filename: str, subdir: str = "data") -> str | None:
    """确保可写目录下存在 filename；若不存在，从打包资源里拷一份种子。

    场景：
        exe 打包时把 data/knowledge.json 作为初始内容带进去；
        用户第一次运行（或换台电脑）时，自动落到可写的 data/ 目录，
        避免"知识库一片空白"。

    Returns:
        目标文件路径；源种子不存在时返回 None（不报错）。
    """
    import shutil

    target = data_path(filename)
    if os.path.exists(target):
        return target

    seed = resource_path(subdir, filename)
    if not os.path.exists(seed):
        return None

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(seed, target)
        return target
    except Exception:
        return None
