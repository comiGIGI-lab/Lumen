# test_eval.py — 20 道固定题测正确率

"""Eval 测试：20 道固定题（10 道 plan 类、10 道 chat 类），断言答对 ≥16 道。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core.intent import parse_intent

# 20 道测试题：(输入, 期望意图)
TEST_CASES = [
    # 10 道 plan 类
    ("机器学习学习计划", "plan"),
    ("帮我制定 Python 学习方案", "plan"),
    ("数据结构课程大纲", "plan"),
    ("Java", "plan"),
    ("机器学习", "plan"),
    ("深度学习学习路线", "plan"),
    ("计算机网络怎么学", "plan"),
    ("操作系统如何学", "plan"),
    ("数据库", "plan"),
    ("算法学习计划", "plan"),
    # 10 道 chat 类
    ("什么是监督学习", "chat"),
    ("为什么需要归一化", "chat"),
    ("线性回归和逻辑回归的区别", "chat"),
    ("梯度下降怎么理解？", "chat"),
    ("什么是过拟合", "chat"),
    ("CNN和RNN有什么区别", "chat"),
    ("什么是反向传播", "chat"),
    ("为什么要用激活函数", "chat"),
    ("决策树怎么理解呢", "chat"),
    ("什么是梯度消失", "chat"),
]


class TestEval:
    """20 道 Eval 测试。"""

    def test_accuracy(self):
        """正确率 ≥ 80%（≥16/20）。
        v18 适配：parse_intent 返回 dict {"type": "generate"|"chat", "course": ...}，
        断言前先把 type 归一化到 "plan"/"chat"。"""
        correct = 0
        failures = []
        for text, expected in TEST_CASES:
            result = parse_intent(text)
            # v18：dict 返回，type=='generate' 即对应 plan
            t = result.get("type") if isinstance(result, dict) else result
            actual = "plan" if t == "generate" else "chat"
            if actual == expected:
                correct += 1
            else:
                failures.append(f'"{text}" → 期望 {expected}, 实际 {actual}（{result}）')

        # 打印详情
        print(f"\nEval 正确率：{correct}/20 = {correct / 20 * 100:.0f}%")
        if failures:
            print("错误用例：")
            for f in failures:
                print(f"  {f}")

        assert correct >= 16, f"正确率不足 80%：{correct}/20，失败：{failures}"

    def test_all_cases_covered(self):
        """确保 20 道题都在。"""
        assert len(TEST_CASES) == 20

    def test_plan_cases(self):
        """10 道 plan 类题目。"""
        plan_cases = [t for t, e in TEST_CASES if e == "plan"]
        assert len(plan_cases) == 10

    def test_chat_cases(self):
        """10 道 chat 类题目。"""
        chat_cases = [t for t, e in TEST_CASES if e == "chat"]
        assert len(chat_cases) == 10
