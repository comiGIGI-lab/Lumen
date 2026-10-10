# -*- coding: utf-8 -*-
"""PDF 解析侧车：MinerU（mineru-kit）可选，pypdf 兜底。

硬约束
------
- 本模块只做「探测 + 调 CLI + 读回 Markdown」。不 import mineru / docling。
- api_server 继续零第三方依赖；MinerU 没装时必须静默退回 pypdf。
- 扫描件 / 几乎抽不到字的 PDF 才走 MinerU；数字文本 PDF 默认仍走 pypdf
  （1.6G 机器上拉起 MinerU 4.0 会把演示打挂）。
- 可用内存低于 2GiB 时 available=false，连强制 mineru 也不拉侧车。
- 强制引擎用环境变量：STUDY_LIU_PDF_ENGINE=mineru | pypdf

CLI（官方 mineru-kit parse）：
    mineru-kit parse <pdf> -o <out.md> --tier basic -f markdown

环境变量
--------
STUDY_LIU_MINERU_BIN     可执行文件；.py 则用当前 Python 解释器跑（测试用）
STUDY_LIU_MINERU_TIER    flash | basic | standard | advanced，默认 basic
STUDY_LIU_MINERU_TIMEOUT 秒，默认 120
STUDY_LIU_PDF_ENGINE     mineru | pypdf | 空（自动）
STUDY_LIU_MINERU_RAM_KB  覆盖 MemAvailable（测试用）
STUDY_LIU_MINERU_MIN_RAM_KB  闸值，默认 2097152（2GiB）；0 关闭
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

MIN_NATIVE_CHARS = 200
SPARSE_FILE_BYTES = 50 * 1024
DEFAULT_TIER = "basic"
DEFAULT_TIMEOUT = 120
# MinerU official basic+ONNX floor is 2GB RAM. 1.6G 演示机必须闸住。
MIN_RAM_KB = 2 * 1024 * 1024
_SERVER_BIN = "/home/admin/asr/mineru/mineru-kit"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _min_ram_kb():
    raw = (os.environ.get("STUDY_LIU_MINERU_MIN_RAM_KB") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return MIN_RAM_KB


def _mem_available_kb():
    """返回可用内存 kB；测不出来返回 None（Windows 本机放行，线上读 /proc）。"""
    raw = (os.environ.get("STUDY_LIU_MINERU_RAM_KB") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    meminfo = "/proc/meminfo"
    try:
        with open(meminfo, "r", encoding="utf-8", errors="ignore") as f:
            available = None
            free = None
            for line in f:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1])
                    break
                if line.startswith("MemFree:") and free is None:
                    free = int(line.split()[1])
            if available is not None:
                return available
            return free
    except (OSError, ValueError, IndexError):
        return None


def ram_ok():
    """(ok, reason)。闸关闭或读不到 /proc 时放行。"""
    need = _min_ram_kb()
    if need <= 0:
        return True, ""
    have = _mem_available_kb()
    if have is None:
        return True, ""
    if have < need:
        return False, (
            "本机可用内存约 %d MB，低于 MinerU basic 的 %d MB 下限；"
            "扫描件走 pypdf，不要强上。"
            % (have // 1024, need // 1024)
        )
    return True, ""


def mineru_cmd():
    """返回调用 mineru-kit 的 argv 前缀；不可用时返回空列表。"""
    raw = (os.environ.get("STUDY_LIU_MINERU_BIN") or "").strip()
    if raw:
        if raw.lower().endswith(".py"):
            return [sys.executable, raw] if os.path.isfile(raw) else []
        return [raw] if os.path.isfile(raw) else []
    found = shutil.which("mineru-kit")
    if found:
        return [found]
    if os.path.isfile(_SERVER_BIN):
        return [_SERVER_BIN]
    local = os.path.join(_repo_root(), "vendor", "asr", "mineru-kit")
    if os.path.isfile(local):
        return [local]
    return []


def available():
    """探测 MinerU 侧车。(ok, reason)"""
    cmd = mineru_cmd()
    if not cmd:
        return False, "未安装 mineru-kit。扫描件 PDF 将走 pypdf 文本层；复杂版式需要在服务器另装 MinerU 侧车。"
    exe = cmd[-1]
    if not os.path.isfile(exe) and shutil.which(exe) is None:
        return False, "mineru-kit 路径无效：%s" % exe
    ok, reason = ram_ok()
    if not ok:
        return False, reason
    return True, ""


def _read_native_pdf(path):
    """读 PDF 文本层。测试可替换本函数。失败抛异常。"""
    from tools.document_importer import read_text
    return read_text(path)


def _should_use_mineru(native_text, path, mineru_ok):
    force = (os.environ.get("STUDY_LIU_PDF_ENGINE") or "").strip().lower()
    if force == "pypdf":
        return False
    if not mineru_ok:
        return False
    if force == "mineru":
        return True
    native = (native_text or "").strip()
    if not native:
        return True
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return len(native) < MIN_NATIVE_CHARS and size >= SPARSE_FILE_BYTES


def _collect_markdown(target, stem):
    """从 -o 指向的文件或目录里拼出 Markdown 正文。"""
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if not os.path.isdir(target):
        return ""
    preferred = []
    others = []
    for root, _dirs, files in os.walk(target):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            p = os.path.join(root, name)
            if stem and stem.lower() in name.lower():
                preferred.append(p)
            else:
                others.append(p)
    chunks = []
    for p in preferred + others:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                chunks.append(f.read())
        except OSError:
            continue
    return "\n\n".join(c.strip() for c in chunks if c and c.strip())


def parse_with_mineru(path, timeout=None):
    """调 mineru-kit 解析单个 PDF。返回 {text, error}。不抛给调用方业务异常。"""
    cmd = mineru_cmd()
    if not cmd:
        return {"text": "", "error": "mineru-kit 不可用"}
    ram_pass, ram_reason = ram_ok()
    if not ram_pass:
        return {"text": "", "error": ram_reason}
    if timeout is None:
        try:
            timeout = int(os.environ.get("STUDY_LIU_MINERU_TIMEOUT") or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
    tier = (os.environ.get("STUDY_LIU_MINERU_TIER") or DEFAULT_TIER).strip() or DEFAULT_TIER
    stem = os.path.splitext(os.path.basename(path))[0] or "doc"
    tmp = tempfile.mkdtemp(prefix="mineru-")
    out_md = os.path.join(tmp, stem + ".md")
    argv = cmd + ["parse", path, "-o", out_md, "--tier", tier, "-f", "markdown"]
    try:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return {"text": "", "error": "找不到 mineru-kit 可执行文件"}
        except subprocess.TimeoutExpired:
            return {"text": "", "error": "MinerU 解析超时（%d 秒）" % timeout}
        except Exception as e:
            return {"text": "", "error": "MinerU 调用失败：%s" % e}

        text = _collect_markdown(out_md, stem)
        if not text:
            text = _collect_markdown(tmp, stem)
        if not text.strip():
            err = (proc.stderr or proc.stdout or b"").decode("utf-8", "ignore").strip()
            if proc.returncode:
                return {"text": "", "error": "MinerU 退出码 %s：%s" % (proc.returncode, err[:300] or "无输出")}
            return {"text": "", "error": "MinerU 没有写出 Markdown"}
        return {"text": text.strip(), "error": ""}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pdf_blocks(text, engine):
    """给 PDF 正文补 blocks。失败返回 []，不抛。"""
    text = (text or "").strip()
    if not text:
        return []
    try:
        import parse_blocks
        if engine == "mineru":
            return parse_blocks.markdown_to_blocks(text)
        return parse_blocks.plaintext_to_blocks(text)
    except Exception:
        return []


def extract_pdf_text(path):
    """PDF → 正文。自动在 MinerU 侧车与 pypdf 之间选择。

    返回：{text, engine, error, blocks}。engine 为 mineru / pypdf / 空串。
    blocks 为 additive，失败路径也给 []。
    """
    native = ""
    native_err = ""
    try:
        native = (_read_native_pdf(path) or "").strip()
    except Exception as e:
        native_err = str(e)

    mineru_ok, mineru_reason = available()
    if _should_use_mineru(native, path, mineru_ok):
        r = parse_with_mineru(path)
        if (r.get("text") or "").strip():
            t = r["text"].strip()
            return {"text": t, "engine": "mineru", "error": "", "blocks": _pdf_blocks(t, "mineru")}
        if native:
            return {"text": native, "engine": "pypdf", "error": "", "blocks": _pdf_blocks(native, "pypdf")}
        return {
            "text": "",
            "engine": "",
            "error": r.get("error") or native_err or mineru_reason or "PDF 解析失败",
            "blocks": [],
        }

    if native:
        return {"text": native, "engine": "pypdf", "error": "", "blocks": _pdf_blocks(native, "pypdf")}
    return {
        "text": "",
        "engine": "",
        "error": native_err or (mineru_reason if not mineru_ok else "") or "文件里没有解析到任何文字",
        "blocks": [],
    }


def capabilities():
    ok, reason = available()
    return {
        "available": ok,
        "engine": "mineru" if ok else "",
        "tier": (os.environ.get("STUDY_LIU_MINERU_TIER") or DEFAULT_TIER),
        "note": "" if ok else reason,
    }
