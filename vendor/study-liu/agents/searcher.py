# searcher.py — Searcher Agent：课程 → 资源列表
# v3：模型只负责「推荐什么」（title + type），**链接一律由程序按标题拼**。
#     mock 模式或 LLM 失败时 fallback 到内置资源库。

"""Searcher Agent：输入课程名，返回推荐学习资源列表。

策略：
- LLM 可用 → 让大模型给出 4-5 条具体资源（只给 title / type）
- 链接不采信模型：按 title 拼成对应平台的**搜索链接**
  （视频 → B 站搜索；书籍 → 豆瓣搜索；其它 → 中国大学 MOOC 搜索），
  这样「点开链接一定在搜这个资源名」，不会再出现标题与网址各写各的。
- 模型即使返回了 url 也一律丢弃，不采用
- 课程名对不上的资源丢掉（只挡明显跑题的，判据见 _is_on_topic）
- 内置资源库（tools/resource_search.py）里的链接是人工核对过的对照表，
  可以保留，不参与上面的「按标题拼链接」
- LLM 不可用 / 超时 / 解析失败 → fallback 到内置资源库（20 个常见课程）
- LLM 生成但不足 2 条 → 用内置库补足，确保资源数 ≥ 2（Reviewer 要求）
"""

import json
import re
from urllib.parse import quote

from core.config import is_mock
from core.llm import generate
from tools.resource_search import search_resources as _builtin_search


# 各平台的「搜索入口」模板。查询词就是资源标题。
# 这样即使模型给的标题不是真实条目，点开也只是「搜这个名字」，
# 而不是跳到一条 404 的假网址。
_SEARCH_VIDEO = "https://search.bilibili.com/all?keyword={q}"
_SEARCH_BOOK = "https://book.douban.com/subject_search?search_text={q}"
_SEARCH_OTHER = "https://www.icourse163.org/search.htm?search={q}"


def _is_llm_unavailable(result):
    """判断 generate() 返回是否失败。"""
    if not result:
        return True
    if result.startswith("[LLM 不可用]"):
        return True
    return False


def _search_url(title, rtype):
    """按资源标题 + 类型拼出搜索链接（查询词 = 标题）。

    视频 → B 站搜索；书籍 → 豆瓣搜索；其它 → 中国大学 MOOC 搜索。
    """
    q = quote((title or "").strip())
    t = (rtype or "").lower()
    if "视频" in t or "video" in t:
        return _SEARCH_VIDEO.format(q=q)
    if "书" in t or "book" in t:
        return _SEARCH_BOOK.format(q=q)
    return _SEARCH_OTHER.format(q=q)


def _course_tokens(course):
    """把课程名切成用于相关性判断的片段。

    英文/数字取 ≥2 字符的词；中文取 2-gram（避免单字过宽）。
    """
    s = (course or "").lower()
    tokens = set(re.findall(r"[a-z0-9]{2,}", s))
    for run in re.findall(r"[\u4e00-\u9fff]+", s):
        if len(run) == 1:
            tokens.add(run)
        for i in range(len(run) - 1):
            tokens.add(run[i:i + 2])
    return tokens


def _is_on_topic(title, course):
    """资源标题是否与本课程对得上。

    判据刻意宽松：标题里出现课程名的任一片段（英文单词 / 中文二字组合）即视为对得上。
    只有「完全跑题」的资源才会被丢掉 —— 因为程序无法真正理解语义，
    过严会把《统计学习方法》这种与「机器学习」相关的正常资源误杀。
    课程名为空时不过滤。
    """
    toks = _course_tokens(course)
    if not toks:
        return True
    t = (title or "").lower()
    return any(tok in t for tok in toks)


def _parse_resources_from_llm(text, course=None):
    """从大模型文本里抽取 JSON 资源数组。

    只采信 title / type 两个字段；url 由 _search_url 按标题生成，
    模型返回的 url 直接丢弃（它并不会去打开那个页面）。
    """

    # 1) 优先尝试整段解析
    text = text.strip()
    # 去掉可能的 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    # 2) 找到第一个 { 到最后一个 } 的 JSON 片段
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    json_text = m.group(0)

    try:
        data = json.loads(json_text)
    except Exception:
        return []

    # 兼容多种结构：{"resources": [...]} 或直接是 [...]
    items = None
    if isinstance(data, dict):
        for k in ("resources", "items", "data", "list"):
            if k in data and isinstance(data[k], list):
                items = data[k]
                break
        if items is None:
            # 任意 key 的 list 值
            for v in data.values():
                if isinstance(v, list):
                    items = v
                    break
    elif isinstance(data, list):
        items = data

    if not items:
        return []

    cleaned = []
    seen = set()
    for it in items:
        if isinstance(it, dict):
            title = (it.get("title") or it.get("name") or "").strip()
            rtype = (it.get("type") or it.get("kind") or "教程").strip()
            # ★ 模型给的 url 一律丢弃，链接只有 _search_url 一个来源
            if not title or len(title) < 2:
                continue
            if not _is_on_topic(title, course):
                continue
            if title in seen:
                continue
            seen.add(title)
            cleaned.append({
                "title": title,
                "type": rtype,
                "url": _search_url(title, rtype),
            })
        elif isinstance(it, str) and it.strip():
            # 容忍纯字符串列表
            title = it.strip()
            if not _is_on_topic(title, course):
                continue
            if title in seen:
                continue
            seen.add(title)
            cleaned.append({
                "title": title,
                "type": "教程",
                "url": _search_url(title, "教程"),
            })
    return cleaned


def _llm_search(course, profile=None):
    """调大模型获取具体资源。失败返回空列表，由调用方 fallback。"""
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
        + "3. **不要输出 url** —— 链接会由系统按资源名自动生成搜索链接，你只需要给标题和类型\n"
        + "4. **禁止** markdown 代码块\n"
        + "5. 严格按下面 JSON 格式输出（不要任何额外文字）：\n"
        + '{"resources": ['
        + '{"title": "具体书名", "type": "书籍"},'
        + '{"title": "具体课程名", "type": "视频"},'
        + '{"title": "具体网站名", "type": "网站"},'
        + '{"title": "具体课程名", "type": "教程"}'
        + "]}"
    )
    result = generate(prompt)
    if _is_llm_unavailable(result):
        return []
    return _parse_resources_from_llm(result, course)


def search_resources(course, profile=None):
    """
    搜索课程资源。
    优先级：
      1. LLM 模式（且 API 配置完整） → 让大模型给资源名，链接由程序拼
      2. 不够/失败 → fallback 到内置 20 个课程的库（保证 Reviewer 通过）
    参数：
        course: 课程名
        profile: 可选，用户画像（注入 LLM prompt 让推荐更个性化）
    返回：
        资源列表，每项 {"title", "type", "url"}
    """
    # LLM 模式：先 LLM，失败 fallback
    if not is_mock():
        llm_result = _llm_search(course, profile=profile)
        if len(llm_result) >= 2:
            return llm_result[:6]
        # 不够 2 条，补充内置库（打降级标记，供 UI 警告）
        from core import llm as _llm_mod
        _llm_mod.mark_degraded("searcher")
        builtin = _builtin_search(course)
        merged = llm_result + [
            r for r in builtin if r not in llm_result
        ]
        if len(merged) >= 2:
            return merged[:6]
        # 实在不够就直接用内置库
        return builtin

    # mock 模式：内置库（人工核对过的链接原样保留）
    return _builtin_search(course)
