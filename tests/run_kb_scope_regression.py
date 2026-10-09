# -*- coding: utf-8 -*-
"""知识库归属与分类回归。只使用临时文件，不触碰真实 knowledge.json。"""
import json
import os
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "study-liu"))
sys.path.insert(0, os.path.join(ROOT, "server"))

from tools.knowledge_store import KnowledgeStore


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    return ok


def test_store():
    path = os.path.join(tempfile.mkdtemp(prefix="kb-scope-"), "knowledge.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"id": 1, "title": "旧公共", "content": "旧", "tags": ["旧分类"]}], f)
    store = KnowledgeStore(path)
    old = store.visible("alice")[0]
    ok = check("旧条目默认公共且保留原分类", old["scope"] == "public" and old["category"] == "旧分类")
    store.add("私有", "只有 alice", owner="alice", scope="private", category="线代")
    store.add("共享", "团队", owner="bob", scope="shared", category="线代")
    visible = {item["title"] for item in store.visible("alice")}
    ok = check("alice 看不到别人的私有", visible == {"旧公共", "私有", "共享"}) and ok
    ok = check("分类从可见条目汇总", store.categories("alice") == ["旧分类", "线代"]) and ok
    return ok


def request(method, path, body=None, token=""):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8765" + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Auth-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http():
    import accounts
    import api_server
    data_dir = tempfile.mkdtemp(prefix="kb-http-")
    kb_path = os.path.join(data_dir, "knowledge.json")
    accounts.configure(data_dir)
    accounts.create_user("alice", "secret1", "user")
    accounts.create_user("bob", "secret2", "user")
    api_server.KnowledgeStore = lambda: KnowledgeStore(kb_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 8765), api_server.ApiHandler)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = request("POST", "/api/knowledge", {"title": "未登录", "content": "x"})
        ok = check("未登录写入返回 401", status == 401)
        status, alice = request("POST", "/api/login", {"username": "alice", "password": "secret1"})
        token = alice["token"]
        request("POST", "/api/knowledge/categories", {"category": "高数"}, token)
        request("POST", "/api/knowledge", {
            "title": "私有笔记", "content": "只给 alice", "scope": "private", "category": "高数",
        }, token)
        status, bob = request("POST", "/api/login", {"username": "bob", "password": "secret2"})
        bob_token = bob["token"]
        status, listed = request("GET", "/api/knowledge", token=bob_token)
        titles = {item["title"] for item in listed["items"]}
        ok = check("bob 列表不包含 alice 私有", "私有笔记" not in titles) and ok
        status, mine = request("GET", "/api/knowledge?scope=private", token=token)
        notes = [item for item in mine["items"] if item.get("content")]
        ok = check("alice 私有资料只含自己", [item["owner"] for item in notes] == ["alice"]) and ok
        note_id = notes[0]["id"]
        status, _denied = request("DELETE", "/api/knowledge/%d" % note_id, token=bob_token)
        ok = check("bob 不能删除 alice 的私有资料", status == 403) and ok
        status, removed = request("DELETE", "/api/knowledge/%d" % note_id, token=token)
        ok = check("alice 可以删除自己的资料", status == 200 and removed.get("ok")) and ok
        accounts.create_user("root", "secret3", "admin")
        status, admin = request("POST", "/api/login", {"username": "root", "password": "secret3"})
        # 接口写入总会带 owner。无主旧资料必须直接落盘，才能测到兼容规则。
        legacy_id = KnowledgeStore(kb_path).add("旧公共", "无归属", tags=["旧分类"])
        status, _blocked = request("DELETE", "/api/knowledge/%d" % legacy_id, token=token)
        ok = check("普通用户不能删除无归属旧资料", status == 403) and ok
        status, cleaned = request("DELETE", "/api/knowledge/%d" % legacy_id, token=admin["token"])
        ok = check("管理员可以删除无归属旧资料", status == 200 and cleaned.get("ok")) and ok
        return ok
    finally:
        server.shutdown()


if __name__ == "__main__":
    passed = test_store() and test_http()
    raise SystemExit(0 if passed else 1)
