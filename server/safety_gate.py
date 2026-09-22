# -*- coding: utf-8 -*-
"""内容安全 · 判定引擎。

对外只暴露两个函数：

    check_sensitive(text) -> list
        与改造前签名、返回结构完全一致：入参 str，返回 list[str]，空列表代表放行。
        三处调用点（/api/plan、/api/chat、/api/plan/stream）不需要改调用方式。
        列表元素是「命中的词」或「命中的片段」，只用于后端日志，不再回显给用户。

    check_detail(text) -> dict
        判定明细（action / layer / hits / reason），供后端日志与回归脚本使用。

判定顺序（命中即返回，不再往下走）：
    1. A1 复合操作词组        → BLOCK
    2. 拼音层（≥3 字母键）     → BLOCK
    3. 意图模式正则           → 先查豁免，未豁免则 BLOCK
    4. A2 议题名词 + 补充变体  → 先查豁免，未豁免则 BLOCK
    5. 其余放行

两个修正点（相对改造前）：
    · 词表项与输入统一 lower —— 改造前只 lower 了输入，词表里的 "DDoS" 永远匹配不上
      小写输入（见缺陷清单 D-01）。
    · 「命中词」不再出现在 HTTP 响应里，只写后端日志。
"""

import json
import os
import re
import time

from safety_rules import (  # noqa: F401  （规则层可单独 import 做配置热改）
    ENABLE_CONTEXT_EXEMPTION,
    ENABLE_INTENT_PATTERNS,
    ENABLE_PINYIN_LAYER,
    INTENT_PATTERN_RES,
    PINYIN_KEYS,
    PINYIN_MIN_KEY_LEN,
    is_exempted,
)
from safety_words import (
    A1_BLOCK_WORDS,
    A2_TOPIC_WORDS,
    EXTRA_TOPIC_WORDS,
)

# 全角 → 半角（数字与字母），用于拼音键匹配与变体识别
_FULLWIDTH = str.maketrans(
    "０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789abcdefghijklmnopqrstuvwxyz",
)
_NON_WORD_RE = re.compile(r"[^\w一-鿿]+")

# 审计日志落盘路径；由 api_server 用 set_audit_log() 指定，未指定时只打控制台
_AUDIT_LOG_PATH = None

# 单条日志里回显的原始输入长度上限（防止超长输入撑爆日志）
_MAX_LOGGED_TEXT = 200


def set_audit_log(path):
    """指定命中明细的落盘路径（JSONL）。传 None 则只打控制台。"""
    global _AUDIT_LOG_PATH
    _AUDIT_LOG_PATH = path


def normalize(text: str) -> str:
    """全角转半角 + 去掉标点与空白，用于抗「加空格 / 加标点 / 全角」的绕过。"""
    if not text:
        return ""
    return _NON_WORD_RE.sub("", text.translate(_FULLWIDTH)).lower()


def _scan(words, low, norm):
    """在「原文小写」与「归一化串」里同时找词，返回命中的词列表。"""
    return [w for w in words if w.lower() in low or w.lower() in norm]


def check_detail(text: str) -> dict:
    """完整判定明细。action 取值 "PASS" / "BLOCK"。"""
    if not text or not text.strip():
        return {"action": "PASS", "layer": "-", "hits": [], "reason": "空输入"}

    raw = text
    low = text.lower()
    norm = normalize(text)

    # 1. A1 复合操作词组：命中即拦
    hits = _scan(A1_BLOCK_WORDS, low, norm)
    if hits:
        return {"action": "BLOCK", "layer": "A1", "hits": hits,
                "reason": "复合操作词组"}

    # 2. 拼音层
    if ENABLE_PINYIN_LAYER:
        compact = norm.replace(" ", "")
        for key, word in PINYIN_KEYS.items():
            if len(key) < PINYIN_MIN_KEY_LEN:      # 双字母键误伤面太大，直接跳过
                continue
            if key in compact:
                return {"action": "BLOCK", "layer": "C", "hits": [word],
                        "reason": "拼音键 %s" % key}

    # 3. 意图模式：命中后先过语境豁免
    if ENABLE_INTENT_PATTERNS:
        for rx in INTENT_PATTERN_RES:
            m = rx.search(raw)
            if not m:
                continue
            if is_exempted(raw):
                return {"action": "PASS", "layer": "B", "hits": [m.group(0)],
                        "reason": "意图命中·语境豁免"}
            return {"action": "BLOCK", "layer": "B", "hits": [m.group(0)],
                    "reason": "意图模式"}

    # 4. A2 议题名词：命中后先过语境豁免
    hits = _scan(A2_TOPIC_WORDS, low, norm)
    hits += [w for w in EXTRA_TOPIC_WORDS if w.lower() in low]
    if hits:
        if is_exempted(raw):
            return {"action": "PASS", "layer": "A2", "hits": hits,
                    "reason": "议题名词·语境豁免"}
        return {"action": "BLOCK", "layer": "A2", "hits": hits,
                "reason": "议题名词"}

    return {"action": "PASS", "layer": "-", "hits": [], "reason": "默认放行"}


def check_sensitive(text: str) -> list:
    """返回文本中命中的内容安全风险项列表（空列表 = 放行）。

    签名与返回结构与改造前保持一致（list[str]），三处调用点无需改动。
    非空列表只在判定为 BLOCK 时出现——这样 `if check_sensitive(x): 拒绝`
    的旧调用语义仍然成立；被语境豁免放行的命中项不出现在返回值里，
    但会保留在 check_detail()["hits"] 中供日志使用。
    """
    d = check_detail(text)
    return d["hits"] if d["action"] == "BLOCK" else []


def log_safety_hit(source: str, text: str, detail: dict, client_id: str = "") -> None:
    """把命中明细写进后端日志。

    控制台一行 + JSONL 落盘（路径由 set_audit_log 指定）。
    用户侧只会看到固定文案「该请求未通过内容安全审核」，命中词不回显。
    """
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "client_id": client_id or "",
        "action": detail.get("action"),
        "layer": detail.get("layer"),
        "hits": detail.get("hits", []),
        "reason": detail.get("reason"),
        # 原始输入截断后入库，便于事后复盘误伤
        "text": (text or "")[:_MAX_LOGGED_TEXT],
    }
    line = json.dumps(record, ensure_ascii=False)
    try:
        print("[safety] " + line, flush=True)
    except Exception:
        pass
    if not _AUDIT_LOG_PATH:
        return
    try:
        os.makedirs(os.path.dirname(_AUDIT_LOG_PATH), exist_ok=True)
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
