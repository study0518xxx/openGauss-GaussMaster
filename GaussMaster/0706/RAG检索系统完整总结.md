# RAG 检索系统完整总结

---

## 一、核心参数设计

### SearchParams 关键参数

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `vector_topk` | 6 | 向量检索召回数量 |
| `text_topk` | 6 | BM25 文本检索召回数量 |
| `rerank_topk` | 3 | 重排序后最终返回数量 |
| `history_len` | 1 | 历史对话轮数 |

### 设计原理

采用**"粗召回 + 精排序"**策略：

```
用户提问
    │
    ├──→ 向量检索(vector_topk=6) → 返回6篇语义相似文档
    ├──→ 文本检索(text_topk=6)  → 返回6篇关键词匹配文档
    │
    └──→ 合并去重 → 重排序 → 返回前rerank_topk=3篇
```

---

## 二、检索算法架构

### 阶段一：混合检索

#### 1. 向量检索（search_vector）

**核心算法**：L2 距离（欧氏距离）

**生成的 SQL**：
```sql
SELECT * 
FROM "knowledge_base" 
WHERE version='5.0' 
ORDER BY "text_vector" <-> '[0.123, -0.456, 0.789, ...]' 
LIMIT 6;
```

**关键技术点**：
- 使用 openGauss 内置的 `<->` 操作符
- 基于 GSDiskANN 向量索引加速
- 支持范围查询模式（当 `distance≠2` 时）

#### 2. 文本检索（search_text）

**核心算法**：BM25（Best Matching 25）

**生成的 SQL**：
```sql
SELECT /*+ no tablescan("knowledge_base")*/ * 
FROM "knowledge_base" 
WHERE version='5.0' 
ORDER BY "title,text" ### '查询文本' desc 
LIMIT 6;
```

**关键技术点**：
- 使用 `###` 操作符进行 BM25 评分
- 通过 Hint 强制使用全文索引
- 支持多字段联合检索

### 阶段二：重排序

**算法**：Cross-Encoder 语义匹配

```python
# 1. 合并去重
dedup_list = list(set(vector_result + text_result))

# 2. 构建候选对
pairs = [[query, doc_text] for doc in dedup_list]

# 3. 计算相关性分数
scores = await reranker.compute_score(pairs)

# 4. 过滤负分并排序
filtered = [(s, r) for s, r in zip(scores, results) if s >= 0]
sorted_results = sorted(filtered, key=lambda x: x[0], reverse=True)[:rerank_topk]
```

---

## 三、距离度量选择

### 支持的距离类型

| 距离类型 | 操作符 | 默认 | 特点 |
|---------|--------|------|------|
| L2 距离 | `<->` | ✓ | 考虑向量长度，速度快 |
| 余弦距离 | `<=>` | - | 只考虑方向，需归一化 |
| 内积 | `<#>` | - | 向量点积 |

### 切换到余弦相似度

**需要修改的位置**：

1. 修改默认配置：
```python
DEFAULT_DISTANCE_STRATEGY = "cosine"  # 原为 "l2"
```

2. 修改查询操作符：
```python
# 当前硬编码为 <->，需要改为动态选择
operator = {"l2": "<->", "cosine": "<=>", "inner": "<#>"}[self.distance_strategy]
sql += f'ORDER BY "vector_column" {operator} {query_vector} LIMIT {topk}'
```

3. 重建向量索引：
```sql
CREATE INDEX vector_idx ON table USING gsdiskann(vector_column cosine);
```

---

## 四、查询优化机制（query_opt_process）

### 触发条件

当直接检索结果为空时触发：
```python
if not search_res:
    async for item in query_opt_process(question, ...):
        ...
```

### 核心技术

#### 1. HyDE（假设性文档嵌入）

**原理**：先生成假设性回答，再用回答去检索

```python
hyde_messages = get_hyde_prompt(question, [], lang)
hyde_result = await generate_answer(hyde_messages, model_name)
query_list.append(hyde_result)
```

