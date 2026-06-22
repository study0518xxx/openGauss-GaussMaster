# 07-多路召回与HyDE详解

> 本文档详解 GaussMaster 的检索优化策略：多路召回和 HyDE（假设文档嵌入）。

---

## 1. 多路召回

### 1.1 什么是多路召回？

**多路召回**是指同时使用多种检索方式，合并结果，提升召回率。

```
用户问题: "GaussDB是什么？"
    │
    ├──→ 向量检索（语义相似度）──┐
    │                            ├──→ 合并去重 ──→ Reranker ──→ 最终结果
    └──→ 文本检索（关键词匹配）──┘
```

### 1.2 向量检索

**原理**：将问题和文档都转为向量，计算余弦相似度。

```python
# 1. 问题向量化
query_embedding = embedding_model.encode("GaussDB是什么？")  # [768] 向量

# 2. 向量数据库检索
SELECT uuid, text, title, source, embedding <=> query_embedding AS distance
FROM knowledge_table
ORDER BY distance ASC
LIMIT vector_topk;  # 默认5条
```

**优点**：
- 理解语义，不受关键词限制
- "GaussDB"和"高斯数据库"可以匹配

**缺点**：
- 对特定术语可能不敏感
- 需要 Embedding 模型

### 1.3 文本检索（BM25）

**原理**：基于词频-逆文档频率（TF-IDF）的改进算法。

```python
# 全文检索
SELECT uuid, text, title, source
FROM knowledge_table
WHERE text LIKE '%GaussDB%' OR title LIKE '%GaussDB%'
LIMIT text_topk;  # 默认5条
```

**优点**：
- 精确匹配关键词
- 对特定术语敏感

**缺点**：
- 无法理解语义
- "GaussDB"和"高斯数据库"无法匹配

### 1.4 合并与去重

```python
# 向量检索结果 + 文本检索结果 → 合并 → 去重
merged_results = vector_results + text_results

# 按uuid去重
def deduplicate(results):
    seen = set()
    unique = []
    for r in results:
        if r['uuid'] not in seen:
            seen.add(r['uuid'])
            unique.append(r)
    return unique

unique_results = deduplicate(merged_results)
```

### 1.5 Reranker 重排序

```python
# 使用交叉编码器模型进行精排
scores = reranker_model.predict([
    (question, doc.text) for doc in unique_results
])

# 按分数排序，取Top-K
final_results = sorted(
    unique_results, 
    key=lambda x: scores[x], 
    reverse=True
)[:rerank_topk]  # 默认3条
```

**原理**：Reranker 是更精确的模型，计算问题与每个文档的相关性分数，重新排序。

**效果**：检索精度提升 15-20%。

---

## 2. HyDE（假设文档嵌入）

### 2.1 问题场景

```
用户问题: "数据库怎么优化？"

问题：这个问题太宽泛，向量检索可能找不到精确匹配的内容。
```

### 2.2 HyDE 原理

**HyDE（Hypothetical Document Embeddings）**：让 LLM 先生成一个"假设答案"，再用假设答案去检索。

```
用户问题: "数据库怎么优化？"
    │
    ▼
┌─────────────────┐
│ LLM生成假设答案  │  "数据库优化可以从以下几个方面入手：
│                 │   1. SQL优化：使用索引、避免全表扫描
│                 │   2. 参数调优：调整内存、连接数等参数
│                 │   3. 架构优化：读写分离、分库分表..."
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 用假设答案检索   │  ← 包含更多关键词，召回率更高
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 用检索结果生成   │  ← 最终答案
│ 最终答案         │
└─────────────────┘
```

### 2.3 代码实现

```python
async def query_opt_process(question, user_id, session_id, ...):
    """
    【查询优化】当检索不到结果时，使用HyDE和查询改写
    """
    # 1. HyDE：生成假设答案
    hypothetical_answer = await llm.generate(f"请简要回答这个问题：{question}")
    
    # 2. 用假设答案检索
    hyde_results = await search(hypothetical_answer, ...)
    
    # 3. 查询改写：生成多个查询变体
    query_variants = await llm.generate(
        f"请生成3个这个问题的不同表述：{question}"
    )
    
    # 4. 多路检索
    all_results = []
    for q in [question] + query_variants.split('\n'):
        all_results.extend(await search(q, ...))
    
    # 5. 合并去重后重排序
    final_results = reranker.rerank(question, all_results)
    
    # 6. 生成最终答案
    async for item in llm_generation(question, final_results, ...):
        yield item
```

### 2.4 效果

| 策略 | 召回率提升 |
|------|-----------|
| 仅向量检索 | 基准 |
| 向量 + 文本 | +10% |
| + Reranker | +15-20% |
| + HyDE | +20-30% |
| + 查询改写 | +25-35% |

---

## 3. 核心代码位置

| 函数 | 文件 | 职责 |
|------|------|------|
| `search()` | `server/web/data_transformer.py` | 检索入口 |
| `search_vector_result_gaussdb()` | `utils/retriever_util.py` | 向量检索 |
| `search_text_result_gaussdb()` | `utils/retriever_util.py` | 文本检索 |
| `reranker_search_result()` | `utils/retriever_util.py` | 重排序 |
| `query_opt_process()` | `server/web/data_transformer.py` | 查询优化 |

---

## 4. 面试重点

### Q: 检索不到怎么办？

**答**: 
1. **HyDE**：让LLM生成假设答案，用假设答案去检索
2. **查询改写**：生成多个查询变体，多路检索
3. **多路召回**：向量检索 + 文本检索同时执行
4. **Reranker**：对合并结果重排序，提升精度

### Q: 为什么需要多路召回？

**答**:
- 向量检索理解语义，但对特定术语不敏感
- 文本检索精确匹配关键词，但无法理解语义
- 两者互补，合并后召回率更高

### Q: Reranker 和 Embedding 的区别？

**答**:
- **Embedding**：双编码器，分别编码问题和文档，计算相似度。速度快，但精度有限。
- **Reranker**：交叉编码器，将问题和文档一起编码，计算相关性。速度慢，但精度高。
- **使用方式**：先用Embedding快速召回Top-100，再用Reranker精排取Top-3。

---

*本文档基于 openGauss-GaussMaster v1.0.0*
