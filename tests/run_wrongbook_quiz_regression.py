# -*- coding: utf-8 -*-
"""错题本 × 闯关题型适配回归。

契约（本切片定义，见 openspec/changes/2026-10-11-wrongbook-quiz-types/spec.md）：

    出题侧三种题型答案编码互不相同（见 server/quiz.py 的 _norm_answer_*）：
        single -> ["A"]      multi -> ["A","C"]（已排序）      judge -> int 0/1
    错题本侧 **不新增存储字段**（vendor/tools/wrong_book_store.py 的 add_item 是
    封闭契约，多余入参直接丢弃，且本仓库约定 vendor 零改动），因此：

        source  = "quiz"                    标记来源（该字段本来就有）
        tags    含 "题型:多选"               承载题型（可检索）
        question 渲染为 "[多选] 题干\\nA. .."  人类可读
        qtype   由服务端从 tags 派生、挂在响应上返回，前端只读不做拼接

    API：POST /api/wrongbook/from-quiz（结构化入错题本）
         GET  /api/wrongbook 支持 source / type 过滤
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(REPO_ROOT, "server")
WEB_DIR = os.path.join(REPO_ROOT, "web")
SRC_DIR = os.path.join(WEB_DIR, "src")
# vendor 是套件package：wrong_book_store 走 tools.*，它内部 import core.paths
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor", "study-liu")

sys.path.insert(0, SERVER_DIR)
sys.path.insert(0, VENDOR_DIR)

FAIL = []
SKIP = []
PASSED = []


def check(name, ok, extra=""):
    if ok:
        PASSED.append(name)
        print("  ok  %s" % name)
    else:
        FAIL.append("%s  %s" % (name, extra))
        print("  !!  %s  %s" % (name, extra))


def skip(name, why=""):
    SKIP.append(name)
    print("  --  %s  %s" % (name, why))


def hr(title):
    print("")
    print("=" * 62)
    print(title)
    print("=" * 62)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ============================================================
# 一、源检查：接线是否到位
# ============================================================
def test_source_wiring():
    hr("一、源检查")

    import re
    wbq = read(os.path.join(SERVER_DIR, "wrongbook_quiz.py"))
    api = read(os.path.join(SERVER_DIR, "api_server.py"))
    panel = read(os.path.join(SRC_DIR, "components", "QuizPanel.vue"))
    wbpage = read(os.path.join(SRC_DIR, "components", "WrongBookPage.vue"))
    client = read(os.path.join(SRC_DIR, "api", "client.js"))
    zh = read(os.path.join(SRC_DIR, "i18n", "auto-zh.json"))
    en = read(os.path.join(SRC_DIR, "i18n", "auto-en.json"))

    check("wbq_module_exists", bool(wbq.strip()), "server/wrongbook_quiz.py 不存在")
    # 纯转换：一个 import 都不许有。一旦有人在里面 import store，这套 runtime
    # 回归就再也跑不快了（会碰磁盘），而且会把 vendor 契约拖进解析层。
    check("wbq_has_no_imports",
          re.search(r"^\s*(import|from)\s+\S", wbq, re.M) is None,
          "wrongbook_quiz 必须保持零 import 的纯函数模块")
    check("api_has_from_quiz_route",
          '/api/wrongbook/from-quiz' in api,
          "缺少 POST /api/wrongbook/from-quiz 路由")
    check("api_list_supports_filters",
          'query.get("source")' in api and 'query.get("type")' in api,
          "列表接口需支持 source / type 过滤")
    # qtype 不落库，必须每次读的时候从 tags 现解出来再挂到响应上
    check("api_returns_derived_qtype",
          "wrongbook_quiz_mod.parse_qtype" in api and '"qtype"' in api,
          "响应应派生 qtype 字段给前端（且必须由 parse_qtype 从 tags 解出）")
    check("client_has_wrongBookAddFromQuiz",
          "wrongBookAddFromQuiz" in client,
          "client.js 缺 wrongBookAddFromQuiz")
    check("panel_uses_from_quiz",
          "wrongBookAddFromQuiz" in panel,
          "QuizPanel 应改为回传结构化题目")
    # 老 bug：多选只取 sel[0] 的文本，导致 C 的选项文字丢失
    check("panel_multi_first_only_bug_gone",
          re.search(r"Array\.isArray\(sel\)\s*\?\s*sel\[0\]\s*:", panel) is None,
          "多选只渲染首个选项文本的旧写法仍在")
    check("wbpage_shows_badges",
          "it.qtype" in wbpage and "it.source" in wbpage,
          "错题本页应渲染题型/来源徽标")
    check("wbpage_has_filters",
          "sourceFilter" in wbpage and "typeFilter" in wbpage,
          "错题本页应有来源/题型筛选")
    # i18n：auto-* 是平铺的点号 key（如 wrongBookQuiz.single），三个检查各管一段：
    #  1) 命名空间在不在   2) 中英 key 是否一致   3) 页面用到的 key 是否都声明过
    zh_keys = set(re.findall(r'"(wrongBookQuiz\.[A-Za-z]+)"', zh))
    en_keys = set(re.findall(r'"(wrongBookQuiz\.[A-Za-z]+)"', en))
    for tag, keys in (("zh", zh_keys), ("en", en_keys)):
        check("i18n_%s_has_namespace" % tag, len(keys) >= 4,
              "i18n %s 缺 wrongBookQuiz 命名空间" % tag)
    check("i18n_key_parity", zh_keys and zh_keys == en_keys,
          "中英 wrongBookQuiz key 不一致：zh=%d en=%d" % (len(zh_keys), len(en_keys)))
    used = set(re.findall(r"wrongBookQuiz\.[A-Za-z]+", wbpage))
    missing = sorted(used - zh_keys)
    check("wbpage_i18n_keys_declared", not missing,
          "页面用了没声明的 key：%s" % missing)


# ============================================================
# 二、runtime：题型 → 错题本字段
# ============================================================
def test_runtime():
    hr("二、runtime")
    try:
        import wrongbook_quiz as wbq
    except Exception as e:
        check("wbq_importable", False, str(e))
        return

    check("wbq_importable", True)

    SINGLE = {"type": "single", "stem": "Python 里哪个结构可变？",
              "options": [{"key": "A", "text": "元组"}, {"key": "B", "text": "列表"},
                          {"key": "C", "text": "字符串"}, {"key": "D", "text": "整数"}]}
    MULTI = {"type": "multi", "stem": "哪些是可迭代对象？",
             "options": [{"key": "A", "text": "列表"}, {"key": "B", "text": "字典"},
                         {"key": "C", "text": "生成器"}, {"key": "D", "text": "整数"}]}
    JUDGE = {"type": "judge", "stem": "Python 列表是可变的。",
             "options": [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}]}

    # ---- 题型归一化 ----
    check("qtype_normalize_unknown",
          wbq.normalize_qtype("weird") == "single",
          "未知题型应回退 single")
    check("qtype_label_multi",
          wbq.qtype_label("multi") == "多选",
          wbq.qtype_label("multi"))

    # ---- 答案格式化：三种编码各走各的路 ----
    check("fmt_single",
          wbq.human_answer(["A"], "single", SINGLE["options"]) == "A. 元组",
          wbq.human_answer(["A"], "single", SINGLE["options"]))
    multi_txt = wbq.human_answer(["A", "C"], "multi", MULTI["options"])
    check("fmt_multi_lists_every_selected",
          "列表" in multi_txt and "生成器" in multi_txt,
          "多选必须把所有选中项文字都带上，实际：%s" % multi_txt)
    check("fmt_multi_keys",
          "A" in multi_txt and "C" in multi_txt, multi_txt)
    check("fmt_judge_true",
          wbq.human_answer(0, "judge", JUDGE["options"]) == "正确",
          wbq.human_answer(0, "judge", JUDGE["options"]))
    check("fmt_judge_false",
          wbq.human_answer(1, "judge", JUDGE["options"]) == "错误",
          wbq.human_answer(1, "judge", JUDGE["options"]))

    # ---- 建条目 ----
    built = wbq.build_quiz_wrong(
        course="Python 入门", question=MULTI,
        selected=["B"], answer=["A", "C"],
        explanation="字典和生成器都可迭代。", knowledge_point="迭代协议")
    check("built_source_is_quiz", built["source"] == "quiz", built.get("source"))
    check("built_question_has_type_label",
          built["question"].startswith("[多选]"),
          built["question"][:30])
    check("built_question_lists_options",
          all(o["text"] in built["question"] for o in MULTI["options"]),
          "题干区应列出所有选项")
    check("built_reason_carries_kp",
          "迭代协议" in built["reason"], built["reason"])
    check("built_tags_has_type_tag",
          wbq.TYPE_TAG_PREFIX + "多选" in built["tags"],
          str(built["tags"]))

    # ---- 往返：从 tags 还原题型 ----
    back = wbq.parse_qtype({"tags": built["tags"]})
    check("roundtrip_qtype", back == "multi", str(back))
    check("parse_qtype_manual_none",
          wbq.parse_qtype({"tags": ["语法", "闯关"]}) is None,
          "手工错题不应解出题型")
    check("is_quiz_item_true", wbq.is_quiz_item({"source": "quiz"}) is True)
    check("is_quiz_item_false", wbq.is_quiz_item({"source": "manual"}) is False)

    # ---- 超长裁剪 ----
    long_q = dict(MULTI)
    long_q["options"] = [{"key": k, "text": "字" * 5000} for k in "ABCD"]
    long_built = wbq.build_quiz_wrong(course="X", question=long_q,
                                      selected=["A"], answer=["B", "C"],
                                      explanation="e", knowledge_point="k")
    check("long_question_clipped",
          len(long_built["question"]) <= wbq.MAX_QUESTION,
          "%d > %d" % (len(long_built["question"]), wbq.MAX_QUESTION))

    # ---- 落盘往返（真 wrong_book_store，临时 data 目录）----
    try:
        import tempfile
        import core.paths as paths_mod
        tmp = tempfile.mkdtemp(prefix="wbq-")
        os.environ["STUDY_LIU_DATA_DIR"] = tmp
        paths_mod.reset_cache()
        # 必须在 wrong_book_store 之前设好 env：它在 import 时就锁死了 _FILE
        from tools import wrong_book_store as wbs
        item = wbs.add_item("cid-test", **built)
        check("store_accepts_built_fields", item is not None, "add_item 拒绝了")
        if item:
            check("store_persists_source", item.get("source") == "quiz",
                  item.get("source"))
            check("store_roundtrip_qtype",
                  wbq.parse_qtype(item) == "multi", str(wbq.parse_qtype(item)))
            check("store_keeps_type_tag",
                  (wbq.TYPE_TAG_PREFIX + "多选") in (item.get("tags") or []),
                  str(item.get("tags")))
    except Exception as e:
        check("store_roundtrip", False, str(e))


# ============================================================
# 三、结论
# ============================================================
def main():
    test_source_wiring()
    test_runtime()
    hr("结论")
    if FAIL:
        for f in FAIL:
            print("  !! " + f)
        print("")
        print("      结果：%d 项失败，先修再提交 ❌" % len(FAIL))
    else:
        print("      结果：全部通过，可以提交 ✅")
    print("")
    print("%d passed, %d failed, %d skipped" % (len(PASSED), len(FAIL), len(SKIP)))
    # 同上：Windows GBK 控制台打不出 ✅/❌，这里统一切成 UTF-8
    sys.exit(1 if FAIL else 0)


# 与 run_crisis_regression.py 保持一致的 UTF-8 兜底（Windows 控制台默认 GBK，
# U+2705/U+274C 编不出来会让「断言全绿」的进程变成 rc=1 的假红）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if __name__ == "__main__":
    main()
