# GaussMaster Demo — 设计文档

## 一、整体架构

```
┌─────────────────────────────────────────────┐
│               FastAPI 服务                   │
│   ┌─────────────┐  ┌────────────────────┐   │
│   │  POST /ask  │  │   POST /tool       │   │
│   │  (RAG QA)   │  │  (Agent Tool)      │   │
│   └──────┬──────┘  └────────┬───────────┘   │
└──────────┼───────────────────┼───────────────┘
           │                   │
┌──────────┴───────────────────┴───────────────┐
│              核心引擎 (engine.py)             │
│                                              │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │  RAG Pipeline │  │  Agent Pipeline      │ │
│  │              │  │                      │ │
│  │ embed(query) │  │ classify_intent()    │ │
│  │   → retriever│  │   → select_tool()    │ │
│  │   → prompt   │  │   → extract_params() │ │
│  │   → LLM      │  │   → validate_params()│ │
│  │   → stream   │  │   → execute_tool()   │ │
│  │              │  │   → LLM summarize    │ │
│  └──────┬───────┘  └──────────┬───────────┘ │
│         │                     │              │
└─────────┼─────────────────────┼──────────────┘
          │                     │
┌─────────┴─────────┐  ┌───────┴──────────────┐
│   向量数据库       │  │     工具注册表        │
│   (Chroma)        │  │   (ToolRegistry)     │
│                   │  │                      │
│ - 文档块 + 向量   │  │ - get_cpu_usage()    │
│ - 持久化存储      │  │ - get_slow_queries() │
│ - 相似度检索      │  │ - get_connections()  │
└───────────────────┘  └──────────────────────┘
          │                     │
┌─────────┴─────────────────────┴──────────────┐
│              外部服务                         │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Embedding API│  │   LLM API (DeepSeek) │ │
│  │ (BGE-large)  │  │   流式 SSE 输出       │ │
│  └──────────────┘  └──────────────────────┘ │
└──────────────────────────────────────────────┘
```

---

## 二、目录结构

```
gaussmaster-demo/
├── .env                  # API Key 配置
├── main.py               # FastAPI 入口 + 三个路由 + 启动
├── engine.py             # 核心引擎（RAG + Agent 调度）
├── loader.py             # 文档加载与分块
├── embedder.py           # Embedding 服务封装（本地模型）
├── retriever.py          # 向量检索（Chroma）
├── agent.py              # 工具调用 Agent（两阶段）
├── memory.py             # 简单对话记忆（3轮滑动窗口）
├── tools/                # 工具定义
│   ├── __init__.py
│   ├── registry.py       # 工具注册表
│   └── db_tools.py       # 模拟数据库工具
├── data/                 # 知识库文档
│   ├── cpu_tuning.md
│   ├── slow_query.md
│   └── connection_mgmt.md
└── chroma_db/            # Chroma 持久化目录（自动生成）
```

---

## 三、模块详细设计

### 3.1 loader.py — 文档加载与分块

```python
# 伪代码
def load_documents(data_dir: str) -> List[Document]:
    """遍历 data/ 目录，加载所有 .md 文件"""
    docs = []
    for file in glob("data/*.md"):
        text = open(file).read()
        docs.append(Document(text, metadata={"source": file}))
    return docs

def split_documents(docs: List[Document], chunk_size=500, overlap=50) -> List[str]:
    """使用 LangChain RecursiveCharacterTextSplitter 按段落切分"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,      # 对应 GaussMaster 的 PROPER_BLOCK_LENGTH
        chunk_overlap=50,    # 相邻块重叠
        separators=["\n## ", "\n### ", "\n", " "]  # 优先按标题切
    )
    return splitter.split_documents(docs)
```

**与 GaussMaster 的对应关系**：
- `chunk_size=500` ↔ `PROPER_BLOCK_LENGTH = 500`
- `separators` 优先按标题切 ↔ GaussMaster 的标题驱动分块
- LangChain 的分块器自动处理代码块不切割的逻辑

### 3.2 embedder.py — Embedding 服务封装

```python
# 伪代码
class Embedder:
    def __init__(self, model="BAAI/bge-large-zh-v1.5"):
        """使用硅基流动 API 或本地 sentence-transformers"""
        self.model = model
        self.dimension = 1024  # 对应 GaussMaster 的 1024 维

    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        # 方式一：调硅基流动 API（免费额度）
        # 方式二：本地 sentence-transformers 库
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        """单个查询向量化"""
        return self.embed([query])[0]
```

