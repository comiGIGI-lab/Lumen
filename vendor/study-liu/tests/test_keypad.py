"""keypad 模块测试 —— v19 第三梯队 #10。

覆盖：
- 加密/解密往返
- is_encrypted 检测
- 篡改检测（GCM tag）
- 明文向后兼容
- settings.json 自动迁移
- mask_key 遮蔽
- 无 cryptography 时的兜底
"""

import base64
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from tools.keypad import (
    encrypt_value,
    decrypt_value,
    is_encrypted,
    has_crypto_lib,
    maybe_migrate_settings,
    mask_key,
    get_secret_fields,
)


# 测试用 keypass
TEST_KEYPASS = "test-keypass-do-not-use-in-prod"


class TestRoundTrip:
    """加密-解密往返测试。"""

    def test_basic(self):
        pt = "sk-1234567890abcdef"
        ct = encrypt_value(pt, keypass=TEST_KEYPASS)
        assert is_encrypted(ct)
        assert decrypt_value(ct, keypass=TEST_KEYPASS) == pt

    def test_long_string(self):
        pt = "x" * 10000
        ct = encrypt_value(pt, keypass=TEST_KEYPASS)
        assert decrypt_value(ct, keypass=TEST_KEYPASS) == pt

    def test_unicode(self):
        pt = "中文 key：🎉 emoji"
        ct = encrypt_value(pt, keypass=TEST_KEYPASS)
        assert decrypt_value(ct, keypass=TEST_KEYPASS) == pt

    def test_empty_string(self):
        ct = encrypt_value("", keypass=TEST_KEYPASS)
        assert decrypt_value(ct, keypass=TEST_KEYPASS) == ""

    def test_none_becomes_empty(self):
        ct = encrypt_value(None, keypass=TEST_KEYPASS)
        assert decrypt_value(ct, keypass=TEST_KEYPASS) == ""


class TestEncryptedDetection:
    """is_encrypted 检测测试。"""

    def test_encrypted_value(self):
        assert is_encrypted("enc:v1:abc123")

    def test_plaintext_value(self):
        assert not is_encrypted("sk-1234")

    def test_empty_string(self):
        assert not is_encrypted("")


class TestKeyDerivation:
    """派生密钥测试。"""

    def test_wrong_keypass_gives_empty(self):
        ct = encrypt_value("secret", keypass=TEST_KEYPASS)
        result = decrypt_value(ct, keypass="wrong-keypass")
        assert result == ""   # 认证失败，返回空

    def test_two_encryptions_are_different(self):
        """每次加密应使用新的 salt+nonce，所以密文不同。"""
        pt = "same plaintext"
        ct1 = encrypt_value(pt, keypass=TEST_KEYPASS)
        ct2 = encrypt_value(pt, keypass=TEST_KEYPASS)
        assert ct1 != ct2
        # 但解密结果相同
        assert decrypt_value(ct1, keypass=TEST_KEYPASS) == pt
        assert decrypt_value(ct2, keypass=TEST_KEYPASS) == pt


