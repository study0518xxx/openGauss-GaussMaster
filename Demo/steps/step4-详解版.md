# 第四步详解：对话记忆 + FastAPI 服务 + 答非所问防护

> 面向小白，逐行解释做了什么、为什么这么做。

---

## 一、新建 memory.py — 让系统记住之前聊了什么

### 问题

之前每一步都是"失忆"的——你问完"CPU 怎么排查"，再问"那慢 SQL 呢"，系统不知道"那"指的是什么。

### 解决

加一个 `ConversationMemory` 类，记最近 3 轮对话。

```python
class ConversationMemory:
    def __init__(self, max_rounds=3):   # 最多记 3 轮
        self.history = []                # 存对话的列表

    def add(self, question, answer):
        """记一轮对话"""
        self.history.append((question, answer))  # 往列表后面加
        while len(self.history) > 3:             # 超过 3 条？
            self.history.pop(0)                  # 删掉最旧的那条

    def get_context(self):
        """把历史对话转成一段文字，拼到 prompt 前面"""
        # [(q1,a1), (q2,a2)] → "用户: q1\n你: a1\n用户: q2\n你: a2"
```

### 举例

```
第1轮: "CPU 使用率过高怎么办" → 记下
第2轮: "那慢 SQL 呢"          → 记下
第3轮: "连接数呢"              → 记下
第4轮: "怎么优化"              → 记下，但超过 3 条，删掉第1轮

现在 history = [第2轮, 第3轮, 第4轮]
```

第4轮问"怎么优化"时，prompt 前面会自动拼上：

```
以下是你和用户之前的对话：
用户: 那慢 SQL 呢
你: 慢 SQL 优化建议...
用户: 连接数呢
你: 当前连接数正常...
用户: 怎么优化
你: （待生成）
```

LLM 看到这个就知道"怎么优化"指的是前面讨论的慢 SQL 和连接数，不会答非所问。

---

## 二、改造 engine.py — 把 Agent 和记忆接进来

### 改前

```python
def process_query(query, ...):
    if is_tool_query:
        return "[Agent] 工具调用功能将在第三步实现"  # ← 占位符
    else:
        return rag_ask(query, ...)
```

### 改后

```python
async def tool_ask(query, llm, registry):
    """调 agent.py 的 agent_pipeline，真正执行工具调用"""
    result = await agent_pipeline(query, llm, registry)
    return result["summary"]

def process_query(query, ..., registry, memory):
    if is_tool_query and registry:
        result = tool_ask(query, ...)     # ← 真的调了！
        memory.add(query, result)          # ← 记下来
        return result
    else:
        answer = rag_ask(query, ..., memory)  # ← RAG 也接上记忆
        memory.add(query, answer)             # ← 记下来
        return answer
```

**核心变化**：Agent 路径不再是假占位符了，真的调 `agent_pipeline`。RAG 和 Agent 路径都接上了记忆。

---

## 三、改造 retriever.py — 检索时返回距离

### 改前

```python
def search(self, query, topk=3):
    ...
    return docs  # 只返回文档文本
```

### 改后

```python
def search(self, query, topk=3, return_distances=False):
    ...
    if return_distances:
        return docs, distances  # 同时返回文本和距离
    return docs
```

多了一个开关参数 `return_distances`。设为 `True` 时，返回两个东西：文档文本列表 + 距离列表。

距离是什么？Chroma 用余弦距离衡量两个向量有多像：
- `0.30` = 非常像
- `0.50` = 一般
- `0.80` = 不太像

有了距离，就能判断检索到的文档到底有没有用。

---

## 四、加了答非所问防护 — 两层

### 第一层：距离阈值

```python
RELEVANCE_THRESHOLD = 0.5  # 阈值

def rag_ask(query, ...):
    docs, distances = retriever.search(query, return_distances=True)
    
    if distances[0] > 0.5:  # 最好的结果距离都超过 0.5
        return "知识库中没有相关资料"  # → 拒绝回答
```

不管问什么，Chroma 都会返回 Top-3。但距离暴露了真相：

```
"CPU 使用率过高" → 和库里 CPU 文档匹配 → 距离 0.30 → 放行
"今天天气怎么样" → 和库里文档完全不搭 → 距离 0.68 → 拦截
```

