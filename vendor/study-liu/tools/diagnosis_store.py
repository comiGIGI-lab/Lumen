# diagnosis_store.py — 诊断性前测记录（data/diagnosis.json）

"""诊断记录存储：data/diagnosis.json。

**为什么单独一个文件**：闯关数据在 quiz_runs.json（有 200 局上限、有对外契约），
诊断是「进课程前的一次性摸底」，生命周期与闯关完全不同，混在一起会互相挤掉。

结构：
{
  "records": {
    "dg-xxxx": {
      "diagnosis_id": "dg-xxxx",
      "course": "数据结构",
      "client_id": "anonymous",
      "created_at": "2026-10-16 16:40:00",
      "graded_at": "",                     # 未判分时为空串
      "count": 6,
      "chapters": ["第1章 线性表", ...],     # 本次覆盖的章节（均衡采样结果）
      "degraded": false,                    # true = 无模型时的纯大纲题兜底
      "questions": [                        # 含 answer，只留服务端
        {"id","type","stem","options","answer","explanation",
         "knowledge_point","chapter","source","sources"}
      ],
      "answers": {"<qid>": {"selected":..., "correct":bool, "answered_at":"..."}},
      "status": "open" | "done"
    }
  }
}

设计取舍：
- **热力图不落盘**，由 heatmap() 现算。落盘会引入"答案改了但热力图没跟着改"的第二真值。
- 对外一律走 public_questions()（剥掉 answer/explanation 之外的标准答案字段），
  答案只在服务端。
- 本模块是 vendor 内部依赖：只允许 import core.paths，**不得 import server 下的任何模块**
  （server 能 import vendor，反过来不行）。判分（对错比较）留在 server/diagnosis.py，
  这里只负责存储 + 聚合 + 出 prompt 段。
"""

import json
import os
import threading
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

# 打包兼容：与 knowledge.json / progress.json / quiz_runs.json 同级
_DATA_DIR = _resolve_data_dir()
_DIAGNOSIS_FILE = os.path.join(_DATA_DIR, "diagnosis.json")

# 只保留最近 N 次诊断，防无限增长（比 quiz 的 200 局小：诊断一课程一般只做一次）
MAX_RECORDS_KEPT = 50

# 掌握度低于该值算「薄弱」，用于 prompt 段与前端高亮
WEAK_THRESHOLD = 60

_LOCK = threading.RLock()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load():
    """读取 diagnosis.json；不存在 / 损坏 → 空结构（绝不抛）。"""
    if not os.path.exists(_DIAGNOSIS_FILE):
        return {"records": {}}
    try:
        with open(_DIAGNOSIS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("records"), dict):
            return {"records": {}}
        return data
    except (json.JSONDecodeError, OSError, ValueError):
        return {"records": {}}


def _save(data):
    """原子写 diagnosis.json（与 progress_store 同惯例）。"""
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _DIAGNOSIS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _DIAGNOSIS_FILE)


def new_id():
    """诊断 id：dg-<时分秒+pid> - <随机>（与 quiz 的 z- 前缀区分开）。"""
    stamp = int(datetime.now().strftime("%H%M%S")) + os.getpid() % 1000
    return "dg-%d-%s" % (stamp, os.urandom(3).hex())


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------

def save_record(rec):
    """落盘一条诊断记录（按 diagnosis_id 覆盖）。返回 rec。"""
    if not isinstance(rec, dict) or not rec.get("diagnosis_id"):
        raise ValueError("diagnosis_id 必填")
    with _LOCK:
        data = _load()
        data["records"][rec["diagnosis_id"]] = rec
        if len(data["records"]) > MAX_RECORDS_KEPT:
            ordered = sorted(
                data["records"].items(),
                key=lambda kv: kv[1].get("created_at") or "",
            )
            for k, _v in ordered[: len(data["records"]) - MAX_RECORDS_KEPT]:
                del data["records"][k]
        _save(data)
    return rec


def get_record(diagnosis_id):
    """按 id 取记录；不存在返回 None。"""
    if not diagnosis_id:
        return None
    with _LOCK:
        return _load()["records"].get(str(diagnosis_id))


def latest_for_course(course, client_id=None):
    """取某课程最近一次诊断；没有返回 None。

    client_id 语义（防串号）：
      - 传了 client_id（含空串）→ **严格**只取该 client 的记录，取不到就返回 None；
      - 传 None → 不限归属，取该课程全局最近一次（Planner 注入走这条：
        画像本身就是全局一份，沿用同一口径）。
    """
    course = str(course or "").strip()
    if not course:
        return None
    with _LOCK:
        records = list(_load()["records"].values())
    hits = [r for r in records if str(r.get("course") or "").strip() == course]
    if client_id is not None:
        wanted = str(client_id or "")
        hits = [r for r in hits if str(r.get("client_id") or "") == wanted]
    if not hits:
        return None
    hits.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return hits[0]


