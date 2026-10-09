# -*- coding: utf-8 -*-
"""离线中文语音转写。

有 whisper.cpp 就优先（1.6G 只用 ggml-small 多语言模型）；缺了才 Vosk。
whisper 已经能扛时 status() 不加载约 150MB 的 Vosk。二进制和 ggml
模型在仓库外。不走 Docling ASR / openai-whisper。

强制引擎：``STUDY_LIU_ASR_ENGINE=whisper|vosk``。

设计要点（改动前请先读）：

1. **导入期零依赖。** 整个后端目前是纯标准库，这是刻意保持的 —— 1.6G 内存的机器上
   多一个装不上的依赖就多一个起不来的可能。所以 vosk 只在**第一次真正要转写时**才 import，
   且 import 失败 / 模型缺失 / 动态库加载失败，都只让 ``available()`` 返回 False，
   绝不让 api_server 起不来。whisper.cpp 同样只在转写时 subprocess 调用。

2. **模型只加载一次。** Model 加载约 0.6s、常驻约 150MB（实测峰值 178MB）。
   必须复用同一个实例；用双检锁保护，否则并发首批请求会重复加载、内存直接翻倍。

3. **只吃 16kHz 单声道 16bit PCM。** 重采样放在浏览器（Web Audio API 的
   ``OfflineAudioContext(1, 1, 16000).decodeAudioData``），
   因此服务器**不需要 ffmpeg**（线上确实没装）。

4. **KaldiRecognizer 不能跨请求复用**，每个请求新建一个；Model 是只读的，可以共享。

路径解析顺序（都可被环境变量覆盖）：
   ``STUDY_LIU_ASR_LIBS``  / ``STUDY_LIU_ASR_MODEL``
   → ``/home/admin/asr/libs`` / ``/home/admin/asr/vosk-model-small-cn-0.22``（线上）
   → ``<仓库根>/vendor/asr/...``（本地自带模型时用）
"""
from __future__ import annotations

import os
import re
import sys
import time
import threading

# 模型只认这个采样率；前端负责把任意音频重采样到这个值后再上传。
SAMPLE_RATE = 16000

# 单次请求的 PCM 上限。16k*16bit*单声道 = 32000 字节/秒，15MB ≈ 8.2 分钟。
# 卡在 15MB 是为了给 nginx 的 client_max_body_size（20m）留出余量。
MAX_PCM_BYTES = 15 * 1024 * 1024
MAX_SECONDS = MAX_PCM_BYTES // (SAMPLE_RATE * 2)

# 线上固定位置。放在仓库外，因为模型 66MB 不能进 git（Gitee 会拒）。
_SERVER_LIBS = "/home/admin/asr/libs"
_SERVER_MODEL = "/home/admin/asr/vosk-model-small-cn-0.22"

_LOCK = threading.Lock()
_MODEL = None
_ERROR = ""  # 加载失败的原因，原样给前端看（都是「怎么修」的中文话术）


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def libs_dir() -> str:
    return os.environ.get("STUDY_LIU_ASR_LIBS") or _SERVER_LIBS


def model_dir() -> str:
    env = os.environ.get("STUDY_LIU_ASR_MODEL")
    if env:
        return env
    if os.path.isdir(_SERVER_MODEL):
        return _SERVER_MODEL
    return os.path.join(_repo_root(), "vendor", "asr", "vosk-model-small-cn-0.22")


