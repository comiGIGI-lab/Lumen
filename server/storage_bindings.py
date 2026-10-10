# -*- coding: utf-8 -*-
"""浏览器 ↔ 账号 绑定存储 —— MySQL 主，JSON 兜底。

仅本文件 import db。data_scope.py 转调本模块；owner_key / owner_keys_for /
profile_path 仍留在 data_scope.py（纯逻辑 / 纯文件系统，不触 DB）。
"""

import json
import os
import threading
import time

import db

_BINDINGS_FILE = None
_LOCK = threading.Lock()


def configure(data_dir):
    global _BINDINGS_FILE
    _BINDINGS_FILE = os.path.join(data_dir, "client_bindings.json") if data_dir else None
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)


# ---------- MySQL ----------
def mysql_bind_client(client_id, username):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO client_bindings (client_id, username, bound_at) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE username=%s, bound_at=%s",
                (client_id, username, int(time.time()), username, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def mysql_client_ids_of(username):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_id FROM client_bindings WHERE username=%s ORDER BY bound_at",
                (username,))
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def mysql_username_of(client_id):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username FROM client_bindings WHERE client_id=%s", (client_id,))
            r = cur.fetchone()
        return r[0] if r else ""
    finally:
        conn.close()


# ---------- 兜底 JSON ----------
def _read_file():
    if not _BINDINGS_FILE or not os.path.exists(_BINDINGS_FILE):
        return {}
    try:
        with open(_BINDINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return {}
    b = data.get("bindings") if isinstance(data, dict) else None
    return b if isinstance(b, dict) else {}


def _write_file(bindings):
    if not _BINDINGS_FILE:
        return
    tmp = _BINDINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"bindings": bindings}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _BINDINGS_FILE)


def _file_bind_client(client_id, username):
    bindings = _read_file()
    if bindings.get(client_id) == username:
        return
    bindings[client_id] = username
    _write_file(bindings)


def _file_client_ids_of(username):
    return [cid for cid, u in _read_file().items() if u == username]


def _file_username_of(client_id):
    return _read_file().get(client_id, "")


# ---------- 公开 API ----------
def bind_client(client_id, username):
    cid = (client_id or "").strip()[:64]
    name = (username or "").strip()
    if not cid or not name:
        return
    try:
        mysql_bind_client(cid, name)
    except db.DbUnavailable:
        _file_bind_client(cid, name)


def client_ids_of(username):
    name = (username or "").strip()
    if not name:
        return []
    try:
        return mysql_client_ids_of(name)
    except db.DbUnavailable:
        return _file_client_ids_of(name)


def username_of(client_id):
    cid = (client_id or "").strip()[:64]
    if not cid:
        return ""
    try:
        return mysql_username_of(cid)
    except db.DbUnavailable:
        return _file_username_of(cid)
