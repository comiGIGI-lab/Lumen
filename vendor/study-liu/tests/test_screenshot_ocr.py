"""screenshot_ocr 模块测试 —— v19 第三梯队 #13-B。

覆盖：
- 后端检测
- format_ocr_for_llm prompt 组装
- explain_with_llm 调用链
- 文件不存在 / 格式错误的容错
- OCR 不可用时的 graceful fallback
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

from tools.screenshot_ocr import (
    is_ocr_available,
    get_backend_name,
    get_supported_formats,
    extract_text_from_image,
    format_ocr_for_llm,
    explain_with_llm,
    MockOCRBackend,
)


# ============================================================
# 后端检测 / 工具
# ============================================================
class TestBackendDetection:
    def test_is_ocr_available_returns_bool(self):
        assert isinstance(is_ocr_available(), bool)

    def test_get_backend_name_returns_str(self):
        assert isinstance(get_backend_name(), str)
        assert get_backend_name() in ("easyocr", "pytesseract", "none")

    def test_supported_formats(self):
        fmts = get_supported_formats()
        assert isinstance(fmts, list)
        assert ".png" in fmts
        assert ".jpg" in fmts


# ============================================================
# OCR 输入校验
# ============================================================
class TestInputValidation:
    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            extract_text_from_image("/no/such/file.png")

    def test_unsupported_format(self, tmp_path):
        # 创建文件（后缀对，但实际内容无所谓 —— 我们在格式检查时就抛错）
        bad = tmp_path / "file.xyz"
        bad.write_text("fake")
        with pytest.raises(ValueError, match="不支持的图片格式"):
            extract_text_from_image(str(bad))

    def test_case_insensitive_extension(self, tmp_path):
        # .PNG 大写也应识别
        bad = tmp_path / "file.PNG"
        bad.write_text("fake")
        # 不应该报"格式错误"，应该走到 OCR
        # 如果 OCR 没装，会返回 error 字段，不会抛异常
        try:
            r = extract_text_from_image(str(bad))
        except (FileNotFoundError, ValueError) as e:
            # 我们只关心格式检查通过
            if "格式" in str(e):
                pytest.fail(f"大写扩展名应被识别：{e}")
            else:
                raise


# ============================================================
# OCR 不可用时的 graceful fallback
# ============================================================
class TestGracefulFallback:
    def test_unavailable_returns_error_field(self, tmp_path, monkeypatch):
        # 强制 OCR 不可用
        monkeypatch.setattr("tools.screenshot_ocr._HAS_EASYOCR", False)
        monkeypatch.setattr("tools.screenshot_ocr._HAS_TESSERACT", False)
        monkeypatch.setattr("tools.screenshot_ocr._READER", None)

        img = tmp_path / "test.png"
        img.write_bytes(b"fake png data")

        result = extract_text_from_image(str(img))
        assert result["text"] == ""
        assert result["backend"] == "none"
        assert "error" in result


# ============================================================
# Prompt 组装
# ============================================================
class TestFormatPrompt:
    def test_basic(self):
        ocr = {"text": "牛顿第二定律\nF = ma", "backend": "easyocr"}
        prompt = format_ocr_for_llm(ocr)
        assert "牛顿第二定律" in prompt
        assert "F = ma" in prompt
        assert "easyocr" in prompt
        assert "讲解" in prompt

    def test_with_user_hint(self):
        ocr = {"text": "abc", "backend": "x"}
        prompt = format_ocr_for_llm(ocr, user_hint="请重点讲公式")
        assert "公式" in prompt

    def test_empty_text(self):
        ocr = {"text": "", "backend": "x"}
        prompt = format_ocr_for_llm(ocr)
        # 没有文字时也应友好提示
        assert "没有识别到任何文字" in prompt

    def test_whitespace_only_text(self):
        ocr = {"text": "   \n  \n  ", "backend": "x"}
        prompt = format_ocr_for_llm(ocr)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_default_backend_missing(self):
        ocr = {"text": "abc"}   # 没有 backend 字段
        prompt = format_ocr_for_llm(ocr)
        assert "unknown" in prompt


# ============================================================
# LLM 集成（mock chat 函数）
# ============================================================
class TestExplainWithLLM:
    def test_with_mock_llm(self):
        ocr = {"text": "测试文本", "backend": "mock"}

        def mock_chat(messages):
            return {"answer": "这是 AI 的讲解", "source": "llm"}

        result = explain_with_llm(ocr, llm_chat_fn=mock_chat)
        assert result["answer"] == "这是 AI 的讲解"
        assert result["source"] == "llm"
        assert "prompt" in result
        assert "测试文本" in result["prompt"]

    def test_llm_returns_string(self):
        ocr = {"text": "abc"}

        def mock_chat(messages):
            return "纯字符串"

        result = explain_with_llm(ocr, llm_chat_fn=mock_chat)
        assert result["answer"] == "纯字符串"

    def test_llm_failure_caught(self):
        ocr = {"text": "abc"}

        def mock_chat(messages):
            raise RuntimeError("network down")

        result = explain_with_llm(ocr, llm_chat_fn=mock_chat)
        assert "失败" in result["answer"]
        assert result["source"] == "error"

    def test_no_llm_fn_graceful(self, monkeypatch):
        # 模拟 core.llm 不可用
        import tools.screenshot_ocr as soc
        # monkeypatch 让 from core.llm import chat 失败
        monkeypatch.setattr(soc, "chat", None, raising=False)

        # 让 import 抛异常
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "core.llm":
                raise ImportError("mocked")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        ocr = {"text": "abc"}
        result = explain_with_llm(ocr)
        # 没 LLM 时应给清晰提示，不崩
        assert isinstance(result["answer"], str)
        assert "LLM" in result["answer"] or "API" in result["answer"]


# ============================================================
# MockOCRBackend
# ============================================================
class TestMockBackend:
    def test_basic(self):
        backend = MockOCRBackend("Hello\nWorld")
        result = backend("any_path.png")
        assert "Hello" in result["text"]
        assert "World" in result["text"]
        assert result["backend"] == "mock"
        assert len(result["blocks"]) == 2

    def test_default_text(self):
        backend = MockOCRBackend()
        result = backend("any.png")
        assert "Mock OCR" in result["text"]

    def test_image_size(self):
        backend = MockOCRBackend("x")
        result = backend("any.png")
        assert result["image_size"] == (100, 100)


# ============================================================
# Mock OCR 完整流程
# ============================================================
class TestEndToEndWithMock:
    def test_full_flow(self, tmp_path, monkeypatch):
        """用 MockOCRBackend 跑完整流程。"""
        # 创建一个假图片文件（mock 后端不看内容）
        img = tmp_path / "demo.png"
        img.write_bytes(b"fake png bytes")

        # monkeypatch OCR 函数用 mock 后端
        import tools.screenshot_ocr as soc
        backend = MockOCRBackend("勾股定理\na² + b² = c²")

        def fake_extract(path):
            return backend(path)

        monkeypatch.setattr(soc, "extract_text_from_image", fake_extract)

        # 调用：OCR
        ocr = soc.extract_text_from_image(str(img))
        assert "勾股定理" in ocr["text"]

        # 调用：拼 prompt
        prompt = soc.format_ocr_for_llm(ocr)
        assert "勾股定理" in prompt
        assert "a² + b² = c²" in prompt

        # 调用：LLM 讲解（mock chat）
        def mock_chat(messages):
            return {"answer": "勾股定理描述了直角三角形三边的关系。", "source": "llm"}

        result = soc.explain_with_llm(ocr, llm_chat_fn=mock_chat)
        assert "勾股定理描述了" in result["answer"]