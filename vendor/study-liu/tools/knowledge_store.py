# knowledge_store.py — 知识库管理：add / search / list / delete（存 JSON 文件）

"""知识库存储模块：用 JSON 文件持久化学习笔记，支持增删查。"""

import json
import os
import threading
from datetime import datetime

from core.paths import data_dir as _resolve_data_dir
from core.paths import ensure_seed_file

# 知识库文件路径（打包兼容，见 core/paths.py）
_DATA_DIR = _resolve_data_dir()
_KNOWLEDGE_FILE = os.path.join(_DATA_DIR, "knowledge.json")


class KnowledgeStore:
    """知识库类，管理学习笔记的增删查。"""

    def __init__(self, filepath=None):
        """初始化，指定文件路径（默认 data/knowledge.json）。"""
        self.filepath = filepath or _KNOWLEDGE_FILE
        if filepath is None:
            # 首次运行 / 打包后换机器：从只读资源拷种子，避免知识库一片空白
            ensure_seed_file("knowledge.json")
        self._ensure_dir()
        # 线程锁：保护 _load → _save 之间的 read-modify-write 原子性
        self._lock = threading.RLock()

    def _ensure_dir(self):
        """确保 data 目录存在。"""
        dir_path = os.path.dirname(self.filepath)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

    def _load(self):
        """读取知识库 JSON 文件，返回列表。"""
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, data):
        """保存知识库到 JSON 文件（中文不转义）。"""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, title, content, tags=None, owner="", scope="public", category=""):
        """
        添加一条笔记。
        参数：
            title: 标题
            content: 内容
            tags: 标签列表（可选）
            owner: 归属账号；旧调用不传，按公共资料保存
            scope: private / shared / public；旧调用默认 public
            category: 用户分类；没有时回退为 tags 的第一项
        返回：
            新增笔记的 id
        """
        clean_tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
        scope = scope if scope in ("private", "shared", "public") else "public"
        category = str(category or "").strip()
        if not category and clean_tags:
            category = clean_tags[0]
        with self._lock:
            data = self._load()
            # id 自增：取现有最大 id + 1
            next_id = max([item["id"] for item in data], default=0) + 1
            note = {
                "id": next_id,
                "title": title,
                "content": content,
                "tags": clean_tags,
                "owner": str(owner or "").strip(),
                "scope": scope,
                "category": category,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            data.append(note)
            self._save(data)
            return next_id

    def normalize(self, item):
        """给旧条目补齐归属字段，只补读取结果，不回写文件。"""
        note = dict(item)
        tags = [str(tag).strip() for tag in (note.get("tags") or []) if str(tag).strip()]
        note["tags"] = tags
        note["owner"] = str(note.get("owner") or "").strip()
        scope = note.get("scope")
        if scope not in ("private", "shared", "public"):
            scope = "public"
        note["scope"] = scope
        note["category"] = str(note.get("category") or (tags[0] if tags else "")).strip()
        return note

    def visible(self, username=""):
        """返回当前账号可见的条目：公共、共享，以及本人私有。"""
        username = str(username or "").strip()
        out = []
        for item in self._load():
            note = self.normalize(item)
            if note["scope"] == "private" and note["owner"] != username:
                continue
            out.append(note)
        return out

    def categories(self, username=""):
        """从可见条目汇总分类，作为没有独立分类表时的可增补分类来源。"""
        seen = []
        for note in self.visible(username):
            category = note.get("category") or ""
            if category and category not in seen:
                seen.append(category)
        return seen

    def search(self, keyword):
        """
        搜索笔记（标题、内容、标签里搜，不区分大小写）。
        参数：
            keyword: 搜索关键词
        返回：
            匹配的笔记列表
        """
        data = self._load()
        kw = keyword.lower()
        results = []
        for item in data:
            # 标题、内容、标签都搜
            in_title = kw in item.get("title", "").lower()
            in_content = kw in item.get("content", "").lower()
            in_tags = any(kw in tag.lower() for tag in item.get("tags", []))
            if in_title or in_content or in_tags:
                results.append(item)
        return results

    def list_all(self):
        """返回所有笔记。"""
        return self._load()

    def retrieve(self, query, top_k=5):
        """
        按相关性检索笔记：分词 → 字段加权 → 覆盖率打分 → 排序。

        与 search() 的区别（这是解决「知识库优先演示不出来」的关键）：
          search()   拿整句去 in —— 只有提问措辞与笔记原文高度一致才命中；
          retrieve() 分词后按命中量打分 —— 口语化改写也能命中。

        实测（线上 25 条真实语料）：「被拦截了怎么办」「缓存有什么用」
        「画像怎么设置比较合适」「四段式链路都有哪些 Agent」这类提问，
        search() 全部搜不到，retrieve() 都能把正确的笔记排到第一。

        search() 保留不动，供桌面版与旧调用方兼容。

        参数：
            query: 用户问题（自然语言，可长可短）
            top_k: 返回条数上限
        返回：
            [(note, score, detail), ...]，score 高者在前；无命中返回 []
        """
        from tools.text_match import rank
        return rank(query, self._load(), top_k=top_k)

    def retrieve_visible(self, query, username="", top_k=5):
        """只在当前账号可见的条目里打分检索。"""
        from tools.text_match import rank
        return rank(query, self.visible(username), top_k=top_k)

    def delete(self, note_id):
        """
        删除指定 id 的笔记。
        参数：
            note_id: 笔记 id
        返回：
            True 删除成功，False 未找到
        """
        with self._lock:
            data = self._load()
            new_data = [item for item in data if item["id"] != note_id]
            if len(new_data) == len(data):
                return False
            self._save(new_data)
            return True
