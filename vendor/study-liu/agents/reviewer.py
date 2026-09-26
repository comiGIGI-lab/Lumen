# reviewer.py — Reviewer Agent：质量检查

"""Reviewer Agent：检查生成结果是否满足质量要求。

v2：资源 URL 必须真实访问到 2xx 才通过（HEAD，超时 5s；被拒再 GET 一字节）。
    背景：模型编造的链接点进去是 404。Searcher 已收回 URL 生成权、改由后端拼接；
    本模块做第二道闸——真实网络校验，而不是信 prompt 或信字段长得像 URL。
    空 URL / 非 http / 4xx/5xx / 超时 一律剔除，comments 记「URL 不可达 N 条」。
    质检不过由 agent_loop 重跑一次 Writer + Searcher（只一次，禁止无限循环）。
"""

import re
from urllib.parse import quote, urlsplit, urlunsplit

try:
    import urllib.request as _urlreq
except Exception:  # 极端环境兜底
    _urlreq = None

_UA = "Mozilla/5.0 (compatible; LUMEN-reviewer/1.0)"


def _is_2xx(status):
    return 200 <= int(status or 0) < 300


def _safe_url(url):
    """把 URL 里残留的非 ASCII（未编码中文）编成可请求的形式。

    队友旧 fallback 会把课程名直接拼进查询串；urlopen 在 Windows 上会
    UnicodeEncodeError，被当成不可达。这里先 quote 再探测。
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii") if host else host
    except Exception:
        host = parts.hostname or ""
    if parts.port:
        host = "{}:{}".format(host, parts.port)
    if parts.username:
        user = parts.username
        if parts.password:
            user = "{}:{}".format(user, parts.password)
        host = "{}@{}".format(user, host) if host else user
    path = quote(parts.path or "", safe="/%:@")
    query = quote(parts.query or "", safe="=&%:@+/,")
    return urlunsplit((parts.scheme, host, path, query, parts.fragment))


def _open(req, timeout):
    with _urlreq.urlopen(req, timeout=timeout) as resp:
        return resp.status


def _head_ok(url, timeout=5):
    """探测 URL 最终是否 2xx（urlopen 会跟随重定向）。

    返回 (ok: bool, status: int)。模块缺失 / 空 URL / 超时 / 连接失败 → (False, 0)。
    """
    if not _urlreq or not url:
        return (False, 0)
    url = _safe_url(url)

    def _try(method, extra_headers=None):
        headers = {"User-Agent": _UA}
        if extra_headers:
            headers.update(extra_headers)
        req = _urlreq.Request(url, method=method, headers=headers)
        try:
            status = _open(req, timeout)
            return (_is_2xx(status), status)
        except Exception as e:
            code = getattr(e, "code", None)
            if code is not None:
                # HTTPError：4xx/5xx 也带 code；2xx 几乎不会走到这里
                return (_is_2xx(code), code)
            raise

    try:
        ok, status = _try("HEAD")
        if ok:
            return (True, status)
        # HEAD 被站点拒绝（403/404/405）时再 GET 确认，避免误杀搜索页
        if status in (403, 404, 405, 501) or status == 0:
            try:
                return _try("GET", extra_headers={"Range": "bytes=0-0"})
            except Exception:
                return (False, status)
        return (False, status)
    except Exception:
        try:
            return _try("GET", extra_headers={"Range": "bytes=0-0"})
        except Exception:
            return (False, 0)


def review(result, check_urls=None):
    """
    检查生成方案的质量。
    检查四项：
        1. outline 至少有 3 章
        2. resources 至少有 2 条
        3. plan 至少有 5 天
        4. (v2, 可关) 资源 URL 必须 2xx：失败项从 resources 移除并计入 comments
    参数：
        result: 包含 outline / resources / plan 的字典
        check_urls: 是否做 URL 校验。None 时：LLM 模式开、mock 模式关（避免演示/单测打外网）
    返回：
        (ok: bool, comments: list[str], result: dict)
        ok 为 True 表示通过，comments 为空列表
        ok 为 False 表示不通过，comments 列出未满足的项
        result 是原 result 的拷贝，URL 不可达条目已剔除
    """
    import copy
    if check_urls is None:
        try:
            from core.config import is_mock
            check_urls = not is_mock()
        except Exception:
            check_urls = True
    comments = []
    result = copy.deepcopy(result) if result else {}

    outline = result.get("outline", [])
    resources = list(result.get("resources", []))
    plan = result.get("plan", [])

    if len(outline) < 3:
        comments.append("大纲不足 3 章")

    if len(plan) < 5:
        comments.append("计划不足 5 天")

    if check_urls and resources:
        live = []
        dead = 0
        for r in resources:
            if not isinstance(r, dict):
                dead += 1
                continue
            url = (r.get("url") or "").strip()
            if not url:
                dead += 1
                continue
            if re.match(r"^https?://", url) is None:
                dead += 1
                continue
            ok, _status = _head_ok(url)
            if ok:
                live.append(r)
            else:
                dead += 1
        if dead:
            comments.append("URL 不可达 {} 条".format(dead))
        result["resources"] = live
        resources = live

    if len(resources) < 2:
        comments.append("资源不足 2 条")

    ok = len(comments) == 0
    return (ok, comments, result)
