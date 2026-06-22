"""
llm_client.py — LLM 客户端（DeepSeek）
对应 GaussMaster: server/web/data_transformer.py:generate_answer()

做了什么：
1. 用 OpenAI SDK 封装 DeepSeek API（DeepSeek 和 OpenAI 接口兼容）
2. chat()        普通调用，返回完整回答
3. chat_stream() 流式调用，逐字返回（对应 GaussMaster 的 SSE 流式）
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        print(f"  [llm] 模型: {self.model}")

    def chat(self, prompt: str, system_prompt: str = None) -> str:
        """普通调用，返回完整回答"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            stream=False,
        )
        return response.choices[0].message.content

    def chat_stream(self, prompt: str, system_prompt: str = None):
        """
        流式调用，逐字返回
        对应 GaussMaster 的 SSE 流式输出（text/event-stream）
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            stream=True,
        )
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content


if __name__ == "__main__":
    print("=== 测试 LLM 客户端 ===")
    llm = LLMClient()

    print("\n--- 普通调用 ---")
    result = llm.chat("用一句话介绍 openGauss 数据库")
    print(result)

    print("\n--- 流式调用 ---")
    for chunk in llm.chat_stream("用一句话介绍 openGauss 数据库"):
        print(chunk, end="", flush=True)
    print()
