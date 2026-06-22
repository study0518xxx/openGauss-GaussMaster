# 检索与 RAG 层面试题

## 一、基础问题

### Q1: 你们的检索系统是怎么设计的？

**回答要点**：
采用**混合检索 + 重排序**的三阶段架构：

1. **向量检索**：Embedding 模型将 query 向量化，在向量表中做 ANN 搜索
2. **全文检索**：BM25 算法做关键词匹配
3. **重排序**：Reranker 交叉编码模型对合并结果重新打分

```python
async def search(question, ...):
    vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk)
    text_result = retriever.search_text_result_gaussdb(question, text_topk)
    reranker_scores, reranker_result = await retriever.reranker_search_result(
        question, vector_result, text_result, rerank_topk
    )
```

---

### Q2: 向量检索和全文检索分别解决什么问题？

**回答要点**：
| 检索方式 | 优势 | 劣势 | 适用场景 |
|:---|:---|:---|:---|
| 向量检索 | 语义理解强，能找同义词、近义词 | 对精确词覆盖不足，计算成本高 | 概念性、语义性问题 |
| 全文检索 | 精确匹配，速度快 | 无法理解语义，同义词会漏 | 专有名词、命令、错误码 |

**为什么两者都要**：互补。向量找语义相关，全文找精确匹配，合并后覆盖更全面。

---

### Q3: 重排序（Reranker）的作用是什么？

**回答要点**：
- 向量检索和全文检索的打分方式不同，不能直接比较
- Reranker 是**交叉编码模型**，将 `(query, document)` 对一起输入，输出相关性分数
- 作用：
  1. 统一打分标准
  2. 更精细的相关性判断（考虑了 query 和 doc 的交互）
  3. 从合并结果中精选最终 TopK

---

## 二、进阶问题

### Q4: 向量数据库用的什么？向量索引是什么？

**回答要点**：
- **数据库**：openGauss（扩展了向量能力）
- **向量字段类型**：`floatvector`，1024 维
- **索引算法**：`gsdiskann`
  - DiskANN 的变种，支持磁盘存储的近似最近邻搜索
  - 支持距离度量：L2（欧氏距离）、余弦相似度、内积
- **建表配置**（`kb_config.py`）：
  ```python
  KT_TABLE_CONFIG = {
      "vector_field": ['text_vector'],
      "bm25_field": ['text'],
      "text_field": ['text', 'title', 'source', ...]
  }
  ```

---

### Q5: 查询优化（Query Optimization）的完整流程？

**回答要点**：
当首轮检索无结果时，触发三阶段优化：

```
首轮检索无结果
    │
    ▼
1. HyDE（假设性文档扩展）
   - 让 LLM 根据问题生成假设性回答
   - 用这段回答做向量检索（扩展语义覆盖）
    │
    ▼
2. 查询改写（Query Transformation）
   - 让 LLM 将原问题改写为多个相关查询
   - 输出格式：带序号列表（1. xxx, 2. xxx）
    │
    ▼
3. 多查询检索 + 合并
   - 对每个改写 query 分别检索
   - 合并所有结果，按相似度排序
   - 取 TopK 交给 LLM
```

**为什么有效**：
- 用户问题可能表述不清，改写后覆盖更多表达方式
- HyDE 生成假设文档，包含了相关关键词，提高向量检索命中率

---

### Q6: 检索参数 `vector_topk`、`text_topk`、`rerank_topk` 怎么配置？

**回答要点**：
- 默认值：`vector_topk=6`，`text_topk=6`，`rerank_topk=3`
- 设计逻辑：
  - 向量检索和全文检索各自多召回一些（6条），保证召回率
  - 重排序后精选少量（3条），保证精确率
  - 最终给 LLM 的上下文有限，避免 Prompt 过长
- 范围限制：`[1, 10]`，防止参数异常

---

### Q7: 知识库是怎么构建的？

**回答要点**：
```python
async def add_knowledge(name, user_id, file, kb_type, ...):
    # 1. 解析文件（PDF/Word/TXT/Markdown）
    # 2. 文本分块（Chunking）
    # 3. 调用 Embedding 模型生成向量
    # 4. 插入向量表（text + text_vector + 元信息）
    # 5. 同时插入关系型表（知识库元信息、数据源信息）
```

**分块策略**：
- 按段落或固定长度分块
- 块之间有重叠（overlap），避免语义断裂
- 每个块生成独立向量

---

## 三、深挖问题

### Q8: 如果检索结果为空，系统怎么处理？

**回答要点**：
1. **首轮检索为空** → 触发查询优化（HyDE + 查询改写）
2. **优化后仍为空** → 返回拒答消息：
   ```
   "无法从知识库中检索到相关知识，暂不支持直接生成答案"
   ```
3. **不会直接让 LLM 瞎编**：避免幻觉，保证答案可靠性

---

### Q9: 怎么评估检索质量？

**回答要点**：
（如果项目有评估的话）
1. **召回率（Recall）**：相关文档是否被检索出来
2. **精确率（Precision）**：检索结果中多少是相关的
3. **MRR（Mean Reciprocal Rank）**：第一个相关文档的排名
4. **NDCG**：考虑排序位置的相关性评估

**优化方向**：
- 调整 `vector_topk` / `text_topk` 平衡召回和精确
- 优化 Embedding 模型（领域微调）
- 优化分块策略（粒度、重叠）

---

### Q10: 如果让你优化检索层，你会怎么做？

**回答要点**：
1. **多路召回**：增加稀疏向量（如 SPLADE）、关键词扩展等更多召回通道
2. **查询理解**：做意图识别，不同意图走不同检索策略
3. **缓存优化**：热门查询缓存检索结果
4. **向量索引优化**：根据数据量选择 HNSW、IVF 等更合适的索引
5. **Reranker 微调**：用业务数据微调重排序模型

---

## 四、手写代码题

### 题目：实现一个简单的向量相似度检索

```python
import numpy as np

class SimpleVectorStore:
    def __init__(self, dim=1024):
        self.dim = dim
        self.vectors = []  # List[np.ndarray]
        self.documents = []  # List[str]
    
    def add(self, vector, document):
        self.vectors.append(np.array(vector))
        self.documents.append(document)
    
    def search(self, query_vector, top_k=3):
        if not self.vectors:
            return []
        
        query = np.array(query_vector)
        # 计算余弦相似度
        vectors = np.stack(self.vectors)
        similarities = np.dot(vectors, query) / (
            np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
        )
        
        # 取 TopK
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [
            {'document': self.documents[i], 'score': float(similarities[i])}
            for i in top_indices
        ]
```
