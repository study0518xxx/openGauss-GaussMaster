# memory 持久化方案对比：Chroma vs JSON

## 方案 A：存 Chroma

```python
class ConversationMemory:
    def __init__(self, retriever, max_rounds=3):
        self.collection = retriever.client.get_or_create_collection("chat_memory")
    
    def add(self, question, answer):
        # 每次对话存进 Chroma
        self.collection.add(
            documents=[f"Q: {question}\nA: {answer}"],
            ids=[str(uuid.uuid4())]
        )
    
    def get_context(self):
        # 从 Chroma 读最近 N 条
        results = self.collection.get()
```

## 方案 B：写 JSON 文件

```python
class ConversationMemory:
    def __init__(self, max_rounds=3, filepath="memory.json"):
        if os.path.exists(filepath):
            self.history = json.load(open(filepath))
        else:
            self.history = []
    
    def add(self, question, answer):
        self.history.append((question, answer))
        while len(self.history) > 3:
            self.history.pop(0)
        json.dump(self.history, open(self.filepath, "w"), ensure_ascii=False)
```

## 对比

| | Chroma | JSON 文件 |
|---|---|---|
| **代码量** | ~20 行 | ~5 行 |
| **依赖** | 无新增（已有 chromadb） | 无（Python 内置 json） |
| **能搜相似对话吗** | ✅ 可以向量搜索"历史上类似的问题" | ❌ 只能按时间顺序读 |
| **人能直接看吗** | ❌ 二进制存储，打不开 | ✅ 记事本直接打开看 |
| **存多少合适** | 几万条没问题 | 几百条就慢 |
| **适合场景** | 要做"语义搜索历史对话" | 只要重启不丢就行 |
| **和 GaussMaster 的对应** | 对应 `gm_tool_history_memory`（向量化的工具历史） | 没有对应，GaussMaster 不存在 JSON 文件 |

## 结论

**Demo 应该用 JSON。** 原因：
- 你只需要重启不丢，不需要语义搜索历史
- 5 行代码，人能直接打开看
- Chroma 存对话记忆是大材小用——Chroma 是用来存文档块做 RAG 的

GaussMaster 把对话分两种：`tb_interaction_memory`（关系型，精确查）和 `gm_tool_history_memory`（向量化，语义搜）。Demo 只要关系型就够了。
