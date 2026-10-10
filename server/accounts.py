# -*- coding: utf-8 -*-
"""账号与权限 —— 公开 API 层（委托 storage_users；token 签名在此）。

存储层已迁移到 MySQL（NFR-01 零依赖约束于 2026-10-11 经用户正式解除，仅限本层
与新存储模块）。所有持久化委托 server/storage_users.py：

  - 用户数据 / 角色 / 管理员保护：storage_users（MySQL 主，JSON 兜底）
  - token 签名密钥：storage_users.token_secret()（优先环境变量 STUDY_LIU_TOKEN_SECRET）

本文件只保留与「密码学 / token / 公开契约」相关的纯逻辑，不触数据库。

token 结构（URL-safe base64，`payload.signature`）：

    payload = "username|role|expire_ts"
    signature = HMAC-SHA256(secret, payload)

**为什么不用 session 表**：单机低配，签名 token 无需服务端状态，重启不掉线。
"""

import base64
import hashlib
import hmac
import time

import storage_users

# ------------------------------------------------------------
# 配置 / 常量（保持对外兼容）
# ------------------------------------------------------------
PBKDF2_ROUNDS = storage_users.PBKDF2_ROUNDS
TOKEN_TTL = 7 * 24 * 3600        # 登录态有效期 7 天
ROLE_ADMIN = storage_users.ROLE_ADMIN
ROLE_USER = storage_users.ROLE_USER
VALID_ROLES = storage_users.VALID_ROLES
DEFAULT_ADMIN = storage_users.DEFAULT_ADMIN
DEFAULT_ADMIN_PASSWORD = storage_users.DEFAULT_ADMIN_PASSWORD


def configure(data_dir):
    """绑定兜底数据目录（仅 MySQL 不可用时使用）。api_server 启动时调一次。"""
    storage_users.configure(data_dir)


# ------------------------------------------------------------
# token 签名
# ------------------------------------------------------------

def _sign(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"),
                   hashlib.sha256).hexdigest()


def issue_token(user):
    """发 token。user 形如 {username, role}。"""
    secret = storage_users.token_secret()
    payload = "%s|%s|%d" % (user["username"], user["role"], int(time.time()) + TOKEN_TTL)
    sig = _sign(secret, payload)
    raw = "%s.%s" % (payload, sig)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def check_token(token):
    """验 token。有效返回 {username, role}，否则 None。"""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, _, sig = raw.rpartition(".")
        username, role, exp = payload.split("|")
        exp = int(exp)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return None

    secret = storage_users.token_secret()
    if not hmac.compare_digest(_sign(secret, payload), sig):
        return None
    if exp < time.time():
        return None
    # 账号可能已被删或改了角色，以存储里的为准
    u = storage_users.get_user(username)
    if not u:
        return None
    return {"username": username, "role": u.get("role", ROLE_USER)}


# ------------------------------------------------------------
# 委托 storage_users 的公开 API（签名保持兼容）
# ------------------------------------------------------------

def verify(username, password):
    return storage_users.verify(username, password)


def create_user(username, password, role=ROLE_USER):
    return storage_users.create_user(username, password, role)


def set_password(username, new_password):
    return storage_users.set_password(username, new_password)


def change_password(username, old_password, new_password):
    return storage_users.change_password(username, old_password, new_password)


def set_role(username, role):
    return storage_users.set_role(username, role)


def delete_user(username):
    return storage_users.delete_user(username)


def list_users():
    return storage_users.list_users()


def get_user(username):
    return storage_users.get_user(username)


def count_admins():
    return storage_users.count_admins()


def ensure_default_admin():
    return storage_users.ensure_default_admin()


def auth_enabled():
    """是否已启用账号体系（有管理员就算启用）。"""
    try:
        return storage_users.count_admins() > 0
    except Exception:
        return False


def register_enabled():
    return storage_users.register_enabled()


def register(username, password):
    """自助注册。只建普通账号。"""
    return storage_users.register(username, password)
