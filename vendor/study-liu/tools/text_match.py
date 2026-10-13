# text_match.py — 中文友好的轻量检索打分（纯标准库，无第三方依赖）
#
# 背景：原来的 KnowledgeStore.search() 是「拿整句去 in」——
#   kw = keyword.lower()
#   if kw in title.lower() or kw in content.lower() or ...
# 只有提问措辞和笔记原文**高度一致**时才命中，稍换说法就搜不到，
# 这正是「知识库优先」演示不出来的根因。
#
# 这个模块提供一个不依赖分词库的替代方案：
#   中文按 2-gram 滑窗切（无需词典，对 OOV 友好）+ 英文/数字按词切，
#   过滤停用词与纯标点，按字段加权、按查询覆盖率打分、再排序。
#
# 为什么不用 jieba / BM25 库：服务器只有 1.6G 内存且后端刻意保持
# 「零第三方依赖」，而这个语料规模（几十~几千条）下 2-gram + 覆盖率
# 的效果已经足够好，且完全可解释、零安装成本。

import math
import re

# ---------- 分词 ----------

# 常见虚词 / 疑问词：它们几乎出现在任何句子里，保留只会稀释信号
STOPWORDS = frozenset("""
的 了 是 在 和 与 及 或 也 都 就 而 但 却 很 太 更 最 又 再 还 只 才 被 把 让 使 给 对 从 到 由 向 为 以 于 之 其 这 那 这些 那些 这个 那个
我 你 他 她 它 我们 你们 他们 咱们 自己 什么 怎么 怎样 如何 为什么 哪些 哪个 哪里 多少 是否 能否 可以 能否 一个 一些 一下 一样 时候 问题 请问 帮 帮忙 告诉 知道
a an the is are was were be been being do does did of to in on at for with and or but if then this that these those it its as by from
how what why when where which who whom whose can could should would will shall may might must
""".split())

# 中文连续片段
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
# 英文 / 数字片段（含小数点与下划线，方便 bge-m3 / gpt-4o 这类模型名）
_ASCII_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-]*")


def tokenize(text):
    """把文本切成检索用的 token 列表（保留重复，供词频统计）。

    中文：连续汉字串按 2-gram 滑窗切（长度 1 的串原样保留）。
    英文/数字：整段作为一个 token，另加小写形式。
    过滤：停用词、纯标点、长度 < 2 的中文单字（如「的」「了」已被停用词拦掉）。
    """
    if not text:
        return []
    text = str(text)
    out = []

    for run in _CJK_RUN.findall(text):
        n = len(run)
        if n == 1:
            if run not in STOPWORDS:
                out.append(run)
            continue
        for i in range(n - 1):
            bigram = run[i:i + 2]
            if bigram not in STOPWORDS:
                out.append(bigram)
        # 完全匹配词典里的中文词（如「三重积分」）时额外保留整段，
        # 让长词命中能得到比 2-gram 更高的权重
        if n >= 3:
            out.append(run)

    for run in _ASCII_RUN.findall(text):
        low = run.lower()
        if low in STOPWORDS:
            continue
        out.append(low)

    return out


def token_counts(text):
    """返回 {token: 出现次数}。"""
    counts = {}
    for t in tokenize(text):
        counts[t] = counts.get(t, 0) + 1
    return counts


# ---------- 打分 ----------

# 字段权重：标题、分类、标签命中都比正文重要。
# 界面上显示的「标签」主要来自 category 和主题 tags，不能只搜标题。
FIELD_WEIGHTS = (
    ("title", 6.0),
    ("category", 5.0),
    ("tags", 4.5),
    ("content", 1.0),
)


