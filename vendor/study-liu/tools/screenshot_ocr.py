"""截图识别 —— v19 第三梯队 #13-B。

设计：
- 友好依赖降级：
    - EasyOCR 优先（易装、纯 Python）
    - pytesseract 兜底（精度高，但需要系统装 tesseract.exe）
    - 都没有则用占位符（不崩，提示用户安装）
- 单例 reader：避免每次都重新加载模型（OCR 模型很大）
- 提供：
        - extract_text_from_image(path) → str    # OCR 主体
        - is_ocr_available() → bool               # 检测依赖
        - get_supported_formats() → list         # 支持的图片格式
        - format_ocr_for_llm(...) → str          # 把 OCR 结果拼成 prompt
- 与 LLM 集成：调用 core/llm.py 的 chat() 来讲解

工作流程：
    [图片] → extract_text_from_image() → [OCR 文本]
                                              ↓
                                     format_ocr_for_llm()
                                              ↓
                                     [讲解放入 prompt]
                                              ↓
                                      LLM.chat(prompt)
                                              ↓
                                         [讲解结果]
"""

from __future__ import annotations

import os
import threading
from typing import Any

# ============================================================
# 可选依赖：EasyOCR / pytesseract / PIL
# ============================================================
_HAS_EASYOCR = False
_HAS_TESSERACT = False
_HAS_PIL = False

try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    easyocr = None

try:
    import pytesseract
    from PIL import Image
    _HAS_TESSERACT = True
    _HAS_PIL = True
except ImportError:
    pytesseract = None
    Image = None

try:
    from PIL import Image as PILImage
    if not _HAS_PIL:
        _HAS_PIL = True
        Image = PILImage
except ImportError:
    pass


# ============================================================
# OCR Reader 单例
# ============================================================
_READER: Any = None
_READER_LOCK = threading.Lock()
_READER_BACKEND_NAME: str = ""


def _get_reader():
    """懒加载 OCR reader（优先 EasyOCR，其次 pytesseract）。"""
    global _READER, _READER_BACKEND_NAME
    with _READER_LOCK:
        if _READER is not None:
            return _READER

        if _HAS_EASYOCR:
            try:
                # 中文 + 英文双语，第一次会下载到 ~/.EasyOCR/
                _READER = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
                _READER_BACKEND_NAME = "easyocr"
                return _READER
            except Exception:
                _READER = None

        # 兜底用 pytesseract
        if _HAS_TESSERACT:
            _READER_BACKEND_NAME = "pytesseract"
            return _READER

        # 都没装
        _READER_BACKEND_NAME = "none"
        return None


# ============================================================
# 状态查询
# ============================================================
def is_ocr_available() -> bool:
    """OCR 是否可用（任意后端就绪）。"""
    return _HAS_EASYOCR or _HAS_TESSERACT


def get_backend_name() -> str:
    """当前 OCR 后端名。"""
    if _READER_BACKEND_NAME:
        return _READER_BACKEND_NAME
    if _HAS_EASYOCR:
        return "easyocr"
    if _HAS_TESSERACT:
        return "pytesseract"
    return "none"


def get_supported_formats() -> list[str]:
    """支持的文件扩展名。"""
    return [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".gif"]


