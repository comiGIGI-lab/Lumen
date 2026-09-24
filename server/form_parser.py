# multipart.py — multipart/form-data 解析（纯标准库，无第三方依赖）
#
# 为什么要手写：
#   1. server/ 刻意保持零第三方依赖；
#   2. Python 3.13 已经**移除了 cgi 模块**，原来的 cgi.FieldStorage 不能再用了；
#   3. 请求体上限、文件数量、单文件大小都要自己控（_read_body 本身没有上限）。
#
# 用到的只有标准库的 bytes.split —— 这正是 multipart 的设计前提：
# 浏览器会挑一个**不会出现在文件内容里**的 boundary，所以按 boundary 切分是安全的。

import re
import urllib.parse

# ---------- 上限（超过就拒绝，避免一次上传把内存/磁盘吃满）----------
MAX_TOTAL = 20 * 1024 * 1024      # 整个请求体 20MB
MAX_FILE = 16 * 1024 * 1024       # 单个文件 16MB
MAX_FILES = 10                    # 一次最多 10 个文件
MAX_FIELD = 8 * 1024              # 普通文本字段 8KB

_BOUNDARY_RE = re.compile(rb'boundary="?([^";]+)"?')
_NAME_RE = re.compile(r'name="([^"]*)"')
_FILENAME_RE = re.compile(r'filename="([^"]*)"')
# RFC 5987 形式：filename*=UTF-8''%E4%B8%AD%E6%96%87.pdf
_FILENAME_STAR_RE = re.compile(r"filename\*\s*=\s*([^;\r\n]+)")


class MultipartError(ValueError):
    """请求体不是合法的 multipart，或超过上限。"""


def get_boundary(content_type):
    """从 Content-Type 里取出 boundary（返回带 -- 前缀的 bytes，便于直接 split）。"""
    if not content_type or "multipart/form-data" not in content_type.lower():
        raise MultipartError("不是 multipart/form-data 请求")
    m = _BOUNDARY_RE.search(content_type.encode("latin-1", "ignore"))
    if not m:
        raise MultipartError("Content-Type 里缺少 boundary")
    boundary = m.group(1).strip()
    if not boundary:
        raise MultipartError("boundary 为空")
    return b"--" + boundary


def _decode_header(raw):
    """头部按 UTF-8 解，失败再退 GBK / latin-1。

    浏览器上传中文文件名时，Content-Disposition 里的字节通常是 UTF-8 原样
    （而不是 RFC 5987 编码），所以这里不能只用 latin-1。
    """
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def _parse_filename(header_text):
    """取文件名。优先 RFC 5987 的 filename*，退回 filename=。"""
    star = _FILENAME_STAR_RE.search(header_text)
    if star:
        val = star.group(1).strip().strip('"')
        if "''" in val:
            charset, _, encoded = val.partition("''")
            try:
                return urllib.parse.unquote(encoded, encoding=charset or "utf-8")
            except (LookupError, UnicodeDecodeError):
                pass
    m = _FILENAME_RE.search(header_text)
    return m.group(1) if m else None


def parse_multipart(body, content_type, max_total=MAX_TOTAL,
                    max_file=MAX_FILE, max_files=MAX_FILES):
    """解析 multipart/form-data。

    参数：
        body: 原始请求体 bytes
        content_type: 请求头里的 Content-Type（含 boundary）
    返回：
        {
          "fields": {字段名: 文本值},
          "files":  [{"name","filename","content_type","data"(bytes)}],
        }
    异常：
        MultipartError —— 格式不对或超过上限
    """
    if not isinstance(body, (bytes, bytearray)):
        raise MultipartError("请求体必须是 bytes")
    if len(body) > max_total:
        raise MultipartError(
            "请求体过大：%.1f MB（上限 %.0f MB）" % (len(body) / 1048576, max_total / 1048576)
        )

    boundary = get_boundary(content_type)
    fields = {}
    files = []

    for raw in body.split(boundary):
        # 开头第一段是 boundary 之前的内容（空），结束段是 b"--\r\n"
        if not raw or raw.startswith(b"--"):
            continue
        # 每段形如：\r\n<headers>\r\n\r\n<data>\r\n
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        if raw.endswith(b"\r\n"):
            raw = raw[:-2]
        if not raw:
            continue

        head, sep, data = raw.partition(b"\r\n\r\n")
        if not sep:
            continue  # 没有头部/正文分隔，跳过这一段

        header_text = _decode_header(head)
        name_m = _NAME_RE.search(header_text)
        field_name = name_m.group(1) if name_m else ""
        filename = _parse_filename(header_text)
        ctype_m = re.search(r"(?im)^content-type:\s*([^\r\n;]+)", header_text)
        part_type = ctype_m.group(1).strip() if ctype_m else ""

        if filename is not None:
            # 文件名可能是空串（某些浏览器对「未选择文件」会这样发）
            if not filename.strip():
                continue
            if len(data) > max_file:
                raise MultipartError(
                    "文件「%s」过大：%.1f MB（上限 %.0f MB）"
                    % (filename, len(data) / 1048576, max_file / 1048576)
                )
            if len(files) >= max_files:
                raise MultipartError("一次最多上传 %d 个文件" % max_files)
            files.append({
                "name": field_name or "file",
                "filename": filename,
                "content_type": part_type,
                "data": bytes(data),
            })
        else:
            if len(data) > MAX_FIELD:
                raise MultipartError("表单字段「%s」过大" % (field_name or "?"))
            fields[field_name] = _decode_header(data)

    if not files and not fields:
        raise MultipartError("没有解析到任何字段或文件")
    return {"fields": fields, "files": files}


