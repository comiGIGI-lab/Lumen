"""配置优先级测试。

根据 docs/core/config.py：
    1. data/settings.json（最高）
    2. 系统环境变量（os.environ）
    3. .env 文件（启动时已读）
    4. 默认值（mock / "" / 默认 URL / 默认 model）

注意：config.py 在 import 阶段就 load_dotenv，所以 .env 一旦 import 就固定。
我们用 monkeypatch + 自定义 settings 路径测试层级关系。
"""

import json
import os
import sys

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# 直接 import core.config —— 副作用是 load_dotenv 在 import 时执行一次
import core.config as config


@pytest.fixture
def custom_settings_path(tmp_path, monkeypatch):
    """把 settings.json 路径换成临时目录的，每次测试独立。"""
    settings_file = tmp_path / "settings.json"
    # monkeypatch 私有函数 _get_settings_path
    monkeypatch.setattr(
        config, "_get_settings_path", lambda: str(settings_file),
    )
    return settings_file


@pytest.fixture
def clean_env(monkeypatch):
    """清空所有 LLM_* 环境变量，避免污染测试。"""
    for key in ["LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]:
        monkeypatch.delenv(key, raising=False)


# ==========================================================
# 默认值（无 settings.json / 无环境变量）
# ==========================================================
def test_default_provider_is_mock(clean_env, custom_settings_path):
    assert config.get_provider() == "mock"


def test_default_api_key_empty(clean_env, custom_settings_path):
    assert config.get_api_key() == ""


def test_default_base_url_is_deepseek(clean_env, custom_settings_path):
    """未配置时默认 base_url 是 DeepSeek。"""
    assert "deepseek" in config.get_base_url().lower()


def test_default_model_is_deepseek_chat(clean_env, custom_settings_path):
    assert config.get_model() == "deepseek-chat"


def test_is_mock_when_default(clean_env, custom_settings_path):
    assert config.is_mock() is True


# ==========================================================
# settings.json 优先于环境变量
# ==========================================================
def test_settings_overrides_env_provider(monkeypatch, custom_settings_path):
    # 写 settings.json
    custom_settings_path.write_text(
        json.dumps({
            "provider": "llm",
            "api_key": "settings-key",
            "base_url": "https://from-settings",
            "model": "settings-model",
        }),
        encoding="utf-8",
    )
    # 环境变量也给一个不同的值
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://from-env")
    monkeypatch.setenv("LLM_MODEL", "env-model")

    assert config.get_provider() == "llm"
    assert config.get_api_key() == "settings-key"
    assert config.get_base_url() == "https://from-settings"
    assert config.get_model() == "settings-model"
    assert config.is_mock() is False


# ==========================================================
# 环境变量回退（无 settings.json）
# ==========================================================
def test_env_fallback_when_no_settings(monkeypatch, custom_settings_path):
    # 没有 settings.json（custom_settings_path 还没写文件）
    monkeypatch.setenv("LLM_PROVIDER", "llm")
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://env")
    monkeypatch.setenv("LLM_MODEL", "env-model")

    assert config.get_provider() == "llm"
    assert config.get_api_key() == "env-key"
    assert config.get_base_url() == "https://env"
    assert config.get_model() == "env-model"


# ==========================================================
# settings.json 部分字段 + 环境变量补全
# ==========================================================
def test_settings_partial_overrides_only_those_fields(
    monkeypatch, custom_settings_path,
):
    """settings.json 只写 provider，其他字段由环境变量补。"""
    custom_settings_path.write_text(
        json.dumps({"provider": "llm"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_API_KEY", "env-key")

    assert config.get_provider() == "llm"            # 来自 settings
    assert config.get_api_key() == "env-key"          # 来自 env
    # base_url 和 model 是空 settings → 走 env → 没有 → 默认
    assert "deepseek" in config.get_base_url().lower()


# ==========================================================
# save_settings + load_settings 往返
# ==========================================================
def test_save_and_load_roundtrip(custom_settings_path):
    path = config.save_settings(
        provider="llm", api_key="key",
        base_url="https://x", model="m",
    )
    assert path == str(custom_settings_path)
    loaded = config.load_settings()
    assert loaded["provider"] == "llm"
    assert loaded["api_key"] == "key"


def test_save_settings_creates_parent_dir(tmp_path, monkeypatch):
    nested = tmp_path / "a" / "b" / "settings.json"
    monkeypatch.setattr(config, "_get_settings_path", lambda: str(nested))
    config.save_settings(provider="mock", api_key="", base_url="", model="")
    assert nested.exists()


# ==========================================================
# 损坏的 settings.json 不崩
# ==========================================================
def test_corrupt_settings_returns_empty(clean_env, custom_settings_path):
    custom_settings_path.write_text("not json {{{", encoding="utf-8")
    # load_settings 返回空 dict，getter 回退到默认值
    assert config.load_settings() == {}
    assert config.get_provider() == "mock"


# ==========================================================
# get_mode_label
# ==========================================================
def test_get_mode_label_mock(clean_env, custom_settings_path):
    label, mode = config.get_mode_label()
    assert mode == "mock"
    assert "Mock" in label


def test_get_mode_label_llm(clean_env, custom_settings_path):
    custom_settings_path.write_text(
        json.dumps({
            "provider": "llm",
            "model": "gpt-4o-mini",
        }),
        encoding="utf-8",
    )
    label, mode = config.get_mode_label()
    assert mode == "llm"
    assert "gpt-4o-mini" in label