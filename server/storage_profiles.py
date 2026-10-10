# -*- coding: utf-8 -*-
"""按用户画像存储 —— MySQL 主，文件兜底（<data_dir>/profiles/<user>.json）。

仅本文件 import db。api_server 的 /api/profile 转调本模块（替代 vendor
user_profile.load_profile/save_profile 的 filepath 用法）。

兜底文件路径复用与 data_scope.profile_path 一致的安全规则（用户名含危险字符时
走哈希文件名，杜绝目录穿越），但不依赖 data_scope，保持本模块自包含。
"""

import hashlib
import json
import os
import re
import threading
import time

import db

_DATA_DIR = None
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,64}$")
_LOCK = threading.Lock()


def configure(data_dir):
    global _DATA_DIR
    _DATA_DIR = data_dir
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)


def _fallback_path(username):
    if not _DATA_DIR or not username:
        return None
    name = username.strip()
    if _SAFE_NAME.match(name) and name not in (".", ".."):
        safe = name
    else:
        safe = "u-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    d = os.path.join(_DATA_DIR, "profiles")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, safe + ".json")


# ---------- MySQL ----------
def mysql_save(username, profile):
    blob = json.dumps(profile, ensure_ascii=False)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO profiles (username, profile_json, updated_at) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE profile_json=%s, updated_at=%s",
                (username, blob, int(time.time()), blob, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def mysql_load(username):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT profile_json FROM profiles WHERE username=%s",
                        (username,))
            r = cur.fetchone()
        if not r or not r[0]:
            return None
        return json.loads(r[0])
    finally:
        conn.close()


# ---------- 兜底 JSON ----------
def _file_save(username, profile):
    p = _fallback_path(username)
    if not p:
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def _file_load(username):
    p = _fallback_path(username)
    if not p or not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------- 公开 API ----------
def save(username, profile):
    name = (username or "").strip()
    if not name:
        return
    try:
        mysql_save(name, profile)
    except db.DbUnavailable:
        _file_save(name, profile)


def load(username):
    name = (username or "").strip()
    if not name:
        return None
    try:
        return mysql_load(name)
    except db.DbUnavailable:
        return _file_load(name)
