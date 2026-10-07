#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""study-liu Web API 后端 —— 纯标准库实现（零第三方依赖）。

设计目标
--------
把 study-liu 桌面版（Tkinter）背后的 **真实 Agent 代码** 原封不动地暴露成 HTTP API，
给 Vue3 + Vite 前端调用，从而跑通：

    课程名 → 意图 → Planner → Searcher → Writer → Reviewer → 三栏结果

所有业务逻辑都来自 study-liu 源码（core / agents / tools），本文件只负责：
  1. 定位源码目录并加入 sys.path
  2. 把函数调用包成 JSON 接口
  3. 把 agent_loop 写出的 data/trace.log 实时转成 SSE 事件流

依赖：Python 3.9+ 标准库（http.server / json / threading）。
      study-liu 的 core.llm 需要 requests；其余依赖（dotenv / cryptography）都是可选的。

启动：
    python server/api_server.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ============================================================
# 1. 定位 study-liu 源码目录
# ============================================================
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_ROOT = os.path.dirname(HERE)                 # study-liu-web/
WORKSPACE = os.path.dirname(WEB_ROOT)            # 竞赛/

# 内容安全模块与本文件同目录。把 HERE 加进 sys.path，使
# `python server/api_server.py` 与 `python -m server.api_server` 两种启动方式都能 import 到。
# 必须在 SOURCE_DIR 插进 sys.path 之前导入，避免被源码目录里的同名模块遮蔽。
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from safety_gate import (                                           # noqa: E402
    # check_sensitive 保持可用（签名与返回结构不变），供外部脚本与后续接口直接复用
    check_detail, check_sensitive, log_safety_hit, set_audit_log,
)
# B30 危机干预复用规则层现成的语境豁免，避免和安全层写成两套判断
from safety_rules import is_exempted                                 # noqa: E402

# 危机响应层（2026-09-26 新增）：判定 + 号码清洗都在那边，本文件只挂接口
from crisis import (                                                 # noqa: E402
    HOTLINES,
    crisis_verdict,
    crisis_result_payload,
    crisis_chat_response,
    strip_non_whitelist_numbers,
)

# 离线语音转写。asr 内部默认 Vosk（延迟 import），whisper.cpp 是可选侧车；
# 引擎/模型缺失只让 /api/asr 返回明确的中文提示，不会拖垮整个服务。
import asr as asr_mod                                               # noqa: E402


def _looks_like_source(path: str) -> bool:
    """判断目录是否是 study-liu 源码根（含 core/agent_loop.py 与 agents/planner.py）。"""
    return (
        os.path.isfile(os.path.join(path, "core", "agent_loop.py"))
        and os.path.isfile(os.path.join(path, "agents", "planner.py"))
    )


def _find_source() -> str:
    """按优先级查找 study-liu 源码根目录。

    1. 环境变量 STUDY_LIU_SRC
    2. 项目内 server/source.json 的 source_path
    3. 工作区里所有名为 study-liu* 的目录（含一层子目录，如
       study-liu源码0918更新版本/study-liu源码）
    """
    candidates = []

    env = os.environ.get("STUDY_LIU_SRC")
    if env:
        candidates.append(env)

    cfg = os.path.join(HERE, "source.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                p = json.load(f).get("source_path")
            if p:
                candidates.append(p if os.path.isabs(p) else os.path.join(WEB_ROOT, p))
        except Exception:
            pass

    # 自动搜索：工作区下匹配 study-liu* 的目录（两层深度内）
    try:
        for entry in sorted(os.listdir(WORKSPACE)):
            if not entry.lower().startswith("study-liu") or entry == os.path.basename(WEB_ROOT):
                continue
            top = os.path.join(WORKSPACE, entry)
            if not os.path.isdir(top):
                continue
            candidates.append(top)
            try:
                for sub in sorted(os.listdir(top)):
                    subp = os.path.join(top, sub)
                    if os.path.isdir(subp):
                        candidates.append(subp)
            except OSError:
                pass
    except OSError:
        pass

    # 兜底：项目内自带的 vendor/study-liu（clone 下来即可直接跑，不依赖外部源码目录）。
    # 放在工作区搜索**之后**，这样本地若同时存在原版源码目录，
    # 仍优先使用原版（连同它的 data/ 历史记录一起）。
    vendor = os.path.join(WEB_ROOT, "vendor")
    if os.path.isdir(vendor):
        try:
            for sub in sorted(os.listdir(vendor)):
                subp = os.path.join(vendor, sub)
                if os.path.isdir(subp):
                    candidates.append(subp)
            candidates.append(vendor)
        except OSError:
            pass

    for c in candidates:
        if c and _looks_like_source(c):
            return os.path.abspath(c)

    raise SystemExit(
        "[study-liu-web] 找不到 study-liu 源码目录。\n"
        "请设置环境变量 STUDY_LIU_SRC，或在 server/source.json 写入 {\"source_path\": \"...\"}\n"
        "（正常情况下 vendor/study-liu 里已自带一份源码）"
    )


SOURCE_DIR = _find_source()
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)