# ============================================================
# 主入口：OCR 识别
# ============================================================
def extract_text_from_image(image_path: str) -> dict:
    """从图片提取文字。

    Returns:
        dict {
            "text": str,          # 拼接好的纯文本（按行）
            "blocks": list,       # 每行：[(text, bbox, confidence)]
            "backend": str,       # 使用的 OCR 后端
            "image_size": (w, h),
        }
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在：{image_path}")

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in get_supported_formats():
        raise ValueError(
            f"不支持的图片格式：{ext}（支持：{get_supported_formats()}）",
        )

    if not is_ocr_available():
        return {
            "text": "",
            "blocks": [],
            "backend": "none",
            "image_size": (0, 0),
            "error": "OCR 未安装：pip install easyocr（或 pip install pytesseract + 系统装 tesseract）",
        }

    # 优先 EasyOCR
    if _HAS_EASYOCR:
        try:
            return _extract_with_easyocr(image_path)
        except Exception as e:
            # 失败不直接 raise —— 兜底用 tesseract 或返回空
            if _HAS_TESSERACT:
                try:
                    return _extract_with_tesseract(image_path)
                except Exception:
                    pass
            return {
                "text": "",
                "blocks": [],
                "backend": "easyocr-failed",
                "image_size": (0, 0),
                "error": f"OCR 失败：{e}",
            }

    # 退到 tesseract
    return _extract_with_tesseract(image_path)


def _extract_with_easyocr(image_path: str) -> dict:
    """用 EasyOCR 识别。"""
    reader = _get_reader()
    if reader is None:
        raise RuntimeError("EasyOCR reader 未就绪")

    results = reader.readtext(image_path)

    blocks = []
    lines = []
    for bbox, text, conf in results:
        blocks.append({"text": text, "bbox": bbox, "confidence": conf})
        lines.append(text)

    # 获取图片尺寸
    w, h = 0, 0
    try:
        from PIL import Image as _Img
        with _Img.open(image_path) as im:
            w, h = im.size
    except Exception:
        pass

    return {
        "text": "\n".join(lines),
        "blocks": blocks,
        "backend": "easyocr",
        "image_size": (w, h),
    }


def _extract_with_tesseract(image_path: str) -> dict:
    """用 pytesseract 识别（要求系统装 tesseract）。"""
    if not _HAS_TESSERACT:
        raise RuntimeError("pytesseract 不可用")

    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    # pytesseract 不直接给 bbox；构造伪 blocks
    blocks = [
        {"text": line, "bbox": None, "confidence": 1.0}
        for line in text.splitlines() if line.strip()
    ]

    return {
        "text": text,
        "blocks": blocks,
        "backend": "pytesseract",
        "image_size": img.size,
    }


# ============================================================
# 格式化 OCR 结果 → LLM prompt
# ============================================================
def format_ocr_for_llm(
    ocr_result: dict,
    user_hint: str = "",
) -> str:
    """把 OCR 结果组装成适合丢给 LLM 的 prompt。

    Args:
        ocr_result: extract_text_from_image 的返回值
        user_hint: 用户附加的提示（如 "请重点讲公式部分"）

    Returns:
        拼好的 prompt 字符串
    """
    text = ocr_result.get("text", "").strip()
    if not text:
        return "（OCR 没有识别到任何文字）"

    n_lines = len([l for l in text.splitlines() if l.strip()])
    backend = ocr_result.get("backend", "unknown")

    parts = [
        f"我刚才用 {backend} 从一张图片里识别出以下文字（共 {n_lines} 行）：",
        "```",
        text,
        "```",
        "",
        "请你帮我讲解一下：",
        "- 这段文字主要讲的是什么？",
        "- 关键概念 / 公式 / 步骤 是什么？",
        "- 如果是错题，讲解正确的思路。",
    ]
    if user_hint:
        parts.insert(-2, f"用户特别关注：{user_hint}")
    parts.append("用通俗易懂的中文讲解，结构清晰。")
    return "\n".join(parts)


# ============================================================
# LLM 讲解（可选步骤）
# ============================================================
def explain_with_llm(
    ocr_result: dict,
    user_hint: str = "",
    llm_chat_fn=None,
) -> dict:
    """调用 LLM 讲解 OCR 结果。

    Args:
        ocr_result: extract_text_from_image 返回值
        user_hint: 用户附加提示
        llm_chat_fn: 外部传入的 chat(messages) 函数
                     默认用 core.llm.chat

    Returns:
        dict {"answer": str, "prompt": str, "source": str}
    """
    if llm_chat_fn is None:
        try:
            from core.llm import chat
            llm_chat_fn = chat
        except Exception:
            llm_chat_fn = None

    prompt = format_ocr_for_llm(ocr_result, user_hint=user_hint)

    if llm_chat_fn is None:
        return {
            "answer": "LLM 不可用。请检查 settings.json 中的 provider/api_key。",
            "prompt": prompt,
            "source": "no-llm",
        }

    try:
        # 用 chat(messages) 接口，传一个简单 user message
        messages = [{"role": "user", "content": prompt}]
        result = llm_chat_fn(messages)
        answer = (
            result.get("answer", "")
            if isinstance(result, dict)
            else str(result)
        )
        return {
            "answer": answer,
            "prompt": prompt,
            "source": result.get("source", "llm") if isinstance(result, dict) else "llm",
        }
    except Exception as e:
        return {
            "answer": f"LLM 调用失败：{e}",
            "prompt": prompt,
            "source": "error",
        }


# ============================================================
# 测试辅助：mock 后端
# ============================================================
class MockOCRBackend:
    """测试用 mock OCR —— 返回固定字符串，跳过真实 OCR。"""

    def __init__(self, fake_text: str = "Mock OCR 文字"):
        self.fake_text = fake_text

    def __call__(self, image_path: str) -> dict:
        return {
            "text": self.fake_text,
            "blocks": [{"text": line, "bbox": None, "confidence": 0.99}
                       for line in self.fake_text.splitlines()],
            "backend": "mock",
            "image_size": (100, 100),
        }