"""
main.py — FastAPI 入口
对应 GaussMaster: controllers/core.py

三个路由：
  POST /ask         — RAG 问答（JSON 返回）
  POST /ask/stream  — RAG 问答（SSE 流式输出）
  POST /tool        — Agent 工具调用（两阶段）
"""
import asyncio
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
import uvicorn

from loader import load_markdown_files, split_documents
from embedder import Embedder
from retriever import Retriever
from llm_client import LLMClient
from engine import rag_ask, tool_ask
from memory import ConversationMemory
from tools.db_tools import registry

# ─── 初始化（启动时执行一次）───
print("=" * 60)
print("GaussMaster Demo 启动中...")
print("=" * 60)

embedder = Embedder()
retriever = Retriever(embedder)
llm = LLMClient()
memory = ConversationMemory(max_rounds=3)

# 如果知识库是空的，自动入库
if retriever.collection.count() == 0:
    print("\n知识库为空，自动初始化...")
    docs = load_markdown_files()
    chunks = split_documents(docs)
    retriever.index_documents(chunks)

app = FastAPI(title="GaussMaster Demo", docs_url="/docs")


# ─── 路由 ───

@app.post("/ask")
async def ask(query: str = Query(..., description="用户问题")):
    """RAG 问答 — JSON 返回完整答案"""
    full_answer = ""
    for chunk in rag_ask(query, retriever, llm, memory):
        full_answer += chunk
    memory.add(query, full_answer)
    return {"answer": full_answer}


@app.post("/ask/stream")
async def ask_stream(query: str = Query(..., description="用户问题")):
    """
    RAG 问答 — SSE 流式输出
    对应 GaussMaster 的 text/event-stream
    """
    async def generate():
        for chunk in rag_ask(query, retriever, llm, memory):
            yield chunk
        memory.add(query, "")  # 流式输出完整内容由前端拼接

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )


@app.post("/tool")
async def tool(query: str = Query(..., description="用户问题（工具调用类）")):
    """
    Agent 工具调用 — 两阶段
    对应 GaussMaster 的 intelligent-interaction
    """
    result = await tool_ask(query, llm, registry)
    memory.add(query, result)
    return {"result": result}


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "kb_chunks": retriever.collection.count(),
        "tools": list(registry._tools.keys()),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