**为什么不用关键词**：无关问题千千万，"推荐一首歌"能想到，"讲个笑话"呢？"帮我写封情书"呢？列不完。距离阈值是数学判断，不依赖词表。

### 第二层：LLM 自己判断

prompt 里加了这句：

```
请判断参考资料是否与用户问题相关。如果相关，基于参考资料回答。
如果不相关，请如实说明"参考资料与问题不匹配"。
```

即使第一层漏了（边界情况），LLM 也会自己检查相关性。

---

## 五、新建 main.py — FastAPI 启动文件

### 启动时做了什么

```python
embedder = Embedder()           # 加载 BGE 模型
retriever = Retriever(embedder) # 连 Chroma
llm = LLMClient()               # 连 DeepSeek
memory = ConversationMemory()   # 初始化记忆

if retriever.collection.count() == 0:
    # 知识库是空的 → 自动从 data/ 加载文档、分块、向量化、入库
```

### 三个路由

| 路由 | 做什么 | 怎么试 |
|------|--------|--------|
| `POST /ask` | RAG 问答，返回完整答案 | `curl "http://localhost:8000/ask?query=CPU使用率过高怎么办"` |
| `POST /ask/stream` | RAG 问答，流式输出（逐字出） | `curl "http://localhost:8000/ask/stream?query=CPU使用率过高怎么办"` |
| `POST /tool` | Agent 工具调用 | `curl "http://localhost:8000/tool?query=查一下db_001的CPU使用率"` |

### 流式输出怎么写

```python
@app.post("/ask/stream")
async def ask_stream(query: str):
    async def generate():
        for chunk in rag_ask(query, ...):
            yield chunk   # ← 每生成一个字就发出去

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",     # ← 告诉浏览器"这是流式数据"
        headers={
            "Cache-Control": "no-cache",     # ← 不要缓存
            "Connection": "keep-alive",      # ← 保持连接
        }
    )
```

用户看到的是逐字打出来的效果，不用等全部生成完。这三个 headers 和 GaussMaster 源码完全一样。

---

## 六、改动前后对比

| 模块 | 改前 | 改后 |
|------|------|------|
| memory.py | 不存在 | 3 轮滑动窗口，自动淘汰 |
| engine.py | Agent 是占位符 "将在第三步实现" | 真的调 agent_pipeline，RAG 和 Agent 都接记忆 |
| retriever.py | search() 只返回文本 | 新增 return_distances 参数，同时返回距离 |
| engine.py 防护 | 无 | 两层：距离阈值 + LLM 自查 |
| main.py | 不存在 | FastAPI 三路由 + SSE 流式 + 自动初始化 |

---

## 七、完整流程跑一遍

```
启动 python main.py
  → 加载 BGE 模型（1024维）
  → 连 Chroma（已有 12 个块）
  → 连 DeepSeek API

用户问 "CPU 使用率过高怎么办"
  → POST /ask
  → rag_ask()
    → 检索: search("CPU 使用率过高") → 3 个文档块 + 距离 [0.30, 0.34, 0.34]
    → 距离阈值: 0.30 < 0.5 ✓ 放行
    → 拼 prompt: "参考资料: [文档1,2,3]\n用户: CPU使用率过高..."
    → LLM 流式生成 → 逐字返回

用户接着问 "那慢 SQL 呢"
  → POST /ask
  → rag_ask()
    → memory.get_context() → "之前聊了: CPU使用率过高..."
    → 拼 prompt: "之前聊了: ...\n参考资料: [慢SQL文档]\n用户: 那慢 SQL 呢"
    → LLM 知道"那"指的是前面的话题 → 生成慢 SQL 建议

用户问 "今天天气怎么样"
  → POST /ask
  → 检索: 距离 [0.72, 0.78, 0.85]
  → 距离阈值: 0.72 > 0.5 ✗ 拦截
  → 返回 "知识库中没有相关资料"

用户问 "查一下 db_001 的 CPU 使用率"
  → POST /tool
  → agent_pipeline()
    → 阶段一: LLM 选工具 → get_cpu_usage
    → 阶段二: LLM 填参数 → {"instance": "db_001"}
    → validate_params() → 通过
    → execute() → {"cpu_percent": 78.5}
    → LLM 总结 → "db_001 当前 CPU 使用率 78.5%"
```
