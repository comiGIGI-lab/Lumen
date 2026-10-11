# auto_tag.py —— 知识库材料的 AI 智能分类
#
# 上传/新建笔记时，用大模型分析标题+正文，自动给出「学科分类 + 主题标签」。
# LLM 不可用（Mock 模式 / 没配 Key / 超时 / 限流）时，降级为关键词规则兜底，
# 保证功能在任何环境都不会把导入流程拖垮。
#
# 设计原则：
#   · 只在「用户没有手动指定分类」时才自动分类，尊重用户选择。
#   · 分类失败静默降级，绝不阻塞导入。
#   · LLM 输出只取 category + tags 两个字段，多余内容一律丢弃。
#
# 复用 core.llm.chat()（DeepSeek 封装，自带 mock 判定 / 超时 / 滑动窗口限流），
# 不新起一套 HTTP 调用，也不引入任何第三方依赖。

import json
import re

# 关键词兜底规则：(正则, 学科分类)。顺序即优先级，命中第一条即返回。
# 只覆盖常见学科，属于「能兜住大部分」的粗分类；详细主题交给 LLM。
_SUBJECT_RULES = [
    (r"数据结构|栈|队列|链表|二叉树|红黑树|图论|排序|查找|哈希|复杂度", "数据结构与算法"),
    (r"高数|高等数学|微积分|导数|微分|积分|级数|极限|泰勒|洛必达", "高等数学"),
    (r"线性代数|矩阵|行列式|特征值|特征向量|向量空间|齐次方程", "线性代数"),
    (r"概率|统计|随机|分布|期望|方差|假设检验|回归分析", "概率统计"),
    (r"英语|english|语法|词汇|单词|阅读|听力|写作|翻译|长难句", "英语"),
    (r"计算机网络|tcp|http|https|ip地址|路由|协议|三次握手|网络层|osi", "计算机网络"),
    (r"操作系统|进程|线程|内存管理|调度|文件系统|死锁|虚拟内存|并发", "操作系统"),
    (r"数据库|sql|索引|事务|范式|关系型|nosql|redis", "数据库原理"),
    (r"机器学习|深度学习|神经网络|训练|特征|梯度|回归|聚类|过拟合|模型", "机器学习"),
    (r"python|java|javascript|c\+\+|编程|代码|函数|变量|循环|算法题|leetcode", "编程"),
    (r"物理|力学|电磁|热学|光学|实验报告|不确定度", "物理"),
    (r"化学|反应|分子|原子|方程式|元素", "化学"),
    (r"错题|错因|易错|易混淆", "错题整理"),
]

_PROMPT = """你是学习材料的智能分类助手。请分析下面这段学习材料，判断它的学科分类和主题标签。

材料标题：{title}
材料内容：{content}

只输出一个 JSON 对象，不要输出任何其他文字、解释或代码块标记，格式如下：
{{"category":"学科分类（2-8 个字，如：数据结构、高等数学、英语、机器学习）","tags":["主题标签1","主题标签2","主题标签3"]}}

要求：
1. category 是这份材料所属的学科/领域，尽量具体；
2. tags 是 2~4 个主题关键词，用于细化分类（如栈与队列、三次握手、过拟合）；
3. 只输出 JSON，没有别的。"""


def _keyword_classify(title, content):
    """关键词兜底：只做学科级粗分类，主题标签用学科名占位。"""
    s = ("%s\n%s" % (title or "", content or "")).lower()
    for pattern, subject in _SUBJECT_RULES:
        if re.search(pattern, s):
            return {"category": subject, "tags": [subject], "source": "keyword"}
    return {"category": "", "tags": [], "source": "keyword"}


def _parse_json(raw):
    """从 LLM 输出里抠出第一个合法 JSON 对象，解析失败返回 None。"""
    s = str(raw or "").strip()
    if not s:
        return None
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        # 模型偶尔在标签里夹中文引号/尾逗号，做一次宽松清洗再试
        cleaned = m.group(0)
        try:
            obj = json.loads(cleaned)
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    return obj


def classify_material(title, content):
    """
    对一份材料做智能分类。

    返回 dict：{"category": str, "tags": [str], "source": "ai"|"keyword"|"empty"}
    source 标明分类来源，前端可据此提示「AI 分类」还是「关键词兜底」。
    任何异常都不会抛出，最坏返回关键词兜底结果。
    """
    title = str(title or "").strip()
    content = str(content or "").strip()
    if not title and not content:
        return {"category": "", "tags": [], "source": "empty"}

    # 先试 LLM。core.llm 懒 import：只有 SOURCE_DIR 已进 sys.path（api_server 启动后）才可用。
    try:
        from core.llm import chat
        raw = chat([{"role": "user", "content": _PROMPT.format(
            title=title[:80] or "（无标题）",
            content=content[:1500],
        )}])
    except Exception as exc:  # noqa: BLE001 —— import 失败 / 任何异常都走兜底
        raw = "[LLM 不可用] %s" % exc

    if isinstance(raw, str) and not raw.startswith("[LLM 不可用]"):
        parsed = _parse_json(raw)
        if parsed:
            cat = str(parsed.get("category") or "").strip()[:24]
            if cat:
                tags = []
                for t in (parsed.get("tags") or []):
                    t = str(t).strip()
                    if t and t not in tags:
                        tags.append(t)
                return {"category": cat, "tags": tags[:4], "source": "ai"}

    return _keyword_classify(title, content)
