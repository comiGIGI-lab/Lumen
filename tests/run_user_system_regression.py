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

硬约束（2026-10-11 存储层 MySQL 化之后）：
    - PyMySQL 只允许出现在 server/db.py、server/storage_*.py、迁移脚本 migrate_json_to_mysql.py
    - accounts.py / data_scope.py / api_server.py / quiz.py 不得 import pymysql|mysql|fastapi|…
    - 未登录仍可走匿名路径；消耗 LLM token 的端点有匿名双闸限速
      （storage_ratelimit + 429 ANON_LIMIT_* + 前端 zjxt:anon-limit）

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

    # accounts / data_scope / api_server 不得直接 import 数据库驱动或重框架
    # （MySQL 只许出现在 server/db.py 与 server/storage_*.py）
    driver_re = re.compile(
        r"^\s*(import|from)\s+(pymysql|mysql|fastapi|langchain|langgraph|chromadb|flask)\b",
        re.M,
    )
    for name, path in (
        ("accounts_no_db_driver", ACCOUNTS),
        ("data_scope_no_db_driver", DATA_SCOPE),
        ("api_server_no_db_driver", API),
    ):
        src = read(path)
        bad = driver_re.search(src)
        check(name, not bad, bad.group(0) if bad else "")

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
    # 知识库的「官方资料库 / 我的个人库」两档视图（dc590c5 起）。
    # 4df5ce7 之后组件文案全面 i18n 化：.vue 里只剩 key，中文挪到
    # web/src/i18n/auto-zh.json。所以两种写法都算通过——组件里硬编码中文，
    # 或组件用 kb.scopePublic/kb.scopePrivate 且中文包里确实是「官方/个人」。
    zh_pkg = read(os.path.join(REPO_ROOT, "web", "src", "i18n", "auto-zh.json"))
    check("knowledge_official_personal_views",
          (("官方" in kb) or ("kb.scopePublic" in kb and "官方" in zh_pkg))
          and (("个人" in kb) or ("kb.scopePrivate" in kb and "个人" in zh_pkg)))

    print("\n[3b] 源检查：MySQL 隔离 + 匿名 LLM 限速")
    db_py = os.path.join(SERVER, "db.py")
    rl = os.path.join(SERVER, "storage_ratelimit.py")
    schema = os.path.join(REPO_ROOT, "db", "schema.sql")
    migrate = os.path.join(VENDOR, "tools", "migrate_json_to_mysql.py")
    app_vue = os.path.join(REPO_ROOT, "web", "src", "App.vue")
    quiz_py = os.path.join(SERVER, "quiz.py")
    check("db_module_exists", os.path.exists(db_py))
    check("schema_rate_limits_table",
          os.path.exists(schema) and "CREATE TABLE IF NOT EXISTS rate_limits" in read(schema))
    check("migrate_script_exists", os.path.exists(migrate))
    check("ratelimit_module_exists", os.path.exists(rl))
    if os.path.exists(rl):
        rls = read(rl)
        check("ratelimit_atomic_update", "count < %s" in rls and "UPDATE rate_limits" in rls)
        check("ratelimit_fail_open", "return True" in rls and "DbUnavailable" in rls)
        check("ratelimit_env_defaults",
              "STUDY_LIU_ANON_DAILY_LIMIT" in rls and "STUDY_LIU_ANON_GLOBAL_DAILY_LIMIT" in rls)
    check("api_enforces_anon_quota", "_enforce_anon_llm_quota" in api
          and "ANON_LIMIT_CLIENT" in api and "ANON_LIMIT_GLOBAL" in api)
    # 四个消耗 token 的入口都挂了闸（定义 1 次 + 至少 4 处调用）
    check("api_quota_on_llm_endpoints", api.count("_enforce_anon_llm_quota") >= 5)
    # 全局配置类接口（settings / settings.test / cache.clear）必须要求**登录**：
    # _require_user 会放行匿名访客，用它守卫全局接口 = 任何人一个空 POST 就能
    # 覆盖 LLM 供应商（2026-10-13 实测踩到）。这三个接口应改用 _require_login。
    check("global_cfg_requires_login", api.count("_require_login(") >= 3)
    _bad_guard = re.search(
        r'path == "/api/(settings|settings/test|cache/clear)":\s*\n\s*guard = self\._require_user\(\)',
        api)
    check("global_cfg_not_guest_guard", not _bad_guard,
          _bad_guard.group(0) if _bad_guard else "")
    check("client_dispatches_anon_limit", "zjxt:anon-limit" in cli and "ANON_LIMIT_CLIENT" in cli)
    check("app_opens_login_on_anon_limit",
          "zjxt:anon-limit" in read(app_vue) and "showLogin" in read(app_vue))
    if os.path.exists(quiz_py):
        qsrc = read(quiz_py)
        bad = re.search(r"^\s*(import|from)\s+(pymysql|mysql)\b", qsrc, re.M)
        check("quiz_no_mysql", not bad, bad.group(0) if bad else "")
    else:
        check("quiz_no_mysql", False, "quiz.py missing")
    # pymysql 只许出现在 db.py / storage_*.py / 迁移脚本
    allowed = {
        os.path.normcase(os.path.abspath(db_py)),
        os.path.normcase(os.path.abspath(migrate)),
    }
    leak = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (
            "node_modules", ".git", "__pycache__", "dist", ".venv", "venv")]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            norm = os.path.normcase(os.path.abspath(path))
            if norm in allowed:
                continue
            rel_norm = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
            if rel_norm.startswith("server/storage_") and rel_norm.endswith(".py"):
                continue
            text = read(path)
            if re.search(r"^\s*(import|from)\s+pymysql\b", text, re.M):
                leak.append(rel_norm)
    check("pymysql_import_isolated", not leak, ",".join(leak))


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