# ---------------------------------------------------------------------------
# 对外投影
# ---------------------------------------------------------------------------

def public_questions(rec):
    """剥掉标准答案：前端只拿题干 / 选项 / 章节 / 知识点。"""
    out = []
    for q in (rec or {}).get("questions") or []:
        if not isinstance(q, dict):
            continue
        out.append({
            "id": q.get("id", ""),
            "type": q.get("type", "single"),
            "stem": q.get("stem", ""),
            "options": q.get("options") or [],
            "knowledge_point": q.get("knowledge_point", ""),
            "chapter": q.get("chapter", ""),
            "source": q.get("source", "kb"),
        })
    return out


def is_done(rec):
    return str((rec or {}).get("status") or "") == "done"


# ---------------------------------------------------------------------------
# 聚合：知识点掌握热力图
# ---------------------------------------------------------------------------

def _mastery(correct, total):
    """正确率 → 0-100 整数掌握度（total=0 视作 0，不除零）。"""
    if not total:
        return 0
    return int(round(100.0 * correct / total))


def heatmap(rec):
    """按章节聚合出掌握热力图，附知识点粒度明细。

    未判分的题按「未作答」处理：既不算对也不算错，因此 total 只统计**已作答**的题，
    避免「还没做题就显示 0% 掌握」误导用户。
    返回 (chapters, knowledge_points, weak)：
      chapters         [{chapter, total, correct, mastery, done}]
      knowledge_points [{knowledge_point, chapter, total, correct, mastery}]
      weak             掌握度 < WEAK_THRESHOLD 的章节名列表（按掌握度升序）
    """
    rec = rec or {}
    answers = rec.get("answers") if isinstance(rec.get("answers"), dict) else {}

    by_chapter = {}
    by_kp = {}
    chapter_order = []
    for q in rec.get("questions") or []:
        if not isinstance(q, dict):
            continue
        ch = str(q.get("chapter") or q.get("knowledge_point") or "未标注章节").strip()
        kp = str(q.get("knowledge_point") or "").strip() or ch
        if ch not in by_chapter:
            by_chapter[ch] = {"chapter": ch, "total": 0, "correct": 0}
            chapter_order.append(ch)
        key = (kp, ch)
        if key not in by_kp:
            by_kp[key] = {"knowledge_point": kp, "chapter": ch, "total": 0, "correct": 0}

        a = answers.get(q.get("id"))
        if not isinstance(a, dict):
            continue  # 未作答：不计入分母
        ok = bool(a.get("correct"))
        by_chapter[ch]["total"] += 1
        by_kp[key]["total"] += 1
        if ok:
            by_chapter[ch]["correct"] += 1
            by_kp[key]["correct"] += 1

    chapters = []
    for ch in chapter_order:
        row = by_chapter[ch]
        row["mastery"] = _mastery(row["correct"], row["total"])
        row["done"] = row["total"] > 0
        chapters.append(row)

    kps = []
    for row in by_kp.values():
        row["mastery"] = _mastery(row["correct"], row["total"])
        if row["total"] > 0:  # 只报已作答的知识点
            kps.append(row)
    kps.sort(key=lambda r: (r["mastery"], r["knowledge_point"]))

    weak = sorted(
        [c["chapter"] for c in chapters if c["done"] and c["mastery"] < WEAK_THRESHOLD],
        key=lambda name: next((c["mastery"] for c in chapters if c["chapter"] == name), 100),
    )
    return chapters, kps, weak


def format_for_prompt(rec, max_weak=3):
    """把一次诊断压成一行「诊断结果」，供注入 Planner prompt。

    没有记录 / 一次都没作答 → 返回空串（调用方据此不加这一段，
    保证「没做诊断」时 prompt 与以前**逐字节一致**）。
    """
    if not isinstance(rec, dict):
        return ""
    chapters, _kps, weak = heatmap(rec)
    answered = [c for c in chapters if c["done"]]
    if not answered:
        return ""
    total = sum(c["total"] for c in answered)
    correct = sum(c["correct"] for c in answered)
    seg = "诊断结果：入门摸底 %d 题，正确 %d/%d（%d%%）" % (
        total, correct, total, _mastery(correct, total))
    if weak:
        shown = "、".join(
            "%s（掌握 %d%%）" % (
                c["chapter"], c["mastery"])
            for c in chapters if c["chapter"] in weak[:max_weak]
        )
        seg += "；薄弱章节：%s，请把这几章拆得更细、补基础示例与练习、适当放慢节奏" % shown
    strong = [c for c in answered if c["mastery"] >= 85]
    if strong:
        seg += "；已较好掌握：%s，可压缩篇幅、直接进练习" % "、".join(
            c["chapter"] for c in strong[:max_weak])
    return seg + "。"
