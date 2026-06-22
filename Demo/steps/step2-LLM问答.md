# 第二步：LLM 客户端 + RAG 问答

## 做了什么

在上一步的检索基础上，接入了 DeepSeek LLM，跑通了完整的 RAG 问答管道：**用户提问 → 检索文档 → 拼 prompt → LLM 生成答案**。

## 新增的文件

| 文件 | 作用 | 对应 GaussMaster 源码 |
|------|------|---------------------|
| `llm_client.py` | 封装 DeepSeek API，支持普通和流式调用 | `data_transformer.py:generate_answer()` |
| `engine.py` | RAG 问答管道 + 意图路由 | `data_transformer.py:ask_gauss()` |

## 核心逻辑

```
用户: "CPU 使用率过高怎么办"
  │
  ▼
engine.rag_ask()
  │
  ├─ ① retriever.search(query, topk=3) → 从 Chroma 搜出 3 个最相关的文档块
  │      │
  │      ▼ 3 个文本块
  │
  ├─ ② 拼接 prompt:
  │    "你是一个 GaussDB 数据库运维专家。
  │     参考资料：
  │     [文档块1]
  │     ---
  │     [文档块2]
  │     ---
  │     [文档块3]
  │     用户问题：CPU 使用率过高怎么办
  │     请回答："
  │      │
  │      ▼ 完整的 prompt（约 2000 字）
  │
  └─ ③ llm.chat_stream(prompt, system_prompt=...)
        │
        ├─ HTTP POST → api.deepseek.com/v1/chat/completions
        ├─ stream=True（流式模式）
        │
        └─ 逐字返回："当" "GaussDB" " " "CPU" " " "使用率" ...
            用户看到逐字打出，体验好
```

## llm_client.py 详解

### 为什么用 OpenAI SDK 而不是自己写 HTTP

DeepSeek 的 API 和 OpenAI 完全兼容，所以直接用 `openai` 这个包，改一下 `base_url` 就行：

```python
client = OpenAI(
    api_key="sk-xxx",
    base_url="https://api.deepseek.com",  # ← 这一行指向 DeepSeek
)
```

`chat()` → 普通调用，`stream=False`，等全部生成完才返回。

`chat_stream()` → 流式调用，`stream=True`，每生成一个字就 yield 出来。

### 流式 vs 非流式

```
非流式: 等 10 秒 → 啪，出来一大堆文字
流式:    当 Ga ussDB CP U 使 用 率 ... 逐字出现
```

GaussMaster 用的就是流式（SSE `text/event-stream`），这里用 `chat_stream()` 实现同样效果。

---

## engine.py 详解

### rag_ask() — RAG 问答管道

三步走：检索 → 拼 prompt → 生成。

**system_prompt** 告诉 LLM 它的角色和规则：

```python
SYSTEM_PROMPT = """你是一个 GaussDB 数据库运维专家。请根据提供的参考资料回答用户问题。
规则：
1. 如果参考资料能回答，就基于参考资料回答，不要编造
2. 如果参考资料不能回答，就如实说"参考资料中没有相关信息"
3. 回答要专业、简洁、有结构化
4. 涉及具体 SQL 或参数时，尽量引用参考资料中的原文"""
```

这个 system_prompt 对应 GaussMaster 的 `INFER_SYSTEM_TMPL`，核心思想一样：**约束 LLM 只基于检索到的文档回答，减少幻觉。**

### process_query() — 意图路由

```python
tool_keywords = ["查一下", "获取", "当前", "多少", "占用了", "帮我看"]
is_tool_query = any(kw in query for kw in tool_keywords)

if is_tool_query:
    return agent_pipeline()  # 第三步实现
else:
    return rag_ask()         # RAG 问答
```

生产版 GaussMaster 用 LLM 做意图分类，Demo 用关键词简化。效果一样——决定走哪条管道。

---

## 怎么跑

```powershell
cd C:\2026\0703ddl\openGauss-GaussMaster\Demo

# 1. 先在 .env 里填 DeepSeek API Key
#    打开 .env，把 your_api_key_here 换成真的 key
#    没有的话去 https://platform.deepseek.com 注册获取

# 2. 先单独测 LLM（验证 API Key 是否有效）
python llm_client.py

# 3. 跑完整 RAG 问答
python engine.py
```

## 预期输出

```
=== 测试 RAG 问答完整链路 ===

--- 初始化 ---
  [embedder] 加载模型: BAAI/bge-large-zh-v1.5 ...
  [embedder] 加载完成，维度: 1024
  [retriever] Chroma 已连接，当前块数: 12
  [llm] 模型: deepseek-chat

--- 用户问题: CPU 使用率过高怎么办 ---
回答: 当 GaussDB 数据库 CPU 使用率过高时，建议按以下步骤排查：

1. **检查慢 SQL**：使用 pg_stat_activity 查看当前正在执行的慢查询...
2. **检查统计信息**：统计信息过期会导致错误的执行计划...
3. **检查连接数**：当连接数超过 max_connections 的 80% 时...
4. **检查参数配置**：shared_buffers 建议设置为物理内存的 25%...
```

## 面试能讲什么

- "RAG 管道分三步：检索 → 拼 prompt → LLM 生成，和 GaussMaster 的 ask_gauss 一样"
- "用了 DeepSeek 的流式 API，stream=True，逐字返回，首 token 延迟 < 1 秒"
- "system_prompt 约束 LLM 只基于检索到的文档回答，减少幻觉"
- "意图路由用关键词判断走 RAG 还是 Agent，生产版 GaussMaster 用 LLM 分类"
