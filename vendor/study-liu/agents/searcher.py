# searcher.py — Searcher Agent：课程 → 资源列表
# v2：在 LLM 模式下让大模型真实推荐具体资源（书名/视频名/网站），
#     mock 模式或者 LLM 失败时 fallback 到内置资源库。

"""Searcher Agent：输入课程名，返回推荐学习资源列表。

策略：
- LLM 可用 → 调大模型生成 4-5 条具体、真实存在的资源（书/视频/网站/课程）
- LLM 不可用 / 超时 / 解析失败 → fallback 到内置资源库（20 个常见课程）
- LLM 生成但不足 2 条 → fallback 拼接到内置库，确保资源数 ≥ 2（Reviewer 要求）
"""

import json
import re

from core.config import is_mock
from core.llm import generate
from tools.resource_search import search_resources as _builtin_search


def _is_llm_unavailable(result):
    """判断 generate() 返回是否失败。"""
    if not result:
        return True
    if result.startswith("[LLM 不可用]"):
        return True
    return False


def _parse_resources_from_llm(text):
    """从大模型文本里抽取 JSON 资源数组。"""

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
    for it in items:
        if isinstance(it, dict):
            title = (it.get("title") or it.get("name") or "").strip()
            rtype = (it.get("type") or it.get("kind") or "教程").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            # 过滤掉空标题和模板化标题（如 "XXX入门教程"、"XXX推荐视频课程"）
            if not title or len(title) < 2:
                continue
            if title.endswith("入门教程") and url == "":
                continue
            cleaned.append({"title": title, "type": rtype, "url": url})
        elif isinstance(it, str) and it.strip():
            # 容忍纯字符串列表
            cleaned.append({"title": it.strip(), "type": "教程", "url": ""})
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
        + "3. **禁止** markdown 代码块\n"
        + "4. 严格按下面 JSON 格式输出（不要任何额外文字）：\n"
        + '{"resources": ['
        + '{"title": "具体书名或课程名", "type": "书籍", "url": "https://真实网址或留空"},'
        + '{"title": "具体书名或课程名", "type": "视频", "url": "https://真实网址或留空"},'
        + '{"title": "具体网站名", "type": "网站", "url": "https://真实网址"},'
        + '{"title": "具体书名或课程名", "type": "书籍", "url": ""}'
        + "]}"
    )
    result = generate(prompt)
    if _is_llm_unavailable(result):
        return []
    return _parse_resources_from_llm(result)


def search_resources(course, profile=None):
    """
    搜索课程资源。
    优先级：
      1. LLM 模式（且 API 配置完整） → 让大模型真实生成
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

    # mock 模式：内置库
    return _builtin_search(course)
