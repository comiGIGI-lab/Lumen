# 生成本地可叠环境声短循环。禁止热链、禁止抓参考站片源。
import math
import random
import struct
import subprocess
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent
SR = 22050
DUR = 10
N = SR * DUR


def write_wav(path, samples):
    peak = max((abs(x) for x in samples), default=1e-6)
    scale = 0.72 / peak if peak else 0
    frames = b"".join(
        struct.pack("<h", max(-32767, min(32767, int(s * scale * 32767)))) for s in samples
    )
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)


def white(rng):
    return rng.uniform(-1.0, 1.0)


def spring_rain():
    rng = random.Random(7)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.96 * b + 0.04 * w
        env = 0.72 + 0.28 * math.sin(2 * math.pi * i / SR / 5.5)
        out[i] += (w * 0.22 + (w - b) * 0.3) * 0.2 * env
    i = 0
    while i < N:
        i += rng.randint(int(SR * 0.01), int(SR * 0.06))
        if i >= N:
            break
        amp = rng.uniform(0.05, 0.2)
        decay = rng.uniform(0.88, 0.96)
        for k in range(rng.randint(30, 180)):
            if i + k >= N:
                break
            out[i + k] += amp * (decay ** k) * white(rng)
    return out


def summer_frogs():
    rng = random.Random(19)
    out = [0.0] * N
    t = 0
    while t < N:
        gap = rng.randint(int(SR * 0.35), int(SR * 1.4))
        t += gap
        f0 = rng.uniform(420, 780)
        length = rng.randint(int(SR * 0.08), int(SR * 0.22))
        for k in range(length):
            if t + k >= N:
                break
            env = math.sin(math.pi * k / length) ** 1.4
            wob = 1 + 0.08 * math.sin(2 * math.pi * 18 * k / SR)
            out[t + k] += env * 0.55 * math.sin(2 * math.pi * f0 * wob * k / SR)
            if k % 7 == 0:
                out[t + k] += env * 0.08 * white(rng)
    for i in range(N):
        out[i] += 0.02 * white(rng)
    return out


def fireplace():
    rng = random.Random(3)
    out = [0.0] * N
    b1 = b2 = 0.0
    for i in range(N):
        w = white(rng)
        b1 = (b1 + 0.03 * w) / 1.03
        b2 = 0.9 * b2 + 0.1 * w
        crack = w if rng.random() < 0.014 else 0.0
        out[i] = b1 * 0.7 + b2 * 0.15 + crack * 0.45
    return out


def cafe():
    rng = random.Random(29)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.993 * b + 0.007 * w
        murmur = b * 0.9 + 0.04 * math.sin(2 * math.pi * 110 * i / SR)
        out[i] = murmur
    i = int(SR * 0.8)
    while i < N:
        length = rng.randint(200, 900)
        for k in range(length):
            if i + k >= N:
                break
            env = math.sin(math.pi * k / length)
            out[i + k] += env * rng.uniform(0.08, 0.22) * white(rng)
        i += rng.randint(int(SR * 1.2), int(SR * 2.8))
    return out


def keyboard():
    rng = random.Random(41)
    out = [0.0] * N
    i = 0
    while i < N:
        i += rng.randint(int(SR * 0.07), int(SR * 0.28))
        if i >= N:
            break
        f = rng.uniform(1800, 4200)
        for k in range(90):
            if i + k >= N:
                break
            env = math.exp(-k / 18)
            out[i + k] += env * 0.7 * math.sin(2 * math.pi * f * k / SR)
            if k < 6:
                out[i + k] += env * 0.3 * white(rng)
    return out


def waves():
    rng = random.Random(13)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.98 * b + 0.02 * w
        swell = 0.5 + 0.5 * math.sin(2 * math.pi * i / SR / 7.0)
        crash = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * i / SR / 3.4)) ** 3
        out[i] = (b * 0.6 + w * 0.18) * swell * crash
    return out


def wind():
    rng = random.Random(17)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.97 * b + 0.03 * w
        lfo = 0.45 + 0.55 * math.sin(2 * math.pi * i / SR / 6.2)
        gust = 0.7 + 0.3 * math.sin(2 * math.pi * i / SR / 1.7)
        out[i] = (w - b) * 0.5 * lfo * gust + b * 0.12
    return out


