# -*- coding: utf-8 -*-
"""whisper.cpp 侧车：可选的离线语音转写。

硬约束
------
- 不 import openai-whisper / mlx-whisper / Docling ASR。只调 ggml-org/whisper.cpp 的 CLI。
- 二进制和模型都在仓库外（Gitee 拒大文件）；缺了就让 asr.py 回退 Vosk。
- 中文必须用多语言模型，拒绝 *.en。
- 输入已是浏览器重采样后的 16 kHz / 16bit / mono PCM，本模块只包一层 WAV 头，不调用 ffmpeg。

CLI：
    whisper-cli -m ggml-small.bin -f input.wav -l zh -otxt -of outprefix

环境变量
--------
STUDY_LIU_WHISPER_BIN     whisper-cli / main；.py 则用当前解释器（测试用）
STUDY_LIU_WHISPER_MODEL   ggml 模型路径（不要 *.en）
STUDY_LIU_WHISPER_TIMEOUT 秒，默认 180
STUDY_LIU_WHISPER_LANG    默认 zh
STUDY_LIU_ASR_ENGINE      whisper | vosk | 空（自动：有 whisper 用 whisper）
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile

SAMPLE_RATE = 16000
DEFAULT_TIMEOUT = 180
_SERVER_BIN = "/home/admin/asr/whisper/whisper-cli"
_SERVER_BIN_LEGACY = "/home/admin/asr/whisper/main"
_SERVER_MODEL = "/home/admin/asr/whisper/ggml-small.bin"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pcm16le_to_wav_bytes(pcm, sample_rate=SAMPLE_RATE):
    """把裸 PCM16LE 单声道包成 WAV。纯标准库，无 ffmpeg。"""
    data = pcm if isinstance(pcm, (bytes, bytearray)) else bytes(pcm)
    if len(data) % 2:
        data = data[:-1]
    n = len(data)
    hdr = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", n)
    return hdr + data


def whisper_cmd():
    raw = (os.environ.get("STUDY_LIU_WHISPER_BIN") or "").strip()
    if raw:
        if raw.lower().endswith(".py"):
            return [sys.executable, raw] if os.path.isfile(raw) else []
        return [raw] if os.path.isfile(raw) else []
    for cand in (
        _SERVER_BIN,
        _SERVER_BIN_LEGACY,
        shutil.which("whisper-cli") or "",
        shutil.which("whisper-cpp") or "",
        os.path.join(_repo_root(), "vendor", "asr", "whisper-cli"),
    ):
        if cand and os.path.isfile(cand):
            return [cand]
    return []


def model_path():
    env = (os.environ.get("STUDY_LIU_WHISPER_MODEL") or "").strip()
    if env:
        return env
    if os.path.isfile(_SERVER_MODEL):
        return _SERVER_MODEL
    local = os.path.join(_repo_root(), "vendor", "asr", "ggml-small.bin")
    if os.path.isfile(local):
        return local
    return _SERVER_MODEL


def _english_only_model(path):
    name = os.path.basename(path or "").lower()
    return name.endswith(".en.bin") or name.endswith(".en")


def probe():
    """探测。(ok, reason, model_basename)"""
    cmd = whisper_cmd()
    model = model_path()
    if not cmd:
        return False, "未安装 whisper.cpp（whisper-cli）。将回退 Vosk（若已部署）。", ""
    if not os.path.isfile(model):
        return False, "whisper.cpp 模型未安装：找不到 %s。中文请用 ggml-small.bin 等多语言模型，不要用 *.en。" % model, ""
    if _english_only_model(model):
        return False, "当前模型是英文专用（%s）。中文转写需要多语言模型，例如 ggml-small.bin。" % os.path.basename(model), ""
    return True, "", os.path.basename(model)


def available():
    ok, _reason, _model = probe()
    return ok


def status():
    ok, reason, model = probe()
    return {
        "ok": ok,
        "available": ok,
        "reason": reason,
        "engine": "whisper.cpp" if ok else "",
        "model": model,
        "sample_rate": SAMPLE_RATE,
    }


def transcribe(pcm, sample_rate=SAMPLE_RATE, timeout=None):
    """PCM16LE → 文字。失败抛 RuntimeError（消息可给用户看）。"""
    ok, reason, _model = probe()
    if not ok:
        raise RuntimeError(reason)
    cmd = whisper_cmd()
    model = model_path()
    if timeout is None:
        try:
            timeout = int(os.environ.get("STUDY_LIU_WHISPER_TIMEOUT") or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
    lang = (os.environ.get("STUDY_LIU_WHISPER_LANG") or "zh").strip() or "zh"

    wav = pcm16le_to_wav_bytes(pcm, sample_rate=sample_rate)
    tmp = tempfile.mkdtemp(prefix="whisper-")
    wav_path = os.path.join(tmp, "in.wav")
    out_prefix = os.path.join(tmp, "out")
    try:
        with open(wav_path, "wb") as f:
            f.write(wav)

        argv = cmd + [
            "-m", model,
            "-f", wav_path,
            "-l", lang,
            "-otxt",
            "-of", out_prefix,
        ]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            raise RuntimeError("找不到 whisper.cpp 可执行文件")
        except subprocess.TimeoutExpired:
            raise RuntimeError("whisper.cpp 转写超时（%d 秒）" % timeout)

        txt_path = out_prefix + ".txt"
        text = ""
        if os.path.isfile(txt_path):
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        if not text.strip():
            # 有的构建把正文打到 stdout
            text = (proc.stdout or b"").decode("utf-8", "ignore")
        if proc.returncode and not text.strip():
            err = (proc.stderr or b"").decode("utf-8", "ignore").strip()
            raise RuntimeError("whisper.cpp 失败（退出码 %s）：%s" % (proc.returncode, err[:300] or "无输出"))
        return {
            "text": (text or "").strip(),
            "engine": "whisper.cpp",
            "model": os.path.basename(model),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
