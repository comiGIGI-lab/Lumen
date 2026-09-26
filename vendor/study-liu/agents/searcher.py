# searcher.py — Searcher Agent：课程 → 资源列表
# v2：生成 URL 的权力不在模型手里。模型只出标题 / 类型 / 简介；
#     链接由后端按类型可靠拼接（标题必须 URL 编码）。
#     背景：模型常编造不存在的路径，点进去 404。prompt 禁写不够，解析时丢弃 url/link。
#     mock 或 LLM 失败时 fallback 到内置资源库（20 门常见课，含空 url 的书目）。

"""Searcher Agent：输入课程名，返回推荐学习资源列表。

工程约束（用户体验 + 严谨性）：
- **模型没有生成 URL 的权力**。即使返回 url / link 也一律丢弃，不采信。
- URL 只由后端 url_for 按 type 拼接，标题走 quote_plus：
    视频 → B 站搜索
    书籍 → 豆瓣读书搜索
    其他 → 中国大学 MOOC 搜索
- LLM 不可用 / 超时 / 解析失败 → fallback 到内置资源库
- LLM 生成但不足 2 条 → 拼上内置库，确保资源数 ≥ 2（Reviewer 要求）
- 内置库已有的真实 URL（B 站 BV 号、官方文档等）原样保留，不覆盖 9 套课程模板
- 活链由 Reviewer 做真实网络 2xx 校验，本模块不探活
"""

import json
import re
from urllib.parse import quote_plus

from core.config import is_mock
from core.llm import generate
from tools.resource_search import search_resources as _builtin_search

# 按类型拼接的搜索页（标题走 quote_plus，空格变成 +）
_URL_VIDEO = "https://search.bilibili.com/all?keyword="
_URL_BOOK = "https://book.douban.com/subject_search?search_text="
_URL_MOOC = "https://www.icourse163.org/search.htm?search="


def _is_llm_unavailable(result):
    """判断 generate() 返回是否失败。"""
    if not result:
        return True
    if result.startswith("[LLM 不可用]"):
        return True
    return False


def _norm_type(rtype):
    t = (rtype or "").strip()
    low = t.lower()
    # 子串匹配：模型常写「视频课程」「公开课视频」「教材书籍」
    if "视频" in t or "影视" in t or "video" in low:
        return "视频"
    if "书" in t or "book" in low:
        return "书籍"
    return t or "教程"


def url_for(rtype, title):
    """后端唯一的 URL 生成入口。标题编码后按类型拼搜索页，不含模型路径。"""
    title = (title or "").strip()
    if not title:
        return ""
    encoded = quote_plus(title)
    t = _norm_type(rtype)
    if t == "视频":
        return _URL_VIDEO + encoded
    if t == "书籍":
        return _URL_BOOK + encoded
    return _URL_MOOC + encoded


def _parse_resources_from_llm(text):
    """从大模型文本里抽取 JSON 资源数组。丢弃 url / link，只留 title / type / intro。"""

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    json_text = m.group(0)

    try:
        data = json.loads(json_text)
    except Exception:
        return []

    items = None
    if isinstance(data, dict):
        for k in ("resources", "items", "data", "list"):
            if k in data and isinstance(data[k], list):
                items = data[k]
                break
        if items is None:
            for v in data.values():
                if isinstance(v, list):
                    items = v
                    break
    elif isinstance(data, list):
        items = data

    if not items:
        return []

    cleaned = []
    for it in items:
        if isinstance(it, dict):
            title = (it.get("title") or it.get("name") or "").strip()
            rtype = _norm_type(it.get("type") or it.get("kind") or "教程")
            intro = (it.get("intro") or it.get("desc") or it.get("summary") or "").strip()
            if not title or len(title) < 2:
                continue
            # 占位标题（「XX入门教程」）丢掉
            if title.endswith("入门教程"):
                continue
            row = {"title": title, "type": rtype, "url": ""}
            if intro:
                row["intro"] = intro[:40]
            cleaned.append(row)
        elif isinstance(it, str) and it.strip():
            cleaned.append({"title": it.strip(), "type": "教程", "url": ""})
    return cleaned