def _ensure_model():
    """返回 Model 实例；不可用时抛 RuntimeError（消息可直接展示给用户）。"""
    global _MODEL, _ERROR
    if _MODEL is not None:
        return _MODEL

    with _LOCK:
        # 双检：等锁期间可能已被别的线程加载好了
        if _MODEL is not None:
            return _MODEL
        if _ERROR:
            raise RuntimeError(_ERROR)

        libs = libs_dir()
        model_path = model_dir()

        if not os.path.isdir(model_path):
            _ERROR = ("语音模型未安装：找不到 %s。" % model_path) + \
                     "把 vosk-model-small-cn-0.22 放到该目录即可，无需重启。"
            raise RuntimeError(_ERROR)

        # 把自带 libs 目录插到 sys.path 最前面：线上没有全局装 vosk。
        if os.path.isdir(libs) and libs not in sys.path:
            sys.path.insert(0, libs)

        try:
            from vosk import Model, SetLogLevel  # noqa: WPS433 延迟导入是刻意的
        except Exception as e:  # ImportError / OSError（缺 libvosk.so）都归到这里
            _ERROR = ("语音识别引擎未就绪：%s。"
                      "需要在服务器执行 pip3 install --target %s vosk" % (e, libs))
            raise RuntimeError(_ERROR)

        try:
            SetLogLevel(-1)  # 关掉 Kaldi 的日志噪音，否则每次请求都刷屏
        except Exception:
            pass

        try:
            _MODEL = Model(model_path)
        except Exception as e:
            _ERROR = "语音模型加载失败：%s" % e
            raise RuntimeError(_ERROR)

        return _MODEL


# 中文之间的空格要去掉（Vosk 小模型的输出形如「同学 们 好」），
# 但西文单词之间、以及中英之间的空格要保留，否则 "hello world 你好" 会被粘成一坨。
_CJK = r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3000-\u303f\uff00-\uffef"
_SPACE_BETWEEN_CJK = re.compile(r"(?<=[%s])\s+(?=[%s])" % (_CJK, _CJK))
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def tidy(text: str) -> str:
    """整理 Vosk 输出：去掉汉字之间的空格、压掉多余空白。不改动标点。"""
    if not text:
        return ""
    out = _SPACE_BETWEEN_CJK.sub("", text)
    out = _MULTI_SPACE.sub(" ", out)
    return out.strip()


def _whisper_mod():
    try:
        import whisper_cpp
        return whisper_cpp
    except Exception:
        return None


def _force_engine():
    return (os.environ.get("STUDY_LIU_ASR_ENGINE") or "").strip().lower()


def _whisper_ready():
    """whisper.cpp 是否可用。强制 vosk 时视为不可用。"""
    if _force_engine() == "vosk":
        return False, "已强制 Vosk（STUDY_LIU_ASR_ENGINE=vosk）", ""
    w = _whisper_mod()
    if w is None:
        return False, "whisper_cpp 模块不可用", ""
    return w.probe()


def available():
    """探测可用性。返回 (ok, reason)。reason 为空串表示可用。"""
    force = _force_engine()
    w_ok, w_reason, _w_model = _whisper_ready()
    if force == "whisper":
        if w_ok:
            return True, ""
        return False, w_reason
    if w_ok:
        return True, ""
    try:
        _ensure_model()
    except RuntimeError as e:
        return False, str(e)
    except Exception as e:  # 不允许任何意外把探测接口自身打挂
        return False, "语音识别不可用：%s" % e
    return True, ""


