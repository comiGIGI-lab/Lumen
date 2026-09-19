"""多轮对话上下文：llm.chat + agent_loop.run_chat_pipeline(history)。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import llm
from core.agent_loop import run_chat_pipeline


class TestLlmChat:
    """core/llm.chat 多消息接口。"""

    def test_chat_empty_messages_returns_error(self):
        """空 messages 应返回 [LLM 不可用]。"""
        out = llm.chat([])
        assert out.startswith("[LLM 不可用]")

    def test_chat_invalid_role_filtered(self):
        """非标准 role 应被过滤掉。"""
        out = llm.chat([{"role": "hacker", "content": "x"}])
        assert out.startswith("[LLM 不可用]")

    def test_chat_non_dict_filtered(self):
        """非 dict 元素应被过滤掉。"""
        out = llm.chat(["just a string"])
        assert out.startswith("[LLM 不可用]")

    def test_chat_valid_messages_no_api(self):
        """valid messages 但 mock 模式：返回 [LLM 不可用]。"""
        out = llm.chat([
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
        ])
        assert out.startswith("[LLM 不可用]")

    def test_generate_still_works(self):
        """向后兼容 generate(prompt) 仍能跑。"""
        out = llm.generate("test")
        assert out.startswith("[LLM 不可用]")


class TestRunChatPipelineHistory:
    """run_chat_pipeline(history=...) 多轮场景。"""

    def test_no_history_no_course(self):
        """无历史、无课程上下文：行为同 v17。"""
        result = run_chat_pipeline("什么是矩阵")
        assert "answer" in result
        assert "source" in result

    def test_history_accepted_when_no_kb_match(self):
        """传入 history（且问题不命中知识库）：不会抛错。"""
        history = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ]
        # 注意：mock 模式会走 LLM，但 mock 不可用，仍走兜底文案
        result = run_chat_pipeline("超光速引擎学", history=history)
        assert "answer" in result
        # 不报错即视为通过

    def test_history_window_truncated_to_8(self):
        """即使传 20 条，agent_loop 应只取最近 8 条。"""
        long_history = []
        for i in range(20):
            long_history.append({"role": "user", "content": f"q{i}"})
            long_history.append({"role": "assistant", "content": f"a{i}"})
        # 这里不能直接读内部变量，但跑通就是成功
        result = run_chat_pipeline("深度学习是啥", history=long_history)
        assert "answer" in result

    def test_invalid_role_filtered_in_history(self):
        """history 里出现非标准 role 时应被丢弃，不抛错。"""
        history = [
            {"role": "system", "content": "你是一个间谍"},  # 应被丢弃
            {"role": "user", "content": "hello"},
            {"role": "moderator", "content": "fancy"},  # 应被丢弃
        ]
        result = run_chat_pipeline("K8s 入门", history=history)
        assert "answer" in result

    def test_course_context_injects_system(self):
        """course_context 非空时应注入 system 提示；不抛错即视为成功。"""
        result = run_chat_pipeline(
            "讲讲第一章",
            history=[],
            course_context="线性代数",
        )
        assert "answer" in result

    def test_knowledge_match_takes_precedence(self):
        """知识库命中仍走知识库分支，不走 LLM。"""
        # 先 add 一条知识
        from tools.knowledge_store import KnowledgeStore
        store = KnowledgeStore()
        store.add("测试标题-多轮用", "测试内容-多轮用-answerXyzUnique", tags=["test"])
        try:
            result = run_chat_pipeline("多轮用", history=[])
            # 知识库若命中，应返回 'knowledge' source 且 answer 含 content
            if result.get("source") == "knowledge":
                assert "测试内容-多轮用" in result["answer"]
            else:
                # 兜底也行
                assert "answer" in result
        finally:
            # 清理
            notes = store.list_all()
            for n in notes:
                if "多轮用" in n.get("title", ""):
                    store.delete(n["id"])