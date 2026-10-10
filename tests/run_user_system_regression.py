# -*- coding: utf-8 -*-
"""用户系统扩展回归（账号-数据打通 / 管理能力 / 按用户画像 / 前端鉴权层）。

契约（本切片定义）：
    POST /api/password {old_password, new_password}   需登录 + 旧密码校验
    GET  /api/accounts                                管理员 → {ok, users}
    POST /api/accounts {action: create|role|password|delete}
    登录态下数据归属：history / progress / wrongbook / mindmap 按 username 隔离，
    匿名保持 client_id 旧行为；登录后当前浏览器自动绑定到账号（换浏览器不丢）。
    前端 client.js 必须提供 me/login/register/accountsList/accountAction/changePassword，
    request() 默认带 X-Auth-Token，planStreamUrl 带 auth_token 参数。

硬约束：
    - server 保持纯标准库（data_scope / accounts 只用 stdlib）
    - vendor 不改动：按用户画像走 load_profile/save_profile 已有的 filepath 参数
    - 未登录行为完全不变（匿名仍走 client_id）

用法（仓库根目录）：

    python tests/run_user_system_regression.py

退出码 0 = 全过。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER = os.path.join(REPO_ROOT, "server")
VENDOR = os.path.join(REPO_ROOT, "vendor", "study-liu")
API = os.path.join(SERVER, "api_server.py")
ACCOUNTS = os.path.join(SERVER, "accounts.py")
DATA_SCOPE = os.path.join(SERVER, "data_scope.py")
CLIENT = os.path.join(REPO_ROOT, "web", "src", "api", "client.js")
LOGIN_DIALOG = os.path.join(REPO_ROOT, "web", "src", "components", "LoginDialog.vue")
ADMIN_DIALOG = os.path.join(REPO_ROOT, "web", "src", "components", "AccountAdminDialog.vue")
PET = os.path.join(REPO_ROOT, "web", "src", "composables", "usePet.js")
TIMER = os.path.join(REPO_ROOT, "web", "src", "composables", "useStudyTimer.js")
KNOWLEDGE = os.path.join(REPO_ROOT, "web", "src", "components", "KnowledgePage.vue")

sys.path.insert(0, SERVER)
sys.path.insert(0, VENDOR)

FAILED = []
PASSED = 0


def check(name, cond, detail=""):
    global PASSED
    if cond:
        PASSED += 1
        print("  ok  %s" % name)
    else:
        FAILED.append(name)
        print("FAIL  %s%s" % (name, (" —— " + str(detail)) if detail else ""))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def source_checks():
    print("\n[1] 源检查：后端路由与模块")
    api = read(API)

    # 自改密码路由
    check("route_password_exists", '"/api/password"' in api, "缺少 POST /api/password 路由")
    check("route_password_uses_change_password", "accounts.change_password" in api)
    check("route_password_requires_auth", "old_password" in api)

    # 数据归属
    check("data_scope_module_exists", os.path.exists(DATA_SCOPE))
    check("api_uses_data_scope", "data_scope" in api and "owner_keys" in api)
    check("api_owner_prefix_u", "data_scope.owner_key" in api
          and '"u:"' in read(DATA_SCOPE))

    # 按用户画像（vendor 不动，走 filepath 参数）
    check("profile_per_user_path", "profile_path" in api and "profiles" in api)
    check("vendor_user_profile_untouched", "def load_profile(filepath=None)" in
          read(os.path.join(VENDOR, "tools", "user_profile.py")))

    # SSE token
    check("sse_accepts_auth_token", "auth_token" in api)

    # 后端保持纯标准库（accounts / data_scope）
    for name, path in (("accounts_stdlib_only", ACCOUNTS), ("data_scope_stdlib_only", DATA_SCOPE)):
        if os.path.exists(path):
            src = read(path)
            bad = re.search(r"^\s*(import|from)\s+(fastapi|langchain|langgraph|chromadb|requests|flask)",
                            src, re.M)
            check(name, not bad, bad.group(0) if bad else "")
        else:
            check(name, False, "文件不存在")

    print("\n[2] 源检查：前端鉴权层")
    cli = read(CLIENT)
    for name, pat in (
        ("client_me", r"me\s*\(\s*\)\s*\{"),
        ("client_login", r"login\s*\(\s*username"),
        ("client_register", r"register\s*\(\s*username"),
        ("client_accounts_list", r"accountsList\s*\("),
        ("client_account_action", r"accountAction\s*\("),
        ("client_change_password", r"changePassword\s*\("),
        ("client_default_auth_header", r"X-Auth-Token"),
        ("client_sse_auth_token", r"auth_token"),
    ):
        check(name, re.search(pat, cli) is not None)

    print("\n[3] 源检查：管理页 / 自改密码入口 / 个性化持久化")
    check("admin_dialog_exists", os.path.exists(ADMIN_DIALOG))
    if os.path.exists(ADMIN_DIALOG):
        dlg = read(ADMIN_DIALOG)
        check("admin_dialog_uses_accounts_api",
              "accountAction" in dlg and "accountsList" in dlg)
    login = read(LOGIN_DIALOG)
    check("login_dialog_admin_entry", "AccountAdminDialog" in login)
    check("login_dialog_change_password_entry", "changePassword" in login or "修改密码" in login
          or "auth.changePw" in login)

    pet = read(PET)
    check("pet_keyed_by_username", "zjxt.pet." in pet or "petKey(" in pet or "pet_key" in pet)
    timer = read(TIMER)
    check("study_settings_persist", "zjxt.study" in timer or "studyKey(" in timer)
    kb = read(KNOWLEDGE)
    check("knowledge_official_personal_views",
          ("官方" in kb) and ("个人" in kb or "private" in kb))


def runtime_checks(tmp):
    print("\n[4] 运行时：data_scope 绑定语义")
    import data_scope
    ds_dir = os.path.join(tmp, "ds")
    os.makedirs(ds_dir, exist_ok=True)
    data_scope.configure(ds_dir)

    data_scope.bind_client("c-1", "alice")
    data_scope.bind_client("c-1", "alice")           # 幂等
    check("ds_bind_basic", data_scope.client_ids_of("alice") == ["c-1"])
    check("ds_username_of", data_scope.username_of("c-1") == "alice")

    data_scope.bind_client("c-1", "bob")             # 改绑：一个浏览器同时只归一个账号
    check("ds_rebind_moves", data_scope.client_ids_of("alice") == []
          and data_scope.client_ids_of("bob") == ["c-1"])

    data_scope.bind_client("c-2", "bob")
    check("ds_multi_browser", set(data_scope.client_ids_of("bob")) == {"c-1", "c-2"})

    data_scope.bind_client("", "bob")                # 空 cid 不写入
    data_scope.bind_client("c-3", "")                # 空用户名不写入
    check("ds_empty_noop", data_scope.username_of("c-3") == "")

    keys = data_scope.owner_keys_for("bob", "c-2")   # 惰性绑定 + 读桶聚合
    check("ds_owner_keys", keys[0] == "u:bob" and set(keys[1:]) == {"c-1", "c-2"})

    # 持久化：重新 configure（模拟重启）后绑定仍在
    data_scope.configure(ds_dir)
    check("ds_persist", data_scope.username_of("c-1") == "bob")

    print("\n[5] 运行时：按用户画像路径")
    p = data_scope.profile_path(os.path.join(tmp, "pf"), "alice")
    check("profile_path_valid", p is not None and p.endswith("alice.json")
          and os.path.isdir(os.path.dirname(p)))
    evil = data_scope.profile_path(os.path.join(tmp, "pf"), "../evil")
    check("profile_path_traversal_safe",
          evil is not None and ".." not in os.path.basename(evil))
    check("profile_path_empty_none", data_scope.profile_path(os.path.join(tmp, "pf"), "") is None)

    print("\n[6] 运行时：accounts.change_password")
    import accounts
    acc_dir = os.path.join(tmp, "acc")
    accounts.configure(acc_dir)
    accounts._read()["users"].clear() if False else None
    # 建独立用户，避免依赖默认管理员状态
    ok, msg = accounts.create_user("carol", "oldpass6", accounts.ROLE_USER)
    check("pw_setup_user", ok, msg)

    ok, msg = accounts.change_password("carol", "wrong-old", "newpass6")
    check("pw_reject_wrong_old", not ok)

    ok, msg = accounts.change_password("carol", "oldpass6", "abc")
    check("pw_reject_short", not ok)

    ok, msg = accounts.change_password("carol", "oldpass6", "newpass6")
    check("pw_accept", ok, msg)
    check("pw_new_works", accounts.verify("carol", "newpass6") is not None)
    check("pw_old_dead", accounts.verify("carol", "oldpass6") is None)
    check("pw_missing_user", not accounts.change_password("ghost", "x" * 6, "y" * 6)[0])


def main():
    tmp = tempfile.mkdtemp(prefix="zjxt-user-sys-")
    try:
        source_checks()
        runtime_checks(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n===== 用户系统扩展回归：%d 通过 / %d 失败 =====" % (PASSED, len(FAILED)))
    if FAILED:
        for name in FAILED:
            print("  FAIL %s" % name)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
