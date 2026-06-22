"""
memory.py — 简单对话记忆（3轮滑动窗口）
对应 GaussMaster: global_vars.py:SESSION_QA_HISTORY + dao_interaction_memory.py

做了什么：
1. 保存最近 3 轮对话
2. 超过 3 轮自动淘汰最旧的（滑动窗口）
3. 把历史转成 LLM prompt 上下文
"""
class ConversationMemory:
    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
        self.history = []  # [(question, answer), ...]

    def add(self, question: str, answer: str):
        """追加一轮对话，超过上限淘汰最旧的"""
        self.history.append((question, answer))
        while len(self.history) > self.max_rounds:
            popped = self.history.pop(0)  # 淘汰最旧
            print(f"  [memory] 淘汰旧对话: {popped[0][:30]}...")

    def get_context(self) -> str:
        """把历史转成 prompt 上下文"""
        if not self.history:
            return ""
        lines = ["以下是你和用户之前的对话："]
        for q, a in self.history:
            lines.append(f"用户: {q}")
            lines.append(f"你: {a[:200]}")  # 截断长回答，避免 prompt 太长
        return '\n'.join(lines)

    def clear(self):
        """清空记忆"""
        self.history = []
