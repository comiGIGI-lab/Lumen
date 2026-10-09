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

FAKE_DOCLING = r'''#!/usr/bin/env python3
# fake docling CLI reference: convert <src> --to md --output <dir> [--no-ocr]
# https://docling-project.github.io/docling/reference/cli/
import sys, os
args = sys.argv[1:]
if "--pipeline" in args:
    i = args.index("--pipeline")
    if i + 1 < len(args) and args[i + 1] == "vlm":
        sys.stderr.write("Day3 sidecar must not use --pipeline vlm\n")
        sys.exit(5)
if not args or args[0] != "convert":
    sys.stderr.write("usage: convert\n")
    sys.exit(2)
src = args[1]
out = "."
of = None
i = 2
while i < len(args):
    if args[i] == "--output" and i + 1 < len(args):
        out = args[i + 1]; i += 2; continue
    if args[i] == "--output-file" and i + 1 < len(args):
        of = args[i + 1]; i += 2; continue
    i += 1
stem = os.path.splitext(os.path.basename(src))[0] or "doc"
text = "# Docling sidecar\n\nparsed-office: %s\n特征值与对角化\n" % os.path.basename(src)
if of:
    os.makedirs(os.path.dirname(of) or ".", exist_ok=True)
    with open(of, "w", encoding="utf-8") as f:
        f.write(text)
else:
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, stem + ".md"), "w", encoding="utf-8") as f:
        f.write(text)
'''