**与 GaussMaster 的对应关系**：
- `dimension = 1024` ↔ `OnlineEmbedding.get_embedding_dimensions() → 1024`
- 独立封装 ↔ GaussMaster 的 HTTP 嵌入服务（这里简化成本地调用）

### 3.3 retriever.py — 向量检索

```python
# 伪代码
class Retriever:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.chroma = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.chroma.get_or_create_collection("gauss_kb")

    def index_documents(self, chunks: List[str], metadatas: List[dict]):
        """文档块向量化 + 存入 Chroma"""
        embeddings = self.embedder.embed(chunks)
        ids = [str(uuid.uuid4()) for _ in chunks]
        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def search(self, query: str, topk=3) -> List[str]:
        """向量检索 Top-K，返回文档文本"""
        query_embedding = self.embedder.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=topk
        )
        return results['documents'][0]
```

**与 GaussMaster 的对应关系**：
- `topk=3` ↔ GaussMaster 的 `vector_topk` 参数
- Chroma 自动建索引 ↔ GSDiskANN 索引
- 简化版没有 BM25 和重排序（Demo 不做）

### 3.4 tools/registry.py — 工具注册表

```python
# 伪代码 — 核心数据结构
class Param:
    """工具参数定义 — 对应 GaussMaster 的 common/plugins/param.py"""
    def __init__(self, name: str, description: str, param_type: str, required: bool = True):
        self.name = name
        self.description = description
        self.type = param_type
        self.required = required

class ToolRegistry:
    """工具注册表 — 对应 GaussMaster 的 common/plugins/registry.py"""
    def __init__(self):
        self._tools = {}  # {tool_name: ToolInfo}

    def register(self, name: str, description: str, params: List[Param]):
        """装饰器，注册工具 — 对应 @base_tools"""
        def decorator(func):
            self._tools[name] = {
                "name": name,
                "description": description,
                "params": params,
                "func": func
            }
            return func
        return decorator

    def get_tools_description(self) -> str:
        """生成工具描述文本 — 对应 detail_str_list（阶段一：选工具）"""
        descs = []
        for tool in self._tools.values():
            param_strs = [f"{p.name}({p.type},{'必填' if p.required else '可选'})" for p in tool["params"]]
            descs.append(f"{tool['name']}: {tool['description']}，参数：{', '.join(param_strs)}")
        return '\n'.join(descs)

    def get_tool_schema(self, tool_name: str) -> str:
        """获取单个工具的详细 schema — 对应 detail_with_param_str（阶段二：填参数）"""
        tool = self._tools[tool_name]
        param_strs = [f"- {p.name}({p.type}){'[必填]' if p.required else '[可选]'}: {p.description}" for p in tool["params"]]
        return f"{tool['name']}: {tool['description']}\n" + '\n'.join(param_strs)

    def validate_params(self, tool_name: str, params: dict) -> tuple[bool, dict, dict]:
        """参数校验 — 对应 has_correct_params() + inspect.signature"""
        tool = self._tools[tool_name]
        # 多给参数 → 丢弃
        valid_params = {k: v for k, v in params.items() if k in [p.name for p in tool["params"]]}
        # 缺参数 → 提示
        missing = [p.name for p in tool["params"] if p.required and p.name not in params]
        if missing:
            return False, valid_params, missing
        return True, valid_params, {}

    def execute(self, tool_name: str, params: dict):
        """执行工具 — 对应 call_tool()"""
        return self._tools[tool_name]["func"](**params)
```

### 3.5 tools/db_tools.py — 模拟数据库工具

```python
# 伪代码 — 注册 3 个模拟工具

registry = ToolRegistry()

@registry.register(
    name="get_cpu_usage",
    description="获取指定数据库实例当前的 CPU 使用率",
    params=[Param("instance", "数据库实例名称，如 db_001", "str", required=True)]
)
def get_cpu_usage(instance: str) -> dict:
    """模拟：返回当前 CPU 使用率"""
    # 真实场景下调 DBMind API，这里返回模拟数据
    return {
        "instance": instance,
        "cpu_percent": 78.5,
        "timestamp": "2025-01-01 12:00:00"
    }

@registry.register(
    name="get_slow_queries",
    description="获取当前正在执行的慢 SQL 列表",
    params=[Param("limit", "返回条数上限", "int", required=False)]
)
def get_slow_queries(limit: int = 5) -> list:
    """模拟：返回慢 SQL 列表"""
    return [
        {"sql": "SELECT * FROM orders WHERE ...", "duration_sec": 12.3, "calls": 150},
        {"sql": "UPDATE users SET ... WHERE ...", "duration_sec": 8.7, "calls": 89},
    ][:limit]

@registry.register(
    name="get_connections",
    description="获取当前数据库的连接数信息",
    params=[]  # 无参数工具
)
def get_connections() -> dict:
    """模拟：返回连接数"""
    return {"total": 120, "active": 45, "idle": 75}
```