#### 2. Query Transformation（查询改写）

**原理**：将复杂问题分解为多个子问题

```python
query_trans_messages = get_query_transform_prompt(question, [], lang)
query_trans_result = await generate_answer(query_trans_messages, model_name)
query_list.extend(parse_sub_queries(query_trans_result))
```

### 执行流程

```
原始检索无结果
    │
    ├──→ HyDE 生成假设性回答 → 添加到 query_list
    ├──→ Query Transformation 生成子问题 → 添加到 query_list
    │
    ├──→ 对每个 query 执行检索 → 收集结果
    │
    └──→ 合并排序 → 生成最终回答
```

### 当前代码问题

**缺少跨查询去重**：不同查询可能返回相同文档，建议在排序前增加去重逻辑：

```python
seen_knowledge_ids = set()
unique_results = []
for score, result in zip(score_list, res_list):
    knowledge_id = result.get('knowledge_id')
    if knowledge_id not in seen_knowledge_ids:
        seen_knowledge_ids.add(knowledge_id)
        unique_results.append(result)
```

---

## 五、数据流向

```
用户提问
    │
    ├──→ search() ───→ search_res (检索结果，不需要 history)
    │         │
    │         └──→ 向量检索 + 文本检索 + 重排序
    │
    ├──→ get_history_chat() ───→ history (历史对话)
    │
    └──→ llm_generation(question, search_res, history) ───→ 最终回答
```

### 历史对话的作用

| 阶段 | 是否需要 history | 原因 |
|------|-----------------|------|
| 检索阶段 | ✗ 不需要 | 只关注当前问题与知识库的匹配 |
| 生成阶段 | ✓ 需要 | 保持对话连贯，理解上下文依赖 |

---

## 六、关键函数职责

| 函数 | 职责 | 文件位置 |
|------|------|---------|
| `search_vector` | 向量相似度检索 | `common/metadatabase/dao/gaussdb_vector.py` |
| `search_text` | BM25 文本检索 | `common/metadatabase/dao/gaussdb_vector.py` |
| `search` | 混合检索入口 | `server/web/data_transformer.py` |
| `get_history_chat` | 获取历史对话 | `server/web/data_transformer.py` |
| `query_opt_process` | 查询优化处理 | `server/web/data_transformer.py` |
| `llm_generation` | LLM 答案生成 | `server/web/data_transformer.py` |
| `generate_answer` | 流式调用 LLM | `server/web/data_transformer.py` |

---

## 七、代码优化建议

### 1. 添加跨查询去重
**位置**：`data_transformer.py` 第 667-671 行

### 2. 统一索引 Hint
**位置**：`gaussdb_vector.py` `search_vector` 函数

### 3. 修复范围查询的 version 缺失
**问题**：当 `distance != 2` 时，SQL 中缺少 version 过滤条件

### 4. 支持动态距离策略
**问题**：当前查询操作符硬编码为 `<->`，应根据 `distance_strategy` 动态选择

---

## 八、核心设计理念

| 理念 | 实现方式 |
|------|---------|
| **高召回率** | 混合检索（向量 + 文本）确保不漏掉相关文档 |
| **高精度** | Cross-Encoder 重排序筛选最相关结果 |
| **优雅降级** | 检索失败时自动触发查询优化 |
| **流式输出** | 支持实时显示，提升用户体验 |

---

## 九、典型应用场景

| 场景 | 示例问题 | 检索方式 |
|------|---------|---------|
| 语义理解 | "什么是向量数据库？" | 向量检索为主 |
| 术语查询 | "VACUUM 命令的用法" | 文本检索为主 |
| 复杂问题 | "数据库性能如何调优？" | 查询优化（HyDE + Query Transformation） |
| 上下文依赖 | "这个错误怎么解决？" | 结合历史对话 |

---

**文档版本**：v1.0  
**生成时间**：2026-06-12  
**适用项目**：openGauss-GaussMaster