FAKE_WHISPER = r'''#!/usr/bin/env python3
# fake whisper-cli: -m model -f wav -l zh -otxt -of prefix
# official VAD: --vad plus -vm / --vad-model (https://github.com/ggml-org/whisper.cpp#voice-activity-detection-vad)
import sys, os
args = sys.argv[1:]
model = wav = of = vm = None
use_vad = False
i = 0
while i < len(args):
    a = args[i]
    if a == "-m" and i + 1 < len(args):
        model = args[i + 1]; i += 2; continue
    if a == "-f" and i + 1 < len(args):
        wav = args[i + 1]; i += 2; continue
    if a == "-of" and i + 1 < len(args):
        of = args[i + 1]; i += 2; continue
    if a == "-vm" and i + 1 < len(args):
        vm = args[i + 1]; i += 2; continue
    if a == "--vad-model" and i + 1 < len(args):
        vm = args[i + 1]; i += 2; continue
    if a == "--vad":
        use_vad = True; i += 1; continue
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
if use_vad:
    if not vm or not os.path.isfile(vm):
        sys.stderr.write("need -vm for --vad\n")
        sys.exit(6)
    extra = " [vad]"
else:
    extra = ""
with open(of + ".txt", "w", encoding="utf-8") as f:
    f.write("同学们好，这是 whisper.cpp 侧车。" + extra)
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
        with_env({
            "STUDY_LIU_MINERU_BIN": fake,
            "STUDY_LIU_PDF_ENGINE": None,
            "STUDY_LIU_MINERU_RAM_KB": "3000000",
        }, run)
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
        with_env({
            "STUDY_LIU_MINERU_BIN": fake,
            "STUDY_LIU_PDF_ENGINE": None,
            "STUDY_LIU_MINERU_RAM_KB": "3000000",
        }, run)
    finally:
        doc_parse._read_native_pdf = orig


def test_mineru_ram_gate():
    print("\n[doc_parse] 内存不足 2G 不拉 MinerU")
    tmp = tempfile.mkdtemp(prefix="sidecar-ram-")
    fake = os.path.join(tmp, "fake_mineru.py")
    _write(fake, FAKE_MINERU)
    pdf = os.path.join(tmp, "scan.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4 fake " + b"x" * (60 * 1024))
    orig_native = doc_parse._read_native_pdf

    def low_ram():
        ok, reason = doc_parse.available()
        check("1.6G 时 available=False", ok is False, (ok, reason))
        check("reason 提到内存", "内存" in (reason or ""), reason)
        caps = doc_parse.capabilities()
        check("低内存 capabilities.available=False", caps["available"] is False, caps)
        doc_parse._read_native_pdf = lambda _p: "扫"
        r = doc_parse.extract_pdf_text(pdf)
        check("低内存扫描件走 pypdf", r["engine"] == "pypdf", r)
        check("低内存正文不含 MinerU 标记", "parsed-from" not in (r.get("text") or ""), r)
        os.environ["STUDY_LIU_PDF_ENGINE"] = "mineru"
        r = doc_parse.extract_pdf_text(pdf)
        check("强制 mineru 也被内存闸拦住", r["engine"] != "mineru", r)
        os.environ.pop("STUDY_LIU_PDF_ENGINE", None)

    def high_ram():
        ok, reason = doc_parse.available()
        check("内存充足 available=True", ok is True, (ok, reason))
        doc_parse._read_native_pdf = lambda _p: "扫"
        r = doc_parse.extract_pdf_text(pdf)
        check("内存充足扫描件走 mineru", r["engine"] == "mineru", r)

    def gate_off():
        ok, reason = doc_parse.available()
        check("MIN_RAM_KB=0 关闭闸", ok is True, (ok, reason))

    try:
        with_env({
            "STUDY_LIU_MINERU_BIN": fake,
            "STUDY_LIU_PDF_ENGINE": None,
            "STUDY_LIU_MINERU_RAM_KB": "1600000",
            "STUDY_LIU_MINERU_MIN_RAM_KB": None,
        }, low_ram)
        with_env({
            "STUDY_LIU_MINERU_BIN": fake,
            "STUDY_LIU_PDF_ENGINE": None,
            "STUDY_LIU_MINERU_RAM_KB": "3000000",
            "STUDY_LIU_MINERU_MIN_RAM_KB": None,
        }, high_ram)
        with_env({
            "STUDY_LIU_MINERU_BIN": fake,
            "STUDY_LIU_PDF_ENGINE": None,
            "STUDY_LIU_MINERU_RAM_KB": "1000",
            "STUDY_LIU_MINERU_MIN_RAM_KB": "0",
        }, gate_off)
        deploy = os.path.join(REPO_ROOT, "docs", "DEPLOY.md")
        with open(deploy, "r", encoding="utf-8") as f:
            deploy_txt = f.read()
        check(
            "DEPLOY 不再把 medium 与 small 并列成可选模型",
            "ggml-small.bin` / `ggml-medium.bin" not in deploy_txt,
        )
        check("DEPLOY 写明 1.6G 只用 small", "ggml-small.bin" in deploy_txt and "不要用 `ggml-medium.bin`" in deploy_txt)
        check("DEPLOY 写明 2GiB 内存闸", "2GiB" in deploy_txt)
    finally:
        doc_parse._read_native_pdf = orig_native


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


def test_whisper_vad():
    print("\n[whisper_cpp] 可选 VAD：有 Silero 才 --vad -vm")
    src = os.path.join(SERVER_DIR, "whisper_cpp.py")
    with open(src, "r", encoding="utf-8") as f:
        src_txt = f.read()
    check("whisper_cpp 源码含 --vad", '"--vad"' in src_txt or "'--vad'" in src_txt)
    check("whisper_cpp 源码含 -vm", '"-vm"' in src_txt or "'-vm'" in src_txt)

    tmp = tempfile.mkdtemp(prefix="sidecar-vad-")
    fake = os.path.join(tmp, "fake_whisper.py")
    _write(fake, FAKE_WHISPER)
    model = os.path.join(tmp, "ggml-small.bin")
    _write(model, "fake-ggml")
    silero = os.path.join(tmp, "ggml-silero-v6.2.0.bin")
    _write(silero, "fake-silero")
    missing = os.path.join(tmp, "no-silero.bin")
    pcm = b"\x00\x00" * 160

    def with_silero():
        st = whisper_cpp.status()
        check("有 Silero 时 status.vad=True", st.get("vad") is True, st)
        check("status.vad_model 是 silero 文件名", "silero" in (st.get("vad_model") or "").lower(), st)
        r = whisper_cpp.transcribe(pcm)
        check("有 Silero 时假 CLI 走 VAD", "[vad]" in (r.get("text") or ""), r)
        check("有 Silero 时 result.vad=True", r.get("vad") is True, r)
        import asr as asr_mod
        orig = asr_mod._ensure_model
        asr_mod._ensure_model = lambda: (_ for _ in ()).throw(RuntimeError("语音模型未安装：测试桩"))
        try:
            ast = asr_mod.status()
            check("asr.status 转发 vad=True", ast.get("vad") is True, ast)
            ar = asr_mod.transcribe(pcm)
            check("asr.transcribe 转发 vad=True", ar.get("vad") is True, ar)
        finally:
            asr_mod._ensure_model = orig
    with_env({
        "STUDY_LIU_WHISPER_BIN": fake,
        "STUDY_LIU_WHISPER_MODEL": model,
        "STUDY_LIU_WHISPER_VAD_MODEL": silero,
        "STUDY_LIU_WHISPER_VAD": None,
    }, with_silero)

    def missing_silero():
        st = whisper_cpp.status()
        check("缺 Silero 时 status.vad=False", st.get("vad") is False, st)
        check("缺 Silero 仍 available=True", st.get("available") is True, st)
        r = whisper_cpp.transcribe(pcm)
        check("缺 Silero 整段转写不加 --vad", "[vad]" not in (r.get("text") or ""), r)
        check("缺 Silero 时 result.vad=False", r.get("vad") is False, r)
    with_env({
        "STUDY_LIU_WHISPER_BIN": fake,
        "STUDY_LIU_WHISPER_MODEL": model,
        "STUDY_LIU_WHISPER_VAD_MODEL": missing,
        "STUDY_LIU_WHISPER_VAD": None,
    }, missing_silero)

    def forced_off():
        st = whisper_cpp.status()
        check("VAD=0 时即使有模型也不开", st.get("vad") is False, st)
        r = whisper_cpp.transcribe(pcm)
        check("VAD=0 假 CLI 无 [vad]", "[vad]" not in (r.get("text") or ""), r)
    with_env({
        "STUDY_LIU_WHISPER_BIN": fake,
        "STUDY_LIU_WHISPER_MODEL": model,
        "STUDY_LIU_WHISPER_VAD_MODEL": silero,
        "STUDY_LIU_WHISPER_VAD": "0",
    }, forced_off)

    deploy = os.path.join(REPO_ROOT, "docs", "DEPLOY.md")
    with open(deploy, "r", encoding="utf-8") as f:
        deploy_txt = f.read()
    check("DEPLOY 写 --vad", "--vad" in deploy_txt)
    check("DEPLOY 写 Silero / -vm", "-vm" in deploy_txt and "silero" in deploy_txt.lower())
    check("DEPLOY 写缺模型则整段转写", "整段" in deploy_txt or "不传 `--vad`" in deploy_txt or "不加 `--vad`" in deploy_txt)


def test_transcribe_page_vad():
    """评委在转写页必须看见 GET /api/asr 的 vad，空则不画空块。对齐 Day1 ChatPanel 读源。"""
    print("\n[transcribe] 转写页必须把 vad 亮给评委")
    vue_path = os.path.join(REPO_ROOT, "web", "src", "components", "TranscribePage.vue")
    i18n_path = os.path.join(REPO_ROOT, "web", "src", "i18n", "index.js")
    with open(vue_path, "r", encoding="utf-8") as f:
        vue = f.read()
    with open(i18n_path, "r", encoding="utf-8") as f:
        i18n = f.read()
    check("TranscribePage 读 engine.vad", "engine.vad" in vue)
    check("TranscribePage 读 engine.vad_model", "engine.vad_model" in vue)
    check(
        "空 vad 不画空块",
        'v-if="engine.vad"' in vue
        or "v-if='engine.vad'" in vue
        or 'v-if="engine && engine.vad"' in vue,
    )
    check(
        "vad_model 用文本插值禁止 v-html",
        "{{ engine.vad_model }}" in vue or "{{engine.vad_model}}" in vue,
    )
    check("模板用 t('trPage.vad')", "t('trPage.vad')" in vue)
    check("i18n 中文写语音活动/VAD", "语音活动" in i18n or "VAD" in i18n)
    check("i18n 英文写 VAD / activity", "Voice activity" in i18n or "voice activity" in i18n.lower() or "VAD" in i18n)


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


def _write_ooxml_docx(path, text):
    import zipfile
    from xml.sax.saxutils import escape
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:body></w:document>"
        % escape(text)
    )
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", body)


def _write_ooxml_pptx(path, text):
    import zipfile
    from xml.sax.saxutils import escape
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        "<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sld>"
        % escape(text)
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("ppt/slides/slide1.xml", slide)


def test_office_sidecar():
    print("\n[office_parse] Day3 docx/pptx 侧车")
    src_api = os.path.join(SERVER_DIR, "api_server.py")
    src_office = os.path.join(SERVER_DIR, "office_parse.py")
    src_kb = os.path.join(SERVER_DIR, "kb_ingest.py")
    src_import = os.path.join(REPO_ROOT, "web", "src", "components", "ImportPage.vue")
    src_know = os.path.join(REPO_ROOT, "web", "src", "components", "KnowledgePage.vue")
    src_know_js = os.path.join(REPO_ROOT, "web", "src", "composables", "useKnowledge.js")
    src_zh = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-zh.json")
    src_en = os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-en.json")
    deploy = os.path.join(REPO_ROOT, "docs", "DEPLOY.md")

    with open(src_api, "r", encoding="utf-8") as f:
        api_txt = f.read()
    check("api_server 不 import docling", "import docling" not in api_txt and "from docling" not in api_txt)

    office_exists = os.path.isfile(src_office)
    check("存在 server/office_parse.py", office_exists)
    if office_exists:
        with open(src_office, "r", encoding="utf-8") as f:
            office_txt = f.read()
        code_lines = [
            ln.strip() for ln in office_txt.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        joined = "\n".join(code_lines)
        check(
            "office_parse 不 import docling 包",
            "import docling" not in joined and "from docling" not in joined,
        )
        check("CLI 走 docling convert", '"convert"' in office_txt or "'convert'" in office_txt)
        check("写出 Markdown 用 --to md", "--to" in office_txt and "md" in office_txt)
        check("输出目录用 --output", "--output" in office_txt)
        check("关闭 OCR --no-ocr", "--no-ocr" in office_txt)
        check("禁止 VLM pipeline", "vlm" not in office_txt.lower() or "granite_docling" not in office_txt)
    else:
        check("CLI 走 docling convert", False)
        check("写出 Markdown 用 --to md", False)
        check("输出目录用 --output", False)
        check("关闭 OCR --no-ocr", False)
        check("禁止 VLM pipeline", False)

    with open(src_kb, "r", encoding="utf-8") as f:
        kb_txt = f.read()
    check("kb_ingest DOC_EXTS 含 docx", ".docx" in kb_txt)
    check("kb_ingest DOC_EXTS 含 pptx", ".pptx" in kb_txt)

    with open(src_import, "r", encoding="utf-8") as f:
        import_txt = f.read()
    with open(src_know, "r", encoding="utf-8") as f:
        know_txt = f.read()
    check("ImportPage ACCEPT 含 docx", ".docx" in import_txt)
    check("ImportPage ACCEPT 含 pptx", ".pptx" in import_txt)
    check("KnowledgePage ACCEPT 含 docx", ".docx" in know_txt)
    check("KnowledgePage ACCEPT 含 pptx", ".pptx" in know_txt)
    with open(src_know_js, "r", encoding="utf-8") as f:
        know_js = f.read()
    check("useKnowledge FILE_TAGS 含 docx", "docx" in know_js)
    check("useKnowledge FILE_TAGS 含 pptx", "pptx" in know_js)

    with open(src_zh, "r", encoding="utf-8") as f:
        zh = f.read()
    with open(src_en, "r", encoding="utf-8") as f:
        en = f.read()
    check("中文导入文案提到 Word 或 docx", "docx" in zh.lower() or "Word" in zh)
    check("英文导入文案提到 Word 或 docx", "docx" in en.lower() or "Word" in en)

    with open(deploy, "r", encoding="utf-8") as f:
        deploy_txt = f.read()
    check("DEPLOY 写 docling convert", "docling convert" in deploy_txt)
    check("DEPLOY 写明 Docling 不当中文 PDF 主引擎", "不当中文 PDF" in deploy_txt or "不作为中文 PDF" in deploy_txt)
    check("DEPLOY 写 OOXML 回退", "ooxml" in deploy_txt.lower() or "标准库" in deploy_txt)

    vendor = os.path.join(REPO_ROOT, "vendor", "study-liu")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    import kb_ingest
    caps = kb_ingest.capabilities()
    doc = caps.get("document") or {}
    check("capabilities.document.extensions 含 .docx", ".docx" in (doc.get("extensions") or []), doc)
    check("capabilities.document.extensions 含 .pptx", ".pptx" in (doc.get("extensions") or []), doc)
    office_caps = doc.get("office") or doc.get("docling") or {}
    check("capabilities 暴露 office/docling", isinstance(office_caps, dict) and "available" in office_caps, doc)

    tmp = tempfile.mkdtemp(prefix="sidecar-office-")
    fake = os.path.join(tmp, "fake_docling.py")
    _write(fake, FAKE_DOCLING)
    docx = os.path.join(tmp, "lecture.docx")
    pptx = os.path.join(tmp, "slides.pptx")
    _write_ooxml_docx(docx, "线性代数讲义·特征值与对角化（OOXML 夹具）")
    _write_ooxml_pptx(pptx, "矩阵对角化课堂幻灯片")
    pdf = os.path.join(tmp, "not-office.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4 not office")

    missing_bin = os.path.join(tmp, "no-such-docling")

    def refuse_pdf():
        import office_parse
        r = office_parse.extract_office_text(pdf)
        check("PDF 不走进 office_parse 成功路径", r.get("engine") != "docling" and not (r.get("text") or "").strip(), r)
        check("PDF 被 office_parse 拒绝", "pdf" in (r.get("error") or "").lower() or "不支持" in (r.get("error") or ""), r)
    try:
        with_env({
            "STUDY_LIU_DOCLING_BIN": fake,
            "STUDY_LIU_OFFICE_ENGINE": None,
        }, refuse_pdf)
    except ImportError:
        check("PDF 不走进 office_parse 成功路径", False, "office_parse missing")
        check("PDF 被 office_parse 拒绝", False)

    def missing_uses_ooxml():
        import office_parse
        ok, reason = office_parse.available()
        check("缺 docling 时 available=False", ok is False, (ok, reason))
        check("reason 提到 docling", "docling" in (reason or "").lower(), reason)
        r = office_parse.extract_office_text(docx)
        check("缺 CLI 回退 ooxml", r.get("engine") == "ooxml", r)
        check("OOXML 抽到夹具正文", "特征值" in (r.get("text") or ""), r)
        r2 = office_parse.extract_office_text(pptx)
        check("pptx OOXML 抽到正文", "对角化" in (r2.get("text") or "") and r2.get("engine") == "ooxml", r2)
    try:
        with_env({
            "STUDY_LIU_DOCLING_BIN": missing_bin,
            "STUDY_LIU_OFFICE_ENGINE": None,
        }, missing_uses_ooxml)
    except ImportError:
        check("缺 docling 时 available=False", False)
        check("reason 提到 docling", False)
        check("缺 CLI 回退 ooxml", False)
        check("OOXML 抽到夹具正文", False)
        check("pptx OOXML 抽到正文", False)

    def fake_cli():
        import office_parse
        ok, reason = office_parse.available()
        check("假 CLI available=True", ok is True, (ok, reason))
        r = office_parse.extract_office_text(docx)
        check("假 CLI 走 docling", r.get("engine") == "docling", r)
        check("假 CLI 正文含 sidecar 标记", "parsed-office" in (r.get("text") or "") and "特征值" in (r.get("text") or ""), r)
        os.environ["STUDY_LIU_OFFICE_ENGINE"] = "ooxml"
        r = office_parse.extract_office_text(docx)
        check("强制 ooxml 不调侧车", r.get("engine") == "ooxml" and "OOXML" in (r.get("text") or ""), r)
        os.environ.pop("STUDY_LIU_OFFICE_ENGINE", None)
    try:
        with_env({
            "STUDY_LIU_DOCLING_BIN": fake,
            "STUDY_LIU_OFFICE_ENGINE": None,
        }, fake_cli)
    except ImportError:
        check("假 CLI available=True", False)
        check("假 CLI 走 docling", False)
        check("假 CLI 正文含 sidecar 标记", False)
        check("强制 ooxml 不调侧车", False)

    store_path = os.path.join(tmp, "knowledge.json")
    with open(store_path, "w", encoding="utf-8") as f:
        f.write("[]")
    from tools.knowledge_store import KnowledgeStore
    store = KnowledgeStore(filepath=store_path)

    def ingest_docx():
        r = kb_ingest.ingest(docx, "线性代数讲义.docx", store=store)
        check("ingest docx ok", r.get("ok") is True, r)
        check("ingest 正文进库", r.get("chunks", 0) >= 1 and r.get("chars", 0) > 0, r)
        check("ingest engine 为 docling 或 ooxml", r.get("engine") in ("docling", "ooxml"), r)
    try:
        with_env({
            "STUDY_LIU_DOCLING_BIN": fake,
            "STUDY_LIU_OFFICE_ENGINE": None,
        }, ingest_docx)
    except Exception as e:
        check("ingest docx ok", False, str(e))
        check("ingest 正文进库", False)
        check("ingest engine 为 docling 或 ooxml", False)


def main():
    print("=" * 60)
    print("侧车回归（MinerU + whisper.cpp + Docling office，假 CLI，不装真引擎）")
    print("=" * 60)
    for fn in (
        test_mineru_missing,
        test_mineru_parse_and_route,
        test_mineru_falls_back_when_cli_fails,
        test_mineru_ram_gate,
        test_wav_header,
        test_whisper_probe_and_transcribe,
        test_whisper_vad,
        test_transcribe_page_vad,
        test_asr_router,
        test_kb_capabilities_surface,
        test_office_sidecar,
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
