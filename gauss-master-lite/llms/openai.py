"""
OpenAI 兼容 API 实现
对标 GaussMaster 的 GaussMaster/llms/Pangu.py / Baichuan.py 等
"""

import logging
from openai import AsyncOpenAI

from .base import BaseLLM, LLMConfig


class OpenAILLM(BaseLLM):
    """支持 OpenAI / ollama / vllm / 硅基流动 等所有兼容 OpenAI 协议的服务"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
        )

    async def chat(self, messages: list[dict]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                return ""
            return content.strip()
        except Exception as e:
            logging.error(f"LLM 调用失败: {e}")
            return f"【LLM 调用异常】{e}"
