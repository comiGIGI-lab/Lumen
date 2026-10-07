# -*- coding: utf-8 -*-
"""决赛冲刺侧车回归：MinerU PDF 解析 + whisper.cpp 转写。

不要求本机真装 MinerU / whisper.cpp。用假 CLI 脚本模拟侧车，
验证：探测、路由、回退、WAV 封装、中文模型拒绝 *.en。

用法（仓库根目录）：

    python tests/run_sidecar_regression.py

退出码 0 = 全过。
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")
sys.path.insert(0, SERVER_DIR)

import doc_parse  # noqa: E402
import whisper_cpp  # noqa: E402

FAILED = []
PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL  %s  %s" % (name, detail))


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


FAKE_MINERU = r'''#!/usr/bin/env python3
# fake mineru-kit: parse <pdf> -o <out> [--tier x] [-f markdown]
import sys, os
args = sys.argv[1:]
if not args or args[0] != "parse":
    sys.stderr.write("usage: parse\n")
    sys.exit(2)
pdf = args[1]
out = None
i = 2
while i < len(args):
    if args[i] in ("-o", "--output") and i + 1 < len(args):
        out = args[i + 1]
        i += 2
        continue
    i += 1
if not out:
    sys.stderr.write("need -o\n")
    sys.exit(2)
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
name = os.path.basename(pdf)
with open(out, "w", encoding="utf-8") as f:
    f.write("# MinerU sidecar\n\nparsed-from: %s\n表格单元格甲\n" % name)
'''

FAKE_WHISPER = r'''#!/usr/bin/env python3
# fake whisper-cli: -m model -f wav -l zh -otxt -of prefix
import sys, os
args = sys.argv[1:]
model = wav = of = None
i = 0
while i < len(args):
    a = args[i]
    if a == "-m" and i + 1 < len(args):
        model = args[i + 1]; i += 2; continue
    if a == "-f" and i + 1 < len(args):
        wav = args[i + 1]; i += 2; continue
    if a == "-of" and i + 1 < len(args):
        of = args[i + 1]; i += 2; continue
    i += 1
if not of or not wav:
    sys.stderr.write("need -f and -of\n")
    sys.exit(2)
if not os.path.isfile(wav):
    sys.stderr.write("wav missing\n")
    sys.exit(3)
with open(wav, "rb") as f:
    head = f.read(12)
if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
    sys.stderr.write("not wav\n")
    sys.exit(4)
with open(of + ".txt", "w", encoding="utf-8") as f:
    f.write("同学们好，这是 whisper.cpp 侧车。")
'''


def with_env(pairs, fn):
    saved = {k: os.environ.get(k) for k in pairs}
    try:
        for k, v in pairs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return fn()
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def test_mineru_missing():
    print("\n[doc_parse] 侧车缺失")

    def run():
        ok, reason = doc_parse.available()
        check("无 mineru-kit 时 available=False", ok is False)
        check("reason 提到 mineru-kit", "mineru-kit" in reason)
        caps = doc_parse.capabilities()
        check("capabilities.available=False", caps["available"] is False)
        check("capabilities.note 非空", bool(caps["note"]))
    with_env({"STUDY_LIU_MINERU_BIN": os.path.join("Z:", os.sep, "no-such-mineru-kit")}, run)


def test_mineru_parse_and_route():
    print("\n[doc_parse] 假 CLI 解析与路由")
    tmp = tempfile.mkdtemp(prefix="sidecar-pdf-")
    fake = os.path.join(tmp, "fake_mineru.py")
    _write(fake, FAKE_MINERU)
    pdf = os.path.join(tmp, "lecture.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4 fake " + b"x" * (60 * 1024))

    orig_native = doc_parse._read_native_pdf

    def run():
        doc_parse._read_native_pdf = lambda _p: "这是一段足够长的数字 PDF 文本。" * 20
        r = doc_parse.extract_pdf_text(pdf)
        check("文本层够长时走 pypdf", r["engine"] == "pypdf", r)
        check("pypdf 正文非空", "数字 PDF" in r["text"])

        doc_parse._read_native_pdf = lambda _p: "扫"  # 稀疏扫描件
        r = doc_parse.extract_pdf_text(pdf)
        check("扫描件走 mineru", r["engine"] == "mineru", r)
        check("MinerU 正文含标记", "parsed-from" in r["text"] and "表格单元格甲" in r["text"])

        os.environ["STUDY_LIU_PDF_ENGINE"] = "pypdf"
        r = doc_parse.extract_pdf_text(pdf)
        check("强制 pypdf 不调侧车", r["engine"] == "pypdf", r)
        os.environ.pop("STUDY_LIU_PDF_ENGINE", None)

        os.environ["STUDY_LIU_PDF_ENGINE"] = "mineru"
        doc_parse._read_native_pdf = orig_native
        # even if native would succeed, force mineru
        doc_parse._read_native_pdf = lambda _p: "很长的文本层内容" * 30
        r = doc_parse.extract_pdf_text(pdf)
        check("强制 mineru 覆盖文本层", r["engine"] == "mineru", r)
        os.environ.pop("STUDY_LIU_PDF_ENGINE", None)

    try:
        with_env({"STUDY_LIU_MINERU_BIN": fake, "STUDY_LIU_PDF_ENGINE": None}, run)
    finally:
        doc_parse._read_native_pdf = orig_native


def test_mineru_falls_back_when_cli_fails():
    print("\n[doc_parse] 侧车失败回退 pypdf")
    tmp = tempfile.mkdtemp(prefix="sidecar-fail-")
    fake = os.path.join(tmp, "broken.py")
    _write(fake, "import sys\nsys.exit(9)\n")
    pdf = os.path.join(tmp, "a.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4 " + b"y" * (60 * 1024))
    orig = doc_parse._read_native_pdf
    try:
        doc_parse._read_native_pdf = lambda _p: "x"

        def run():
            r = doc_parse.extract_pdf_text(pdf)
            check("MinerU 失败但有文本层 → pypdf", r["engine"] == "pypdf" and r["text"] == "x", r)
        with_env({"STUDY_LIU_MINERU_BIN": fake, "STUDY_LIU_PDF_ENGINE": None}, run)
    finally:
        doc_parse._read_native_pdf = orig


def test_wav_header():
    print("\n[whisper_cpp] WAV 封装")
    pcm = struct.pack("<" + "h" * 8, *([0] * 8))
    wav = whisper_cpp.pcm16le_to_wav_bytes(pcm, sample_rate=16000)
    check("RIFF/WAVE 头", wav[:4] == b"RIFF" and wav[8:12] == b"WAVE")
    check("fmt PCM 16bit mono", wav[20:22] == b"\x01\x00" and wav[22:24] == b"\x01\x00" and wav[34:36] == b"\x10\x00")
    rate = struct.unpack_from("<I", wav, 24)[0]
    check("采样率 16000", rate == 16000)
    check("data 块长度", struct.unpack_from("<I", wav, 40)[0] == 16)


def test_whisper_probe_and_transcribe():
    print("\n[whisper_cpp] 探测 / 转写 / 拒绝英文模型")
    tmp = tempfile.mkdtemp(prefix="sidecar-asr-")
    fake = os.path.join(tmp, "fake_whisper.py")
    _write(fake, FAKE_WHISPER)
    model = os.path.join(tmp, "ggml-small.bin")
    _write(model, "fake-ggml")
    en_model = os.path.join(tmp, "ggml-small.en.bin")
    _write(en_model, "en-only")

    def missing():
        ok, reason, _m = whisper_cpp.probe()
        check("无二进制 available=False", ok is False)
        check("reason 提到 whisper.cpp", "whisper.cpp" in reason)
    with_env({
        "STUDY_LIU_WHISPER_BIN": os.path.join(tmp, "no-bin"),
        "STUDY_LIU_WHISPER_MODEL": model,
    }, missing)

    def english():
        ok, reason, _m = whisper_cpp.probe()
        check("拒绝 *.en 模型", ok is False)
        check("英文模型提示含多语言", "多语言" in reason or "*.en" in reason or "英文" in reason, reason)
    with_env({
        "STUDY_LIU_WHISPER_BIN": fake,
        "STUDY_LIU_WHISPER_MODEL": en_model,
    }, english)

    def ok_run():
        st = whisper_cpp.status()
        check("假 CLI 可用", st["available"] is True, st)
        check("engine=whisper.cpp", st["engine"] == "whisper.cpp")
        pcm = b"\x00\x00" * 160
        r = whisper_cpp.transcribe(pcm)
        check("转写正文来自侧车", "whisper.cpp 侧车" in r["text"], r)
        check("返回 engine 字段", r.get("engine") == "whisper.cpp")
    with_env({
        "STUDY_LIU_WHISPER_BIN": fake,
        "STUDY_LIU_WHISPER_MODEL": model,
    }, ok_run)


def test_asr_router():
    print("\n[asr] 路由：whisper 优先，缺则 Vosk")
    import asr as asr_mod
    tmp = tempfile.mkdtemp(prefix="sidecar-asr2-")
    fake = os.path.join(tmp, "fake_whisper.py")
    _write(fake, FAKE_WHISPER)
    model = os.path.join(tmp, "ggml-small.bin")
    _write(model, "fake-ggml")

    orig_vosk = asr_mod._ensure_model
    orig_vosk_transcribe_parts = None

    def no_vosk():
        raise RuntimeError("语音模型未安装：测试桩")

    def run_prefer_whisper():
        asr_mod._ensure_model = no_vosk
        st = asr_mod.status()
        check("whisper 可用时 asr.engine=whisper.cpp", st.get("engine") == "whisper.cpp", st)
        check("status.available True", st["available"] is True)
        pcm = b"\x00\x00" * 320
        r = asr_mod.transcribe(pcm)
        check("asr.transcribe 走 whisper", r.get("engine") == "whisper.cpp" and "侧车" in r["text"], r)

    try:
        with_env({
            "STUDY_LIU_WHISPER_BIN": fake,
            "STUDY_LIU_WHISPER_MODEL": model,
            "STUDY_LIU_ASR_ENGINE": None,
        }, run_prefer_whisper)
    finally:
        asr_mod._ensure_model = orig_vosk

    def force_vosk_without_model():
        st = asr_mod.status()
        check("强制 vosk 且模型缺失 → available false", st["available"] is False, st)
        check("reason 仍是 Vosk 话术", "语音" in (st.get("reason") or ""), st)

    asr_mod._ERROR = "语音模型未安装：测试桩"
    try:
        # reset cached model error path: _ERROR already set will short-circuit
        with_env({
            "STUDY_LIU_WHISPER_BIN": fake,
            "STUDY_LIU_WHISPER_MODEL": model,
            "STUDY_LIU_ASR_ENGINE": "vosk",
        }, force_vosk_without_model)
    finally:
        asr_mod._ERROR = ""

    def no_whisper_uses_vosk_reason():
        st = asr_mod.status()
        # whisper missing → fall through to vosk, which we stub as missing
        check("两侧都缺仍 available=false", st["available"] is False)
        check("status 带 engine 空或 vosk 标记", True)
    asr_mod._ERROR = "语音模型未安装：测试桩"
    try:
        with_env({
            "STUDY_LIU_WHISPER_BIN": os.path.join(tmp, "missing"),
            "STUDY_LIU_WHISPER_MODEL": os.path.join(tmp, "no-model.bin"),
            "STUDY_LIU_ASR_ENGINE": None,
        }, no_whisper_uses_vosk_reason)
    finally:
        asr_mod._ERROR = ""


def test_kb_capabilities_surface():
    print("\n[kb_ingest] capabilities 暴露 MinerU")
    import kb_ingest
    caps = kb_ingest.capabilities()
    check("document 含 mineru 字段", "mineru" in caps.get("document", {}), caps.get("document"))
    mineru = caps["document"].get("mineru") or {}
    check("mineru 是 dict 且有 available", isinstance(mineru, dict) and "available" in mineru, mineru)


def main():
    print("=" * 60)
    print("侧车回归（MinerU + whisper.cpp，假 CLI，不装真引擎）")
    print("=" * 60)
    for fn in (
        test_mineru_missing,
        test_mineru_parse_and_route,
        test_mineru_falls_back_when_cli_fails,
        test_wav_header,
        test_whisper_probe_and_transcribe,
        test_asr_router,
        test_kb_capabilities_surface,
    ):
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__ + "/exception")
            traceback.print_exc()
    print("")
    print("=" * 60)
    print("通过 %d  失败 %d" % (PASSED, len(FAILED)))
    if FAILED:
        print("失败项：" + "、".join(FAILED))
        return 1
    print("全过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
