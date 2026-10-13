#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""study-liu Web API 后端 —— 标准库实现（零第三方依赖；仅 quiz 出题链路经队长批准引入 langchain-tavily）。

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
# 0. Tavily key 映射（quiz 出题链路使用 langchain-tavily）
# ============================================================
# 队长批准放宽零依赖约束：仅 quiz 出题链路引入 langchain-tavily，其要求环境变量
# TAVILY_API_KEY。这里把既有的 STUDY_LIU_TAVILY_KEY 映射过去（不入库、不落盘）。
os.environ["TAVILY_API_KEY"] = os.environ.get("STUDY_LIU_TAVILY_KEY", "")

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

# quiz 顶层 from core.paths / core.agent_loop（core 仅 vendor/study-liu 有），
# 必须放在 sys.path.insert 之后，否则 `python server/api_server.py` 直接崩
# `ModuleNotFoundError: No module named 'core'`（回归 #rLRaaT 修复）。
import quiz as quiz_mod                                             # noqa: E402
# 闯关错题 → 错题本的题型适配（纯转换，无 IO）。同样依赖 SOURCE_DIR 已在 path 里。
import wrongbook_quiz as wrongbook_quiz_mod                         # noqa: E402

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
# 用户系统存储层（MySQL 主，JSON 兜底）：用同名别名替换 vendor store，
# 使下方 _wrongbook_items / mindmap_store_list_many / 进度路由无需改动。
import storage_progress as progress_store                           # noqa: E402
import storage_wrongbook as wrong_book_store                        # noqa: E402
import storage_mindmap as mindmap_store                             # noqa: E402
import storage_profiles                                              # noqa: E402
import storage_ratelimit                                              # noqa: E402
import db                                                            # noqa: E402
import error_text                                                    # noqa: E402
import accounts                                                      # noqa: E402
import data_scope                                                    # noqa: E402
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
# 用户系统存储层：MySQL 初始化（连接参数来自 .env 的 STUDY_LIU_MYSQL_*，
# 由 _load_dotenv_stdlib 在 import 前注入 os.environ）。MySQL 不可用时静默降级，
# accounts / data_scope 会自动退回 JSON 兜底，服务仍可启动。
db.configure()
try:
    db.ensure_schema()
except Exception as _schema_err:  # 数据库不可用时不影响启动，仅记录
    sys.stderr.write("[api] MySQL schema 初始化失败（将退回 JSON 兜底）：%s\n" % _schema_err)
accounts.configure(DATA_DIR)
# 归属绑定 / 按用户画像的 JSON 兜底目录（MySQL 不可用时才用得到；
# 原版没配，兜底文件会写不进去，这里补上）
data_scope.configure(DATA_DIR)
storage_profiles.configure(DATA_DIR)
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


# ============================================================
# 3.0 请求参数安全取值（公网接口必须对畸形入参免疫）
# ============================================================
# 历史写法 `(body.get("course") or "").strip()` 只在客户端老实传字符串时成立。
# 任何非字符串（数字 / 列表 / 对象）都会在 .strip() 上抛 AttributeError，
# 被 do_POST 的兜底 except 吞成 **500「服务暂时不可用」**——2026-10-13 线上实测：
#   POST /api/plan   {"course":123}          → 500
#   POST /api/login  {"username":123,...}   → 500
# 也就是说任何访客都能用一个数字就把接口打成 500。下面两个助手统一收口：
#   标量（str/int/float）照常接受；bool / None / 列表 / 对象一律当作「没传」，
# 由各接口原有的参数校验回 400，不再冒 500。
def _as_text(value) -> str:
    """任意 JSON 值 → 去空白字符串，绝不抛异常。容器与 bool 视为空。"""
    if isinstance(value, str):
        return value.strip()
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _as_int(value, default: int, low=None, high=None) -> int:
    """任意 JSON 值 → 受限整数。解析失败或越界一律回落到 default。"""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if low is not None:
        n = max(low, n)
    if high is not None:
        n = min(high, n)
    return n


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
    """生成方案成功后，把课程记到该归属桶名下（MySQL course_access）。"""
    try:
        progress_store.record_course(client_id, course)
    except Exception:
        pass


def client_courses(client_id: str) -> set:
    if not client_id:
        return set()
    try:
        return progress_store.courses_of(client_id)
    except Exception:
        return set()


def client_courses_many(keys) -> set:
    """聚合多个归属桶的课程（登录 = 用户名桶 + 绑定浏览器桶；匿名 = 单桶）。"""
    out = set()
    for k in keys or []:
        out |= client_courses(k)
    return out


# ---------- 错题本 / 导图的多桶聚合读 ----------
#
# wrong_book_store / mindmap_store 按 client_id 过滤全局文件，这里把
# 「登录用户名桶 + 绑定浏览器桶」的结果合并（错题按 id 去重，id 全局唯一）。

def _quiz_wrongbook_items(course):
    """给 quiz 的「加入错题」用：取本课程全部未掌握错题。

    归属桶按当前请求解析。SSE 在主线程里消费生成器，这里读到的就是发起请求的用户。
    """
    keys = ApiHandler._active_owner_keys()
    raw = _wrongbook_items(keys, course=course, status="unmastered")
    return [{
        "course": it.get("course") or "",
        "question": it.get("question") or "",
        "answer": it.get("answer") or "",
        "reason": it.get("reason") or "",
        "qtype": wrongbook_quiz_mod.parse_qtype(it) or "single",
    } for it in raw if (it.get("question") or "").strip()]


quiz_mod.set_wrongbook_provider(_quiz_wrongbook_items)


def _wrongbook_items(keys, course=None, keyword=None, status=None):
    items, seen = [], set()
    for k in keys or []:
        for it in wrong_book_store.list_items(
                k, course=course, keyword=keyword, status=status):
            iid = it.get("id")
            if iid in seen:
                continue
            seen.add(iid)
            items.append(it)
    return items


def _wrongbook_stats(items):
    """与 wrong_book_store.stats() 同口径，但直接对聚合后的条目计算。"""
    total = len(items)
    mastered = sum(1 for it in items if it.get("mastered"))
    by_course = {}
    for it in items:
        c = it.get("course") or "未归类"
        slot = by_course.setdefault(c, {"course": c, "total": 0, "mastered": 0})
        slot["total"] += 1
        if it.get("mastered"):
            slot["mastered"] += 1
    due = sum(1 for it in items
              if not it.get("mastered") and int(it.get("review_count") or 0) < 3)
    return {
        "total": total,
        "mastered": mastered,
        "unmastered": total - mastered,
        "due": due,
        "ratio": round(mastered / total, 4) if total else 0.0,
        "by_course": sorted(by_course.values(), key=lambda x: -x["total"]),
    }


