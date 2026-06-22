# 第四步：对话记忆 + FastAPI 完整服务

## 做了什么

1. 加了 `memory.py`（3 轮滑动窗口对话记忆）
2. 更新 `engine.py`，Agent 占位符替换为真实的 `agent_pipeline`
3. 创建 `main.py`，FastAPI 三个路由 + SSE 流式输出

## 新增/修改的文件

| 文件 | 作用 | 对应 GaussMaster 源码 |
|------|------|---------------------|
| `memory.py` | 3 轮滑动窗口对话记忆 | `global_vars.py:SESSION_QA_HISTORY` |
| `engine.py`（更新） | 集成 Agent + 记忆 | `data_transformer.py` |
| `main.py` | FastAPI 入口 + 路由 + SSE | `controllers/core.py` |

## memory.py 详解

```python
class ConversationMemory:
    max_rounds = 3          # 最多记 3 轮，和 GaussMaster 的 history_len=3 一样
    history = []             # [(question, answer), ...]

    def add(q, a):
        history.append((q, a))        # 追加
        while len > 3: history.pop(0) # 淘汰最旧 → 滑动窗口

    def get_context():
        # 把 [("CPU高怎么办","建议1..."), ("那慢SQL呢","建议2...")]
        # 转成 "用户: CPU高怎么办\n你: 建议1...\n用户: 那慢SQL呢..."
        # 拼到 LLM prompt 前面
```

**和 GaussMaster 的对应**：
- `max_rounds=3` ↔ `history_len=3`
- `pop(0)` ↔ `add_to_local_memory` 的滑动窗口淘汰
- 纯内存不持久化 ↔ GaussMaster 内存 + MetaDatabase 双写（Demo 简化）

## main.py 详解

### 三个路由

| 路由 | 方法 | 做什么 | 对应 GaussMaster |
|------|------|--------|-----------------|
| `/ask` | POST | RAG 问答，JSON 返回 | `ask_gauss` |
| `/ask/stream` | POST | RAG 问答，SSE 流式 | `ask_gauss` 的 SSE |
| `/tool` | POST | Agent 工具调用 | `intelligent-interaction` |
| `/health` | GET | 健康检查 | — |

### SSE 流式输出怎么写

```python
@app.post("/ask/stream")
async def ask_stream(query: str):
    async def generate():
        for chunk in rag_ask(query, ...):
            yield chunk   # 逐字 yield

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",   # ← 和 GaussMaster 源码一样
        headers={
            "Cache-Control": "no-cache",   # ← 和 GaussMaster 一样
            "Connection": "keep-alive",    # ← 和 GaussMaster 一样
        }
    )
```

这三个 headers 和 GaussMaster 源码 `data_transformer.py:423` 完全一致。

## 完整架构回顾

```
main.py (FastAPI)
├─ POST /ask          → rag_ask()          → retriever.search() → LLM 流式
├─ POST /ask/stream   → rag_ask() + SSE    → 同上 + text/event-stream
├─ POST /tool         → tool_ask()         → agent_pipeline()  → 两阶段调用
└─ GET  /health       → 健康检查

engine.py
├─ rag_ask()          RAG 问答管道（检索→prompt→LLM）
├─ tool_ask()         Agent 工具调用（调用 agent_pipeline）
└─ process_query()    意图路由（关键词判断 RAG 还是 Agent）

memory.py → ConversationMemory → 3轮滑动窗口 → 注入 prompt
```

## 怎么跑

```powershell
cd C:\2026\0703ddl\openGauss-GaussMaster\Demo

# 启动服务
python main.py

# 另一个终端测试
curl -X POST "http://localhost:8000/ask?query=CPU使用率过高怎么办"

# 流式输出
curl -X POST "http://localhost:8000/ask/stream?query=CPU使用率过高怎么办"

# 工具调用
curl -X POST "http://localhost:8000/tool?query=查一下db_001的CPU使用率"

# 健康检查
curl http://localhost:8000/health

# 或者浏览器打开 http://localhost:8000/docs 用 Swagger 界面
```

## 面试能讲什么

- "FastAPI + SSE 流式输出，headers 和 GaussMaster 源码一致"
- "对话记忆用 3 轮滑动窗口，pop(0) 自动淘汰，和 GaussMaster 的 add_to_local_memory 一样"
- "三个路由覆盖了 RAG 问答和 Agent 工具调用两种场景"
- "引擎集成后 RAG 和 Agent 共用同一套记忆，无缝切换"

---

## 补充：答非所问防护

> 问题：Chroma 永远返回 Top-3，即使问"今天天气怎么样"也会凑 3 个不相关的文档块。

### 两层防护

```
用户问题
  │
  ├─ 第一层：距离阈值过滤
  │     RELEVANCE_THRESHOLD = 0.5
  │     检索到的最佳距离 > 0.5 → 判定为"不相关" → 拒绝
  │     "今天天气怎么样" → 和库里 CPU 文档不搭 → 距离 > 0.6 → 拦截
  │     "CPU 使用率过高" → 和 CPU 文档匹配 → 距离 ≈ 0.3 → 放行
  │
  └─ 第二层：LLM 自己判断（system_prompt 约束）
       prompt 里明确要求"先判断参考资料是否相关"
       第一层漏了（边界情况），LLM 自己说"参考资料与问题不匹配"
```

**为什么不用关键词过滤**：无关问题千千万，关键词列不完。"推荐一首歌"能拦，"讲个笑话"怎么办？距离阈值不依赖词表，它是数学判断——两个向量在 1024 维空间里离得远就是远，跟词表没关系。

### 源码改动

**retriever.py**：`search()` 新增 `return_distances=True` 参数。

**engine.py**：
```python
RELEVANCE_THRESHOLD = 0.5

def rag_ask(...):
    docs, distances = retriever.search(query, return_distances=True)
    
    if distances[0] > RELEVANCE_THRESHOLD:  # 第一层
        yield "知识库中没有相关资料..."
        return
    
    # 第二层：prompt 要求 LLM 先判断相关性
    prompt = "请判断参考资料是否与用户问题相关..."
```

### 和 GaussMaster 的对应

GaussMaster 用 DFA + XLNet 做安全检测。Demo 用距离阈值简化，核心思路一样：**在检索结果进 LLM 之前先过滤掉明显不相关的。**