**与 GaussMaster 的对应关系**：
- `@registry.register` ↔ `@base_tools`
- `Param(name, type, required)` ↔ GaussMaster 的 `Param` 类
- `validate_params()` ↔ `has_correct_params()` + `inspect.signature`
- `get_connections` 无参数 ↔ GaussMaster 的无参数工具快捷路径

### 3.6 agent.py — 两阶段工具调用

```python
# 伪代码 — 核心逻辑
async def agent_pipeline(query: str, llm_client, registry: ToolRegistry):
    """
    两阶段工具调用 — 对应 GaussMaster 的 interact_with_tool()
    
    阶段一：选工具
      把工具列表给 LLM → LLM 选一个工具名
    阶段二：填参数
      把工具详细 schema 给 LLM → LLM 提取参数 → 校验 → 执行
    """
    
    # ═══ 阶段一：工具选择 ═══
    tools_desc = registry.get_tools_description()
    stage1_prompt = f"""你是一个数据库运维助手。以下是可以使用的工具列表：
{tools_desc}

用户问题：{query}

请只输出一个最合适的工具名，不要输出其他内容。"""
    
    stage1_response = await llm_client.chat(stage1_prompt)
    tool_name = stage1_response.strip()
    
    # 校验工具是否存在 — 对应 check_has_valid_tool()
    if tool_name not in registry._tools:
        return {"error": f"无法识别工具: {tool_name}"}
    
    # ═══ 阶段二：参数提取 ═══
    tool_schema = registry.get_tool_schema(tool_name)
    
    # 无参数工具快捷路径 — 对应 check_is_no_param_tool()
    if len(registry._tools[tool_name]["params"]) == 0:
        result = registry.execute(tool_name, {})
        return {"tool": tool_name, "result": result}
    
    stage2_prompt = f"""根据用户问题提取工具参数：
{tool_schema}

用户问题：{query}

请以 JSON 格式输出参数，例如：{{"instance": "db_001", "limit": 5}}"""
    
    stage2_response = await llm_client.chat(stage2_prompt)
    params = json.loads(stage2_response)
    
    # 参数校验 — 对应 verify_arguments() + inspect.signature
    valid, correct_params, missing = registry.validate_params(tool_name, params)
    if not valid:
        return {"error": f"缺少必填参数: {missing}"}
    
    # 执行工具
    result = registry.execute(tool_name, correct_params)
    
    # LLM 总结结果
    summarize_prompt = f"""工具 {tool_name} 返回了以下结果：{json.dumps(result, ensure_ascii=False)}
请用自然语言总结这个结果。"""
    summary = await llm_client.chat(summarize_prompt)
    
    return {"tool": tool_name, "result": result, "summary": summary}
```

### 3.7 engine.py — 核心引擎（意图路由）

```python
# 伪代码
async def process_query(query: str, retriever: Retriever, registry: ToolRegistry, llm_client):
    """
    意图路由 — 判断走 RAG 问答还是 Agent 工具
    简化版：用关键词判断（生产版 GaussMaster 用 LLM 分类）
    """
    
    # 简单意图识别：包含"查"/"获取"/"当前"关键词 → 工具模式
    tool_keywords = ["查", "获取", "当前", "帮我看", "多少", "占用了"]
    is_tool_query = any(kw in query for kw in tool_keywords)
    
    if is_tool_query:
        # Agent 工具调用路径
        return await agent_pipeline(query, llm_client, registry)
    else:
        # RAG 问答路径
        docs = retriever.search(query, topk=3)
        if not docs:
            return {"answer": "未找到相关知识，请换个问法试试。"}
        
        context = "\n\n".join(docs)
        prompt = f"""你是一个数据库运维专家。请根据以下参考资料回答用户问题。
如果参考资料无法回答，请如实说明。

参考资料：
{context}

用户问题：{query}"""
        
        answer = await llm_client.chat_stream(prompt)  # 流式输出
        return {"answer": answer, "sources": docs}
```

### 3.8 memory.py — 简单对话记忆（对应 SESSION_QA_HISTORY）