class TestTamperDetection:
    """篡改检测（GCM tag）。"""

    @pytest.mark.skipif(not has_crypto_lib(), reason="需要 cryptography 库")
    def test_tampered_ciphertext_fails(self):
        ct = encrypt_value("secret-data", keypass=TEST_KEYPASS)
        # 改一个字符
        tampered = ct[:-2] + ("A" if ct[-1] != "A" else "B") + ct[-1]
        assert decrypt_value(tampered, keypass=TEST_KEYPASS) == ""

    @pytest.mark.skipif(not has_crypto_lib(), reason="需要 cryptography 库")
    def test_truncated_ciphertext_fails(self):
        ct = encrypt_value("secret-data", keypass=TEST_KEYPASS)
        truncated = ct[:len(ct) // 2]
        # 解密失败或为空
        result = decrypt_value(truncated, keypass=TEST_KEYPASS)
        assert result == "" or result != "secret-data"


class TestPlaintextBackwardCompat:
    """明文向后兼容。"""

    def test_plaintext_passes_through(self):
        assert decrypt_value("plaintext-key", keypass=TEST_KEYPASS) == "plaintext-key"

    def test_legacy_settings_loads_correctly(self):
        """模拟 v18 时代的明文 settings.json。

        迁移使用默认 keypass（_get_keypass()），所以测试中也必须用
        同样的默认 keypass 才能解出。
        """
        from tools.keypad import _get_keypass
        legacy = {
            "provider": "llm",
            "api_key": "sk-old-plain-1234",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        }
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump(legacy, f)
            path = f.name
        try:
            migrated, data = maybe_migrate_settings(path)
            assert migrated is True
            assert is_encrypted(data["api_key"])
            # 加密后还能解出 —— 用同一个默认 keypass
            assert decrypt_value(data["api_key"], keypass=_get_keypass()) == "sk-old-plain-1234"
            # 其他字段不变
            assert data["provider"] == "llm"
            assert data["base_url"] == "https://api.deepseek.com"
        finally:
            os.unlink(path)


class TestMigration:
    """迁移测试。"""

    def test_no_settings_file(self):
        """settings.json 不存在时不报错。"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            migrated, data = maybe_migrate_settings(path)
            assert migrated is False
            assert data == {}

    def test_already_encrypted_no_double_encrypt(self):
        """已加密的不重复加密。"""
        ct = encrypt_value("sk-secret", keypass=TEST_KEYPASS)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"api_key": ct, "provider": "llm"}, f)
            path = f.name
        try:
            migrated, data = maybe_migrate_settings(path)
            assert migrated is False
            # 仍然能解出
            assert decrypt_value(data["api_key"], keypass=TEST_KEYPASS) == "sk-secret"
        finally:
            os.unlink(path)

    def test_migrated_file_is_atomic(self):
        """迁移后文件可读、内容正确。"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            json.dump({"api_key": "sk-plain", "provider": "mock"}, f)
            path = f.name
        try:
            maybe_migrate_settings(path)
            with open(path, "r", encoding="utf-8") as f:
                new = json.load(f)
            assert is_encrypted(new["api_key"])
            assert new["provider"] == "mock"
        finally:
            os.unlink(path)

    def test_corrupted_settings_no_crash(self):
        """settings.json 损坏时不应崩。"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8",
        ) as f:
            f.write("not json {")
            path = f.name
        try:
            migrated, data = maybe_migrate_settings(path)
            assert migrated is False
            assert data == {}
        finally:
            os.unlink(path)


class TestMaskKey:
    """Key 遮蔽测试（用于 UI 显示）。"""

    def test_normal_key(self):
        masked = mask_key("sk-1234567890abcdef")
        # sk-1 + 8 个 * + cdef = "sk-1********cdef"
        assert masked.startswith("sk-1")
        assert masked.endswith("cdef")
        assert "*" in masked
        assert len(masked) == len("sk-1234567890abcdef")

    def test_short_key(self):
        masked = mask_key("abc")
        assert masked == "***"

    def test_exact_boundary(self):
        masked = mask_key("abcd")   # head=4 + tail=4 = 8 > 4
        assert masked == "****"

    def test_empty_key(self):
        assert mask_key("") == ""

    def test_custom_head_tail(self):
        # "sk-abcdefghij" 长度 = 13，head=2 + tail=2，中间 = 13-4 = 9 个 *
        masked = mask_key("sk-abcdefghij", head=2, tail=2)
        assert masked == "sk*********ij"
        assert len(masked) == 13


class TestSecretFields:
    """get_secret_fields 测试。"""

    def test_includes_api_key(self):
        fields = get_secret_fields()
        assert "api_key" in fields

    def test_returns_list(self):
        assert isinstance(get_secret_fields(), list)