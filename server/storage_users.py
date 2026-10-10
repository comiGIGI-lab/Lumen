# -*- coding: utf-8 -*-
"""用户存储 —— MySQL 主，JSON 兜底（accounts.json 旧格式）。

仅本文件 import db（db 再 import pymysql）。accounts.py 转调本模块，保持原有公开 API。

兜底策略：MySQL 不可用时退回到 <data_dir>/accounts.json（旧格式
{"users":{name:{salt,hash,role,created}}, "secret":..., "allow_register":...}），
保证「数据库宕机 / 未配置」时登录与回归测试仍能跑通；MySQL 恢复后自动切回。
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

import db

PBKDF2_ROUNDS = 120_000
ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)
DEFAULT_ADMIN = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

_DATA_DIR = None
_ACCOUNTS_FILE = None
_LOCK = threading.Lock()


def configure(data_dir):
    """绑定兜底数据目录（仅 MySQL 不可用时使用）。"""
    global _DATA_DIR, _ACCOUNTS_FILE
    _DATA_DIR = data_dir
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
        _ACCOUNTS_FILE = os.path.join(data_dir, "accounts.json")


# ---------- token 签名密钥 ----------
def token_secret():
    """优先环境变量 STUDY_LIU_TOKEN_SECRET；否则用兜底文件里的 secret（首次生成并持久化）。"""
    env = os.environ.get("STUDY_LIU_TOKEN_SECRET")
    if env:
        return env
    with _LOCK:
        if _ACCOUNTS_FILE and os.path.exists(_ACCOUNTS_FILE):
            try:
                with open(_ACCOUNTS_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("secret"):
                    return d["secret"]
            except Exception:
                pass
        secret = secrets.token_urlsafe(32)
        if _ACCOUNTS_FILE:
            try:
                data = {}
                if os.path.exists(_ACCOUNTS_FILE):
                    with open(_ACCOUNTS_FILE, encoding="utf-8") as f:
                        data = json.load(f)
                data["secret"] = secret
                _write_file(data)
            except Exception:
                pass
        return secret


# ---------- 密码 ----------
def _hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), dk.hex()


def _verify_password(password, salt_hex, hash_hex):
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    _, calc = _hash_password(password, salt)
    return hmac.compare_digest(calc, hash_hex)


# ---------- MySQL 实现 ----------
def mysql_create_user(username, password, role):
    salt, h = _hash_password(password)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, salt, password_hash, role, created_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (username, salt, h, role, int(time.time())))
        conn.commit()
        return True, "已创建"
    finally:
        conn.close()


def mysql_get_user(username):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT salt, password_hash, role, created_at FROM users WHERE username=%s",
                (username,))
            r = cur.fetchone()
        if not r:
            return None
        return {"salt": r[0], "hash": r[1], "role": r[2],
                "created": r[3] or 0}
    finally:
        conn.close()


def mysql_set_password(username, new_password):
    salt, h = _hash_password(new_password)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET salt=%s, password_hash=%s WHERE username=%s",
                (salt, h, username))
            if cur.rowcount == 0:
                return False, "账号不存在"
        conn.commit()
        return True, "已更新"
    finally:
        conn.close()


def mysql_set_role(username, role):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row:
                return False, "账号不存在"
            cur_role = row[0]
            if cur_role == role:
                return True, "角色未变"
            if cur_role == ROLE_ADMIN and role != ROLE_ADMIN:
                cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
                if (cur.fetchone()[0] or 0) <= 1:
                    return False, "至少要保留一个管理员账号"
            cur.execute("UPDATE users SET role=%s WHERE username=%s", (role, username))
        conn.commit()
        return True, "已设为" + ("管理员" if role == ROLE_ADMIN else "普通账号")
    finally:
        conn.close()


def mysql_delete_user(username):
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row:
                return False, "账号不存在"
            if row[0] == ROLE_ADMIN:
                cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
                if (cur.fetchone()[0] or 0) <= 1:
                    return False, "至少要保留一个管理员账号"
            cur.execute("DELETE FROM users WHERE username=%s", (username,))
        conn.commit()
        return True, "已删除"
    finally:
        conn.close()


def mysql_list_users():
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, role, created_at FROM users ORDER BY "
                "(role<>'admin'), username")
            rows = cur.fetchall()
        return [{"username": r[0], "role": r[1], "created": r[2] or 0}
                for r in rows]
    finally:
        conn.close()


def mysql_count_admins():
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            return cur.fetchone()[0] or 0
    finally:
        conn.close()


def mysql_ensure_default_admin():
    if mysql_count_admins() > 0:
        return False, "已有管理员，跳过"
    return mysql_create_user(DEFAULT_ADMIN, DEFAULT_ADMIN_PASSWORD, ROLE_ADMIN)


# ---------- 兜底 JSON 实现 ----------
def _read_file():
    if not _ACCOUNTS_FILE or not os.path.exists(_ACCOUNTS_FILE):
        return {"users": {}, "secret": secrets.token_urlsafe(32)}
    try:
        with open(_ACCOUNTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("users", {})
    if not data.get("secret"):
        data["secret"] = secrets.token_urlsafe(32)
    return data


def _write_file(data):
    if not _ACCOUNTS_FILE:
        return
    tmp = _ACCOUNTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _ACCOUNTS_FILE)
    try:
        os.chmod(_ACCOUNTS_FILE, 0o600)
    except OSError:
        pass


def _file_create_user(username, password, role):
    data = _read_file()
    if username in data["users"]:
        return False, "用户名已存在"
    salt, h = _hash_password(password)
    data["users"][username] = {"salt": salt, "hash": h, "role": role,
                               "created": int(time.time())}
    _write_file(data)
    return True, "已创建"


def _file_get_user(username):
    return _read_file()["users"].get(username)


def _file_set_password(username, new_password):
    data = _read_file()
    u = data["users"].get(username)
    if not u:
        return False, "账号不存在"
    salt, h = _hash_password(new_password)
    u["salt"], u["hash"] = salt, h
    _write_file(data)
    return True, "已更新"


def _file_set_role(username, role):
    data = _read_file()
    u = data["users"].get(username)
    if not u:
        return False, "账号不存在"
    if u.get("role") == role:
        return True, "角色未变"
    if u.get("role") == ROLE_ADMIN and role != ROLE_ADMIN:
        admins = [n for n, x in data["users"].items() if x.get("role") == ROLE_ADMIN]
        if len(admins) <= 1:
            return False, "至少要保留一个管理员账号"
    u["role"] = role
    _write_file(data)
    return True, "已设为" + ("管理员" if role == ROLE_ADMIN else "普通账号")


def _file_delete_user(username):
    data = _read_file()
    u = data["users"].get(username)
    if not u:
        return False, "账号不存在"
    if u.get("role") == ROLE_ADMIN:
        admins = [n for n, x in data["users"].items() if x.get("role") == ROLE_ADMIN]
        if len(admins) <= 1:
            return False, "至少要保留一个管理员账号"
    del data["users"][username]
    _write_file(data)
    return True, "已删除"


def _file_list_users():
    data = _read_file()
    out = [{"username": n, "role": u.get("role", ROLE_USER),
            "created": u.get("created", 0)}
           for n, u in data["users"].items()]
    out.sort(key=lambda x: (x["role"] != ROLE_ADMIN, x["username"]))
    return out


def _file_count_admins():
    return sum(1 for u in _read_file()["users"].values()
               if u.get("role") == ROLE_ADMIN)


def _file_ensure_default_admin():
    if _file_count_admins() > 0:
        return False, "已有管理员，跳过"
    return _file_create_user(DEFAULT_ADMIN, DEFAULT_ADMIN_PASSWORD, ROLE_ADMIN)


# ---------- 公开 API（MySQL 优先，DbUnavailable 降级 JSON）----------
def create_user(username, password, role=ROLE_USER):
    username = (username or "").strip()
    if not username or len(username) > 32:
        return False, "用户名需为 1–32 个字符"
    if len(password or "") < 6:
        return False, "密码至少 6 位"
    if role not in VALID_ROLES:
        return False, "角色只能是 admin 或 user"
    try:
        return mysql_create_user(username, password, role)
    except db.DbUnavailable:
        if username in _read_file()["users"]:
            return False, "用户名已存在"
        return _file_create_user(username, password, role)


def get_user(username):
    try:
        return mysql_get_user((username or "").strip())
    except db.DbUnavailable:
        return _file_get_user((username or "").strip())


def set_password(username, new_password):
    if len(new_password or "") < 6:
        return False, "密码至少 6 位"
    try:
        return mysql_set_password((username or "").strip(), new_password)
    except db.DbUnavailable:
        return _file_set_password((username or "").strip(), new_password)


def change_password(username, old_password, new_password):
    if not verify(username, old_password or ""):
        return False, "原密码不正确"
    return set_password(username, new_password or "")


def set_role(username, role):
    if role not in VALID_ROLES:
        return False, "角色只能是 admin 或 user"
    try:
        return mysql_set_role((username or "").strip(), role)
    except db.DbUnavailable:
        return _file_set_role((username or "").strip(), role)


def delete_user(username):
    try:
        return mysql_delete_user((username or "").strip())
    except db.DbUnavailable:
        return _file_delete_user((username or "").strip())


def list_users():
    try:
        return mysql_list_users()
    except db.DbUnavailable:
        return _file_list_users()


def count_admins():
    try:
        return mysql_count_admins()
    except db.DbUnavailable:
        return _file_count_admins()


def verify(username, password):
    """校验账号密码；成功返回 {username, role}，失败返回 None。"""
    name = (username or "").strip()
    try:
        u = mysql_get_user(name)
    except db.DbUnavailable:
        u = _file_get_user(name)
    if not u:
        _hash_password(password or "", b"0" * 16)  # 恒定时间，防账号枚举
        return None
    if not _verify_password(password or "", u.get("salt", ""), u.get("hash", "")):
        return None
    return {"username": name, "role": u.get("role", ROLE_USER)}


def ensure_default_admin():
    try:
        return mysql_ensure_default_admin()
    except db.DbUnavailable:
        return _file_ensure_default_admin()


def register_enabled():
    env = os.environ.get("STUDY_LIU_ALLOW_REGISTER")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    try:
        return _read_file().get("allow_register", True) is not False
    except Exception:
        return True


def register(username, password):
    if not register_enabled():
        return False, "本站已关闭自助注册，请联系管理员开通账号"
    return create_user(username, password, ROLE_USER)
