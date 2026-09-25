# wrong_book_store.py — 错题本存储
#
# 存储位置：data/wrong_book.json（与 progress.json 同目录，见 core.paths.data_dir）
#
# 结构：
# {
#   "seq": 3,                         # 自增 id 游标
#   "items": [
#     {
#       "id": 1,
#       "client_id": "c-xxxx",        # 按浏览器隔离，与 client_history.json 同思路
#       "course": "Python 入门",
#       "question": "题干",
#       "my_answer": "我的错答",
#       "answer": "正确解法 / 解析",
#       "reason": "错因（看错条件 / 概念混淆 …）",
#       "tags": ["语法", "循环"],
#       "mastered": false,            # 是否已掌握（复习通过）
#       "review_count": 0,            # 复习次数
#       "created_at": "…",
#       "updated_at": "…",
#       "last_review_at": "…"
#     }
#   ]
# }

import json
import os
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir

_DATA_DIR = _resolve_data_dir()
_FILE = os.path.join(_DATA_DIR, "wrong_book.json")

# 单题字段长度上限：写入接口是公网无鉴权的，留个天花板防止被灌爆磁盘
MAX_QUESTION = 4000
MAX_ANSWER = 6000
MAX_REASON = 1000
MAX_TAGS = 12
MAX_ITEMS_PER_CLIENT = 500


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load():
    if not os.path.exists(_FILE):
        return {"seq": 0, "items": []}
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"seq": 0, "items": []}
        data.setdefault("seq", 0)
        if not isinstance(data.get("items"), list):
            data["items"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"seq": 0, "items": []}


def _save(data):
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _FILE)


def _clean_tags(tags):
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace('，', ',').split(',')]
    if not isinstance(tags, list):
        return []
    out = []
    for t in tags:
        t = str(t).strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def _clip(text, limit):
    s = ('' if text is None else str(text)).strip()
    return s[:limit]


# ------------------------------------------------------------
# 读
# ------------------------------------------------------------

def list_items(client_id, course=None, keyword=None, status=None):
    """列出某浏览器的错题。

    course  —— 只看某门课
    keyword —— 在题干/答案/错因/标签里模糊匹配
    status  —— "unmastered" 只看未掌握 / "mastered" 只看已掌握
    """
    data = _load()
    items = [it for it in data["items"] if it.get("client_id") == client_id]

    if course:
        items = [it for it in items if it.get("course") == course]

    if status == "unmastered":
        items = [it for it in items if not it.get("mastered")]
    elif status == "mastered":
        items = [it for it in items if it.get("mastered")]

    if keyword:
        kw = keyword.strip().lower()
        def hit(it):
            blob = ' '.join([
                str(it.get("question") or ''),
                str(it.get("answer") or ''),
                str(it.get("my_answer") or ''),
                str(it.get("reason") or ''),
                ' '.join(it.get("tags") or []),
            ]).lower()
            return kw in blob
        items = [it for it in items if hit(it)]

    # 未掌握的排前面，其次按更新时间倒序
    items.sort(key=lambda it: (
        1 if it.get("mastered") else 0,
        _neg_time(it.get("updated_at") or it.get("created_at") or ''),
    ))
    return items


def _neg_time(ts):
    """把「YYYY-mm-dd HH:MM:SS」倒过来用于正序排序。取不到就给个极小值。"""
    try:
        return -datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, TypeError):
        return 0.0


def get_item(client_id, item_id):
    data = _load()
    for it in data["items"]:
        if it.get("id") == item_id and it.get("client_id") == client_id:
            return it
    return None


def stats(client_id):
    """错题本概览：总数 / 已掌握 / 未掌握 / 按课程分布 / 待复习。"""
    data = _load()
    items = [it for it in data["items"] if it.get("client_id") == client_id]
    total = len(items)
    mastered = sum(1 for it in items if it.get("mastered"))

    by_course = {}
    for it in items:
        c = it.get("course") or '未归类'
        slot = by_course.setdefault(c, {"course": c, "total": 0, "mastered": 0})
        slot["total"] += 1
        if it.get("mastered"):
            slot["mastered"] += 1
    courses = sorted(by_course.values(), key=lambda x: -x["total"])

    # 「待复习」= 未掌握且复习次数 < 3（复习够了还没标掌握的不再催）
    due = sum(1 for it in items
              if not it.get("mastered") and int(it.get("review_count") or 0) < 3)

    return {
        "total": total,
        "mastered": mastered,
        "unmastered": total - mastered,
        "due": due,
        "ratio": round(mastered / total, 4) if total else 0.0,
        "by_course": courses,
    }