```python
# 伪代码 — 极简版滑动窗口，对应 GaussMaster 的 SESSION_QA_HISTORY
class ConversationMemory:
    def __init__(self, max_rounds=3):
        self.max_rounds = max_rounds
        self.history = []   # [(question, answer), ...]

    def add(self, question: str, answer: str):
        """追加一轮对话"""
        self.history.append((question, answer))
        while len(self.history) > self.max_rounds:
            self.history.pop(0)    # 滑动窗口淘汰最旧的

    def get_context(self) -> str:
        """把历史转成 prompt 上下文"""
        if not self.history:
            return ""
        lines = ["以下是你和用户之前的对话："]
        for q, a in self.history:
            lines.append(f"用户: {q}")
            lines.append(f"你: {a}")
        return '\n'.join(lines)
```

**与 GaussMaster 的对应关系**：
- `max_rounds=3` ↔ `history_len=3`
- `self.history.pop(0)` ↔ `add_to_local_memory` 的滑动窗口淘汰
- 简化：纯内存，不持久化 ↔ GaussMaster 内存+MetaDatabase 双写

### 3.9 main.py — FastAPI 入口（对应 controllers/core.py）

```python
# 伪代码
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
import uvicorn
import asyncio

app = FastAPI(title="GaussMaster Demo")

# 初始化组件（启动时执行一次）
embedder = Embedder()
retriever = Retriever(embedder)
registry = create_tools()
memory = ConversationMemory(max_rounds=3)


@app.post("/ask")
async def ask(query: str = Query(...)):
    """RAG 问答 — 普通返回，展示完整检索链路"""
    docs = retriever.search(query, topk=3)
    
    # 多轮上下文
    history_context = memory.get_context()
    
    prompt = f"""{history_context}
你是 GaussDB 数据库运维专家。参考以下资料回答问题。
资料：{'\\n'.join(docs)}
用户问题：{query}"""
    
    answer = await llm_client.chat(prompt)
    memory.add(query, answer)
    
    return {"answer": answer, "sources": docs}


@app.post("/ask/stream")
async def ask_stream(query: str = Query(...)):
    """RAG 问答 — SSE 流式输出（对应 GaussMaster 的 text/event-stream）"""
    docs = retriever.search(query, topk=3)
    history_context = memory.get_context()
    prompt = f"{history_context}\n参考资料：{'\\n'.join(docs)}\n用户问题：{query}"
    
    async def generate():
        async for chunk in llm_client.chat_stream(prompt):
            yield chunk
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@app.post("/tool")
async def tool(query: str = Query(...)):
    """Agent 工具调用 — 两阶段（对应 GaussMaster 的 intelligent-interaction）"""
    result = await agent_pipeline(query, llm_client, registry)
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 四、数据流图

### RAG 问答流程

```
用户输入 "CPU 使用率过高怎么办"
  │
  ▼
embedder.embed_query() → 1024 维向量
  │
  ▼
retriever.search(topk=3) → Chroma 相似度检索
  │
  ▼
拼接 prompt = "你是数据库专家...\n参考资料：[检索到的3个文档块]\n用户问题：..."
  │
  ▼
llm_client.chat_stream(prompt) → SSE 流式输出
  │
  ▼
FastAPI SSE 流式返回（text/event-stream）
```

### Agent 工具调用流程

```
用户输入 "查一下 db_001 的 CPU 使用率"
  │
  ▼
意图路由 → 识别为工具调用
  │
  ├─ 阶段一：选工具
  │    prompt = "可用工具：[get_cpu_usage, get_slow_queries, get_connections]\n用户问题：..."
  │    LLM → "get_cpu_usage"
  │    ↓
  ├─ 校验：registry._tools 里有 get_cpu_usage ✓
  │    ↓
  ├─ 阶段二：填参数
  │    prompt = "get_cpu_usage 需要参数：instance(str,必填)\n用户问题：..."
  │    LLM → '{"instance": "db_001"}'
  │    ↓
  ├─ validate_params("get_cpu_usage", {"instance": "db_001"})
  │    instance 已满足 ✓
  │    ↓
  ├─ registry.execute("get_cpu_usage", {"instance": "db_001"})
  │    返回 {"cpu_percent": 78.5, ...}
  │    ↓
  └─ LLM 总结 → "db_001 当前 CPU 使用率为 78.5%，处于较高水平。"
