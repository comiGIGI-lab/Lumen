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

    def add(self, title, content, tags=None):
        """
        添加一条笔记。
        参数：
            title: 标题
            content: 内容
            tags: 标签列表（可选）
        返回：
            新增笔记的 id
        """
        with self._lock:
            data = self._load()
            # id 自增：取现有最大 id + 1
            next_id = max([item["id"] for item in data], default=0) + 1
            note = {
                "id": next_id,
                "title": title,
                "content": content,
                "tags": tags or [],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            data.append(note)
            self._save(data)
            return next_id

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
