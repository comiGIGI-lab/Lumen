# -*- coding: utf-8 -*-
"""数据归属 —— 把「浏览器」与「账号」绑起来（零依赖，只用标准库）。

## 为什么需要

之前学习历史 / 进度 / 错题本 / 导图全部按 `X-Client-Id`（随机浏览器 ID）存取，
和登录账号完全无关：换浏览器数据就"丢"了，同一浏览器换账号数据混在一起。

本模块提供一张极小的绑定表：

    client_id  →  username（一个浏览器同一时刻只归一个账号）

读数据时（GET），登录用户看「自己名下历史桶」+「绑定过的浏览器桶」的并集；
写数据时（POST），登录用户写 `u:<username>` 桶，匿名用户仍写 client_id 桶
（旧行为完全不变）。

## 存储

`<DATA_DIR>/client_bindings.json`：

    {"bindings": {"c-1a2b3c": "alice", ...}}

## 按用户画像

`profile_path(data_dir, username)` 返回按用户隔离的画像文件路径
（`<data_dir>/profiles/<username>.json`）。vendor 的
`load_profile/save_profile` 本来就支持 `filepath` 参数，这里只负责给出
**安全**的路径：用户名里出现路径分隔符等危险字符时改用哈希文件名，
杜绝目录穿越。
"""

import hashlib
import json
import os
import re

_BINDINGS_FILE = None

# 用户名允许直接当文件名的白名单（含 CJK）；不满足就走哈希，不报错
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,64}$")


def configure(data_dir):
    """绑定数据目录。api_server 启动时调一次。"""
    global _BINDINGS_FILE
    _BINDINGS_FILE = os.path.join(data_dir, "client_bindings.json")
    os.makedirs(data_dir, exist_ok=True)


# ------------------------------------------------------------
# 文件读写
# ------------------------------------------------------------

def _read():
    try:
        with open(_BINDINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    b = data.get("bindings")
    return b if isinstance(b, dict) else {}


def _write(bindings):
    tmp = _BINDINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"bindings": bindings}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _BINDINGS_FILE)


# ------------------------------------------------------------
# 绑定
# ------------------------------------------------------------

def bind_client(client_id, username):
    """把浏览器绑到账号名下（幂等；重复绑定 = 改绑）。

    空参数直接忽略。登录态的每个请求都会调它（惰性绑定），
    所以文件写入要足够便宜：只在映射真的变化时落盘。
    """
    if not _BINDINGS_FILE:
        return
    cid = (client_id or "").strip()[:64]
    name = (username or "").strip()
    if not cid or not name:
        return
    bindings = _read()
    if bindings.get(cid) == name:
        return
    bindings[cid] = name
    _write(bindings)


def client_ids_of(username):
    """某账号名下绑定过的所有浏览器（按绑定先后）。"""
    name = (username or "").strip()
    if not name:
        return []
    return [cid for cid, u in _read().items() if u == name]


def username_of(client_id):
    """浏览器当前绑定的账号（没绑过返回空串）。"""
    cid = (client_id or "").strip()[:64]
    if not cid:
        return ""
    return _read().get(cid, "")


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
# 按用户画像路径
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
