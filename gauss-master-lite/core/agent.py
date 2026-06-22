"""
Agent 编排引擎 —— 工具调用流程的核心
对标 GaussMaster 的 multiagents/agents/dba.py 的 interact_with_tool()
"""

import json
import logging
from typing import AsyncGenerator, Optional

from core.memory import MemoryManager, QARecord
from core.registry import ToolRegistry
from llms.base import BaseLLM
from prompts.agent import (
    TOOL_MATCH_SYSTEM_PROMPT_ZH,
    PARAM_EXTRACT_SYSTEM_ZH,
    TOOL_RESULT_FORMAT_ZH,
)


class AgentOrchestrator:
    """
    Agent 编排器
    
    流程:
    1. 检查是否有未完成的工具意图（多轮参数收集）
    2. LLM 匹配工具
    3. LLM 提取参数
    4. 校验参数完整性
    5. 调用工具
    6. LLM 格式化输出结果
    """

    def __init__(
        self,
        llm: BaseLLM,
        tool_registry: ToolRegistry,
        memory_mgr: MemoryManager,
    ):
        self.llm = llm
        self.tools = tool_registry
        self.memory_mgr = memory_mgr

    async def execute(
        self,
        question: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> AsyncGenerator[dict, None]:
        """
        执行 Agent 流程，逐步 yield 输出
        yield 格式: {"type": "progress"|"result"|"error", "content": ...}
        """
        session = self.memory_mgr.get_session(user_id, session_id)

        # ── Step 1: 检查是否有未完成的工具意图 ──
        pending_tool = session.get_pending_tool()

        if pending_tool:
            # 有未完成的意图 → 尝试提取参数
            yield {"type": "progress", "content": "检测到未完成的工具调用，正在提取参数..."}
            async for step in self._extract_and_call(question, pending_tool, session):
                yield step
            return

        # ── Step 2: 匹配工具 ──
        yield {"type": "progress", "content": "正在分析问题，匹配数据库运维工具..."}
        matched_tool = await self._match_tool(question)

        if matched_tool is None:
            # 没有匹配的工具 → 无法处理
            msg = "抱歉，您的问题无法通过当前的数据库诊断工具回答。请尝试更具体的问题，例如：'查一下数据库状态'、'有没有慢 SQL'。"
            session.add_record(QARecord(question=question, answer=msg))
            yield {"type": "result", "content": msg}
            return

        # ── Step 3: 检查工具是否需要参数 ──
        tool_func = self.tools.get(matched_tool)
        required_params = [p for p in tool_func.__tool_params__ if p["required"]]

        if not required_params:
            # 无参工具 → 直接调用
            yield {"type": "progress", "content": f"正在调用工具: {matched_tool}..."}
            async for step in self._call_and_format(matched_tool, {}, question, session):
                yield step
            return

        # ── Step 4: 需要参数 → 尝试从问题中提取 ──
        yield {"type": "progress", "content": f"需要提取工具 {matched_tool} 的参数..."}

        # 先把工具记入 session，以便后续补充参数
        session.set_pending_tool(matched_tool)

        async for step in self._extract_and_call(question, matched_tool, session):
            yield step

    async def _match_tool(self, question: str) -> Optional[str]:
        """LLM 匹配工具"""
        tool_descriptions = "\n".join(self.tools.list_details())

        prompt = TOOL_MATCH_SYSTEM_PROMPT_ZH.format(tool_descriptions=tool_descriptions)

        result = await self.llm.chat_with_tool(system_prompt=prompt, user_prompt=question)

        result = result.strip()

        # 检查是否是有效的工具名
        if result == "无匹配工具":
            return None

        if self.tools.get(result) is not None:
            return result

        return None

    async def _extract_and_call(
        self,
        question: str,
        tool_name: str,
        session,
    ) -> AsyncGenerator[dict, None]:
        """尝试提取参数并调用工具"""
        tool_func = self.tools.get(tool_name)
        tool_detail = self.tools.get_detail(tool_name)

        # 构建参数提取 prompt
        prompt = PARAM_EXTRACT_SYSTEM_ZH.format(
            tool_name=tool_name,
            tool_description=tool_detail,
        )

        # 把对话历史作为 user prompt 的上下文
        context = session.build_context()
        user_prompt = f"历史对话:\n{context}\n\n当前用户问题: {question}"

        result = await self.llm.chat_with_tool(system_prompt=prompt, user_prompt=user_prompt)

        # 解析结果
        try:
            # 尝试解析 JSON
            params = json.loads(result)

            if params.get("missing"):
                # 参数不完整 → 让用户补充
                missing_params = params.get("required_params", [])
                msg = f"工具 {tool_name} 需要以下参数: {', '.join(missing_params)}。请提供完整信息。"
                # 保持 pending_tool 状态，下次继续
                yield {"type": "result", "content": msg}
                return

            # 参数完整 → 校验并调用
            is_complete, valid_params, missing = self.tools.validate_params(tool_name, params)

            if not is_complete and missing:
                missing_names = list(missing.keys())
                msg = f"参数不完整，缺少: {', '.join(missing_names)}。请补充。"
                # pending_tool 保持
                yield {"type": "result", "content": msg}
                return

            # 调用工具
            session.set_pending_tool(None)  # 清除 pending
            yield {"type": "progress", "content": f"正在调用工具: {tool_name}..."}
            async for step in self._call_and_format(tool_name, valid_params, question, session):
                yield step

        except json.JSONDecodeError:
            # LLM 返回的不是 JSON → 可能是直接回复
            msg = f"参数提取异常，请重新描述您的问题。LLM 返回: {result}"
            yield {"type": "error", "content": msg}

    async def _call_and_format(
        self,
        tool_name: str,
        params: dict,
        question: str,
        session,
    ) -> AsyncGenerator[dict, None]:
        """调用工具并用 LLM 格式化结果"""
        tool_func = self.tools.get(tool_name)

        try:
            # 执行工具
            tool_result = tool_func(**params)
        except Exception as e:
            logging.exception(f"工具 {tool_name} 调用失败")
            msg = f"工具 {tool_name} 调用失败: {e}"
            session.add_record(QARecord(question=question, answer=msg, tool_name=tool_name))
            yield {"type": "error", "content": msg}
            return

        # 用 LLM 格式化结果
        format_prompt = TOOL_RESULT_FORMAT_ZH.format(
            tool_name=tool_name,
            tool_result=json.dumps(tool_result, ensure_ascii=False, indent=2),
        )

        formatted_answer = await self.llm.chat_with_tool(
            system_prompt="你是一个数据库运维助手。",
            user_prompt=format_prompt,
        )

        # 保存到记忆
        session.add_record(QARecord(
            question=question,
            answer=formatted_answer,
            tool_name=tool_name,
            tool_params=params,
        ))

        yield {
            "type": "result",
            "content": formatted_answer,
            "tool_name": tool_name,
            "raw_result": tool_result,
        }
