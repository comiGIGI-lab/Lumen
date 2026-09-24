# vision_ocr.py — 用「多模态大模型」做图片文字识别（替代本地 OCR）
#
# 为什么走模型而不是本地 OCR：
#   本地方案（tools/screenshot_ocr.py 的 easyocr / pytesseract）依赖
#   torch 或系统 tesseract —— 前者要 2GB+ 磁盘与大量内存，本项目线上是
#   1.6G 内存的 ECS，装不下也跑不动；后者要在服务器装系统包。
#   而 deepseek-flash 官方支持**图像理解**，一次 API 调用就能识图，
#   不占本地内存、不引入任何依赖，且对复杂版式（表格/公式/手写）比
#   传统 OCR 更稳。缺点是要花钱（图片按 token 计费，但很便宜）。
#
# 接口刻意与 screenshot_ocr.py 保持一致，便于上层统一调度：
#   is_ocr_available() / get_backend_name() / get_supported_formats()
#   extract_text_from_image(path) -> {"text", "backend", "error"}
# 注意：本模块**从不抛异常**，失败一律通过返回值的 error 字段表达 ——
#       与 screenshot_ocr 的契约相同，上层的降级逻辑才好写。

import base64
import os

# 支持的图片格式
_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"]

# 单张图片原始字节上限。base64 会膨胀约 33%，主流网关对单请求体积都有上限，
# 这里守住 4MB（≈5.3MB base64），超了就明确报错而不是让网关返回难懂的 413。
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# 识图的输出上限。转写一张图文混排的图片通常几百字，留 3000 足够。
OCR_MAX_TOKENS = 3000

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}

PROMPT = (
    "请把这张图片里的内容转写为文字，要求：\n"
    "1. 文字**逐字完整**转写，不要概括、不要省略；\n"
    "2. 保持原有的段落、标题层级与列表结构（标题用 Markdown 的 # 表示）；\n"
    "3. 表格用 Markdown 表格还原；\n"
    "4. 数学公式用 LaTeX 写（行内 $...$，独立成行 $$...$$）；\n"
    "5. 若是示意图/流程图，用简洁的文字说明它表达了什么；\n"
    "6. 只输出转写结果本身，不要加「以下是图片内容」这类前后缀。"
)


def get_supported_formats():
    """返回支持的图片扩展名（与 screenshot_ocr 同签名）。"""
    return list(_IMAGE_EXTS)


def get_backend_name():
    """返回当前识图后端名。"""
    return "vision-llm"


def is_ocr_available():
    """是否可用：看是否配了 API Key（模型本身要支持图像理解）。

    这里只做「配置层面」的判断 —— 真正支不支持视觉，要等调用时由网关告知。
    """
    try:
        from core.config import get_api_key, is_mock
        if is_mock():
            return False
        return bool(get_api_key())
    except Exception:
        return False


def _resolve_url():
    """把 base_url 拼成 chat/completions 端点（与 core/llm.py 的规则一致：
    已填完整端点则原样使用，否则补 /chat/completions）。"""
    from core.config import get_base_url
    base = (get_base_url() or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def extract_text_from_image(path):
    """识别图片中的文字。

    返回 {"text": str, "backend": "vision-llm", "error": str|None}
    —— 失败不抛异常，text 为空、error 有说明。
    """
    result = {"text": "", "backend": "vision-llm", "error": None}

    ext = os.path.splitext(path)[1].lower()
    if ext not in _MIME:
        result["error"] = "不支持的图片格式：%s（支持 %s）" % (ext, "/".join(_IMAGE_EXTS))
        return result
    if not os.path.exists(path):
        result["error"] = "图片不存在：%s" % path
        return result

    size = os.path.getsize(path)
    if size > MAX_IMAGE_BYTES:
        result["error"] = "图片过大：%.1f MB（上限 %.0f MB），请压缩后再传" % (
            size / 1048576, MAX_IMAGE_BYTES / 1048576)
        return result
    if size == 0:
        result["error"] = "图片是空文件"
        return result

    try:
        from core.config import get_api_key, get_model
        import requests
    except Exception as e:
        result["error"] = "依赖导入失败：%s" % e
        return result

    key = get_api_key()
    if not key:
        result["error"] = "未配置 API Key，无法用模型识图"
        return result
    model = get_model()

    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        result["error"] = "读取图片失败：%s" % e
        return result

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": "data:%s;base64,%s" % (_MIME[ext], b64)}},
            ],
        }],
        "temperature": 0.2,          # 转写任务要的是稳定，不是创造性
        "max_tokens": OCR_MAX_TOKENS,
    }

    try:
        r = requests.post(
            _resolve_url(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
            json=payload,
            timeout=120,
        )
    except Exception as e:
        result["error"] = "请求失败：%s" % type(e).__name__
        return result

    if r.status_code != 200:
        # 常见情况：当前模型不支持图像理解（v4-pro 就不支持）。把原来的
        # 报错带出去，方便判断是「模型不支持」还是「配额/鉴权」问题。
        detail = (r.text or "")[:200].replace("\n", " ")
        result["error"] = "模型返回 HTTP %s：%s" % (r.status_code, detail)
        return result

    try:
        data = r.json()
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        text = (msg.get("content") or "").strip()
    except Exception as e:
        result["error"] = "解析响应失败：%s" % e
        return result

    if not text:
        result["error"] = (
            "模型没有返回文字（可能是当前模型 %s 不支持图像理解，"
            "可在设置里换成支持视觉的模型）" % model
        )
        return result

    result["text"] = text
    return result


if __name__ == "__main__":
    print("支持的图片格式:", get_supported_formats())
    print("后端:", get_backend_name(), "| 可用:", is_ocr_available())
    print("端点规则测试:")
    print("   (本模块需在项目上下文里运行才有 base_url)")
