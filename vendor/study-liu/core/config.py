# config.py — 配置管理：settings.json > .env > 环境变量

"""配置模块：统一读取 LLM 相关配置。

优先级（从高到低）：
1. data/settings.json（UI 设置面板写入，最高优先级）
2. 系统环境变量
3. exe/脚本同目录的 .env
4. 项目根目录的 .env
5. ~/.studybuddy/.env
6. 找不到则用 mock 兜底
"""

import json
import os
import sys

try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


# ============================================================
# .env 加载（低优先级回退）
# ============================================================
def _find_env_file():
    if not _HAS_DOTENV:
        return None
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, ".env"))
    project_root = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    candidates.append(os.path.join(project_root, ".env"))
    home_env = os.path.join(os.path.expanduser("~"), ".studybuddy", ".env")
    candidates.append(home_env)
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


_env_path = _find_env_file()
if _env_path:
    load_dotenv(_env_path)


# ============================================================
# settings.json 读写（最高优先级）
# ============================================================
def _get_settings_path():
    """返回 settings.json 的路径（统一走 core.paths，打包兼容）。"""
    from core.paths import data_path
    return data_path("settings.json")


# ============================================================
# API Key 加密（v19 第三梯队 #10 接线）
# ============================================================
# 设计原则：**对上层完全透明**
#   - 磁盘上 api_key 存密文（enc:v1:...）
#   - 内存里/调用方拿到的永远是明文
#   - 旧版明文 settings.json 在首次读取时自动加密并原子写回（幂等）
#
# 实现要点：用 (mtime_ns, size) 做读取缓存，避免每次取配置都跑一遍
# PBKDF2-100k（否则一次 get_mode_label() 就要解密 4 次，肉眼可见变卡）。
try:
    from tools.keypad import (
        decrypt_value as _kp_decrypt,
        encrypt_value as _kp_encrypt,
        is_encrypted as _kp_is_encrypted,
    )
    _HAS_KEYPAD = True
except Exception:      # pragma: no cover - 极端情况下退化为明文
    _HAS_KEYPAD = False

    def _kp_encrypt(v):
        return v

    def _kp_decrypt(v):
        return v

    def _kp_is_encrypted(v):
        return False


# path -> (mtime_ns, size, raw_dict)
_RAW_CACHE: dict = {}


def _atomic_write_json(path, data):
    """原子写 JSON（temp + os.replace），避免半写损坏配置文件。"""
    import tempfile
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def _read_raw_settings(path):
    """读取磁盘上的 settings.json（带缓存 + 明文自动加密迁移）。

    Returns:
        磁盘原始内容的 dict 副本（api_key 可能仍是密文）。
    """
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}

    cached = _RAW_CACHE.get(path)
    if cached is not None and (cached[0], cached[1]) == sig:
        return dict(cached[2])

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    # ---- 平滑迁移：明文 api_key → 密文 ----
    raw_key = data.get("api_key")
    if _HAS_KEYPAD and raw_key and not _kp_is_encrypted(raw_key):
        try:
            data["api_key"] = _kp_encrypt(raw_key)
            _atomic_write_json(path, data)
            try:
                st = os.stat(path)
                sig = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        except Exception:
            # 迁移失败：保留明文，绝不让用户打不开应用
            pass

    _RAW_CACHE[path] = (sig[0], sig[1], dict(data))
    return dict(data)


def load_settings():
    """读取 settings.json，返回 dict（api_key 已解密为明文）。

    每次调用都会校验文件 mtime，保证实时性；文件没变则走内存缓存。
    """
    path = _get_settings_path()
    if not os.path.exists(path):
        return {}

    data = _read_raw_settings(path)
    if not data:
        return {}

    # 对上层透明：把密文解密回明文
    if _HAS_KEYPAD and data.get("api_key"):
        try:
            data["api_key"] = _kp_decrypt(data["api_key"])
        except Exception:
            pass
    return data


def save_settings(provider, api_key, base_url, model):
    """保存配置到 settings.json（api_key 落盘前自动加密）。"""
    path = _get_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    stored_key = api_key or ""
    if _HAS_KEYPAD and stored_key and not _kp_is_encrypted(stored_key):
        try:
            stored_key = _kp_encrypt(stored_key)
        except Exception:
            stored_key = api_key

    data = {
        "provider": provider,
        "api_key": stored_key,
        "base_url": base_url,
        "model": model,
    }
    _atomic_write_json(path, data)
    # 主动失效缓存，避免同进程内读到旧值
    _RAW_CACHE.pop(path, None)
    return path


def get_settings_raw():
    """返回磁盘上的原始内容（api_key 为密文），供密钥管理面板展示。"""
    return _read_raw_settings(_get_settings_path())


def get_settings_path():
    """返回 settings.json 路径（供 UI 显示）。"""
    return _get_settings_path()


# ============================================================
# 配置 getter（settings.json > 环境变量 > 默认值）
# ============================================================
def get_provider():
    s = load_settings()
    if s.get("provider"):
        return s["provider"]
    return os.environ.get("LLM_PROVIDER", "mock")


def get_api_key():
    s = load_settings()
    if s.get("api_key"):
        return s["api_key"]
    return os.environ.get("LLM_API_KEY", "")


def get_base_url():
    s = load_settings()
    if s.get("base_url"):
        return s["base_url"]
    return os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")


def get_model():
    s = load_settings()
    if s.get("model"):
        return s["model"]
    return os.environ.get("LLM_MODEL", "deepseek-chat")


def is_mock():
    return get_provider() == "mock"


def get_env_path():
    return _env_path


def get_mode_label():
    """返回当前模式的可读标签（供 UI 显示）。"""
    if is_mock():
        return "Mock 模式", "mock"
    model = get_model()
    return f"LLM 模式 · {model}", "llm"
