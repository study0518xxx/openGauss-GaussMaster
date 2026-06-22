"""
GaussMaster Lite - FastAPI 入口
对标 GaussMaster 的 startup.py + controllers/core.py
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# 确保能从项目根目录 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llms import create_llm, BaseLLM
from core.memory import MemoryManager
from core.agent import AgentOrchestrator
from core.rag import RAGEngine
from tools import tool_registry
from knowledge import loader
from knowledge.vector_store import kb_store as knowledge_base_store


# ── 全局变量 ──
config: dict = {}
llm: BaseLLM = None
memory_mgr: MemoryManager = None
agent: AgentOrchestrator = None
rag: RAGEngine = None


# ── 请求模型 ──

class ChatRequest(BaseModel):
    question: str
    user_id: str = "default"
    session_id: str = "default"
    mode: str = "auto"  # "auto" | "rag" | "agent"


# ── 启动 / 关闭 ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, llm, memory_mgr, agent, rag

    # 加载配置
    config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.yaml"))
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logging.info("配置加载完成")

    # 初始化 LLM
    llm_config = config.get("llm", {})
    llm = create_llm(llm_config)
    logging.info(f"LLM 初始化完成: {llm_config.get('model', 'unknown')}")

    # 初始化记忆管理器
    max_history = config.get("agent", {}).get("max_history", 5)
    memory_mgr = MemoryManager()
    logging.info("记忆管理器初始化完成")

    # 初始化 Agent
    agent = AgentOrchestrator(llm=llm, tool_registry=tool_registry, memory_mgr=memory_mgr)
    logging.info(f"Agent 初始化完成，已注册 {len(tool_registry.all_tools())} 个工具")

    # 初始化嵌入模型（如果配置了 sentence-transformers）
    embedder = _init_embedder(config.get("embedding", {}))

    # 加载知识库
    loader.load_builtin_knowledge(embedding_fn=embedder)
    logging.info(f"知识库加载完成，共 {knowledge_base_store.count()} 条文档")

    # 初始化 RAG
    kb_config = config.get("knowledge_base", {})
    rag = RAGEngine(
        llm=llm,
        embedder=embedder,
        memory_mgr=memory_mgr,
        top_k=kb_config.get("top_k", 5),
        similarity_threshold=kb_config.get("similarity_threshold", 0.3),
    )
    logging.info("RAG 引擎初始化完成")

    yield

    logging.info("服务关闭")


def _init_embedder(embedding_config: dict):
    """初始化嵌入模型"""
    if not embedding_config.get("model_name"):
        return None

    model_name = embedding_config["model_name"]
    device = embedding_config.get("device", "cpu")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name, device=device)
        logging.info(f"嵌入模型加载完成: {model_name} on {device}")

        def embed_fn(text: str):
            return model.encode(text)

        return embed_fn
    except Exception as e:
        logging.warning(f"嵌入模型加载失败，将使用关键词检索: {e}")
        return None


# ── FastAPI 应用 ──

app = FastAPI(
    title="GaussMaster Lite",
    description="数据库智能运维 Copilot (简化版)",
    version="1.0.0",
    lifespan=lifespan,
)


# ── API 路由 ──

@app.get("/")
async def root():
    return {
        "service": "GaussMaster Lite",
        "version": "1.0.0",
        "tools_count": len(tool_registry.all_tools()),
        "doc_count": knowledge_base_store.count(),
    }


@app.get("/tools")
async def list_tools():
    """列出所有可用工具"""
    tools = {}
    for name, func in tool_registry.all_tools().items():
        tools[name] = {
            "description": func.__tool_description__,
            "params": func.__tool_params__,
        }
    return {"tools": tools}


@app.get("/health")
async def health():
    return {"status": "ok", "llm_configured": llm is not None}


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    统一聊天接口
    
    支持三种模式:
    - auto: 自动判断走 RAG 还是 Agent
    - rag: 强制走知识库问答
    - agent: 强制走工具调用
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 简单的模式判断
    mode = req.mode
    if mode == "auto":
        # Agent 工具关键词
        agent_keywords = ["状态", "运行", "慢 SQL", "慢查询", "锁", "磁盘", "连接数",
                          "正在执行", "查询", "告警", "性能", "诊断"]
        if any(kw in req.question for kw in agent_keywords):
            mode = "agent"
        else:
            mode = "rag"

    if mode == "rag":
        return await _handle_rag(req)
    elif mode == "agent":
        return await _handle_agent(req)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的 mode: {mode}")


async def _handle_rag(req: ChatRequest) -> dict:
    """处理 RAG 问答"""
    result_content = ""
    source_docs = []
    async for step in rag.ask(
        question=req.question,
        user_id=req.user_id,
        session_id=req.session_id,
    ):
        if step["type"] == "result":
            result_content = step["content"]
            source_docs = step.get("source_docs", [])
    return {
        "mode": "rag",
        "answer": result_content,
        "source_count": len(source_docs),
    }


async def _handle_agent(req: ChatRequest) -> dict:
    """处理 Agent 工具调用"""
    result_content = ""
    tool_used = None
    async for step in agent.execute(
        question=req.question,
        user_id=req.user_id,
        session_id=req.session_id,
    ):
        if step["type"] == "result":
            result_content = step["content"]
            tool_used = step.get("tool_name")
    return {
        "mode": "agent",
        "answer": result_content,
        "tool_used": tool_used,
    }


# ── 启动入口 ──

if __name__ == "__main__":
    import uvicorn

    # 启动前先加载配置用于端口绑定
    _cfg_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.yaml"))
    _bootstrap_config = {}
    if os.path.exists(_cfg_path):
        with open(_cfg_path, "r", encoding="utf-8") as _f:
            _bootstrap_config = yaml.safe_load(_f) or {}

    _host = _bootstrap_config.get("server", {}).get("host", "0.0.0.0")
    _port = _bootstrap_config.get("server", {}).get("port", 8000)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s %(levelname)s] %(message)s",
    )

    uvicorn.run(app, host=_host, port=_port)