# ------------------------------------------------------------
# 1.5 用标准库加载 .env（必须在 import core.config 之前）
#
# 背景：study-liu 的 core/config.py 依赖第三方包 python-dotenv 才能读到 .env。
# 而本后端刻意只用标准库（不装任何第三方依赖）。本机没装 dotenv 时，
# core.config 会**静默跳过 .env**，导致 .env 里写的
#   LLM_PROVIDER=llm
#   LLM_API_KEY=sk-xxxx
# 全部失效，永远退回 mock 模式 —— 前端表现为「没有 LLM 模式」。
#
# 这里先用标准库把 .env 读进 os.environ，再 import core.config，
# 行为就与桌面版一致了，同时不引入任何第三方依赖。
# 真实环境变量优先级更高，不会被 .env 覆盖。
# ------------------------------------------------------------
def _load_dotenv_stdlib():
    """把 .env 的键值对写入 os.environ（已存在的环境变量不覆盖），返回加载的键名列表。"""
    loaded = []
    for path in (os.path.join(SOURCE_DIR, ".env"), os.path.join(WEB_ROOT, ".env")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key.lower().startswith("export "):      # 兼容 `export KEY=value`
                        key = key[7:].strip()
                    if not key:
                        continue
                    value = value.strip()
                    # 去掉成对引号
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                        value = value[1:-1]
                    if key not in os.environ:
                        os.environ[key] = value
                        loaded.append(key)
        except OSError:
            continue
    return loaded


ENV_LOADED = _load_dotenv_stdlib()

# ============================================================
# 2. 导入 study-liu 真实业务模块
# ============================================================
from core.agent_loop import run_plan_pipeline, run_chat_pipeline  # noqa: E402
from core import agent_loop as agent_loop_mod                      # noqa: E402
from core.config import (                                          # noqa: E402
    get_api_key, get_base_url, get_model, get_mode_label, get_provider, is_mock,
    load_settings, save_settings,
)
from core.intent import parse_intent                                # noqa: E402
from tools.user_profile import (                                    # noqa: E402
    DEFAULT_PROFILE, DAILY_HOURS, GOALS, LEVELS,
    format_profile_text, load_profile, save_profile, suggest_plan_length,
)
from tools.markdown_export import render_plan_markdown, suggest_filename   # noqa: E402
from tools.docx_export import render_plan_docx, suggest_docx_filename      # noqa: E402
from tools import progress_store                                    # noqa: E402
from tools import wrong_book_store                                  # noqa: E402
from tools import mindmap_store                                     # noqa: E402
import error_text                                                    # noqa: E402
import accounts                                                      # noqa: E402
from tools import cache_store                                       # noqa: E402
from tools.knowledge_store import KnowledgeStore                    # noqa: E402
from core.paths import data_dir as _data_dir                        # noqa: E402

# 知识库导入：multipart 解析 + 按扩展名分发（都刻意保持零第三方依赖）
from form_parser import MultipartError, parse_multipart             # noqa: E402
from kb_ingest import (                                             # noqa: E402
    capabilities as kb_capabilities, cleanup_uploads, ingest, ingest_text, save_upload,
)

# 上传请求体上限。与 nginx 的 client_max_body_size 保持一致（见 docs/DEPLOY.md）——
# 只调这里不调 nginx 会在 nginx 层被挡（413）；只调 nginx 不调这里会被这层挡。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 知识库总条目上限：这是**公网无鉴权**的写入接口，留个天花板防止被灌满磁盘
MAX_KB_NOTES = 3000

TRACE_FILE = agent_loop_mod._TRACE_FILE
# 历史 / 设置 / 缓存的实际落盘目录（源码运行时 = <源码>/data，不可写时回退 ~/.study-liu/data）
DATA_DIR = _data_dir()

# 账号体系：账号文件放 data/ 下（与其它运行数据一起，备份即整体搬走）。
# 首次启动若一个管理员都没有，自动建 admin/admin123 —— 上线后请立刻改密。
accounts.configure(DATA_DIR)
_created_admin, _admin_msg = accounts.ensure_default_admin()
# 内容安全命中明细的落盘位置（JSONL），与 client_history.json 同目录；
# 写失败时 safety_gate 会静默降级为只打控制台，不影响主流程。
set_audit_log(os.path.join(DATA_DIR, "safety_audit.jsonl"))


# ============================================================
# 3.1 客户端历史隔离（修复"所有人共享同一份历史"）
# ============================================================
# progress.json 是全局的（沿用桌面版存储），这里在上层加一个
# client_id → [course] 的映射文件：历史列表/详情都按浏览器隔离。
CLIENT_HISTORY_FILE = os.path.join(DATA_DIR, "client_history.json")

# 同一浏览器最多保留的历史课程数（防止无限膨胀）
_MAX_CLIENT_COURSES = 50


def load_client_history() -> dict:
    try:
        with open(CLIENT_HISTORY_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_client_history(d: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CLIENT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def record_client_course(client_id: str, course: str) -> None:
    """生成方案成功后，把课程记到该客户端名下（置顶 + 去重 + 截断）。"""
    if not client_id or not course:
        return
    d = load_client_history()
    lst = d.get(client_id, [])
    if course in lst:
        lst.remove(course)
    lst.insert(0, course)
    d[client_id] = lst[:_MAX_CLIENT_COURSES]
    save_client_history(d)


def client_courses(client_id: str) -> set:
    if not client_id:
        return set()
    return set(load_client_history().get(client_id, []))


# ============================================================
# 3.2 内容安全校验
# ============================================================
# 判定逻辑已拆到同目录的三个模块，本文件只负责调用：
#   safety_words.py  词表层（A1 复合操作词组 / A2 议题名词 / 补充变体 / 旧 78 词对照）
#   safety_rules.py  规则层（拼音键、学术与防护语境豁免、意图模式正则，全部可配置）
#   safety_gate.py   判定引擎（check_sensitive / check_detail / log_safety_hit）
#
# check_sensitive(text) -> list 的签名与返回结构与拆分前一致，三处调用点不变。
# 命中后对外只返回固定文案，命中明细写后端日志，不回显给用户。
# 统一成一句固定文案的原因：原实现把命中词直接拼进 error 回显，
# 等于向调用方暴露词表内容，可被用来反向探测词表边界。
SAFETY_ERROR_MESSAGE = "该请求未通过内容安全审核"


# ============================================================
# 3.3 B30 危机干预：固定话术 + 前置短路（独立于内容安全层）
# ============================================================
# 设计原则：
# 1) 危机优先级高于内容安全 —— detect_crisis 在三处调用点的 check_detail() 之前
#    短路，自伤求助永远拿到 200 + 热线，不会被 400 推走。
# 2) 话术与号码都不经模型 —— 危机时刻不赌大模型即兴发挥。
# 3) 热线只放可核验来源 —— 12356 + 010-82951332（都人工拨通过）。
#    号源头收在 server/crisis.py 的 HOTLINES，改号码只需改那一处。
# 4) ★ 判定逻辑已升级（2026-09-26）：原先这里是本文件内的一张短词表
#    （自杀 / 我想死 / 不想活 / 割腕 …）。线上实测发现
#    「最近觉得活着很没意思，有点不想继续了」一个词都不命中 →
#    落到普通问答 → 模型自由发挥时**编了一个热线号码**
#    （400-161-9995，机构名还挂错了）。给错的求救号码比不给更严重，
#    所以判定与清洗整体搬到 server/crisis.py：
#      · 两级触发：strong 命中 1 个即触发 / weak 需 ≥2 个
#      · 配套两级教育豁免：扩词表后「如何识别学生轻生倾向并干预」仍能放行
#      · strip_non_whitelist_numbers() 删掉模型编的号码，白名单号码留住
#      · 该函数同时挂在 /api/chat 出口上：不只危机路径，**任何**模型回答
#        里的号码都会过一遍（"哪个回答会提到电话"无法预判）
#    回归：python tests/run_crisis_regression.py（单元级，不用重启，exit 0 = 全过）
CRISIS_RESPECT_CONTEXT_EXEMPTION = False
# ↑ 旧的「整段复用内容安全语境豁免」开关，默认仍是 False。
#   新的豁免在 crisis.py 里做（两级词表，比"一刀切"细），
#   此开关保留只为不破坏外部引用与历史语义。

# 下游（前端旧版本 / 历史脚本）仍在引用这个名字，保留成 crisis.HOTLINES 的别名
CRISIS_HOTLINE_ITEMS = HOTLINES


def detect_crisis(text: str) -> bool:
    """判断文本是否含危机信号。优先级高于内容安全校验。

    判定本体在 server/crisis.py::crisis_verdict（两级词表 + 两级教育豁免）。
    这里只保留函数名 —— 三处调用点与外部脚本引用的都是这个名字。

    fail-safe：判定层抛异常时按「非危机」处理，绝不拖垮主流程
    （宁可这一次漏给卡片，也不能让整个问答 500）。
    """
    try:
        is_crisis, _hit = crisis_verdict(text)
        if not is_crisis:
            return False
        if CRISIS_RESPECT_CONTEXT_EXEMPTION and is_exempted(text):
            return False
        return True
    except Exception:
        traceback.print_exc()
        return False


def _crisis_response_plan(course: str) -> dict:
    """plan / plan-stream 接口的危机话术 payload。

    结构定义在 server/crisis.py::crisis_result_payload，要点：
    - outline / resources / plan 必须是数组 —— 前端会直接读 .length，缺字段会抛异常
    - answer 按 "\\n" 切行渲染；以「【」开头的行由热线卡片接管，正文里滤掉
    - duration_ms 给 StatusBar 用，短路时就是几毫秒，这本身就是"没跑 Agent"的证据
    """
    return crisis_result_payload(course)


def _crisis_response_chat(question: str) -> dict:
    """chat 接口的危机话术 payload。

    聊天面板不渲染 ResultsGrid 的热线卡片，所以 crisis.py 把号码以纯文本
    写进 answer，保证用户不看卡片也拿得到正确号码。
    """
    return crisis_chat_response(question)


def log_crisis(source: str, text: str, client_id: str = "") -> None:
    """危机命中写审计日志。

    与内容安全共用同一份 JSONL，用 action=CRISIS 区分 ——
    这样「谁在什么时间触发了危机通道」在同一个文件里就能复盘，
    也让 content安全 与 危机干预 两件事的审计口径一致。
    """
    log_safety_hit(source, text, {
        "action": "CRISIS",
        "layer": "B30",
        "hits": [],
        "reason": "危机干预·已返回热线话术",
    }, client_id)


# ============================================================
# 3. 工具函数
# ============================================================
def _j(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _mask(key: str) -> str:
    """API Key 脱敏展示。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * 6}{key[-4:]}"


def _rel(path: str) -> str:
    """把绝对路径转成相对项目根目录的展示路径。

    为什么要转：/api/health、/api/mode、/api/bootstrap 会把这些路径返回给浏览器，
    而前端把 source_dir 直接显示在界面上（「业务逻辑来源：…」）。
    返回绝对路径等于把服务器的用户名与目录结构公开出去 ——
    对一个暴露在公网、日志里已经能看到有人在扫 /api/.env 的站点来说没必要。
    转成相对路径后界面上依然有意义（vendor/study-liu），但不再泄露绝对位置。

    基准是 WEB_ROOT（项目根）而不是 WORKSPACE —— WORKSPACE 是项目上一级目录，
    在服务器上会得到 ai-coding/vendor/... 这种结果，仍然多带了一层目录名。
    """
    if not path:
        return ""
    try:
        rel = os.path.relpath(path, WEB_ROOT)
    except ValueError:                      # 跨盘符（Windows）等异常情况
        return os.path.basename(path)
    # 路径不在项目根目录之下时会得到一堆 ..，此时退化成纯文件名
    return rel if not rel.startswith("..") else os.path.basename(path)


def test_llm_connection(payload: dict) -> dict:
    """测试 LLM 连接 —— 与桌面版「测试连接」按钮等价，但只用标准库实现。

    判定方式与桌面版一致：向 {base_url}/chat/completions 发一个最小请求，
    返回 200 即视为连通。表单里没填 Key 时回落到已保存的配置。
    """
    api_key = (payload.get("api_key") or "").strip() or get_api_key()
    base_url = (payload.get("base_url") or "").strip() or get_base_url()
    model = (payload.get("model") or "").strip() or get_model()

    if not api_key:
        return {"ok": False, "error": "请先填 API Key"}
    if not base_url:
        return {"ok": False, "error": "请先填 Base URL"}

    url = base_url.rstrip("/") + "/chat/completions"
    raw_body = json.dumps({
        "model": model or "deepseek-chat",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = int((time.time() - started) * 1000)
            sample = resp.read(400).decode("utf-8", "replace")
            return {
                "ok": True,
                "status": resp.status,
                "ms": elapsed,
                "message": "连接成功",
                "sample": sample[:200],
            }
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(300).decode("utf-8", "replace")
        except Exception:
            pass
        return {
            "ok": False,
            "status": exc.code,
            # 网关原文（含模型名/额度信息）只进日志，不回显
            "error": error_text.model_error(exc),
        }
    except Exception as exc:
        return {"ok": False, "error": error_text.model_error(exc)}


def mode_info() -> dict:
    """当前运行模式（供前端顶部角标）。"""
    label, mode = get_mode_label()
    key = ""
    try:
        key = load_settings().get("api_key") or os.environ.get("LLM_API_KEY", "")
    except Exception:
        pass

    provider = get_provider()
    has_key = bool(key)

    # 把「为什么是/不是 LLM 模式」讲清楚，避免用户对着 mock 角标猜原因
    reason = ""
    if provider != "mock" and not has_key:
        reason = "已配置 LLM 模式，但缺少 API Key（.env 的 LLM_API_KEY 为空），实际调用会降级"
    elif provider == "mock":
        if not ENV_LOADED and os.path.isfile(os.path.join(SOURCE_DIR, ".env")):
            reason = "源码目录存在 .env，但未能加载（检查文件编码/格式）"
        elif has_key:
            reason = "已配置 API Key，但 LLM_PROVIDER 仍为 mock（设置里切换为 llm 即可）"
        else:
            reason = "未配置 API Key：在源码 .env 填写 LLM_API_KEY，或在前端「设置」里填写"

    return {
        "provider": provider,
        "label": label,
        "mode": mode,               # mock | llm
        "is_mock": is_mock(),
        "base_url": get_base_url(),
        "model": get_model(),
        "has_key": has_key,
        "api_key_masked": _mask(key),
        "reason": reason,
        "env_loaded": ENV_LOADED,
        "source_dir": _rel(SOURCE_DIR),
        "env_file": _rel(os.path.join(SOURCE_DIR, ".env")),
        "env_file_exists": os.path.isfile(os.path.join(SOURCE_DIR, ".env")),
    }


def bootstrap(client_id: str = "") -> dict:
    """一次性返回前端启动所需的全部元信息。"""
    profile = load_profile()
    allowed = client_courses(client_id)
    return {
        "app": "study-liu-web",
        "version": "1.0.0",
        "source_dir": _rel(SOURCE_DIR),
        "trace_file": _rel(TRACE_FILE),
        "mode": mode_info(),
        "profile": profile,
        "options": {
            "levels": LEVELS,
            "daily_hours": DAILY_HOURS,
            "goals": GOALS,
        },
        "profile_preview": format_profile_text(profile),
        "suggested_days": suggest_plan_length(profile),
        "cache": cache_store.cache_stats(),
        # 历史按客户端隔离：只返回当前浏览器自己生成过的课程
        "history": [
            c for c in progress_store.list_courses() if c.get("course") in allowed
        ][:20],
    }


def normalize_plan_items(plan) -> list:
    """把 plan 归一化成 {day,title,chapters,tasks}，与桌面版 plan_normalize 同源。

    额外挂一个 `_idx`：该项在**原始 plan 列表**里的下标（0 基）。

    为什么需要它：进度勾选（/api/progress/done）的 index 是按原始 plan 编的
    （见 tools/progress_store._plan_to_progress），而归一化会跳过 None / 空白项，
    一旦 plan 里存在空项，两边下标就会错位 —— 勾了 Day 3 却存到 Day 4。
    所以前端必须用 `_idx`，不能用渲染序号。
    """
    from tools.plan_normalize import normalize_day as _nd
    if not isinstance(plan, list):
        return []
    items = []
    for i, day in enumerate(plan):
        if day is None:
            continue
        if isinstance(day, str) and not day.strip():
            continue
        item = _nd(day, i + 1)
        item["_idx"] = i
        items.append(item)
    return items


def build_payload(course: str, result: dict, duration_ms: int) -> dict:
    """把 run_plan_pipeline 的返回值包装成前端可直接渲染的结构。"""
    outline = result.get("outline") or []
    resources = result.get("resources") or []
    plan = result.get("plan") or []
    profile = result.get("profile") or {}

    markdown = ""
    try:
        markdown = render_plan_markdown(result, course=course)
    except Exception:
        pass

    return {
        "ok": True,
        "course": course,
        "outline": outline,
        "resources": resources,
        "plan": plan,
        "plan_items": normalize_plan_items(plan),
        "profile": profile,
        "profile_text": format_profile_text(profile) if profile else "",
        "from_cache": bool(result.get("_from_cache")),
        "degraded": result.get("_degraded"),
        "duration_ms": duration_ms,
        "stats": {
            "outline": len(outline),
            "resources": len(resources),
            "plan": len(plan),
        },
        "markdown": markdown,
        "suggested_filename": suggest_filename(course),
    }


# ============================================================
# 4. trace.log 实时跟随（SSE 用）
# ============================================================
# 与前端步骤条对应的阶段定义
STAGE_ORDER = ["planner", "searcher", "writer", "reviewer"]

_STEP_MAP = {
    "planner_start": ("planner", "running", "Planner 正在规划章节大纲…"),
    "planner_done": ("planner", "done", None),
    "searcher_start": ("searcher", "running", "Searcher 正在检索学习资源…"),
    "searcher_done": ("searcher", "done", None),
    "writer_start": ("writer", "running", "Writer 正在编排学习计划…"),
    "writer_done": ("writer", "done", None),
    "reviewer_start": ("reviewer", "running", "Reviewer 正在质检…"),
    "reviewer_done": ("reviewer", "done", None),
}


def _parse_trace_line(line: str):
    """解析 `[ts] event | {json}` → (ts, event, data|None)。"""
    line = line.strip()
    if not line.startswith("["):
        return None
    try:
        end = line.index("]")
    except ValueError:
        return None
    ts = line[1:end]
    rest = line[end + 1:].strip()
    if "|" in rest:
        event, _, raw = rest.partition("|")
        event = event.strip()
        try:
            data = json.loads(raw.strip())
        except Exception:
            data = {"raw": raw.strip()}
    else:
        event, data = rest.strip(), None
    return {"ts": ts, "event": event, "data": data}


def stream_pipeline(course: str, profile: dict, use_cache: bool, emit) -> dict:
    """在后台线程跑真实流水线，同时把新写入的 trace 行实时推给前端。

    参数：
        emit(event_name, payload) —— 向前端推送一个 SSE 事件
    返回：
        build_payload() 的结果
    """
    offset = os.path.getsize(TRACE_FILE) if os.path.exists(TRACE_FILE) else 0
    box: dict = {"done": False}

    def worker():
        try:
            box["result"] = run_plan_pipeline(
                course, profile=profile, use_cache=use_cache,
            )
        except Exception as e:
            box["error"] = f"{e}"
            box["traceback"] = traceback.format_exc()
        finally:
            box["done"] = True

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    buffer = ""
    started = time.time()
    while True:
        offset, chunk = _read_new(TRACE_FILE, offset)
        if chunk:
            buffer += chunk
            while "\n" in buffer:
                line, _, buffer = buffer.partition("\n")
                parsed = _parse_trace_line(line)
                if not parsed:
                    continue
                emit("trace", parsed)
                step = _STEP_MAP.get(parsed["event"])
                if step:
                    key, status, hint = step
                    payload = {
                        "key": key,
                        "status": status,
                        "index": STAGE_ORDER.index(key),
                        "hint": hint,
                        "ts": parsed["ts"],
                    }
                    if parsed["data"]:
                        payload["data"] = parsed["data"]
                    emit("step", payload)
        if box.get("done") and not chunk:
            break
        time.sleep(0.05)

    if box.get("error"):
        raise RuntimeError(box["error"])

    result = box["result"]
    duration_ms = int((time.time() - started) * 1000)

    # 与桌面版一致：写入 progress.json（历史记录 + 进度清单）
    try:
        progress_store.save_result(course, result)
    except Exception:
        pass

    payload = build_payload(course, result, duration_ms)
    emit("result", payload)
    return payload


def _read_new(path: str, offset: int):
    """读取 path 中 offset 之后的新增内容，返回 (新 offset, 文本)。"""
    if not os.path.exists(path):
        return offset, ""
    try:
        size = os.path.getsize(path)
    except OSError:
        return offset, ""
    if size <= offset:
        return offset, ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            return size, f.read()
    except OSError:
        return offset, ""


def tail_trace(limit: int = 120) -> list:
    """读取 trace.log 最后 limit 行（日志回放）。"""
    if not os.path.exists(TRACE_FILE):
        return []
    try:
        with open(TRACE_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        parsed = _parse_trace_line(ln)
        if parsed:
            out.append(parsed)
    return out


# ============================================================
# 5. HTTP 处理
# ============================================================
class ApiHandler(BaseHTTPRequestHandler):
    server_version = "study-liu-web/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 基础响应 ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Client-Id")
        # 跨域下前端默认读不到 Content-Disposition，导出时拿不到文件名；
        # 显式放行这个响应头，前端就能用后端定的文件名。
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition")

    def _send_json(self, obj, status: int = 200):
        body = _j(obj)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200,
                   content_type: str = "text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(self, data: bytes, content_type: str,
                     filename: str = "", status: int = 200):
        """发送二进制响应（Word 导出用）。

        filename 非空时带下载头。中文文件名必须走 RFC 5987 的 filename* 形式，
        否则浏览器会拿到乱码；同时保留一个 ASCII 的 filename 兜底给老浏览器。
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "plan.docx"
            self.send_header(
                "Content-Disposition",
                "attachment; filename=\"%s\"; filename*=UTF-8''%s"
                % (ascii_name, urllib.parse.quote(filename)),
            )
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _read_raw_body(self, max_bytes: int) -> bytes:
        """读取原始请求体 bytes（**只给 multipart 上传用**）。

        不能复用 _read_body()：它会把请求体整个读走并尝试 JSON 解析，
        multipart 会被它当成"解析失败"丢掉，上传接口就拿不到文件了。
        所以上传路由必须在调用 _read_body() **之前**分流。
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > max_bytes:
            raise MultipartError(
                "请求体过大：%.1f MB（上限 %.0f MB）" % (length / 1048576, max_bytes / 1048576)
            )
        return self.rfile.read(length)

    # ---------- 知识库：上传导入 ----------
    def _handle_knowledge_import(self):
        """POST /api/knowledge/import —— multipart 上传，解析后写入知识库。

        支持一次传多个文件；单个文件失败不影响其它文件（逐条返回结果）。
        解析完立刻删除落盘临时文件，不留垃圾。
        """
        try:
            raw = self._read_raw_body(MAX_UPLOAD_BYTES)
            parsed = parse_multipart(raw, self.headers.get("Content-Type") or "")
        except MultipartError as e:
            return self._send_json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"ok": False, "error": "上传解析失败：%s" % e}, 400)

        files = parsed["files"]
        if not files:
            return self._send_json({"ok": False, "error": "没有收到文件"}, 400)

        fields = parsed["fields"]
        tags = [t.strip() for t in (fields.get("tags") or "").split(",") if t.strip()]
        # 「归入的笔记名」：界面选了某条笔记时传过来，这批文件的块都用它作前缀，
        # 分组时就聚到同一条笔记下；不传则每个文件按自己的文件名各成一条。
        group_title = (fields.get("title") or "").strip()

        store = KnowledgeStore()
        existing = len(store.list_all())
        if existing >= MAX_KB_NOTES:
            return self._send_json({
                "ok": False,
                "error": "知识库已达上限 %d 条，请先删除一些笔记" % MAX_KB_NOTES,
            }, 400)

        cleanup_uploads(DATA_DIR)   # 顺手清过期临时文件，不需要定时任务

        results = []
        for f in files:
            path = None
            try:
                path = save_upload(f["data"], f["filename"], DATA_DIR)
                r = ingest(path, f["filename"], tags=tags, store=store, title=group_title)
            except Exception as e:
                traceback.print_exc()
                r = {"ok": False, "kind": "", "notes": [], "chunks": 0, "chars": 0,
                     "error": "导入异常：%s" % e}
            finally:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            r["filename"] = f["filename"]
            r["size"] = len(f["data"])
            results.append(r)

        ok_n = sum(1 for r in results if r.get("ok"))
        return self._send_json({
            "ok": ok_n > 0,
            "imported": ok_n,
            "failed": len(results) - ok_n,
            "results": results,
            "total": len(store.list_all()),
        }, 200 if ok_n > 0 else 400)

    def _handle_asr_transcribe(self):
        """POST /api/asr —— 16kHz 单声道 16bit PCM（原始字节流，非 multipart）→ 文字。

        为什么不用 multipart：这里只有一个字段、且是二进制，套一层 multipart
        只是白白多出 boundary 解析和 base64 风险。前端直接把 Int16Array 的
        ArrayBuffer 当 body 发过来即可。

        为什么采样率转换放在前端：服务器没装 ffmpeg（实测），
        而浏览器的 OfflineAudioContext(1,1,16000).decodeAudioData() 能把
        mp3/m4a/webm/ogg/wav 直接解成 16k 单声道，零依赖零安装。
        """
        try:
            raw = self._read_raw_body(asr_mod.MAX_PCM_BYTES)
        except MultipartError as e:
            # 超长音频走到这里，_read_raw_body 的文案已经说清「多少 MB / 上限多少」
            return self._send_json({"ok": False, "error": str(e)}, 413)
        except Exception as e:
            return self._send_json({"ok": False, "error": "读取音频失败：%s" % e}, 400)

        if not raw:
            return self._send_json({"ok": False, "error": "没有收到音频数据"}, 400)

        try:
            r = asr_mod.transcribe(raw)
        except RuntimeError as e:
            # 引擎/模型不可用、音频过长 —— 都是「用户能看懂并照做」的提示，原样返回
            return self._send_json({"ok": False, "error": str(e)}, 503)
        except Exception as e:
            traceback.print_exc()  # 原始异常进日志，用户只看固定文案
            return self._send_json(
                {"ok": False, "error": error_text.internal_error(e)}, 500)

        r["ok"] = True
        if not r["text"]:
            # 不是错误：说了话但没识别出来（纯音乐、环境噪音、方言口音重）
            r["hint"] = "没有识别到中文内容。请确认音频里有人说话，且是普通话。"
        return self._send_json(r)

    def log_message(self, fmt, *args):  # 收敛控制台噪音
        if self.path.startswith("/api/plan/stream"):
            return
        sys.stderr.write("[api] %s\n" % (fmt % args))

    def _auth(self):
        """取当前登录用户；未登录返回 None。"""
        return accounts.check_token(self.headers.get("X-Auth-Token") or "")

    def _require_admin(self):
        """管理员校验。

        返回 None 表示放行；否则返回 (响应体, HTTP 状态码)，调用处直接回给前端。
        注意：一个管理员都没有时（老部署还没建号）**放行**，避免升级后
        把删除功能一键锁死 —— 我们会自动建默认管理员，所以正常情况不会走到这。
        """
        if not accounts.auth_enabled():
            return None
        user = self._auth()
        if not user:
            return {"ok": False, "error": "请先登录管理员账号"}, 401
        if user.get("role") != "admin":
            return {"ok": False, "error": "需要管理员权限"}, 403
        return None

    def _client_id(self, query=None) -> str:
        """取客户端标识：优先 X-Client-Id 请求头，SSE 场景回落 client_id 查询参数。"""
        cid = (self.headers.get("X-Client-Id") or "").strip()
        if not cid and query:
            cid = (query.get("client_id") or [""])[0].strip()
        return cid[:64] or "anonymous"

    # ---------- SSE ----------
    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self._cors()
        self.end_headers()

    def _sse_send(self, event: str, data) -> None:
        payload = "event: %s\ndata: %s\n\n" % (
            event, json.dumps(data, ensure_ascii=False),
        )
        raw = payload.encode("utf-8")
        self.wfile.write(("%X\r\n" % len(raw)).encode("ascii"))
        self.wfile.write(raw)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _sse_close(self):
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except Exception:
            pass

    # ---------- 路由 ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/me":
                user = self._auth()
                return self._send_json({
                    "ok": bool(user),
                    "username": (user or {}).get("username", ""),
                    "role": (user or {}).get("role", ""),
                    "auth_enabled": accounts.auth_enabled(),
                })

            if path == "/api/accounts":
                guard = self._require_admin()
                if guard:
                    return self._send_json(guard[0], guard[1])
                return self._send_json({"ok": True, "users": accounts.list_users()})

            if path == "/api/health":
                return self._send_json({
                    "ok": True,
                    "source_dir": _rel(SOURCE_DIR),
                    "trace_file": _rel(TRACE_FILE),
                    "data_dir": _rel(DATA_DIR),          # 历史/设置实际落盘的位置
                    "env_loaded": ENV_LOADED,      # 从 .env 读到哪些键
                })

            if path == "/api/bootstrap":
                return self._send_json(bootstrap(self._client_id(query)))

            if path == "/api/mode":
                return self._send_json(mode_info())

            if path == "/api/trace":
                limit = int((query.get("limit") or ["120"])[0])
                return self._send_json({"lines": tail_trace(limit)})

            if path == "/api/history":
                allowed = client_courses(self._client_id(query))
                courses = [
                    c for c in progress_store.list_courses()
                    if c.get("course") in allowed
                ]
                return self._send_json({"courses": courses})

            if path.startswith("/api/history/"):
                course = urllib.parse.unquote(path[len("/api/history/"):])
                if course not in client_courses(self._client_id(query)):
                    return self._send_json(
                        {"ok": False, "error": "该课程不在你的历史记录中"}, 404)
                result = progress_store.load_result(course)
                if not result:
                    return self._send_json({"ok": False, "error": "未找到该课程"}, 404)
                payload = build_payload(course, result, 0)
                payload["progress"] = progress_store.get_progress(course)
                return self._send_json(payload)

            if path == "/api/progress/overview":
                # 学情面板：该浏览器名下所有课程的勾选完成度汇总。
                # progress.json 全局共享，所以仍要按 client 过滤（同 /api/history）。
                allowed = client_courses(self._client_id(query))
                rows = []
                for c in progress_store.list_courses():
                    name = c.get("course")
                    if name not in allowed:
                        continue
                    d, t, r = progress_store.get_stats(name)
                    rows.append({
                        "course": name,
                        "done": d,
                        "total": t,
                        "ratio": round(r, 4),
                        "created_at": c.get("created_at", ""),
                        "last_seen_at": c.get("last_seen_at", ""),
                    })
                total_done = sum(x["done"] for x in rows)
                total_all = sum(x["total"] for x in rows)
                return self._send_json({
                    "ok": True,
                    "courses": rows,
                    "summary": {
                        "courses": len(rows),
                        "done": total_done,
                        "total": total_all,
                        "ratio": round(total_done / total_all, 4) if total_all else 0.0,
                    },
                })

            if path == "/api/wrongbook":
                cid = self._client_id(query)
                items = wrong_book_store.list_items(
                    cid,
                    course=(query.get("course") or [""])[0].strip() or None,
                    keyword=(query.get("q") or [""])[0].strip() or None,
                    status=(query.get("status") or [""])[0].strip() or None,
                )
                return self._send_json({
                    "ok": True,
                    "items": items,
                    "total": len(items),
                    "stats": wrong_book_store.stats(cid),
                    "courses": wrong_book_store.courses(cid),
                })

            if path == "/api/asr":
                # 语音转写能力探测：引擎/模型缺失时这里就告诉前端，
                # 界面可以直接把入口置灰并给出「去怎么修」的提示，而不是让用户白录一遍
                return self._send_json(asr_mod.status())

            if path == "/api/mindmap":
                # 列表：只给「课程 / 更新时间 / 节点数」，不带节点，列表页够用
                return self._send_json({
                    "ok": True,
                    "items": mindmap_store.list_maps(self._client_id(query)),
                })

            if path.startswith("/api/mindmap/"):
                course = urllib.parse.unquote(path[len("/api/mindmap/"):])
                entry = mindmap_store.get_map(self._client_id(query), course)
                if not entry:
                    return self._send_json({"ok": False, "error": "该课程还没有思维导图"}, 404)
                out = dict(entry)
                out.pop("_client", None)
                return self._send_json({"ok": True, "map": out})

            if path == "/api/knowledge/capabilities":
                # 前端据此置灰不支持的入口（例如没装 pypdf 时 PDF 不可用）
                return self._send_json({"ok": True, **kb_capabilities()})

            if path == "/api/knowledge":
                q = (query.get("q") or [""])[0].strip()
                store = KnowledgeStore()
                if not q:
                    items = store.list_all()
                    return self._send_json({"items": items, "total": len(items)})
                # 打分检索：替代原来的「整句子串匹配」。
                # 旧实现只有措辞和笔记原文高度一致才命中，口语化提问一律搜不到。
                try:
                    top_k = max(1, min(50, int((query.get("top_k") or ["20"])[0])))
                except ValueError:
                    top_k = 20
                hits = store.retrieve(q, top_k=top_k)
                items = []
                for note, score, detail in hits:
                    it = dict(note)
                    it["_score"] = round(score, 2)
                    it["_match"] = detail
                    items.append(it)
                return self._send_json({
                    "items": items, "total": len(items), "query": q, "mode": "retrieve",
                })

            if path == "/api/plan/stream":
                return self._handle_stream(query)

            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()  # 原始异常进日志，用户只看固定文案
            return self._send_json({"ok": False, "error": error_text.internal_error(e)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # ⚠️ 上传路由必须在 _read_body() 之前分流：
        # _read_body() 会把请求体整个读走并尝试 JSON 解析，multipart 会被它丢掉。
        if path == "/api/knowledge/import":
            return self._handle_knowledge_import()
        # 同理：/api/asr 收的是原始 PCM 字节流，不是 JSON
        if path == "/api/asr":
            return self._handle_asr_transcribe()

        body = self._read_body()

        try:
            # ---- 账号：登录 / 账号管理（读 body，必须放在 _read_body() 之后）----
            if path == "/api/login":
                username = (body.get("username") or "").strip()
                password = body.get("password") or ""
                user = accounts.verify(username, password)
                if not user:
                    # 不区分「账号不存在」和「密码错」，避免被拿来枚举账号
                    return self._send_json({"ok": False, "error": "账号或密码不正确"}, 401)
                return self._send_json({
                    "ok": True,
                    "token": accounts.issue_token(user),
                    "username": user["username"],
                    "role": user["role"],
                })

            if path == "/api/register":
                # 自助注册：只建普通账号，注册完直接登录
                username = (body.get("username") or "").strip()
                password = body.get("password") or ""
                ok, msg = accounts.register(username, password)
                if not ok:
                    return self._send_json({"ok": False, "error": msg}, 400)
                user = accounts.verify(username, password)
                if not user:
                    return self._send_json({"ok": False, "error": "注册成功但登录失败，请手动登录"}, 500)
                return self._send_json({
                    "ok": True,
                    "token": accounts.issue_token(user),
                    "username": user["username"],
                    "role": user["role"],
                })

            if path == "/api/accounts":
                guard = self._require_admin()
                if guard:
                    return self._send_json(guard[0], guard[1])
                act = body.get("action") or "create"
                target = (body.get("username") or "").strip()
                if act == "create":
                    ok, msg = accounts.create_user(
                        target, body.get("password") or "", body.get("role") or accounts.ROLE_USER
                    )
                elif act == "role":
                    # 提拔 / 降级（如把某个账号设为管理员）
                    ok, msg = accounts.set_role(target, body.get("role") or "")
                elif act == "password":
                    ok, msg = accounts.set_password(target, body.get("password") or "")
                elif act == "delete":
                    ok, msg = accounts.delete_user(target)
                else:
                    ok, msg = False, "未知操作"
                if not ok:
                    return self._send_json({"ok": False, "error": msg}, 400)
                return self._send_json({"ok": True, "message": msg, "users": accounts.list_users()})

            if path == "/api/knowledge":
                # 粘贴文本入库（与上传导入共用分块 + 内容安全逻辑）
                text = (body.get("content") or body.get("text") or "").strip()
                title = (body.get("title") or "").strip()
                tags = body.get("tags")
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                store = KnowledgeStore()
                if len(store.list_all()) >= MAX_KB_NOTES:
                    return self._send_json(
                        {"ok": False, "error": "知识库已达上限 %d 条" % MAX_KB_NOTES}, 400)

                # 允许「只给标题、正文留空」——界面上「新建笔记」就是先建一个空容器，
                # 等导入材料再填进去。标题和正文同时为空才算无效请求。
                if not text:
                    if not title:
                        return self._send_json(
                            {"ok": False, "error": "标题和内容不能同时为空"}, 400)
                    try:
                        note_id = store.add(
                            title=title, content="",
                            tags=tags if isinstance(tags, list) and tags else ["#manual"])
                    except Exception as e:
                        return self._send_json({"ok": False, "error": "写入失败：%s" % e}, 500)
                    return self._send_json({
                        "ok": True, "kind": "empty",
                        "notes": [{"id": note_id, "title": title}],
                        "chunks": 1, "chars": 0, "error": None,
                        "total": len(store.list_all()),
                    })

                if len(text) > 100_000:
                    return self._send_json(
                        {"ok": False, "error": "内容过长（上限 10 万字）"}, 400)
                r = ingest_text(text, title=title or None, tags=tags, store=store)
                r["total"] = len(store.list_all())
                return self._send_json(r, 200 if r.get("ok") else 400)

            if path == "/api/profile":
                profile = {
                    "level": body.get("level", DEFAULT_PROFILE["level"]),
                    "daily_hours": body.get("daily_hours", DEFAULT_PROFILE["daily_hours"]),
                    "goal": body.get("goal", DEFAULT_PROFILE["goal"]),
                    "deadline": body.get("deadline", ""),
                }
                save_profile(profile)
                saved = load_profile()
                return self._send_json({
                    "ok": True,
                    "profile": saved,
                    "profile_preview": format_profile_text(saved),
                    "suggested_days": suggest_plan_length(saved),
                })

            if path == "/api/plan":
                course = (body.get("course") or "").strip()
                if not course:
                    return self._send_json({"ok": False, "error": "请先输入课程名"}, 400)
                # B30: 危机干预前置短路——优先级高于内容安全校验
                if detect_crisis(course):
                    log_crisis("plan", course, self._client_id())
                    return self._send_json(_crisis_response_plan(course))
                detail = check_detail(course)
                if detail["action"] == "BLOCK":
                    log_safety_hit("plan", course, detail, self._client_id())
                    return self._send_json(
                        {"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)
                profile = body.get("profile") or load_profile()
                use_cache = bool(body.get("use_cache", True))
                t0 = time.time()
                result = run_plan_pipeline(course, profile=profile, use_cache=use_cache)
                try:
                    progress_store.save_result(course, result)
                    record_client_course(self._client_id(), course)
                except Exception:
                    pass
                payload = build_payload(course, result, int((time.time() - t0) * 1000))
                return self._send_json(payload)

            if path == "/api/chat":
                question = (body.get("question") or "").strip()
                if not question:
                    return self._send_json({"ok": False, "error": "请输入问题"}, 400)
                # B30: 危机干预前置短路——优先级高于内容安全校验
                if detect_crisis(question):
                    log_crisis("chat", question, self._client_id())
                    return self._send_json(_crisis_response_chat(question))
                detail = check_detail(question)
                if detail["action"] == "BLOCK":
                    log_safety_hit("chat", question, detail, self._client_id())
                    return self._send_json(
                        {"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)
                intent = parse_intent(question)
                if intent.get("type") == "generate":
                    return self._send_json({
                        "ok": True,
                        "type": "generate",
                        "course": intent.get("course") or question,
                        "answer": "该输入看起来是「生成方案」请求，请点击「生成方案」。",
                        "source": "intent",
                    })
                res = run_chat_pipeline(
                    question,
                    history=body.get("history") or [],
                    course_context=body.get("course_context") or None,
                )
                return self._send_json({
                    "ok": True,
                    "type": "chat",
                    # 号码白名单清洗：模型有时会"顺手"给出心理援助 / 咨询电话，
                    # 而这些号码无法保证真实（2026-09-26 线上就出现过编造的 400-161-9995）。
                    # 这一步只删非白名单号码，正常正文不受影响（有回归守）。
                    "answer": strip_non_whitelist_numbers(res.get("answer", "")),
                    "source": res.get("source", "llm"),
                    # RAG 检索到的资料（id/title/score），供前端展示「参考资料」。
                    # source 仍沿用 knowledge / llm 两值，前端标签不会落到兜底分支。
                    "retrieved": res.get("retrieved") or [],
                    "degraded": res.get("degraded"),
                })

            if path == "/api/export":
                course = (body.get("course") or "").strip()
                fmt = (body.get("format") or "markdown").strip().lower()
                result = body.get("result") or progress_store.load_result(course)
                if not result:
                    return self._send_json({"ok": False, "error": "没有可导出的方案"}, 400)
                # Word：直接回二进制流（浏览器按 Content-Disposition 落盘），
                # 不走 JSON——docx 是 zip，塞进 JSON 还得 base64，白白涨 33%。
                if fmt in ("docx", "word"):
                    try:
                        blob = render_plan_docx(result, course=course or None)
                    except Exception as e:
                        traceback.print_exc()
                        return self._send_json(
                            {"ok": False, "error": "Word 生成失败：%s" % e}, 500)
                    return self._send_binary(
                        blob,
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document",
                        suggest_docx_filename(course or "学习方案"),
                    )
                md = render_plan_markdown(result, course=course or None)
                return self._send_json({
                    "ok": True,
                    "markdown": md,
                    "filename": suggest_filename(course or "学习方案"),
                })

            if path == "/api/settings/test":
                return self._send_json(test_llm_connection(body))

            if path == "/api/settings":
                # 「留空 = 保持现有 Key」。
                # 前端出于安全不回填明文 Key（桌面版会回填），若这里照搬
                # save_settings 的「空值即清空」语义，用户只是切一下模式
                # 就会把磁盘上已保存的 Key 抹掉。所以这里显式区分：
                #   clear_key=true  → 主动清空
                #   api_key 非空     → 更新
                #   其余（含 api_key=""）→ 沿用 settings.json 里已有的 Key
                provider = body.get("provider") or "mock"
                base_url = body.get("base_url") or "https://api.deepseek.com"
                model = body.get("model") or "deepseek-chat"

                if body.get("clear_key"):
                    api_key = ""
                elif (body.get("api_key") or "").strip():
                    api_key = body["api_key"].strip()
                else:
                    try:
                        api_key = load_settings().get("api_key") or ""
                    except Exception:
                        api_key = ""

                save_settings(provider, api_key, base_url, model)
                return self._send_json({"ok": True, "mode": mode_info()})

            if path == "/api/progress/done":
                # 勾选/取消勾选大纲或计划里的某一项。
                # 底层 progress_store.set_done() 在桌面版就写好了，只是从来没有路由调它。
                course = (body.get("course") or "").strip()
                kind = (body.get("kind") or "").strip()
                if not course or kind not in ("outline", "plan"):
                    return self._send_json(
                        {"ok": False, "error": "需要 course 与 kind（outline/plan）"}, 400)
                try:
                    index = int(body.get("index"))
                except (TypeError, ValueError):
                    return self._send_json(
                        {"ok": False, "error": "index 必须是整数"}, 400)
                if not progress_store.set_done(course, kind, index, bool(body.get("done"))):
                    return self._send_json(
                        {"ok": False, "error": "未找到该课程或该项越界"}, 404)
                done, total, ratio = progress_store.get_stats(course)
                return self._send_json({
                    "ok": True,
                    "progress": progress_store.get_progress(course),
                    "stats": {"done": done, "total": total, "ratio": round(ratio, 4)},
                })

            if path == "/api/mindmap":
                # 整张图覆盖保存。前端负责布局与增删，后端只做结构校验：
                # id 合法唯一、parent 存在、恰好一个根、无环（见 mindmap_store._clean_nodes）
                entry, err = mindmap_store.save_map(
                    self._client_id(),
                    (body.get("course") or "").strip(),
                    body.get("nodes"),
                )
                if err:
                    return self._send_json({"ok": False, "error": err}, 400)
                return self._send_json({"ok": True, "map": entry})

            if path == "/api/wrongbook":
                cid = self._client_id()
                try:
                    item = wrong_book_store.add_item(
                        cid,
                        course=body.get("course") or "",
                        question=body.get("question") or "",
                        my_answer=body.get("my_answer") or "",
                        answer=body.get("answer") or "",
                        reason=body.get("reason") or "",
                        tags=body.get("tags"),
                        source=body.get("source") or "manual",
                    )
                except ValueError as e:
                    return self._send_json({"ok": False, "error": str(e)}, 400)
                if not item:
                    return self._send_json({"ok": False, "error": "题干不能为空"}, 400)
                return self._send_json({
                    "ok": True, "item": item,
                    "stats": wrong_book_store.stats(cid),
                    "courses": wrong_book_store.courses(cid),
                })

            if path.startswith("/api/wrongbook/"):
                cid = self._client_id()
                raw_id = urllib.parse.unquote(path[len("/api/wrongbook/"):])
                try:
                    item_id = int(raw_id)
                except ValueError:
                    return self._send_json({"ok": False, "error": "id 必须是数字"}, 400)

                # review=true 走「记一次复习」分支（可同时带 mastered 改掌握状态）
                if body.get("review"):
                    item = wrong_book_store.review_item(
                        cid, item_id, mastered=body.get("mastered"))
                else:
                    fields = {
                        k: body[k] for k in
                        ("course", "question", "my_answer", "answer",
                         "reason", "tags", "mastered")
                        if k in body
                    }
                    item = wrong_book_store.update_item(cid, item_id, **fields)

                if not item:
                    return self._send_json(
                        {"ok": False, "error": "未找到该错题（或题干被清空）"}, 404)
                return self._send_json({
                    "ok": True, "item": item,
                    "stats": wrong_book_store.stats(cid),
                })

            if path == "/api/cache/clear":
                n = cache_store.clear_cache(body.get("course") or None)
                return self._send_json({"ok": True, "cleared": n})

            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()  # 原始异常进日志，用户只看固定文案
            return self._send_json({"ok": False, "error": error_text.internal_error(e)}, 500)

    # ---------- DELETE：知识库删条目 ----------
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path.startswith("/api/mindmap/"):
                course = urllib.parse.unquote(path[len("/api/mindmap/"):])
                if not mindmap_store.delete_map(self._client_id(), course):
                    return self._send_json({"ok": False, "error": "未找到该思维导图"}, 404)
                return self._send_json({"ok": True, "course": course})

            if path.startswith("/api/wrongbook/"):
                cid = self._client_id()
                raw_id = urllib.parse.unquote(path[len("/api/wrongbook/"):])
                try:
                    item_id = int(raw_id)
                except ValueError:
                    return self._send_json({"ok": False, "error": "id 必须是数字"}, 400)
                if not wrong_book_store.delete_item(cid, item_id):
                    return self._send_json({"ok": False, "error": "未找到该错题"}, 404)
                return self._send_json({
                    "ok": True, "id": item_id,
                    "stats": wrong_book_store.stats(cid),
                    "courses": wrong_book_store.courses(cid),
                })

            if path.startswith("/api/knowledge/"):
                # 删除不可逆，且知识库是多人共用的 —— 只允许管理员
                guard = self._require_admin()
                if guard:
                    return self._send_json(guard[0], guard[1])
                raw_id = urllib.parse.unquote(path[len("/api/knowledge/"):])
                try:
                    note_id = int(raw_id)
                except ValueError:
                    return self._send_json({"ok": False, "error": "id 必须是数字"}, 400)
                store = KnowledgeStore()
                if not store.delete(note_id):
                    return self._send_json({"ok": False, "error": "未找到该笔记"}, 404)
                return self._send_json({
                    "ok": True, "id": note_id, "total": len(store.list_all()),
                })
            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()  # 原始异常进日志，用户只看固定文案
            return self._send_json({"ok": False, "error": error_text.internal_error(e)}, 500)

    # ---------- SSE：生成方案全链路 ----------
    def _handle_stream(self, query):
        course = (query.get("course") or [""])[0].strip()
        if not course:
            return self._send_json({"ok": False, "error": "缺少 course 参数"}, 400)
        client_id = self._client_id(query)
        # B30: 危机干预前置短路——SSE 通道必须发事件流，不能直接 return JSON。
        # 注意发的是 meta + result + done 三个事件，而不是「meta + done」：
        # 前端只认 result 事件来渲染结果（done 仅做收尾，见 usePlanStream.js），
        # 只发 done 的话危机话术会被前端丢掉。
        if detect_crisis(course):
            log_crisis("plan_stream", course, client_id)
            self._sse_open()
            self.close_connection = True
            self._sse_send("meta", {
                "course": course,
                "source": "crisis_intervention",
                "type": "crisis",
            })
            self._sse_send("result", _crisis_response_plan(course))
            self._sse_send("done", {"ok": True, "type": "crisis"})
            return
        detail = check_detail(course)
        if detail["action"] == "BLOCK":
            log_safety_hit("plan_stream", course, detail, client_id)
            return self._send_json(
                {"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)

        profile = load_profile()
        if query.get("level"):
            profile["level"] = query["level"][0]
        if query.get("daily_hours"):
            profile["daily_hours"] = query["daily_hours"][0]
        if query.get("goal"):
            profile["goal"] = query["goal"][0]
        if "deadline" in query:
            profile["deadline"] = query["deadline"][0]
        try:
            save_profile(profile)
        except Exception:
            pass

        use_cache = (query.get("use_cache") or ["1"])[0] not in ("0", "false", "False")

        self._sse_open()
        self.close_connection = True

        def emit(event, data):
            try:
                self._sse_send(event, data)
            except (BrokenPipeError, ConnectionResetError):
                raise

        started = time.time()
        try:
            emit("meta", {
                "course": course,
                "profile": profile,
                "profile_text": format_profile_text(profile),
                "use_cache": use_cache,
                "mode": mode_info(),
                "stages": STAGE_ORDER,
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            stream_pipeline(course, profile, use_cache, emit)
            try:
                record_client_course(client_id, course)
            except Exception:
                pass
            emit("done", {"ok": True, "duration_ms": int((time.time() - started) * 1000)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                emit("error", {"ok": False, "error": error_text.internal_error(e)})
                emit("done", {"ok": False, "error": error_text.internal_error(e)})
            except Exception:
                pass
        finally:
            self._sse_close()


class ThreadingHTTPServer6(ThreadingHTTPServer):
    """并发 HTTP 服务（每请求一线程），SSE 不会阻塞其它接口。"""

    daemon_threads = True
    allow_reuse_address = True


# ============================================================
# 6. 入口
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="study-liu Web API 后端")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    try:
        print(f"[study-liu-web] 源码目录 : {SOURCE_DIR}")
        print(f"[study-liu-web] trace 文件: {TRACE_FILE}")
        print(f"[study-liu-web] 运行模式  : {mode_info()['label']}")
        print(f"[study-liu-web] API 地址  : http://{args.host}:{args.port}")
        httpd = ThreadingHTTPServer6((args.host, args.port), ApiHandler)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[study-liu-web] 已停止")


if __name__ == "__main__":
    main()