def train():
    rng = random.Random(31)
    out = [0.0] * N
    for i in range(N):
        rumble = 0.22 * math.sin(2 * math.pi * 48 * i / SR) + 0.12 * math.sin(2 * math.pi * 96 * i / SR)
        out[i] = rumble + 0.06 * white(rng)
        if (i * 4 // SR) % 2 == 0:
            clack = math.exp(-((i % (SR // 4)) / 90))
            out[i] += clack * 0.28 * white(rng)
    return out


def stream():
    rng = random.Random(11)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.92 * b + 0.08 * w
        hiss = w - b
        bubble = 0.0
        if rng.random() < 0.01:
            bubble = rng.uniform(0.08, 0.2)
        out[i] = hiss * 0.45 + b * 0.1 + bubble * w
    return out


def cicada():
    rng = random.Random(23)
    out = [0.0] * N
    for i in range(N):
        t = i / SR
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 4.8 * t)
        buzz = math.sin(2 * math.pi * 4200 * t) * math.sin(2 * math.pi * 70 * t)
        out[i] = 0.35 * pulse ** 3 * buzz + 0.03 * white(rng)
    return out


def page_turn():
    rng = random.Random(61)
    out = [0.0] * N
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.985 * b + 0.015 * w
        out[i] = (w - b) * 0.018
    t = int(SR * 0.35)
    while t < N:
        length = rng.randint(int(SR * 0.08), int(SR * 0.15))
        for k in range(length):
            if t + k >= N:
                break
            env = math.sin(math.pi * k / length) ** 1.15
            hiss = white(rng)
            sweep = 720 + 1480 * (k / length)
            rustle = hiss * 0.52 + 0.16 * math.sin(2 * math.pi * sweep * k / SR)
            out[t + k] += env * 0.6 * rustle
        t += rng.randint(int(SR * 1.15), int(SR * 1.9))
    return out


def whale_song():
    rng = random.Random(73)
    out = [0.0] * N
    t = int(SR * 0.4)
    calls = 0
    while t < N and calls < 3:
        length = rng.randint(int(SR * 1.35), int(SR * 2.15))
        if t + length >= N:
            break
        f0 = rng.uniform(90, 180)
        f1 = rng.uniform(220, 360)
        for k in range(length):
            env = math.sin(math.pi * k / length) ** 1.6
            frac = k / length
            f = f0 + (f1 - f0) * (0.15 + 0.85 * frac)
            wob = 1 + 0.012 * math.sin(2 * math.pi * 0.7 * k / SR)
            tone = math.sin(2 * math.pi * f * wob * k / SR)
            over = 0.12 * math.sin(2 * math.pi * f * 1.5 * k / SR)
            out[t + k] += env * 0.28 * (tone + over)
        t += length + rng.randint(int(SR * 0.9), int(SR * 1.8))
        calls += 1
    b = 0.0
    for i in range(N):
        w = white(rng)
        b = 0.997 * b + 0.003 * w
        out[i] += b * 0.02
    return out


def birds():
    rng = random.Random(37)
    out = [0.0] * N
    i = int(SR * 0.4)
    while i < N:
        length = rng.randint(int(SR * 0.12), int(SR * 0.32))
        f0 = rng.uniform(1400, 3200)
        bend = rng.uniform(-900, 1400)
        for k in range(length):
            if i + k >= N:
                break
            env = math.sin(math.pi * k / length) ** 1.2
            f = f0 + bend * (k / length)
            out[i + k] += env * 0.5 * math.sin(2 * math.pi * f * k / SR)
        i += rng.randint(int(SR * 0.7), int(SR * 1.8))
    for i in range(N):
        out[i] += 0.015 * white(rng)
    return out


MAKERS = {
    "spring-rain": spring_rain,
    "summer-frogs": summer_frogs,
    "fireplace": fireplace,
    "cafe": cafe,
    "keyboard": keyboard,
    "waves": waves,
    "wind": wind,
    "train": train,
    "stream": stream,
    "cicada": cicada,
    "birds": birds,
    "page-turn": page_turn,
    "whale-song": whale_song,
}

FFMPEG = Path(r"D:\ffmpeg\bin\ffmpeg.exe")


def main():
    import sys
    names = sys.argv[1:] or list(MAKERS)
    ffmpeg = str(FFMPEG if FFMPEG.exists() else "ffmpeg")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        fn = MAKERS[name]
        wav = OUT / f"{name}.wav"
        mp3 = OUT / f"{name}.mp3"
        write_wav(wav, fn())
        subprocess.run(
            [ffmpeg, "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "64k", str(mp3)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wav.unlink(missing_ok=True)
        print("ok", mp3.name, mp3.stat().st_size)


if __name__ == "__main__":
    main()