```

---

## 五、依赖清单

```
pip install fastapi uvicorn chromadb langchain langchain-text-splitters openai sentence-transformers python-dotenv
```

| 包 | 用途 |
|----|------|
| fastapi + uvicorn | Web 框架 + ASGI 服务器 |
| chromadb | 本地向量数据库 |
| langchain + langchain-text-splitters | 文档分块 |
| openai | DeepSeek SDK（兼容 OpenAI 格式） |
| sentence-transformers | BGE-large 本地 embedding |
| python-dotenv | .env 配置读取 |

---

## 六、与 GaussMaster 源码的对应关系

| Demo 模块 | GaussMaster 源码文件 | Demo 的简化 |
|---------|---------------------|------------|
| `loader.py` | `utils/split_util_md.py` + `utils/doc_util.py` | 用 LangChain 分块器代替自研 776 行分块代码 |
| `embedder.py` | `utils/retriever_util.py:OnlineEmbedding` | 本地模型代替 HTTP 服务 |
| `retriever.py` | `utils/retriever_util.py:BaseRetriever` + `gaussdb_vector.py:GaussDB` | Chroma 代替 openGauss+GSDiskANN |
| `tools/registry.py` | `common/plugins/registry.py` + `common/plugins/param.py` | 核心逻辑完全一致，简化了角色权限 |
| `tools/db_tools.py` | `multiagents/tools/dbmind_interface.py` | 3 个模拟工具代替 21 个真实工具 |
| `agent.py` | `llms/executor.py` + `multiagents/agents/dba.py` | 核心两阶段逻辑完全一致 |
| `engine.py` | `server/web/data_transformer.py` | 简化了 HyDE/查询改写降级策略 |
| `memory.py` | `global_vars.py:SESSION_QA_HISTORY` + `dao_interaction_memory.py` | 纯内存 3 轮滑动窗口，不持久化 |
| `main.py` | `controllers/core.py` + `ui/` | FastAPI 三个路由代替完整的 Web 层 |

---

## 七、开发顺序（建议）

| 顺序 | 模块 | 预计时间 | 产出 |
|------|------|---------|------|
| 1 | `loader.py` + `embedder.py` + `retriever.py` | 2 小时 | 能加载文档、向量化、检索到结果 |
| 2 | RAG 问答（engine.py 的 RAG 部分） | 1 小时 | 能输入问题，LLM 基于检索结果回答 |
| 3 | `tools/registry.py` + `tools/db_tools.py` | 1.5 小时 | 3 个模拟工具注册完毕 |
| 4 | `agent.py` 两阶段工具调用 | 2 小时 | 能选工具、填参数、执行、总结 |
| 5 | `engine.py` 意图路由 + `memory.py` 对话记忆 | 0.5 小时 | RAG 和 Agent 自动切换 + 3 轮滑动窗口 |
| 6 | `main.py` FastAPI 路由 + SSE 流式 | 1 小时 | 三个路由可 curl 调用 |
| **总计** | | **约 8 小时** | 完整可演示的 Demo |

---

## 八、面试讲解要点

> 做完 Demo 后，面试打开 IDE 讲代码时，每个模块对应一个话题。

| 打开哪个文件 | 面试可以讲什么 | 背什么数字/概念 |
|------------|--------------|---------------|
| `loader.py` | 文档分块策略，为什么用 500 字，LangChain 的分块器怎么优先按标题切 | `chunk_size=500`、`overlap=50`、标题驱动的层次化分块 |
| `embedder.py` | BGE-large 选型原因，1024 维 vs 768 维，本地模型 vs HTTP 服务的区别 | `BAAI/bge-large-zh-v1.5`、`1024维`、独立封装 |
| `retriever.py` | 向量检索流程，Chroma 自动建索引，GaussMaster 用 GSDiskANN 的区别 | `topk=3`、`<->` L2距离、Chroma vs openGauss |
| `tools/registry.py` | 自研 Registry 的原因，参数校验为什么用 inspect 而非 prompt | `Param(name, type, required)`、`validate_params()`、确定性校验 |
| `agent.py` | 两阶段工具调用的核心设计，63维→21+3维的数学直觉 | 阶段一选工具、阶段二填参数、准确率 60%→95% |
| `memory.py` | 滑动窗口淘汰，3 轮上限的设计原因 | `max_rounds=3`、`pop(0)`淘汰、上下文窗口有限 |
| `main.py` | FastAPI + SSE 流式输出，和 GaussMaster 一样用的是 `text/event-stream` | `StreamingResponse`、`keep-alive`、`no-cache`、`uvicorn` |

**每个模块讲 2 分钟，7 个模块 = 14 分钟，刚好是面试中"项目深挖"的标准时长。**