def courses(client_id):
    """错题本里出现过的课程名（供筛选下拉）。"""
    data = _load()
    seen = []
    for it in data["items"]:
        if it.get("client_id") != client_id:
            continue
        c = it.get("course") or '未归类'
        if c not in seen:
            seen.append(c)
    return seen


# ------------------------------------------------------------
# 写
# ------------------------------------------------------------

def add_item(client_id, *, course='', question='', my_answer='', answer='',
             reason='', tags=None, source='manual'):
    """新增一道错题，返回新条目；题干为空则返回 None。"""
    question = _clip(question, MAX_QUESTION)
    if not question:
        return None

    data = _load()
    mine = [it for it in data["items"] if it.get("client_id") == client_id]
    if len(mine) >= MAX_ITEMS_PER_CLIENT:
        raise ValueError('错题本已达上限 %d 条，请先清理' % MAX_ITEMS_PER_CLIENT)

    data["seq"] = int(data.get("seq") or 0) + 1
    now = _now()
    item = {
        "id": data["seq"],
        "client_id": client_id,
        "course": _clip(course, 80),
        "question": question,
        "my_answer": _clip(my_answer, MAX_ANSWER),
        "answer": _clip(answer, MAX_ANSWER),
        "reason": _clip(reason, MAX_REASON),
        "tags": _clean_tags(tags),
        "source": _clip(source, 20) or 'manual',
        "mastered": False,
        "review_count": 0,
        "created_at": now,
        "updated_at": now,
        "last_review_at": "",
    }
    data["items"].append(item)
    _save(data)
    return item


def update_item(client_id, item_id, **fields):
    """更新字段。可改：course / question / my_answer / answer / reason / tags / mastered。"""
    data = _load()
    for it in data["items"]:
        if it.get("id") != item_id or it.get("client_id") != client_id:
            continue

        if 'question' in fields:
            q = _clip(fields.get('question'), MAX_QUESTION)
            if not q:
                return None
            it["question"] = q
        if 'my_answer' in fields:
            it["my_answer"] = _clip(fields.get('my_answer'), MAX_ANSWER)
        if 'answer' in fields:
            it["answer"] = _clip(fields.get('answer'), MAX_ANSWER)
        if 'reason' in fields:
            it["reason"] = _clip(fields.get('reason'), MAX_REASON)
        if 'course' in fields:
            it["course"] = _clip(fields.get('course'), 80)
        if 'tags' in fields:
            it["tags"] = _clean_tags(fields.get('tags'))
        if 'mastered' in fields:
            it["mastered"] = bool(fields.get('mastered'))

        it["updated_at"] = _now()
        _save(data)
        return it
    return None


def review_item(client_id, item_id, mastered=None):
    """记一次复习。mastered 传 True/False 时同时更新掌握状态。"""
    data = _load()
    for it in data["items"]:
        if it.get("id") != item_id or it.get("client_id") != client_id:
            continue
        it["review_count"] = int(it.get("review_count") or 0) + 1
        it["last_review_at"] = _now()
        it["updated_at"] = it["last_review_at"]
        if mastered is not None:
            it["mastered"] = bool(mastered)
        _save(data)
        return it
    return None


def delete_item(client_id, item_id):
    data = _load()
    before = len(data["items"])
    data["items"] = [
        it for it in data["items"]
        if not (it.get("id") == item_id and it.get("client_id") == client_id)
    ]
    if len(data["items"]) == before:
        return False
    _save(data)
    return True


def clear(client_id, only_mastered=False):
    """清空错题本；only_mastered=True 时只清掉已掌握的。"""
    data = _load()
    before = len(data["items"])
    if only_mastered:
        data["items"] = [
            it for it in data["items"]
            if not (it.get("client_id") == client_id and it.get("mastered"))
        ]
    else:
        data["items"] = [
            it for it in data["items"] if it.get("client_id") != client_id
        ]
    removed = before - len(data["items"])
    if removed:
        _save(data)
    return removed
