"""i18n 国际化 —— v19 第三梯队 #9。

设计原则：
- **零外部依赖**：纯 stdlib，避免引入 gettext/babel 等重依赖
- **后向兼容**：默认中文，未初始化时一切照旧
- **简单切换**：`set_language("en")` 一行生效
- **支持占位符**：`t("生成 {n} 章", n=3)` 自动格式化
- **懒加载**：首次调用时才加载模块
- **线程安全**：用 threading.Lock 保护切换

模块结构：
- `i18n/zh.py`：中文文案
- `i18n/en.py`：英文文案
- `i18n/__init__.py`：本文件，提供 t() / set_language() / get_language() 等 API
"""

import threading
from typing import Any

_lock = threading.Lock()
_LANGUAGE = "zh"   # 当前语言
_FALLBACK = "zh"   # 兜底语言（一般保持中文，避免英文翻译缺失时炸 UI）


def set_language(name: str) -> None:
    """切换全局语言。

    Args:
        name: "zh" / "en"
    """
    global _LANGUAGE
    with _lock:
        if name not in ("zh", "en"):
            return   # 未知语言静默忽略，保持当前
        _LANGUAGE = name


def get_language() -> str:
    """当前语言标识。"""
    return _LANGUAGE


def get_available_languages() -> list[str]:
    """可用语言列表。"""
    return ["zh", "en"]


def _load(lang: str) -> dict[str, str]:
    """懒加载某个语言模块的字典。"""
    if lang == "zh":
        from i18n import zh as mod
    elif lang == "en":
        from i18n import en as mod
    else:
        # 兜底用中文，避免 KeyError
        from i18n import zh as mod
    # 取模块内所有字符串 / 列表属性
    # 注：list 类型用于 HELP_SECTIONS、SETTINGS_TIPS 这类多段文案
    return {
        k: getattr(mod, k)
        for k in dir(mod)
        if k.isupper() and isinstance(getattr(mod, k), (str, list))
    }


# 缓存：避免每次 t() 都 import 子模块
_CACHE: dict[str, dict[str, str]] = {}


def t(key: str, **kwargs: Any) -> str:
    """翻译一个 key。

    Args:
        key: 大写常量名，如 "BTN_GENERATE"
        **kwargs: 占位符，如 n=3、name="Python"

    Returns:
        翻译后的字符串。找不到时返回 key 本身（方便调试 + 不会 NPE）。
    """
    with _lock:
        lang = _LANGUAGE
        if lang not in _CACHE:
            _CACHE[lang] = _load(lang)

    text = _CACHE[lang].get(key)
    if text is None:
        # 回退到默认语言
        if _FALLBACK not in _CACHE:
            _CACHE[_FALLBACK] = _load(_FALLBACK)
        text = _CACHE[_FALLBACK].get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def clear_cache() -> None:
    """清空缓存（测试用）。"""
    with _lock:
        _CACHE.clear()