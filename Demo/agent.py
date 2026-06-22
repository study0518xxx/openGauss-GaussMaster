"""
agent.py — 两阶段工具调用 Agent
对应 GaussMaster: llms/executor.py + multiagents/agents/dba.py

核心设计（和 GaussMaster 完全一致）：
1. 阶段一：LLM 从工具列表里选一个名字
2. 阶段二：LLM 根据工具 schema 填参数
3. 参数校验：多余丢弃，缺失提示（模拟 inspect.signature）
4. 执行 + LLM 总结

准确率优化的关键：21个工具×3个参数=63维搜索 → 拆成 21维+3维
"""
import json
from llm_client import LLMClient
from tools.registry import ToolRegistry


async def agent_pipeline(query: str, llm: LLMClient, registry: ToolRegistry) -> dict:
    """
    两阶段工具调用 — 对应 GaussMaster 的 interact_with_tool()
    
    返回: {"tool": 工具名, "params": 参数, "result": 工具返回, "summary": LLM总结}
    """
    print(f"\n  [agent] 用户问题: {query}")

    # ═══════════════ 阶段一：工具选择 ═══════════════
    print("  [agent] === 阶段一：工具选择 ===")
    tools_desc = registry.get_tools_desc()
    print(f"  [agent] 可用工具:\n{tools_desc}")

    stage1_prompt = f"""你是一个数据库运维专家。以下是你可以使用的工具列表：
{tools_desc}

用户问题：{query}

请判断应该使用哪个工具来处理用户的问题。
只输出工具名称，不要输出其他任何内容。"""

    tool_name = llm.chat(stage1_prompt).strip()
    print(f"  [agent] LLM 选择: {tool_name}")

    # 校验工具是否存在 — 对应 check_has_valid_tool()
    if tool_name not in registry._tools:
        return {"error": f"无法识别的工具: {tool_name}，可用工具: {list(registry._tools.keys())}"}

    # ═══════════════ 阶段二：参数提取 ═══════════════
    print(f"  [agent] === 阶段二：参数提取 ===")

    # 无参数工具快捷路径 — 对应 check_is_no_param_tool()
    if registry.is_no_param(tool_name):
        print(f"  [agent] 无参数工具，直接执行")
        result = registry.execute(tool_name, {})
        summary = llm.chat(
            f"工具 {tool_name} 返回了以下结果：\n{json.dumps(result, ensure_ascii=False)}\n\n请用自然语言总结这个结果。"
        )
        return {"tool": tool_name, "params": {}, "result": result, "summary": summary}

    # 有参数 → 提取参数
    tool_schema = registry.get_tool_schema(tool_name)
    print(f"  [agent] 工具 schema:\n{tool_schema}")

    stage2_prompt = f"""根据用户问题提取工具参数。

{tool_schema}

用户问题：{query}

请以 JSON 格式输出参数值。只输出 JSON，不要输出其他内容。
示例：{{"instance": "db_001"}} 或 {{"limit": 5}}"""

    params_str = llm.chat(stage2_prompt).strip()
    # 清理 LLM 可能多输出的 ```json 标记
    params_str = params_str.replace("```json", "").replace("```", "").strip()
    print(f"  [agent] LLM 输出参数: {params_str}")

    try:
        params = json.loads(params_str)
    except json.JSONDecodeError:
        return {"error": f"参数解析失败，LLM 输出不是有效 JSON: {params_str}"}

    # 参数校验 — 对应 verify_arguments() + inspect.signature
    print(f"  [agent] === 参数校验 ===")
    valid, correct_params, missing = registry.validate_params(tool_name, params)
    print(f"  [agent] 校验结果: 通过={valid}, 清洗后={correct_params}, 缺失={missing}")

    if not valid:
        return {
            "error": f"缺少必填参数: {missing}",
            "tool": tool_name,
            "provided_params": params
        }

    # 执行工具 — 对应 call_tool()
    print(f"  [agent] === 执行工具 ===")
    result = registry.execute(tool_name, correct_params)
    print(f"  [agent] 工具返回: {json.dumps(result, ensure_ascii=False)[:200]}...")

    # LLM 总结结果
    print(f"  [agent] === LLM 总结 ===")
    summary = llm.chat(
        f"你是数据库运维专家。工具 {tool_name} 返回了以下结果：\n"
        f"{json.dumps(result, ensure_ascii=False, indent=2)}\n\n"
        f"请用自然语言总结这个结果，给出建议。"
    )

    return {
        "tool": tool_name,
        "params": correct_params,
        "result": result,
        "summary": summary
    }


if __name__ == "__main__":
    import asyncio

    async def test():
        from llm_client import LLMClient
        from tools.db_tools import registry

        llm = LLMClient()

        print("=" * 60)
        print("测试1: 有参数工具 — CPU 使用率")
        print("=" * 60)
        r = await agent_pipeline("查一下 db_001 的 CPU 使用率", llm, registry)
        print(f"\n结果: {r.get('summary', r.get('error'))}")

        print("\n" + "=" * 60)
        print("测试2: 无参数工具 — 连接数（快捷路径）")
        print("=" * 60)
        r = await agent_pipeline("当前数据库有多少连接", llm, registry)
        print(f"\n结果: {r.get('summary', r.get('error'))}")

        print("\n" + "=" * 60)
        print("测试3: 模糊问题 — 应该选慢 SQL")
        print("=" * 60)
        r = await agent_pipeline("帮我查一下有哪些慢查询", llm, registry)
        print(f"\n结果: {r.get('summary', r.get('error'))}")

    asyncio.run(test())
