# -*- coding: utf-8 -*-
"""数据归属 —— 把「浏览器」与「账号」绑起来（委托 storage_bindings）。

读数据时（GET），登录用户看「自己名下历史桶」+「绑定过的浏览器桶」的并集；
写数据时（POST），登录用户写 `u:<username>` 桶，匿名用户仍写 client_id 桶。

存储层已迁移到 MySQL（NFR-01 于 2026-10-11 经用户正式解除，仅限新存储模块）。
绑定表读写委托 server/storage_bindings.py；owner_key / owner_keys_for / profile_path
是本模块的纯逻辑 / 纯文件系统辅助，不触数据库。
"""

import hashlib
import os
import re

import storage_bindings

# 用户名允许直接当文件名的白名单（含 CJK）；不满足就走哈希，不报错
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,64}$")


def configure(data_dir):
    """绑定兜底数据目录（仅 MySQL 不可用时使用）。api_server 启动时调一次。"""
    storage_bindings.configure(data_dir)


# ------------------------------------------------------------
# 绑定（委托 storage_bindings）
# ------------------------------------------------------------

def bind_client(client_id, username):
    storage_bindings.bind_client(client_id, username)


def client_ids_of(username):
    return storage_bindings.client_ids_of(username)


def username_of(client_id):
    return storage_bindings.username_of(client_id)


# ------------------------------------------------------------
# 归属键
# ------------------------------------------------------------

def owner_key(username):
    """写路径的归属桶名：登录用户 `u:<username>`，与浏览器 ID 永不冲突。"""
    return "u:" + (username or "").strip()


def owner_keys_for(username, current_cid):
    """读路径的桶列表：用户名桶 + 该账号绑定过的所有浏览器桶。

    会顺带把当前浏览器惰性绑定到账号（登录后原浏览器的匿名历史归入账号）。
    """
    name = (username or "").strip()
    if not name:
        cid = (current_cid or "").strip()[:64]
        return [cid] if cid else []
    bind_client(current_cid, name)
    keys = [owner_key(name)] + client_ids_of(name)
    return keys


# ------------------------------------------------------------
# 按用户画像路径（纯文件系统，保持目录穿越防护；供应商 profile 走 MySQL）
# ------------------------------------------------------------

def profile_path(data_dir, username):
    """按用户的画像文件路径；username 为空返回 None（走全局 profile.json）。

    用户名含危险字符（路径分隔符等）时改用 sha256 前 16 位做文件名，
    保证永远不会写出 profiles/ 目录之外。
    """
    name = (username or "").strip()
    if not name or not data_dir:
        return None
    if _SAFE_NAME.match(name) and name not in (".", ".."):
        safe = name
    else:
        safe = "u-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    d = os.path.join(data_dir, "profiles")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, safe + ".json")
