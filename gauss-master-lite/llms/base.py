"""
LLM 抽象基类
对标 GaussMaster 的 GaussMaster/llms/executor.py + llms/base/
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    api_type: str = "openai"
    api_base: str = ""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048


class BaseLLM(ABC):
    """LLM 抽象基类"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """
        同步聊天接口
        messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        返回: 模型回复文本
        """
        ...

    async def chat_with_tool(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """简易聊天封装"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.chat(messages)
