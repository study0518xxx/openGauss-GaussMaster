"""
会话记忆管理
对标 GaussMaster 的 SESSION_QA_HISTORY + SESSION_TOOL_HISTORY + metadatabase 持久化
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class QARecord:
    """单条问答记录"""
    question: str
    answer: str
    tool_name: Optional[str] = None
    tool_params: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SessionMemory:
    """
    单会话记忆管理
    
    功能:
    1. 存储问答历史 (SESSION_QA_HISTORY)
    2. 跟踪未完成的工具意图 (SESSION_TOOL_HISTORY)
    3. 多轮对话上下文构建
    """

    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self.history: list[QARecord] = []
        self.pending_tool: Optional[str] = None  # 未完成的工具意图

    def add_record(self, record: QARecord):
        """添加问答记录，超出 max_history 自动裁剪"""
        self.history.append(record)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def set_pending_tool(self, tool_name: Optional[str]):
        """设置/清除未完成的工具意图"""
        self.pending_tool = tool_name

    def get_pending_tool(self) -> Optional[str]:
        return self.pending_tool

    def build_context(self) -> str:
        """构建多轮对话上下文字符串（给 LLM prompt 用）"""
        if not self.history:
            return ""
        lines = []
        for i, record in enumerate(self.history, 1):
            lines.append(f"[第{i}轮]")
            lines.append(f"  用户: {record.question}")
            lines.append(f"  助手: {record.answer}")
            if record.tool_name:
                lines.append(f"  调用工具: {record.tool_name}")
        return "\n".join(lines)

    def clear(self):
        self.history.clear()
        self.pending_tool = None


class MemoryManager:
    """全局记忆管理器（对标 global_vars.SESSION_QA_HISTORY）"""

    def __init__(self):
        # {user_id: {session_id: SessionMemory}}
        self._sessions: dict[str, dict[str, SessionMemory]] = {}

    def get_session(self, user_id: str, session_id: str, max_history: int = 5) -> SessionMemory:
        if user_id not in self._sessions:
            self._sessions[user_id] = {}
        if session_id not in self._sessions[user_id]:
            self._sessions[user_id][session_id] = SessionMemory(max_history)
        return self._sessions[user_id][session_id]