def safe_name(filename, fallback="upload"):
    """把用户提供的文件名清洗成可以安全落盘的名字。

    只保留基名、去掉路径分隔符与控制字符，避免 ../ 之类的路径穿越。
    中文名保留（Linux 下没问题），但把空格与引号换成下划线。
    """
    import os
    import unicodedata

    name = (filename or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '\r\n\t')
    name = name.strip().strip(".")
    for bad in ('"', "'", " ", ";", "|", "&", "$", "`"):
        name = name.replace(bad, "_")
    if not name:
        name = fallback
    # 控制长度（文件系统上限一般是 255 字节）
    stem, ext = os.path.splitext(name)
    return (stem[:80] + ext[:16]) or fallback


# ---------- 自测 ----------
if __name__ == "__main__":
    B = b"----testboundary123"
    CT = b'multipart/form-data; boundary=----testboundary123'

    def build(parts):
        out = b""
        for p in parts:
            out += b"--" + B + b"\r\n"
            out += p[0]
            out += b"\r\n\r\n"
            out += p[1]
            out += b"\r\n"
        out += b"--" + B + b"--\r\n"
        return out

    # 造一个含 \r\n 的"二进制"文件，验证不会被误切
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) + b"\r\n--notboundary--\r\n"

    body = build([
        (b'Content-Disposition: form-data; name="title"', "三重积分笔记".encode("utf-8")),
        (b'Content-Disposition: form-data; name="tags"', "高数,积分".encode("utf-8")),
        (b'Content-Disposition: form-data; name="file"; filename="\xe9\xab\x98\xe6\x95\xb0.pdf"\r\n'
         b'Content-Type: application/pdf', b"%PDF-1.4 fake content"),
        (b'Content-Disposition: form-data; name="file"; filename="shot.png"\r\n'
         b'Content-Type: image/png', png),
    ])

    r = parse_multipart(body, CT.decode())
    ok = 0
    total = 0

    total += 1
    if r["fields"].get("title") == "三重积分笔记":
        ok += 1; print("OK   中文文本字段")
    else:
        print("FAIL 中文文本字段 ->", repr(r["fields"].get("title")))

    total += 1
    if r["fields"].get("tags") == "高数,积分":
        ok += 1; print("OK   多值字段")
    else:
        print("FAIL 多值字段")

    total += 1
    if len(r["files"]) == 2:
        ok += 1; print("OK   解析出 2 个文件")
    else:
        print("FAIL 文件数 =", len(r["files"]))

    total += 1
    if r["files"][0]["filename"] == "高数.pdf":
        ok += 1; print("OK   中文文件名（UTF-8 原样）")
    else:
        print("FAIL 中文文件名 ->", repr(r["files"][0]["filename"]))

    total += 1
    if r["files"][1]["data"] == png:
        ok += 1; print("OK   二进制完整（含 \\r\\n 与疑似 boundary）")
    else:
        print("FAIL 二进制被破坏，长度 %d != %d" % (len(r["files"][1]["data"]), len(png)))

    total += 1
    if r["files"][1]["content_type"] == "image/png":
        ok += 1; print("OK   分片 Content-Type")
    else:
        print("FAIL 分片 Content-Type")

    total += 1
    if safe_name("../../etc/passwd") == "passwd":
        ok += 1; print("OK   路径穿越被清洗 ->", safe_name("../../etc/passwd"))
    else:
        print("FAIL 路径穿越 ->", safe_name("../../etc/passwd"))

    total += 1
    try:
        parse_multipart(b"x" * 100, "multipart/form-data; boundary=zz", max_total=50)
        print("FAIL 超限没被拦住")
    except MultipartError:
        ok += 1; print("OK   超限被拦住")

    print("\n%d/%d 通过" % (ok, total))
