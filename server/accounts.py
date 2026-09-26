# -*- coding: utf-8 -*-
"""账号与权限 —— 零依赖（只用标准库）。

## 为什么需要

知识库里的材料是多人共用的，删除是不可逆操作。之前 `DELETE /api/knowledge/<id>`
谁都能调，任何人点一下就删掉了。现在加一层账号体系：

  - **普通账号**：可以看、可以导入、可以问
  - **管理员账号**：额外可以**删除知识库内容**

## 存储

`<DATA_DIR>/accounts.json`，密码**不存明文**，存 PBKDF2-HMAC-SHA256 派生值：

    {"users": {"admin": {"salt": "...", "hash": "...", "role": "admin", ...}},
     "secret": "<token 签名密钥>"}

文件权限建议 600（与其他 data/*.json 一致）。备份/迁移时**可以整目录拷走**，
因为密钥也在里面，拷过去旧 token 仍然有效。

## 登录态

登录成功发一个 HMAC 签名的 token，前端存 localStorage，之后每个请求带
`X-Auth-Token` 头。服务端验签 + 查过期，解出 {username, role}。

token 结构（URL-safe base64，`payload.signature`）：

    payload = "username|role|expire_ts"
    signature = HMAC-SHA256(secret, payload)

**为什么不用 session 表**：这台机器只有 1.6G 内存、后端是单文件标准库服务，
签名 token 无需服务端状态，重启不掉线，也不占内存。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------

PBKDF2_ROUNDS = 120_000          # 本地低配机器上约 60ms，够用且不拖慢登录
TOKEN_TTL = 7 * 24 * 3600        # 登录态有效期 7 天
ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)

# 首次启动自动创建的管理员。**上线后请立刻改掉密码**（见 docs 说明）。
DEFAULT_ADMIN = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

_ACCOUNTS_FILE = None            # 由 configure() 注入


def configure(data_dir):
    """绑定数据目录。api_server 启动时调一次。"""
    global _ACCOUNTS_FILE
    _ACCOUNTS_FILE = os.path.join(data_dir, "accounts.json")
    os.makedirs(data_dir, exist_ok=True)
    _ensure_file()


# ------------------------------------------------------------
# 文件读写
# ------------------------------------------------------------

def _ensure_file():
    """文件不存在就建一个空壳，并生成 token 签名密钥。"""
    if os.path.exists(_ACCOUNTS_FILE):
        return
    data = {"users": {}, "secret": secrets.token_urlsafe(32)}
    _write(data)
    try:
        os.chmod(_ACCOUNTS_FILE, 0o600)
    except OSError:
        pass


def _read():
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


def _write(data):
    tmp = _ACCOUNTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _ACCOUNTS_FILE)


# ------------------------------------------------------------
# 密码
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 账号管理
# ------------------------------------------------------------

def list_users():
    """返回账号列表（**不含**任何密码信息）。"""
    data = _read()
    out = []
    for name, u in data["users"].items():
        out.append({
            "username": name,
            "role": u.get("role", ROLE_USER),
            "created": u.get("created", 0),
        })
    out.sort(key=lambda x: (x["role"] != ROLE_ADMIN, x["username"]))
    return out


def get_user(username):
    return _read()["users"].get(username)


def create_user(username, password, role=ROLE_USER):
    """建号。返回 (ok, 说明)。用户名已存在、密码太短、角色非法都会拒绝。"""
    username = (username or "").strip()
    if not username or len(username) > 32:
        return False, "用户名需为 1–32 个字符"
    if len(password or "") < 6:
        return False, "密码至少 6 位"
    if role not in VALID_ROLES:
        return False, "角色只能是 admin 或 user"

    data = _read()
    if username in data["users"]:
        return False, "用户名已存在"

    salt, h = _hash_password(password)
    data["users"][username] = {
        "salt": salt,
        "hash": h,
        "role": role,
        "created": int(time.time()),
    }
    _write(data)
    return True, "已创建"


def set_password(username, new_password):
    if len(new_password or "") < 6:
        return False, "密码至少 6 位"
    data = _read()
    u = data["users"].get(username)
    if not u:
        return False, "账号不存在"
    salt, h = _hash_password(new_password)
    u["salt"], u["hash"] = salt, h
    _write(data)
    return True, "已更新"


def set_role(username, role):
    """改角色（提拔/降级）。返回 (ok, 说明)。

    保护：**不允许把最后一个管理员降级**，否则没人能删知识库了。
    """
    if role not in VALID_ROLES:
        return False, "角色只能是 admin 或 user"
    data = _read()
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
    _write(data)
    return True, "已设为" + ("管理员" if role == ROLE_ADMIN else "普通账号")


def delete_user(username):
    """删号。**不允许删掉最后一个管理员**，否则没人能删知识库了。"""
    data = _read()
    u = data["users"].get(username)
    if not u:
        return False, "账号不存在"
    if u.get("role") == ROLE_ADMIN:
        admins = [n for n, x in data["users"].items() if x.get("role") == ROLE_ADMIN]
        if len(admins) <= 1:
            return False, "至少要保留一个管理员账号"
    del data["users"][username]
    _write(data)
    return True, "已删除"


def count_admins():
    return sum(1 for u in _read()["users"].values() if u.get("role") == ROLE_ADMIN)


# ------------------------------------------------------------
# 登录态
# ------------------------------------------------------------

def _sign(secret, payload):
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(username, password):
    """校验账号密码。成功返回 {username, role}，失败返回 None。"""
    u = get_user((username or "").strip())
    if not u:
        # 账号不存在也走一次哈希，避免用响应时间探测账号是否存在
        _hash_password(password or "", b"0" * 16)
        return None
    if not _verify_password(password or "", u.get("salt", ""), u.get("hash", "")):
        return None
    return {"username": username.strip(), "role": u.get("role", ROLE_USER)}


def issue_token(user):
    """发 token。user 形如 {username, role}。"""
    secret = _read()["secret"]
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

    secret = _read()["secret"]
    if not hmac.compare_digest(_sign(secret, payload), sig):
        return None
    if exp < time.time():
        return None
    # 账号可能已被删或改了角色，以文件里的为准
    u = get_user(username)
    if not u:
        return None
    return {"username": username, "role": u.get("role", ROLE_USER)}


def ensure_default_admin():
    """首次启动建默认管理员。返回 (created: bool, message)。"""
    if count_admins() > 0:
        return False, "已有管理员，跳过"
    ok, msg = create_user(DEFAULT_ADMIN, DEFAULT_ADMIN_PASSWORD, ROLE_ADMIN)
    return ok, msg


def auth_enabled():
    """是否已启用账号体系（有管理员就算启用）。没有则删除操作放行，
    避免把老部署一键锁死 —— 前端会提示去创建管理员。"""
    try:
        return count_admins() > 0
    except Exception:
        return False


# ------------------------------------------------------------
# 自助注册
# ------------------------------------------------------------

def register_enabled():
    """是否允许自助注册。

    默认允许 —— 注册出来的都是普通账号（不能删知识库），风险可控。
    需要关闭时在 accounts.json 里加 `"allow_register": false`。
    """
    try:
        return _read().get("allow_register", True) is not False
    except Exception:
        return True


def register(username, password):
    """自助注册。**只建普通账号** —— 管理员必须由现有管理员创建，
    否则任何人都能把自己提成管理员，权限体系就没意义了。"""
    if not register_enabled():
        return False, "本站已关闭自助注册，请联系管理员开通账号"
    return create_user(username, password, ROLE_USER)
