"""
直接对话界面 - 输入问题就能问
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import yaml
from llms import create_llm
from core.memory import MemoryManager
from core.agent import AgentOrchestrator
from core.rag import RAGEngine
from tools import tool_registry
from knowledge.loader import load_builtin_knowledge

# 加载配置
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# 初始化
llm = create_llm(config["llm"])
memory_mgr = MemoryManager()
agent = AgentOrchestrator(llm=llm, tool_registry=tool_registry, memory_mgr=memory_mgr)
rag = RAGEngine(llm=llm, memory_mgr=memory_mgr, top_k=5, similarity_threshold=0.3)

load_builtin_knowledge()

print("=" * 50)
print("  GaussMaster Lite - 数据库运维助手")
print("=" * 50)
print("  输入问题即可，自动判断走 Agent 还是 RAG")
print("  输入 quit/exit 退出")
print("=" * 50)

# 关键词判断走哪个模式
agent_keywords = ["状态", "运行", "慢sql", "慢SQL", "慢查询", "锁", "磁盘", "连接", "查询", "告警", "性能", "诊断", "表大小"]

async def run():
    while True:
        try:
            question = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break

        # 判断模式
        mode = "agent" if any(kw in question for kw in agent_keywords) else "rag"
        print(f"\n[模式: {mode}]")

        if mode == "agent":
            async for step in agent.execute(question):
                if step["type"] == "progress":
                    print(f"  ...{step['content']}")
                elif step["type"] == "result":
                    print(f"\n助手: {step['content']}")
        else:
            async for step in rag.ask(question):
                if step["type"] == "progress":
                    print(f"  ...{step['content']}")
                elif step["type"] == "result":
                    print(f"\n助手: {step['content']}")

import asyncio
asyncio.run(run())
print("\n再见！")