def status():
    force = _force_engine()
    w_ok, w_reason, w_model = _whisper_ready()
    vosk_ok, vosk_reason = False, ""
    # whisper 已经能扛时不要再把 150MB Vosk 拉进 1.6G 机器。
    if force == "vosk" or not w_ok:
        try:
            _ensure_model()
            vosk_ok, vosk_reason = True, ""
        except RuntimeError as e:
            vosk_reason = str(e)
        except Exception as e:
            vosk_reason = "语音识别不可用：%s" % e
    else:
        vosk_reason = "未探测（当前走 whisper.cpp）"

    use_whisper = w_ok and force != "vosk"
    if force == "whisper":
        use_whisper = w_ok
        ok = w_ok
        reason = "" if w_ok else w_reason
    elif use_whisper:
        ok, reason = True, ""
    else:
        ok, reason = vosk_ok, ("" if vosk_ok else vosk_reason)

    if use_whisper:
        engine, model = "whisper.cpp", w_model
    elif vosk_ok:
        engine, model = "vosk", os.path.basename(model_dir())
    else:
        engine, model = "", ""

    w_vad, w_vad_model = False, ""
    if w_ok:
        w = _whisper_mod()
        try:
            wst = w.status() if w else {}
            w_vad = bool(wst.get("vad"))
            w_vad_model = wst.get("vad_model") or ""
        except Exception:
            w_vad, w_vad_model = False, ""

    return {
        "ok": ok,
        "available": ok,
        "reason": reason,
        "engine": engine,
        "model": model,
        "vad": bool(use_whisper and w_vad),
        "vad_model": w_vad_model if use_whisper else "",
        "backends": {
            "whisper.cpp": {
                "available": w_ok,
                "reason": w_reason,
                "model": w_model,
                "vad": w_vad,
                "vad_model": w_vad_model,
            },
            "vosk": {"available": vosk_ok, "reason": vosk_reason if not vosk_ok else "",
                     "model": os.path.basename(model_dir()) if vosk_ok else ""},
        },
        "sample_rate": SAMPLE_RATE,
        "max_bytes": MAX_PCM_BYTES,
        "max_seconds": MAX_SECONDS,
    }


def transcribe(pcm: bytes):
    """把 16k 单声道 16bit PCM 转成文字。

    返回 dict：{text, duration, elapsed, rtf}。异常一律抛 RuntimeError。
    """
    if not pcm:
        raise RuntimeError("没有收到音频数据")
    if len(pcm) % 2:
        # 奇数长度说明前端切字节切歪了，直接截断比让 Kaldi 报错好
        pcm = pcm[:-1]
    if len(pcm) > MAX_PCM_BYTES:
        raise RuntimeError("音频过长：%.1f 分钟，上限 %.0f 分钟"
                           % (len(pcm) / (SAMPLE_RATE * 2) / 60,
                              MAX_SECONDS / 60))

    w_ok, w_reason, _w_model = _whisper_ready()
    force = _force_engine()
    use_whisper = w_ok and force != "vosk"
    if force == "whisper" and not w_ok:
        raise RuntimeError(w_reason)

    if use_whisper:
        w = _whisper_mod()
        t0 = time.time()
        r = w.transcribe(pcm)
        elapsed = time.time() - t0
        duration = len(pcm) / (SAMPLE_RATE * 2)
        return {
            "text": tidy(r.get("text") or ""),
            "duration": round(duration, 2),
            "elapsed": round(elapsed, 2),
            "rtf": round(elapsed / duration, 3) if duration else 0,
            "engine": "whisper.cpp",
            "model": r.get("model") or "",
            "vad": bool(r.get("vad")),
            "vad_model": r.get("vad_model") or "",
        }

    model = _ensure_model()

    import json
    from vosk import KaldiRecognizer

    rec = KaldiRecognizer(model, SAMPLE_RATE)
    # 关掉 SetWords，只要正文；开词级时间戳会让结果 JSON 大很多，这里用不上。

    # 4000 字节一片（约 0.125s），与桌面版脚本保持一致
    CHUNK = 4000
    t0 = time.time()
    parts = []
    for i in range(0, len(pcm), CHUNK):
        if rec.AcceptWaveform(pcm[i:i + CHUNK]):
            try:
                parts.append(json.loads(rec.Result()).get("text", ""))
            except Exception:
                pass
    try:
        parts.append(json.loads(rec.FinalResult()).get("text", ""))
    except Exception:
        pass

    elapsed = time.time() - t0
    duration = len(pcm) / (SAMPLE_RATE * 2)
    text = tidy(" ".join(p for p in parts if p))

    return {
        "text": text,
        "duration": round(duration, 2),
        "elapsed": round(elapsed, 2),
        # 语速比：<1 表示比实时快。实测服务器约 0.10（小模型 + 2 vCPU）
        "rtf": round(elapsed / duration, 3) if duration else 0,
        "engine": "vosk",
        "model": os.path.basename(model_dir()),
    }