def score_item(query_tokens, item):
    """给单条笔记打分。

    返回 (score, detail)。score 为 0 表示完全没命中。

    打分公式（可解释、可调）：
        score = 命中权重和 × √覆盖率 + 6×标题覆盖率 + 整句精确命中加成

    ★ 为什么覆盖率要开平方、而且不与「命中权重和」相除：
    最初写成 `命中权重 / 查询token总数 × 覆盖率`，用真实语料一测就露馅——
    长问句被 token 数量稀释。例如「四段式链路都有哪些 Agent」本该命中
    一条写着「四段式 Agent 链路」的笔记（命中 4 个 token），但因为
    查询有 9 个 token，被除完只剩 0.24，低于阈值直接被丢掉。
    「绝对命中量」才是主信号，覆盖率只做轻微调节，所以用 √ 而不是线性。

    ★ √ 而不是直接相乘：全命中（覆盖 1.0）与半命中（覆盖 0.5）的差距
    不该是 2 倍那么剧烈——用户问句里本来就常带无关的修饰词。
    """
    if not query_tokens:
        return 0.0, {}

    uniq = set(query_tokens)
    tags = [str(tag).lstrip("#") for tag in (item.get("tags", []) or [])]
    title_c = token_counts(item.get("title", ""))
    category_c = token_counts(item.get("category", ""))
    tags_c = token_counts(" ".join(tags))
    content_c = token_counts(item.get("content", ""))
    field_maps = {
        "title": title_c,
        "category": category_c,
        "tags": tags_c,
        "content": content_c,
    }

    hit_weight = 0.0          # 命中权重和（绝对量，不按查询长度除）
    covered = set()
    per_field_hits = {"title": 0, "category": 0, "tags": 0, "content": 0}

    for tok in uniq:
        best = 0.0
        hit_fields = []
        for fname, weight in FIELD_WEIGHTS:
            freq = field_maps[fname].get(tok)
            if not freq:
                continue
            hit_fields.append(fname)
            # 长 token（长词）更具体，给 1.0~1.6 的加成
            specificity = 1.0 + min(0.6, (len(tok) - 2) * 0.15)
            best = max(best, weight * specificity * (1.0 + 0.35 * math.log1p(freq - 1)))
        if best > 0:
            hit_weight += best
            covered.add(tok)
            for fname in hit_fields:
                per_field_hits[fname] += 1

    if not covered:
        return 0.0, {}

    coverage = len(covered) / len(uniq)
    score = hit_weight * math.sqrt(coverage)

    # 标题覆盖率单独加成：问「三重积分怎么学」时，标题为《三重积分学习路径》应排最前
    title_cov = per_field_hits["title"] / len(uniq)
    score += 6.0 * title_cov

    # 整句精确命中（大小写不敏感）→ 强加成，保住「精确匹配一定最优」
    raw = " ".join(query_tokens)
    phrase = "".join(query_tokens).lower()
    for fname, weight in FIELD_WEIGHTS:
        if fname == "tags":
            text = " ".join(tags)
        else:
            text = item.get(fname) or ""
        if not isinstance(text, str):
            continue
        low = text.lower()
        if raw and raw in low:
            score += 20.0
            break
        # 分类和主题标签常是一个整词。二字切分后再拼回去，避免只因没写进标题就搜不到。
        if fname in ("category", "tags") and phrase and phrase in low.replace(" ", ""):
            score += 20.0
            break

    detail = {"coverage": round(coverage, 3), "hits": per_field_hits,
              "matched": len(covered)}
    return score, detail


def rank(query, items, top_k=5, min_score=1.0, rel_cut=0.15):
    """对一批笔记打分并排序，返回 [(item, score, detail), ...]，分数高在前。

    两级阈值：
      · min_score —— 绝对下限，挡掉「只碰到一两个常见 token」的噪声命中
      · rel_cut   —— 相对下限（相对最高分），避免一个高分结果后面挂一串
                     勉强及格的陪跑项
    """
    qt = tokenize(query)
    if not qt:
        return []
    scored = []
    for it in items:
        s, d = score_item(qt, it)
        if s > 0:
            scored.append((it, s, d))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[1], str(x[0].get("title", ""))))
    top = scored[0][1]
    cutoff = max(min_score, top * rel_cut)
    out = [x for x in scored if x[1] >= cutoff]
    return out[:top_k] if top_k else out


# ---------- 自测 ----------
if __name__ == "__main__":
    NOTES = [
        {"id": 1, "title": "三重积分学习路径", "content": "三重积分需要先掌握二重积分与空间解析几何，重点是直角坐标与柱面坐标的转换。",
         "tags": ["高等数学"]},
        {"id": 2, "title": "为什么课程名会被拦截", "content": "内容安全层会拦截危险词，被拦截时返回 400。",
         "tags": ["使用说明", "内容安全"]},
        {"id": 3, "title": "费曼技巧", "content": "用自己的话复述一遍，发现讲不清的地方就是没懂的地方。",
         "tags": ["学习方法"]},
    ]
    cases = [
        ("什么是三重积分", 1),
        ("三重积分怎么学", 1),
        ("积分积分", 1),
        ("课程名为什么被拦截", 2),
        ("被拦了怎么办", 2),
        ("怎么用费曼技巧", 3),
        ("完全无关的问题天气如何", None),
    ]
    ok = 0
    for q, expect in cases:
        r = rank(q, NOTES, top_k=3)
        top = r[0][0]["id"] if r else None
        flag = "OK  " if top == expect else "FAIL"
        if top == expect:
            ok += 1
        print("%s %-22s -> top=%-4s score=%.2f  期望=%s" % (
            flag, q, top, r[0][1] if r else 0, expect))
        if r:
            print("        候选: %s" % [(x[0]["id"], round(x[1], 2)) for x in r])
    print("\n%d/%d 通过" % (ok, len(cases)))
