# 02-RAG流程详解

> 本文档详解 GaussMaster 的 RAG（检索增强生成）智能问答流程。

---

## 1. RAG 是什么？

**RAG（Retrieval-Augmented Generation，检索增强生成）** 是一种结合向量检索和大模型生成的技术，解决大模型知识不足和幻觉问题。

**核心思想**：先检索相关知识，再让 LLM 基于检索结果生成答案，而非直接让 LLM "编造"。

---

## 2. RAG 整体流程

```
用户提问: "GaussDB是什么？"
    │
    ▼
┌─────────────────┐
│  1. 参数校验     │  ← 检查question是否为空
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  2. 敏感词检测   │  ← DFA算法检测不安全内容
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  3. 初始化QA记录 │  ← 生成answer_id，准备存储
└─────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  4. RAG检索 (search函数)                 │
│  ┌─────────────┐    ┌─────────────┐     │
│  │  向量检索    │ +  │  文本检索    │     │
│  │ (语义相似度) │    │ (关键词匹配) │     │
│  └─────────────┘    └─────────────┘     │
│           │                              │
│           ▼                              │
│  ┌─────────────────┐                     │
│  │  合并 + 去重     │                     │
│  └─────────────────┘                     │
│           │                              │
│           ▼                              │
│  ┌─────────────────┐                     │
│  │  Reranker重排序  │  ← 提升检索精度      │
│  └─────────────────┘                     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────┐
│  5. LLM生成答案 │  ← 基于检索结果生成
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  6. 保存到数据库 │  ← SQLite持久化
└─────────────────┘
```

---

## 3. 检索流程详解

### 3.1 向量检索（语义相似度）

```python
# 1. 问题向量化
query_embedding = embedding_model.encode(question)  # [768] 向量

# 2. 向量数据库检索
SELECT uuid, text, title, source, embedding <=> query_embedding AS distance
FROM knowledge_table
ORDER BY distance ASC
LIMIT vector_topk;  # 默认5条
```

**原理**：将问题和知识库文档都转为向量，计算余弦相似度，找最相似的文档。

### 3.2 文本检索（关键词匹配）

```python
# 使用BM25算法进行全文检索
SELECT uuid, text, title, source
FROM knowledge_table
WHERE text LIKE '%关键词%' OR title LIKE '%关键词%'
LIMIT text_topk;  # 默认5条
```

**原理**：基于词频-逆文档频率（TF-IDF）的改进算法，找包含关键词的文档。

### 3.3 合并与去重

```python
# 向量检索结果 + 文本检索结果 → 合并 → 去重
merged_results = vector_results + text_results
unique_results = deduplicate(merged_results)  # 按uuid去重
```

### 3.4 Reranker 重排序

```python
# 使用交叉编码器模型进行精排
scores = reranker_model.predict([
    (question, doc.text) for doc in unique_results
])
# 按分数排序，取Top-K
final_results = sorted(unique_results, key=lambda x: scores[x], reverse=True)[:rerank_topk]
```

**原理**：Reranker 是更精确的模型，计算问题与每个文档的相关性分数，重新排序。

---

## 4. 查询优化策略

### 4.1 HyDE（假设文档嵌入）

**问题**：用户问题太简单，检索不到相关内容。

**解决**：让 LLM 先生成一个"假设答案"，再用假设答案去检索。

```python
# 步骤1: 生成假设答案
hypothetical_answer = llm.generate(f"请回答这个问题：{question}")

# 步骤2: 用假设答案检索
search_results = vector_db.search(hypothetical_answer, top_k=5)

# 步骤3: 用检索结果生成最终答案
final_answer = llm.generate(f"基于以下资料回答问题：{search_results}\n问题：{question}")
```

**效果**：假设答案包含更多相关关键词，检索召回率提升 20-30%。

### 4.2 查询改写

**问题**：用户问题表述多样，检索不到。

**解决**：让 LLM 生成多个改写版本，同时检索。

```python
# 生成多个查询变体
queries = llm.generate(f"请生成3个这个问题的不同表述：{question}")
# 例如："GaussDB是什么？" → "介绍一下GaussDB", "GaussDB数据库概述"

# 多路检索
all_results = []
for q in queries:
    all_results.extend(vector_db.search(q, top_k=3))

# 合并去重后重排序
final_results = reranker.rerank(question, all_results)
```

---

## 5. LLM 生成答案

### 5.1 Prompt 构建

```python
system_prompt = """你是一个数据库专家助手。请基于以下参考资料回答用户问题。
如果参考资料不足以回答问题，请说明"根据现有资料无法回答"。

参考资料：
{references}
"""

user_prompt = question
```

### 5.2 流式生成

```python
# 使用SSE流式输出
async for chunk in llm.generate_stream(messages):
    yield {"type": "answer", "data": chunk}
```

**用户体验**：用户可以看到答案逐字出现，而非等待全部生成。

---

## 6. 核心代码位置

| 函数 | 文件 | 职责 |
|------|------|------|
| `ask_gauss()` | `server/web/data_transformer.py` | RAG问答入口 |
| `search()` | `server/web/data_transformer.py` | 检索核心 |
| `search_vector_result_gaussdb()` | `utils/retriever_util.py` | 向量检索 |
| `search_text_result_gaussdb()` | `utils/retriever_util.py` | 文本检索 |
| `reranker_search_result()` | `utils/retriever_util.py` | 重排序 |
| `llm_generation()` | `server/web/data_transformer.py` | LLM生成 |

---

## 7. 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `vector_topk` | 5 | 向量检索返回条数 |
| `text_topk` | 5 | 文本检索返回条数 |
| `rerank_topk` | 3 | 重排序后最终返回条数 |
| `history_len` | 3 | 多轮对话历史长度 |

---

## 8. 性能优化

| 优化点 | 方案 | 效果 |
|--------|------|------|
| 检索速度 | 向量索引 + 缓存 | <100ms |
| 生成速度 | SSE流式输出 | 用户感知 <1s |
| 准确率 | Reranker重排 | 提升15-20% |
| 召回率 | HyDE + 查询改写 | 提升20-30% |

---

## 9. 与 Agent 流程的对比

| 维度 | RAG流程 | Agent流程 |
|------|---------|-----------|
| **输入** | 知识问题 | 运维指令 |
| **处理** | 检索+生成 | 意图识别+工具调用 |
| **输出** | 文本答案 | 工具执行结果 |
| **核心** | 知识库 | 工具集 |
| **示例** | "GaussDB是什么？" | "查看昨天告警" |

---

*本文档基于 openGauss-GaussMaster v1.0.0*