def _wrongbook_courses(items):
    seen = []
    for it in items:
        c = it.get("course") or "未归类"
        if c not in seen:
            seen.append(c)
    return seen


def mindmap_store_list_many(keys):
    out, seen = [], set()
    for k in keys or []:
        for entry in mindmap_store.list_maps(k):
            course = entry.get("course")
            if course in seen:
                continue
            seen.add(course)
            out.append(entry)
    return out


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


def bootstrap(client_id: str = "", owner_keys=None, profile_file=None) -> dict:
    """一次性返回前端启动所需的全部元信息。

    owner_keys / profile_file 由调用方按登录态传入：
    登录用户画像读 profiles/<用户名>.json、历史读「用户名桶 + 绑定浏览器桶」；
    未登录两者都是 None/[client_id]，行为与旧版完全一致。
    """
    profile = load_profile(filepath=profile_file)
    allowed = client_courses_many(owner_keys) if owner_keys is not None \
        else client_courses(client_id)
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
        "retrieved": result.get("retrieved") or [],
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


def stream_pipeline(course: str, profile: dict, use_cache: bool, emit, owner: str = "") -> dict:
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
        progress_store.save_result(course, result, owner)
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
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Client-Id, X-Auth-Token")
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
        # 必须封顶：Content-Length 是客户端说了算的。
        # 传一个超大整数会让 rfile.read(length) 抛 OverflowError
        # （2026-10-13 线上实测：`Content-Length: 99999999999999999999` → 500），
        # 也会让请求体无限进内存。上限与 nginx client_max_body_size 对齐。
        if length > MAX_UPLOAD_BYTES:
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

        user = self._auth()
        if not user:
            guard = self._require_user()
            if guard:
                return self._send_json(guard[0], guard[1])
            user = {"username": "guest", "role": "guest"}

        files = parsed["files"]
        if not files:
            return self._send_json({"ok": False, "error": "没有收到文件"}, 400)

        fields = parsed["fields"]
        tags = [t.strip() for t in (fields.get("tags") or "").split(",") if t.strip()]
        scope = self._knowledge_scope(fields.get("scope"))
        category = (fields.get("category") or "").strip()
        # 「归入的笔记名」：界面选了某条笔记时传过来，这批文件的块都用它作前缀，
        # 分组时就聚到同一条笔记下；不传则每个文件按自己的文件名各成一条。
        group_title = (fields.get("title") or "").strip()

        guest = user.get("username") == "guest"
        cap = 8 if guest else MAX_KB_NOTES
        store = KnowledgeStore()
        existing = len(store.visible(user["username"])) if guest else len(store.list_all())
        if existing >= cap:
            return self._send_json({
                "ok": False,
                "error": ("未登录最多体验 %d 条资料，登录后可继续导入并保存到账号" % cap)
                if guest else ("知识库已达上限 %d 条，请先删除一些笔记" % MAX_KB_NOTES),
                "guest": guest,
            }, 400)

        cleanup_uploads(DATA_DIR)   # 顺手清过期临时文件，不需要定时任务

        results = []
        for f in files:
            path = None
            try:
                path = save_upload(f["data"], f["filename"], DATA_DIR)
                r = ingest(
                    path, f["filename"], tags=tags, store=store, title=group_title,
                    owner=user["username"], scope=scope, category=category)
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
            "total": len(store.visible(user["username"])),
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
        if self.path.startswith("/api/plan/stream") or self.path.startswith("/api/quiz/stream"):
            return
        sys.stderr.write("[api] %s\n" % (fmt % args))

    def _auth(self, query=None):
        """取当前登录用户；未登录返回 None。

        SSE（EventSource）不能自定义请求头，token 回落到查询参数 token。
        """
        token = (self.headers.get("X-Auth-Token") or "").strip()
        if not token and query:
            token = (query.get("token") or [""])[0].strip()
        return accounts.check_token(token)

    def _knowledge_scope(self, raw):
        """上传空间只接受三档；缺省或非法值都落到本人私有空间。"""
        scope = str(raw or "").strip().lower()
        return scope if scope in ("private", "shared", "public") else "private"

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

    # 未登录也能用全部学习功能，但按浏览器限量（与 LLM 双闸分开计数）。
    # 管理员/设置/知识库分享口令不走这里，仍要求登录。
    GUEST_DAILY_CAP = 30

    def _require_user(self):
        """学习功能写接口：已登录或账号体系未启用时放行。

        未登录不 401，改为本浏览器每日限量。用尽才 429，并提示登录后不限次、
        且数据才会写入账号。返回 None 表示放行；否则返回 (响应体, HTTP 状态码)。
        """
        if not accounts.auth_enabled():
            return None
        if self._auth():
            return None
        cid = self._client_id()
        day = storage_ratelimit._today()
        if not storage_ratelimit.check_and_incr(
                "guest:" + cid, day, self.GUEST_DAILY_CAP):
            return {
                "ok": False,
                "error": "今日体验次数已用完。登录后可继续使用，数据才会保存到账号。",
                "code": "GUEST_LIMIT",
                "guest": True,
            }, 429
        return None

    def _require_login(self, error="请先登录后再操作"):
        """全局配置类写接口：必须「已登录」（不限角色）；账号体系未启用时放行。

        与 _require_user 的区别：后者**对匿名访客放行**（只按浏览器日限），
        只适合个人学习数据的写接口。像 /api/settings 这种改动**全局**
        配置（LLM 供应商 / Key / 模型）的接口若走 _require_user，任何
        匿名访客一个空 body 的 POST 就能把 provider 覆盖成 mock，拖垮整站
        模型能力（2026-10-13 实测踩到并修复）。见上方
        「管理员/设置/知识库分享口令不走这里，仍要求登录」的约定。
        返回 None 表示放行；否则返回 (响应体, HTTP 状态码)。
        """
        if not accounts.auth_enabled():
            return None
        if not self._auth():
            return {"ok": False, "error": error}, 401
        return None

    def _client_id(self, query=None) -> str:
        """取客户端标识：优先 X-Client-Id 请求头，SSE 场景回落 client_id 查询参数。"""
        cid = (self.headers.get("X-Client-Id") or "").strip()
        if not cid and query:
            cid = (query.get("client_id") or [""])[0].strip()
        return cid[:64] or "anonymous"

    # ---------- 登录态与数据归属 ----------
    #
    # 数据身份原本只有 client_id（随机浏览器 ID），登录账号与之无关：
    # 换浏览器数据就"丢"了，同浏览器换账号数据混在一起。现在分两条轨道：
    #   写（POST/DELETE）：登录 → 「u:<用户名>」桶（顺带把当前浏览器惰性绑定到
    #                     账号）；匿名 → client_id 桶（旧行为完全不变）。
    #   读（GET）：登录 → 用户名桶 + 该账号绑定过的所有浏览器桶的并集；
    #             匿名 → 仅当前浏览器桶。

    def _auth_any(self, query=None):
        """登录态：优先 X-Auth-Token 头；SSE（EventSource 不能带自定义头）
        回落 auth_token 查询参数。"""
        token = (self.headers.get("X-Auth-Token") or "").strip()
        if not token and query:
            token = (query.get("auth_token") or [""])[0].strip()
        return accounts.check_token(token or "")

    def _owner_id(self, query=None) -> str:
        """写路径的归属桶名。"""
        user = self._auth_any(query)
        if user:
            try:
                data_scope.bind_client(self._client_id(query), user["username"])
            except Exception:
                pass
            return data_scope.owner_key(user["username"])
        return self._client_id(query)

    # 当前正在处理的请求，给模块级回调读归属桶用。只在本请求线程内有效。
    _request_local = threading.local()

    def _owner_keys(self, query=None) -> list:
        """读路径的桶列表。"""
        user = self._auth_any(query)
        if user:
            try:
                return data_scope.owner_keys_for(user["username"], self._client_id(query))
            except Exception:
                return [data_scope.owner_key(user["username"])]
        cid = self._client_id(query)
        return [cid] if cid else ["anonymous"]

    def _profile_file(self, query=None):
        """按用户隔离的画像文件路径；未登录返回 None（走全局 profile.json 旧行为）。"""
        user = self._auth_any(query)
        if not user:
            return None
        try:
            return data_scope.profile_path(DATA_DIR, user["username"])
        except Exception:
            return None

    # ---------- 匿名 LLM 调用限速（防团队 token 被刷完）----------
    #
    # 双闸：每浏览器每日上限 (anon:<client_id>) + 全局匿名每日池 (anon:global)。
    # 仅对消耗 LLM token 的端点生效：/api/chat、/api/plan、/api/plan/stream、
    # /api/quiz/generate。登录用户视为可信队友，直接放行。MySQL 异常时 fail-open。
    def _enforce_anon_llm_quota(self, query=None):
        """返回 True 表示已拦截（已发出 429），调用方应 return。"""
        user = self._auth_any(query)
        if user:
            return False
        cid = self._client_id(query)
        day = storage_ratelimit._today()
        # 1) 全局匿名池：最防「刷完」——所有匿名用户共享一个每日总上限
        if not storage_ratelimit.check_and_incr(
                "anon:global", day, storage_ratelimit.anon_global_limit()):
            self._send_json({
                "ok": False,
                "error": "今日匿名体验额度已用完，登录后即可不限次使用全部 AI 功能。",
                "code": "ANON_LIMIT_GLOBAL",
            }, 429)
            return True
        # 2) 每浏览器每日：防单个匿名访客猛刷
        if not storage_ratelimit.check_and_incr(
                "anon:" + cid, day, storage_ratelimit.anon_per_browser_limit()):
            self._send_json({
                "ok": False,
                "error": "今日该浏览器的匿名体验额度已用完，登录后即可不限次使用全部 AI 功能。",
                "code": "ANON_LIMIT_CLIENT",
            }, 429)
            return True
        return False

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
        ApiHandler._request_local.handler = self
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
                return self._send_json(bootstrap(
                    self._client_id(query),
                    owner_keys=self._owner_keys(query),
                    profile_file=self._profile_file(query),
                ))

            if path == "/api/mode":
                return self._send_json(mode_info())

            if path == "/api/trace":
                # 日志页是公开只读接口：limit 必须容错（原来 int("abc") 会抛
                # ValueError ⇒ 任何访客一个 ?limit=abc 就能打出 500），
                # 同时封顶，避免 ?limit=99999999… 把整个 trace.log 吐出去。
                limit = _as_int((query.get("limit") or ["120"])[0], 120, low=1, high=1000)
                return self._send_json({"lines": tail_trace(limit)})

            if path == "/api/history":
                allowed = client_courses_many(self._owner_keys(query))
                courses = [
                    c for c in progress_store.list_courses()
                    if c.get("course") in allowed
                ]
                return self._send_json({"courses": courses})

            if path.startswith("/api/history/"):
                course = urllib.parse.unquote(path[len("/api/history/"):])
                if course not in client_courses_many(self._owner_keys(query)):
                    return self._send_json(
                        {"ok": False, "error": "该课程不在你的历史记录中"}, 404)
                result = progress_store.load_result(course, self._owner_id(query))
                if not result:
                    return self._send_json({"ok": False, "error": "未找到该课程"}, 404)
                payload = build_payload(course, result, 0)
                payload["progress"] = progress_store.get_progress(course, self._owner_id(query))
                return self._send_json(payload)

            if path == "/api/progress/overview":
                # 学情面板：该归属名下所有课程的勾选完成度汇总。
                # progress.json 全局共享，所以仍要按归属过滤（登录 = 账号桶 +
                # 绑定浏览器桶；匿名 = 浏览器桶，同 /api/history）。
                allowed = client_courses_many(self._owner_keys(query))
                rows = []
                for c in progress_store.list_courses():
                    name = c.get("course")
                    if name not in allowed:
                        continue
                    d, t, r = progress_store.get_stats(name, self._owner_id(query))
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
                keys = self._owner_keys(query)
                items = _wrongbook_items(
                    keys,
                    course=(query.get("course") or [""])[0].strip() or None,
                    keyword=(query.get("q") or [""])[0].strip() or None,
                    status=(query.get("status") or [""])[0].strip() or None,
                )
                # 来源 / 题型两个维度只能在**读的时候**过滤：store 的 list_items
                # 不认这两个过滤条件，而 add_item 又是封闭契约（不能加字段存题型），
                # 所以题型只能由 tags 里的 "题型:多选" 现解出来。
                want_source = (query.get("source") or [""])[0].strip()
                want_type = (query.get("type") or [""])[0].strip()
                enriched = []
                for it in items:
                    if want_source and str(it.get("source") or "") != want_source:
                        continue
                    qtype = wrongbook_quiz_mod.parse_qtype(it)
                    if want_type and qtype != want_type:
                        continue
                    row = dict(it)
                    row["qtype"] = qtype or ""
                    row["qtype_label"] = (
                        wrongbook_quiz_mod.qtype_label(qtype) if qtype else "")
                    enriched.append(row)
                return self._send_json({
                    "ok": True,
                    "items": enriched,
                    "total": len(enriched),
                    "stats": _wrongbook_stats(items),
                    "courses": _wrongbook_courses(items),
                })

            if path == "/api/asr":
                # 语音转写能力探测：引擎/模型缺失时这里就告诉前端，
                # 界面可以直接把入口置灰并给出「去怎么修」的提示，而不是让用户白录一遍
                return self._send_json(asr_mod.status())

            if path == "/api/mindmap":
                # 列表：只给「课程 / 更新时间 / 节点数」，不带节点，列表页够用
                return self._send_json({
                    "ok": True,
                    "items": mindmap_store_list_many(self._owner_keys(query)),
                })

            if path.startswith("/api/mindmap/"):
                course = urllib.parse.unquote(path[len("/api/mindmap/"):])
                entry = None
                for k in self._owner_keys(query):
                    entry = mindmap_store.get_map(k, course)
                    if entry:
                        break
                if not entry:
                    return self._send_json({"ok": False, "error": "该课程还没有思维导图"}, 404)
                out = dict(entry)
                out.pop("_client", None)
                return self._send_json({"ok": True, "map": out})

            if path == "/api/knowledge/capabilities":
                # 前端据此置灰不支持的入口（例如没装 pypdf 时 PDF 不可用）
                return self._send_json({"ok": True, **kb_capabilities()})

            if path == "/api/knowledge/categories":
                user = self._auth()
                store = KnowledgeStore()
                username = (user or {}).get("username", "") or "guest"
                return self._send_json({
                    "ok": True,
                    "categories": store.categories(username),
                })

            if path == "/api/knowledge":
                user = self._auth()
                # 未登录只看本次体验写入的 guest 资料，看不到别人的 private。
                username = (user or {}).get("username", "") or "guest"
                q = (query.get("q") or [""])[0].strip()
                scope = (query.get("scope") or [""])[0].strip().lower()
                category = (query.get("category") or [""])[0].strip()
                store = KnowledgeStore()
                if not q:
                    items = store.visible(username)
                    if scope in ("private", "shared", "public"):
                        items = [item for item in items if item.get("scope") == scope]
                    if category:
                        items = [item for item in items if item.get("category") == category]
                    return self._send_json({"items": items, "total": len(items)})
                # 打分检索：替代原来的「整句子串匹配」。
                # 旧实现只有措辞和笔记原文高度一致才命中，口语化提问一律搜不到。
                try:
                    top_k = max(1, min(50, int((query.get("top_k") or ["20"])[0])))
                except ValueError:
                    top_k = 20
                # 向量 RAG 切片：优先混合检索（0.6×向量+0.4×词法），
                # 开关关闭 / chromadb 未装 / 任何异常时函数内部直接回退词法，
                # 返回形状与 retrieve_visible 完全一致。retrieval_hybrid 惰性
                # import，api_server 本体不触碰 chromadb（范围闸约束）。
                try:
                    import retrieval_hybrid
                    hits = retrieval_hybrid.retrieve(
                        q, store=store, username=username, top_k=top_k)
                except Exception:
                    hits = store.retrieve_visible(q, username, top_k=top_k)
                items = []
                for note, score, detail in hits:
                    it = store.normalize(note)
                    if scope in ("private", "shared", "public") and it.get("scope") != scope:
                        continue
                    if category and it.get("category") != category:
                        continue
                    it["_score"] = round(score, 2)
                    it["_match"] = detail
                    items.append(it)
                return self._send_json({
                    "items": items, "total": len(items), "query": q, "mode": "retrieve",
                })

            if path == "/api/plan/stream":
                return self._handle_stream(query)

            if path == "/api/quiz/stream":
                return self._handle_quiz_stream(query)

            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()  # 原始异常进日志，用户只看固定文案
            return self._send_json({"ok": False, "error": error_text.internal_error(e)}, 500)

    def do_POST(self):
        ApiHandler._request_local.handler = self
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
                username = _as_text(body.get("username"))
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
                username = _as_text(body.get("username"))
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

            if path == "/api/password":
                # 自助改密：登录态 + 旧密码校验（token 只证明登录，不证明本人）
                user = self._auth()
                if not user:
                    return self._send_json(
                        {"ok": False, "error": "请先登录后再修改密码"}, 401)
                ok, msg = accounts.change_password(
                    user["username"],
                    body.get("old_password") or "",
                    body.get("new_password") or "",
                )
                if not ok:
                    return self._send_json({"ok": False, "error": msg}, 400)
                return self._send_json({"ok": True, "message": msg})

            if path == "/api/accounts":
                guard = self._require_admin()
                if guard:
                    return self._send_json(guard[0], guard[1])
                act = body.get("action") or "create"
                target = _as_text(body.get("username"))
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

            if path == "/api/knowledge/categories":
                user = self._auth()
                if not user:
                    return self._send_json({"ok": False, "error": "请先登录后再添加分类"}, 401)
                category = str(body.get("category") or "").strip()
                if not category or len(category) > 40:
                    return self._send_json({"ok": False, "error": "分类名需为 1–24 个字符"}, 400)
                store = KnowledgeStore()
                note_id = store.add(
                    title=category, content="", tags=[category],
                    owner=user["username"], scope="private", category=category)
                return self._send_json({
                    "ok": True, "id": note_id, "category": category,
                    "categories": store.categories(user["username"]),
                })

            if path == "/api/knowledge/share":
                user = self._auth()
                if not user:
                    return self._send_json({"ok": False, "error": "请先登录后再分享"}, 401)
                raw_ids = body.get("ids") or []
                if not isinstance(raw_ids, list):
                    return self._send_json({"ok": False, "error": "ids 必须是数组"}, 400)
                store = KnowledgeStore()
                code = store.issue_share(raw_ids, user["username"])
                if not code:
                    return self._send_json({"ok": False, "error": "只能分享自己的笔记"}, 403)
                return self._send_json({"ok": True, "code": code})

            if path == "/api/knowledge/redeem":
                user = self._auth()
                if not user:
                    return self._send_json({"ok": False, "error": "请先登录后再兑换"}, 401)
                store = KnowledgeStore()
                created = store.redeem_share(body.get("code"), user["username"])
                if not created:
                    return self._send_json({"ok": False, "error": "口令无效或笔记已删除"}, 404)
                return self._send_json({"ok": True, "ids": created, "count": len(created)})

            if path == "/api/knowledge/category":
                # 已有笔记改归用户自定义分类。不同学校课名不同，不能只靠上传时的自动标签。
                user = self._auth()
                if not user:
                    guard = self._require_user()
                    if guard:
                        return self._send_json(guard[0], guard[1])
                    user = {"username": "guest", "role": "guest"}
                raw_ids = body.get("ids") or []
                if not isinstance(raw_ids, list) or not raw_ids:
                    return self._send_json({"ok": False, "error": "请选择要归类的笔记"}, 400)
                category = str(body.get("category") or "").strip()
                if not category or len(category) > 40:
                    return self._send_json({"ok": False, "error": "分类名需为 1–40 个字符"}, 400)
                store = KnowledgeStore()
                updated = []
                is_admin = user.get("role") == "admin"
                for raw in raw_ids:
                    try:
                        note_id = int(raw)
                    except (TypeError, ValueError):
                        continue
                    target = next(
                        (store.normalize(item) for item in store.list_all()
                         if item.get("id") == note_id),
                        None)
                    if not target:
                        continue
                    owner = str(target.get("owner") or "").strip()
                    if not is_admin and (not owner or owner != user.get("username")):
                        continue
                    if store.set_category(note_id, category):
                        updated.append(note_id)
                        try:
                            import vector_store
                            vector_store.set_note_category(note_id, category)
                        except Exception:
                            pass
                if not updated:
                    return self._send_json({"ok": False, "error": "只能改自己的资料"}, 403)
                return self._send_json({
                    "ok": True, "ids": updated, "category": category,
                    "categories": store.categories(user["username"]),
                })

            if path == "/api/knowledge":
                # 粘贴文本入库（与上传导入共用分块 + 内容安全逻辑）
                user = self._auth()
                if not user:
                    guard = self._require_user()
                    if guard:
                        return self._send_json(guard[0], guard[1])
                    user = {"username": "guest", "role": "guest"}
                text = (body.get("content") or body.get("text") or "").strip()
                title = _as_text(body.get("title"))
                tags = body.get("tags")
                scope = self._knowledge_scope(body.get("scope"))
                category = str(body.get("category") or "").strip()
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]

                store = KnowledgeStore()
                guest = user.get("username") == "guest"
                kb_cap = 8 if guest else MAX_KB_NOTES
                kb_have = len(store.visible(user["username"])) if guest else len(store.list_all())
                if kb_have >= kb_cap:
                    return self._send_json({
                        "ok": False,
                        "error": ("未登录最多体验 %d 条资料，登录后可继续导入并保存到账号" % kb_cap)
                        if guest else ("知识库已达上限 %d 条" % MAX_KB_NOTES),
                        "guest": guest,
                    }, 400)

                # 允许「只给标题、正文留空」——界面上「新建笔记」就是先建一个空容器，
                # 等导入材料再填进去。标题和正文同时为空才算无效请求。
                if not text:
                    if not title:
                        return self._send_json(
                            {"ok": False, "error": "标题和内容不能同时为空"}, 400)
                    try:
                        note_id = store.add(
                            title=title, content="",
                            tags=tags if isinstance(tags, list) and tags else ["#manual"],
                            owner=user["username"], scope=scope, category=category)
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
                r = ingest_text(
                    text, title=title or None, tags=tags, store=store,
                    owner=user["username"], scope=scope, category=category)
                r["total"] = len(store.list_all())
                return self._send_json(r, 200 if r.get("ok") else 400)

            if path == "/api/profile":
                # 画像按用户隔离：登录用户走 MySQL（storage_profiles），未登录退回
                # 全局 profile.json 旧行为（vendor user_profile）。
                profile = {
                    # 一律过 _as_text：传数组/对象这类不可哈希值时，
                    # 下游 user_profile._normalize 的 `v not in ...` 会抛
                    # TypeError → 500（2026-10-13 线上实测）。
                    "level": _as_text(body.get("level")) or DEFAULT_PROFILE["level"],
                    "daily_hours": (_as_text(body.get("daily_hours"))
                                    or DEFAULT_PROFILE["daily_hours"]),
                    "goal": _as_text(body.get("goal")) or DEFAULT_PROFILE["goal"],
                    "deadline": _as_text(body.get("deadline")),
                }
                user = self._auth_any()
                if user:
                    try:
                        storage_profiles.save(user["username"], profile)
                        saved = storage_profiles.load(user["username"]) or profile
                    except Exception:
                        # MySQL 不可用时退回文件兜底
                        pf = self._profile_file()
                        save_profile(profile, filepath=pf)
                        saved = load_profile(filepath=pf)
                else:
                    pf = self._profile_file()
                    save_profile(profile, filepath=pf)
                    saved = load_profile(filepath=pf)
                return self._send_json({
                    "ok": True,
                    "profile": saved,
                    "profile_preview": format_profile_text(saved),
                    "suggested_days": suggest_plan_length(saved),
                })

            if path == "/api/plan":
                course = _as_text(body.get("course"))
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
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                profile = body.get("profile") or load_profile(
                    filepath=self._profile_file())
                use_cache = bool(body.get("use_cache", True))
                t0 = time.time()
                # 匿名 LLM 限速双闸
                if self._enforce_anon_llm_quota():
                    return
                result = run_plan_pipeline(course, profile=profile, use_cache=use_cache)
                try:
                    progress_store.save_result(course, result, self._owner_id())
                    record_client_course(self._owner_id(), course)
                except Exception:
                    pass
                payload = build_payload(course, result, int((time.time() - t0) * 1000))
                return self._send_json(payload)

            if path == "/api/chat":
                question = _as_text(body.get("question"))
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
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                intent = parse_intent(question)
                if intent.get("type") == "generate":
                    return self._send_json({
                        "ok": True,
                        "type": "generate",
                        "course": intent.get("course") or question,
                        "answer": "该输入看起来是「生成方案」请求，请点击「生成方案」。",
                        "source": "intent",
                    })
                # 匿名 LLM 限速双闸（登录用户已在方法内直接放行）
                if self._enforce_anon_llm_quota():
                    return
                res = run_chat_pipeline(
                    question,
                    history=body.get("history") or [],
                    course_context=body.get("course_context") or None,
                )
                # Phase B（Agentic 检索）：弱命中联网补题。知识库没检索到
                # （retrieved 空）时尝试 Tavily 检索回灌增强；任何失败保持原答案。
                # web_tools 惰性 import：未装 langchain-tavily / 无 key 时秒退。
                web_sources = []
                if not (res.get("retrieved") or []):
                    try:
                        import web_tools
                        enhanced = web_tools.enhance_chat(
                            question, res.get("answer") or "",
                            history=body.get("history") or [])
                        if enhanced:
                            res = {"answer": enhanced["answer"],
                                   "source": enhanced["source"],
                                   "retrieved": []}
                            web_sources = enhanced.get("web_sources") or []
                    except Exception:
                        pass   # 联网补题是增强路径，绝不能打挂问答
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
                    # 联网补题来源（弱命中走 Tavily 时非空；新增字段，前端可忽略）
                    "web_sources": web_sources,
                })


            if path == "/api/quiz/generate":
                # 选择题闯关出题（Day5）：安全闸与 /api/chat 同一套。
                # answer 只存服务端（data/quiz_runs.json），本响应不带答案。
                course = _as_text(body.get("course"))
                if not course:
                    return self._send_json({"ok": False, "error": "请先输入课程名"}, 400)
                if detect_crisis(course):
                    log_crisis("quiz", course, self._client_id())
                    return self._send_json(_crisis_response_chat(course))
                detail = check_detail(course)
                if detail["action"] == "BLOCK":
                    log_safety_hit("quiz", course, detail, self._client_id())
                    return self._send_json(
                        {"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                # 匿名 LLM 限速双闸
                if self._enforce_anon_llm_quota():
                    return
                res = quiz_mod.generate_quiz(
                    course,
                    difficulty=body.get("difficulty") or "medium",
                    count=body.get("count") or 5,
                    types=body.get("types") or None,
                    web_search=body.get("web_search", True),
                    lively=body.get("lively", False),
                    client_id=self._client_id(),
                    topics=body.get("topics") or None,
                    include_wrong=bool(body.get("include_wrong")),
                )
                return self._send_json(res)

            if path == "/api/quiz/grade":
                # 服务端判分：correct/answer/explanation 从缓存的标准答案对照得出
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                quiz_id = _as_text(body.get("quiz_id"))
                question_id = _as_text(body.get("question_id"))
                # 多选是数组。对 list 做 .strip() 会直接 500，整卷流式答题时必须保留原值。
                raw_sel = body.get("selected")
                selected = raw_sel.strip() if isinstance(raw_sel, str) else raw_sel
                if not quiz_id or not question_id:
                    return self._send_json(
                        {"ok": False, "error": "缺少 quiz_id 或 question_id"}, 400)
                try:
                    g = quiz_mod.grade_quiz(quiz_id, question_id, selected)
                except KeyError:
                    return self._send_json(
                        {"ok": False, "error": "本局不存在或已过期，请重新出题"}, 404)
                return self._send_json(g)

            if path == "/api/quiz/report":
                # 选择题闯关复盘（Day6）：与 /api/chat 同一套安全闸，作用于本局课程名。
                # run_id 取 POST body 或查询串 ?run_id=，二选一。
                run_id = _as_text(body.get("run_id"))
                if not run_id:
                    _q = urllib.parse.parse_qs(parsed.query)
                    run_id = (_q.get("run_id") or [""])[0].strip()
                if not run_id:
                    return self._send_json({"ok": False, "error": "缺少 run_id"}, 400)
                try:
                    rep = quiz_mod.quiz_report(run_id)
                except KeyError:
                    return self._send_json(
                        {"ok": False, "error": "本局不存在或已过期"}, 404)
                course = rep.get("course") or ""
                if course:
                    if detect_crisis(course):
                        log_crisis("quiz", course, self._client_id())
                        return self._send_json(_crisis_response_chat(course))
                    detail = check_detail(course)
                    if detail["action"] == "BLOCK":
                        log_safety_hit("quiz", course, detail, self._client_id())
                        return self._send_json(
                            {"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                return self._send_json(rep)

            if path == "/api/quiz/from-wrongbook":
                # 错题重做：取本桶下指定 id 的错题，为每道生成同知识点新题（不联网）。
                # 试卷整体已通过 /api/quiz/generate 安全闸，这里仅按归属桶读取错题，不再拦一次。
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                if self._enforce_anon_llm_quota():
                    return
                raw_ids = body.get("ids") or []
                if not isinstance(raw_ids, list) or not raw_ids:
                    return self._send_json({"ok": False, "error": "请选择要重做的错题"}, 400)
                cid = self._owner_id()
                items = []
                for rid in raw_ids:
                    try:
                        item_id = int(rid)
                    except (TypeError, ValueError):
                        continue
                    it = wrong_book_store.get_item(cid, item_id)
                    if not it:
                        continue
                    items.append({
                        "course": it.get("course") or "",
                        "question": it.get("question") or "",
                        "answer": it.get("answer") or "",
                        "reason": it.get("reason") or "",
                        "qtype": wrongbook_quiz_mod.parse_qtype(it) or "single",
                    })
                if not items:
                    return self._send_json({"ok": False, "error": "没有可重做的错题"}, 400)
                res = quiz_mod.generate_quiz_from_wrongbook(
                    items,
                    difficulty=body.get("difficulty") or "medium",
                    types=body.get("types") or None,
                    client_id=self._client_id(),
                )
                return self._send_json(res)
            if path == "/api/export":
                course = _as_text(body.get("course"))
                fmt = _as_text(body.get("format") or "markdown").lower()
                result = body.get("result") or progress_store.load_result(course, self._owner_id())
                if not result:
                    return self._send_json({"ok": False, "error": "没有可导出的方案"}, 400)
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
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
                guard = self._require_login("请先登录后再测试模型连接")
                if guard:
                    return self._send_json(guard[0], guard[1])
                return self._send_json(test_llm_connection(body))

            if path == "/api/settings":
                guard = self._require_login("请先登录后再修改设置")
                if guard:
                    return self._send_json(guard[0], guard[1])
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
                elif _as_text(body.get("api_key")):
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
                course = _as_text(body.get("course"))
                kind = _as_text(body.get("kind"))
                if not course or kind not in ("outline", "plan"):
                    return self._send_json(
                        {"ok": False, "error": "需要 course 与 kind（outline/plan）"}, 400)
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                try:
                    index = int(body.get("index"))
                except (TypeError, ValueError):
                    return self._send_json(
                        {"ok": False, "error": "index 必须是整数"}, 400)
                if not progress_store.set_done(
                        course, self._owner_id(), kind, index, bool(body.get("done"))):
                    return self._send_json(
                        {"ok": False, "error": "未找到该课程或该项越界"}, 404)
                done, total, ratio = progress_store.get_stats(course, self._owner_id())
                return self._send_json({
                    "ok": True,
                    "progress": progress_store.get_progress(course, self._owner_id()),
                    "stats": {"done": done, "total": total, "ratio": round(ratio, 4)},
                })

            if path == "/api/progress/importance":
                # 标注大纲/计划某项的重要程度：普通(0)/重点(1)/核心(2)。
                course = _as_text(body.get("course"))
                kind = _as_text(body.get("kind"))
                if not course or kind not in ("outline", "plan"):
                    return self._send_json(
                        {"ok": False, "error": "需要 course 与 kind（outline/plan）"}, 400)
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                try:
                    index = int(body.get("index"))
                    importance = int(body.get("importance") or 0)
                except (TypeError, ValueError):
                    return self._send_json(
                        {"ok": False, "error": "index / importance 必须是整数"}, 400)
                if not progress_store.set_importance(
                        course, self._owner_id(), kind, index, importance):
                    return self._send_json(
                        {"ok": False, "error": "未找到该课程或该项越界"}, 404)
                return self._send_json({
                    "ok": True,
                    "progress": progress_store.get_progress(course, self._owner_id()),
                })

            if path == "/api/mindmap":
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                # 整张图覆盖保存。前端负责布局与增删，后端只做结构校验：
                # id 合法唯一、parent 存在、恰好一个根、无环（见 mindmap_store._clean_nodes）
                entry, err = mindmap_store.save_map(
                    self._owner_id(),
                    _as_text(body.get("course")),
                    body.get("nodes"),
                )
                if err:
                    return self._send_json({"ok": False, "error": err}, 400)
                return self._send_json({"ok": True, "map": entry})

            if path == "/api/wrongbook":
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                cid = self._owner_id()
                # 文本字段一律过 _as_text：原先 `body.get(..) or ""` 对数组/对象
                # 是**真值**，会原样落库——2026-10-13 实测
                # POST /api/wrongbook {"question":{"a":1}} 把 "{'a': 1}"
                # 写进了 MySQL，错题页直接渲染出这段 Python 字面量。
                # 过 _as_text 后容器值变空串，被下面的「题干不能为空」挡回 400。
                raw_tags = body.get("tags")
                try:
                    item = wrong_book_store.add_item(
                        cid,
                        course=_as_text(body.get("course")),
                        question=_as_text(body.get("question")),
                        my_answer=_as_text(body.get("my_answer")),
                        answer=_as_text(body.get("answer")),
                        reason=_as_text(body.get("reason")),
                        tags=raw_tags if isinstance(raw_tags, list) else None,
                        source=_as_text(body.get("source")) or "manual",
                    )
                except ValueError as e:
                    return self._send_json({"ok": False, "error": str(e)}, 400)
                if not item:
                    return self._send_json({"ok": False, "error": "题干不能为空"}, 400)
                return self._send_json({
                    "ok": True, "item": item,
                    "stats": _wrongbook_stats(_wrongbook_items(self._owner_keys())),
                    "courses": _wrongbook_courses(_wrongbook_items(self._owner_keys())),
                })

            if path == "/api/wrongbook/from-quiz":
                # 闯关错题入错题本。前端只回传**结构化题目**，渲染与选型格式化
                # 全在 wrongbook_quiz 里做——否则三种题型的答案编码
                # （["A"] / ["A","C"] / int 0-1）要在 TypeScript 里重写一遍，
                # 多选大概率又变成「只显示第一个选项的文字」。
                # 课程名已经过 /api/quiz/generate 的安全闸，这里不再拦一次。
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                cid = self._owner_id()
                q = body.get("question")
                q = q if isinstance(q, dict) else {}
                if not str(q.get("stem") or "").strip():
                    return self._send_json(
                        {"ok": False, "error": "题干不能为空"}, 400)
                try:
                    built = wrongbook_quiz_mod.build_quiz_wrong(
                        course=_as_text(body.get("course")),
                        question=q,
                        selected=body.get("selected"),
                        answer=body.get("answer"),
                        explanation=_as_text(body.get("explanation")),
                        knowledge_point=_as_text(body.get("knowledge_point")),
                        extra_tags=body.get("tags"),
                    )
                    item = wrong_book_store.add_item(cid, **built)
                except ValueError as e:
                    # 错题本满 500 条时 store 抛的，文案直接透给用户
                    return self._send_json({"ok": False, "error": str(e)}, 400)
                if not item:
                    return self._send_json(
                        {"ok": False, "error": "题干不能为空"}, 400)
                return self._send_json({
                    "ok": True,
                    "item": dict(item,
                                 qtype=wrongbook_quiz_mod.parse_qtype(item) or ""),
                    "stats": _wrongbook_stats(_wrongbook_items(self._owner_keys())),
                    "courses": _wrongbook_courses(_wrongbook_items(self._owner_keys())),
                })

            if path.startswith("/api/wrongbook/"):
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                cid = self._owner_id()
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
                    "stats": _wrongbook_stats(_wrongbook_items(self._owner_keys())),
                })

            if path == "/api/cache/clear":
                # 方案缓存是**全局**的（key 只含课程+画像，不含账号）：匿名访客
                # 反复清空会迫使整站重复调用 LLM（成本放大），同样要求登录。
                guard = self._require_login("请先登录后再清空缓存")
                if guard:
                    return self._send_json(guard[0], guard[1])
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
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                course = urllib.parse.unquote(path[len("/api/mindmap/"):])
                if not mindmap_store.delete_map(self._owner_id(), course):
                    return self._send_json({"ok": False, "error": "未找到该思维导图"}, 404)
                return self._send_json({"ok": True, "course": course})

            if path.startswith("/api/wrongbook/"):
                guard = self._require_user()
                if guard:
                    return self._send_json(guard[0], guard[1])
                cid = self._owner_id()
                raw_id = urllib.parse.unquote(path[len("/api/wrongbook/"):])
                try:
                    item_id = int(raw_id)
                except ValueError:
                    return self._send_json({"ok": False, "error": "id 必须是数字"}, 400)
                if not wrong_book_store.delete_item(cid, item_id):
                    return self._send_json({"ok": False, "error": "未找到该错题"}, 404)
                return self._send_json({
                    "ok": True, "id": item_id,
                    "stats": _wrongbook_stats(_wrongbook_items(self._owner_keys())),
                    "courses": _wrongbook_courses(_wrongbook_items(self._owner_keys())),
                })

            if path.startswith("/api/knowledge/"):
                # 删除不可逆。管理员维持原权限；普通登录用户只能删除自己拥有的条目。
                # 没有 owner 的旧公共资料仍只允许管理员删除。
                raw_id = urllib.parse.unquote(path[len("/api/knowledge/"):])
                try:
                    note_id = int(raw_id)
                except ValueError:
                    return self._send_json({"ok": False, "error": "id 必须是数字"}, 400)
                user = self._auth()
                if not user:
                    guard = self._require_user()
                    if guard:
                        return self._send_json(guard[0], guard[1])
                    user = {"username": "guest", "role": "guest"}
                store = KnowledgeStore()
                target = next(
                    (store.normalize(item) for item in store.list_all()
                     if item.get("id") == note_id),
                    None)
                if not target:
                    return self._send_json({"ok": False, "error": "未找到该笔记"}, 404)
                owner = str(target.get("owner") or "").strip()
                is_admin = user.get("role") == "admin"
                if not is_admin and (not owner or owner != user.get("username")):
                    return self._send_json({"ok": False, "error": "只能删除自己的资料"}, 403)
                if not store.delete(note_id):
                    return self._send_json({"ok": False, "error": "未找到该笔记"}, 404)
                # 向量 RAG 切片：知识库删除成功后同步清理向量库。
                # 惰性 import + 全包 try：未装 chromadb / 清理失败都不能影响删除结果
                # （向量残块会被 retrieval_hybrid 按 store.visible 过滤掉，只是浪费一点空间）。
                try:
                    import vector_store
                    vector_store.delete_note(note_id)
                except Exception:
                    pass
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

        # 匿名 LLM 限速双闸（必须在 _sse_open 之前判定，否则已发流无法回 429）
        if self._enforce_anon_llm_quota(query):
            return
        profile = load_profile(filepath=self._profile_file(query))
        if query.get("level"):
            profile["level"] = query["level"][0]
        if query.get("daily_hours"):
            profile["daily_hours"] = query["daily_hours"][0]
        if query.get("goal"):
            profile["goal"] = query["goal"][0]
        if "deadline" in query:
            profile["deadline"] = query["deadline"][0]
        try:
            save_profile(profile, filepath=self._profile_file(query))
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
            stream_pipeline(course, profile, use_cache, emit, self._owner_id(query))
            try:
                record_client_course(self._owner_id(query), course)
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

    @staticmethod
    def _active_owner_keys():
        handler = getattr(ApiHandler._request_local, "handler", None)
        if handler is None:
            return ["anonymous"]
        return handler._owner_keys()

    def _handle_quiz_stream(self, query):
        """GET /api/quiz/stream —— 第一题校验通过即推，后续题继续推。

        事件：meta / question / error / done。question 不含 answer。
        安全闸与 POST /api/quiz/generate 相同。EventSource 只能 GET，登录 token 走查询参数。
        """
        course = (query.get("course") or [""])[0].strip()
        if not course:
            return self._send_json({"ok": False, "error": "缺少 course 参数"}, 400)
        client_id = self._client_id(query)
        if detect_crisis(course):
            log_crisis("quiz_stream", course, client_id)
            self._sse_open()
            self.close_connection = True
            self._sse_send("error", _crisis_response_chat(course))
            self._sse_send("done", {"ok": False, "type": "crisis"})
            return self._sse_close()
        detail = check_detail(course)
        if detail["action"] == "BLOCK":
            log_safety_hit("quiz_stream", course, detail, client_id)
            return self._send_json({"ok": False, "error": SAFETY_ERROR_MESSAGE}, 400)
        if accounts.auth_enabled() and not self._auth(query):
            return self._send_json({"ok": False, "error": "请先登录后再操作"}, 401)
        # 匿名 LLM 限速双闸（SSE：必须在 _sse_open 之前判定）
        if self._enforce_anon_llm_quota(query):
            return

        difficulty = (query.get("difficulty") or ["medium"])[0]
        types = (query.get("types") or ["mixed"])[0]
        raw_count = (query.get("count") or ["5"])[0]
        raw_web = (query.get("web_search") or ["1"])[0]
        web_search = raw_web not in ("0", "false", "False")
        raw_lively = (query.get("lively") or ["0"])[0]
        lively = raw_lively in ("1", "true", "True")
        raw_topics = query.get("topics") or []
        topics = [str(t).strip() for t in raw_topics if str(t).strip()]
        raw_wrong = (query.get("include_wrong") or ["0"])[0]
        include_wrong = raw_wrong in ("1", "true", "True")

        self._sse_open()
        self.close_connection = True

        def emit(event, data):
            self._sse_send(event, data)

        try:
            for event, data in quiz_mod.iter_generate_quiz(
                course,
                difficulty=difficulty,
                count=raw_count,
                types=types,
                web_search=web_search,
                lively=lively,
                client_id=client_id,
                topics=topics or None,
                include_wrong=include_wrong,
            ):
                emit(event, data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            traceback.print_exc()
            try:
                emit("error", {"ok": False, "error": error_text.internal_error(e)})
                emit("done", {"ok": False})
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
