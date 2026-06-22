from .base import BaseLLM, LLMConfig
from .openai import OpenAILLM


def create_llm(config: dict) -> BaseLLM:
    """LLM 工厂方法"""
    llm_config = LLMConfig(
        api_type=config.get("api_type", "openai"),
        api_base=config.get("api_base", ""),
        api_key=config.get("api_key", ""),
        model=config.get("model", "gpt-4o-mini"),
        temperature=config.get("temperature", 0.7),
        max_tokens=config.get("max_tokens", 2048),
    )

    if llm_config.api_type == "openai":
        return OpenAILLM(llm_config)
    raise ValueError(f"不支持的 LLM 类型: {llm_config.api_type}")