def _enrich_url(item, overwrite=False):
    """后端补齐 URL。overwrite=True 时无视模型给的 url（LLM 路径必须如此）。

    内置模板路径 overwrite=False：已有真实链接保留，空 url 才按类型拼接。
    """
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None
    item = dict(item)
    item["title"] = title
    item["type"] = _norm_type(item.get("type"))
    existing = (item.get("url") or "").strip()
    if overwrite or not existing:
        item["url"] = url_for(item["type"], title)
    else:
        item["url"] = existing
    return item


def _fill_missing_urls(items):
    """内置库：空 url 按类型拼接，已有链接不动。"""
    out = []
    for it in items or []:
        e = _enrich_url(it, overwrite=False)
        if e:
            out.append(e)
    return out


def _llm_search(course, profile=None):
    """调大模型拿标题 / 类型 / 简介。URL 字段即使模型写了也丢弃，改由 url_for 补。"""
    profile_text = ""
    if profile:
        try:
            from tools.user_profile import format_profile_text
            profile_text = format_profile_text(profile) + "\n"
        except Exception:
            profile_text = ""
    prompt = (
        profile_text
        + "你是学习资源推荐助手。请为课程「" + course + "」推荐 4-5 个**真实、优质**的学习资源。\n"
        + "要求：\n"
        + "1. 必须是真实存在的资源名——具体到**出版社+书名** / **B站/MOOC 上某门具体课程名** / **某个知名网站**\n"
        + "2. **禁止**输出「" + course + "入门教程」「" + course + "推荐视频课程」「" + course + "经典教材」"
        + "这种占位符标题\n"
        + "3. **不要输出 URL 字段**。链接由后端按类型拼接，模型编 URL 会 404。\n"
        + "4. type 只能是：视频 / 书籍 / 教程 / 网站 之一\n"
        + "5. **禁止** markdown 代码块\n"
        + "6. 严格按下面 JSON 格式输出（不要任何额外文字）：\n"
        + '{"resources": ['
        + '{"title": "具体书名", "type": "书籍", "intro": "一句话简介（不超过 30 字）"},'
        + '{"title": "具体课程名", "type": "视频", "intro": "一句话简介"},'
        + '{"title": "具体网站名", "type": "网站", "intro": "一句话简介"},'
        + '{"title": "具体书名", "type": "书籍", "intro": "一句话简介"}'
        + "]}"
    )
    result = generate(prompt)
    if _is_llm_unavailable(result):
        return []
    parsed = _parse_resources_from_llm(result)
    enriched = []
    for it in parsed:
        e = _enrich_url(it, overwrite=True)
        if e:
            enriched.append(e)
    return enriched


def search_resources(course, profile=None):
    """
    搜索课程资源。
    优先级：
      1. LLM 模式（且 API 配置完整） → 大模型只出标题，后端拼 URL
      2. 不够/失败 → fallback 到内置 20 个课程的库（保证 Reviewer 通过）
    参数：
        course: 课程名
        profile: 可选，用户画像（注入 LLM prompt 让推荐更个性化）
    返回：
        资源列表，每项 {"title", "type", "url"}，可选 intro
    """
    if not is_mock():
        llm_result = _llm_search(course, profile=profile)
        if len(llm_result) >= 2:
            return llm_result[:6]
        from core import llm as _llm_mod
        _llm_mod.mark_degraded("searcher")
        builtin = _fill_missing_urls(_builtin_search(course))
        seen = {(r.get("title"), r.get("url")) for r in llm_result}
        merged = list(llm_result)
        for r in builtin:
            key = (r.get("title"), r.get("url"))
            if key in seen:
                continue
            merged.append(r)
            seen.add(key)
        if len(merged) >= 2:
            return merged[:6]
        return builtin

    return _fill_missing_urls(_builtin_search(course))
