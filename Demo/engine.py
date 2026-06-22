"""
engine.py — 核心引擎（RAG 问答 + Agent 工具调用 + 意图路由 + 对话记忆）
对应 GaussMaster: server/web/data_transformer.py + multiagents/agents/dba.py

完整功能：
1. rag_ask()      — RAG 问答管道（检索 → prompt → LLM 流式）
2. tool_ask()     — Agent 工具调用（两阶段 → 执行 → LLM 总结）
3. process_query()— 意图路由：判断走 RAG 还是 Agent + 对话记忆
"""
import asyncio
from loader import load_markdown_files, split_documents
from embedder import Embedder
from retriever import Retriever
from llm_client import LLMClient
from agent import agent_pipeline
from memory import ConversationMemory


SYSTEM_PROMPT = """你是一个 GaussDB 数据库运维专家。请根据提供的参考资料回答用户问题。
规则：
1. 如果参考资料能回答，就基于参考资料回答，不要编造
2. 如果参考资料不能回答，或者用户问题与数据库运维无关，就如实说"参考资料中没有相关信息"
3. 回答要专业、简洁、有结构化（分点、表格等）
4. 涉及具体 SQL 或参数时，尽量引用参考资料中的原文"""

# 相关性阈值：所有检索结果的余弦距离都高于此值 → 判定为"不相关"
# 距离越小越相关（0=完全一样，1=完全不相关）
RELEVANCE_THRESHOLD = 0.5


def is_domain_related(query: str) -> bool:
    """判断问题是否与数据库运维领域相关（快速关键词过滤）"""
    return any(kw in query for kw in DOMAIN_KEYWORDS)


def rag_ask(query: str, retriever: Retriever, llm: LLMClient, memory: ConversationMemory = None, topk: int = 3):
    """
    RAG 问答管道 — 对应 GaussMaster 的 ask_gauss()
    """
    # ═══ 检索 ═══
    print(f"\n  [engine:RAG] 检索中: topk={topk}")
    docs, distances = retriever.search(query, topk=topk, return_distances=True)

    if not docs:
        yield "未找到相关知识，请换个问法试试。"
        return

    # ═══ 第一层防护：距离阈值 ═══
    # 不管问什么，Chroma 都会返回 Top-K。但距离暴露了相关性。
    # "今天天气怎么样" → 和库里 CPU/慢SQL 文档完全不搭 → 距离 > 0.6
    # "CPU 使用率过高" → 和 CPU 文档高度匹配 → 距离 ≈ 0.3
    best_distance = distances[0] if distances else 1.0
    print(f"  [engine:RAG] 最佳距离: {best_distance:.4f} (阈值: {RELEVANCE_THRESHOLD})")

    if best_distance > RELEVANCE_THRESHOLD:
        print(f"  [engine:RAG] 检索结果相关性不足，拒答")
        yield "抱歉，知识库中没有与您问题相关的资料。请确认问题是否在 GaussDB 数据库运维范围内，或尝试换个问法。"
        return

    # ═══ 第二层防护：LLM 自己判断（system_prompt 约束）════
    history_context = memory.get_context() if memory else ""

    context = "\n\n---\n\n".join(docs)
    prompt = f"""{history_context}
参考资料：
{context}

用户问题：{query}

请判断参考资料是否与用户问题相关。如果相关，基于参考资料回答。如果不相关，请如实说明"参考资料与问题不匹配"。

请回答："""

    print(f"  [engine:RAG] prompt 长度: {len(prompt)} 字")
    for chunk in llm.chat_stream(prompt, system_prompt=SYSTEM_PROMPT):
        yield chunk


async def tool_ask(query: str, llm: LLMClient, registry):
    """Agent 工具调用 — 对应 GaussMaster 的 intelligent-interaction"""
    result = await agent_pipeline(query, llm, registry)
    if "error" in result:
        return f"[错误] {result['error']}"
    return result.get("summary", str(result))


def process_query(query: str, retriever: Retriever, llm: LLMClient,
                  registry=None, memory: ConversationMemory = None) -> str:
    """意图路由 + 对话记忆"""
    tool_keywords = ["查一下", "获取", "当前", "多少", "占用了", "帮我看", "连接"]

    # Agent 工具路径
    if any(kw in query for kw in tool_keywords) and registry:
        print(f"\n  [engine:Agent] 用户问题: {query}")
        result = asyncio.run(tool_ask(query, llm, registry))
        if memory:
            memory.add(query, result)
        return result

    # RAG 问答路径
    full_answer = ""
    for chunk in rag_ask(query, retriever, llm, memory):
        full_answer += chunk
    if memory:
        memory.add(query, full_answer)
    return full_answer


if __name__ == "__main__":
    from tools.db_tools import registry

    print("=== 测试完整引擎（RAG + Agent + 记忆）===\n")

    print("--- 初始化 ---")
    embedder = Embedder()
    retriever = Retriever(embedder)
    llm = LLMClient()
    memory = ConversationMemory(max_rounds=3)

    if retriever.collection.count() == 0:
        docs = load_markdown_files()
        chunks = split_documents(docs)
        retriever.index_documents(chunks)

    # 测试 RAG
    q1 = "CPU 使用率过高怎么办"
    print(f"\n--- RAG: {q1} ---")
    a1 = process_query(q1, retriever, llm, memory=memory)
    print(f"\n回答: {a1[:300]}...")

    # 测试多轮记忆
    q2 = "那慢 SQL 呢"
    print(f"\n--- RAG(多轮): {q2} ---")
    a2 = process_query(q2, retriever, llm, memory=memory)
    print(f"\n回答: {a2[:300]}...")

    # 测试 Agent
    q3 = "查一下 db_001 的 CPU 使用率"
    print(f"\n--- Agent: {q3} ---")
    a3 = process_query(q3, retriever, llm, registry=registry, memory=memory)
    print(f"\n回答: {a3[:300]}...")

    # 测试距离阈值防护
    q5 = "今天天气怎么样"
    print(f"\n--- RAG(不相关): {q5} ---")
    print("回答: ", end="")
    full = ""
    for chunk in rag_ask(q5, retriever, llm, memory):
        full += chunk
        print(chunk, end="", flush=True)
    print()
