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
from tools import progress_store                                    # noqa: E402
from tools import cache_store                                       # noqa: E402
from tools.knowledge_store import KnowledgeStore                    # noqa: E402
from core.paths import data_dir as _data_dir                        # noqa: E402

TRACE_FILE = agent_loop_mod._TRACE_FILE
# 历史 / 设置 / 缓存的实际落盘目录（源码运行时 = <源码>/data，不可写时回退 ~/.study-liu/data）
DATA_DIR = _data_dir()


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
# 3.2 敏感词过滤（修复"无敏感词校验"）
# ============================================================
# 覆盖违法/色情/作弊/欺诈等明显不适合"学习助手"场景的输入。
# 命中即拒绝（HTTP 400），不做改写、不上送大模型。
SENSITIVE_WORDS = [
    # 赌博 / 毒品
    "赌博", "博彩", "赌场", "六合彩", "毒品", "吸毒", "制毒", "冰毒", "大麻",
    "贩毒", "毒贩", "摇头丸",
    # 武器 / 暴力 —— 用组合词（如"自制枪"）而非单字（"枪"），
    # 避免误伤《枪械设计原理》、军事历史等合法学习内容
    "枪支", "弹药", "军火", "炸药", "爆炸物", "管制刀具",
    "自制枪", "造枪", "做枪", "配枪弹", "自制炸弹", "造炸弹", "做炸弹",
    "制爆", "土制炸", "燃烧瓶", "自制武器",
    "杀人", "杀死", "谋杀", "暗杀", "行凶", "砍人", "投毒", "下毒",
    "自杀", "轻生", "自残",
    # 色情
    "色情", "裸聊", "援交", "嫖娼", "卖淫",
    # 学术不端 / 网络违法
    "代考", "替考", "代写论文", "外挂", "洗钱", "诈骗", "传销", "黑客攻击", "DDoS",
    "作弊", "考试作弊", "买答案", "买考题", "卖答案", "窃题", "包过",
    "开挂", "入侵系统", "盗号", "钓鱼网站",
    # 隐私侵犯
    "人肉搜索", "开盒", "查住址", "查身份证号", "定位某人", "监控他人", "偷拍",
    # 其他
    "人体器官", "买卖器官", "代办证件", "假钞", "假币", "套现",
]


def check_sensitive(text: str) -> list:
    """返回文本中命中的敏感词列表（不区分大小写）。"""
    if not text:
        return []
    low = text.lower()
    return [w for w in SENSITIVE_WORDS if w in low]


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
            "error": "HTTP %s: %s" % (exc.code, detail[:200] or exc.reason),
        }
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


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
        "source_dir": SOURCE_DIR,
        "env_file": os.path.join(SOURCE_DIR, ".env"),
        "env_file_exists": os.path.isfile(os.path.join(SOURCE_DIR, ".env")),
    }


def bootstrap(client_id: str = "") -> dict:
    """一次性返回前端启动所需的全部元信息。"""
    profile = load_profile()
    allowed = client_courses(client_id)
    return {
        "app": "study-liu-web",
        "version": "1.0.0",
        "source_dir": SOURCE_DIR,
        "trace_file": TRACE_FILE,
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
    """把 plan 归一化成 {day,title,chapters,tasks}，与桌面版 plan_normalize 同源。"""
    from tools.plan_normalize import normalize_plan as _np
    return _np(plan)


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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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

    def log_message(self, fmt, *args):  # 收敛控制台噪音
        if self.path.startswith("/api/plan/stream"):
            return
        sys.stderr.write("[api] %s\n" % (fmt % args))

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
            if path == "/api/health":
                return self._send_json({
                    "ok": True,
                    "source_dir": SOURCE_DIR,
                    "trace_file": TRACE_FILE,
                    "data_dir": DATA_DIR,          # 历史/设置实际落盘的位置
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

            if path == "/api/knowledge":
                q = (query.get("q") or [""])[0]
                store = KnowledgeStore()
                items = store.search(q) if q else store.list_all()
                return self._send_json({"items": items, "total": len(items)})

            if path == "/api/plan/stream":
                return self._handle_stream(query)

            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_body()

        try:
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
                hits = check_sensitive(course)
                if hits:
                    return self._send_json(
                        {"ok": False,
                         "error": f"课程名包含敏感词（{'、'.join(hits)}），请修改后重试"},
                        400)
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
                hits = check_sensitive(question)
                if hits:
                    return self._send_json(
                        {"ok": False,
                         "error": f"提问包含敏感词（{'、'.join(hits)}），请修改后重试"},
                        400)
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
                    "answer": res.get("answer", ""),
                    "source": res.get("source", "llm"),
                })

            if path == "/api/export":
                course = (body.get("course") or "").strip()
                result = body.get("result") or progress_store.load_result(course)
                if not result:
                    return self._send_json({"ok": False, "error": "没有可导出的方案"}, 400)
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

            if path == "/api/cache/clear":
                n = cache_store.clear_cache(body.get("course") or None)
                return self._send_json({"ok": True, "cleared": n})

            return self._send_json({"ok": False, "error": f"未知接口 {path}"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._send_json({"ok": False, "error": str(e)}, 500)

    # ---------- SSE：生成方案全链路 ----------
    def _handle_stream(self, query):
        course = (query.get("course") or [""])[0].strip()
        if not course:
            return self._send_json({"ok": False, "error": "缺少 course 参数"}, 400)
        hits = check_sensitive(course)
        if hits:
            return self._send_json(
                {"ok": False,
                 "error": f"课程名包含敏感词（{'、'.join(hits)}），请修改后重试"},
                400)
        client_id = self._client_id(query)

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
                emit("error", {"ok": False, "error": str(e)})
                emit("done", {"ok": False, "error": str(e)})
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
