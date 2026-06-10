# GaussMaster 多路召回与 HyDE 查询优化详解

## 目录

- [多路召回实现原理](#多路召回实现原理)
- [HyDE 查询优化详解](#hyde-查询优化详解)

---

## 多路召回实现原理

### 什么是多路召回？

> **多路召回** = 用多种不同的方法同时检索，然后合并结果，提升召回率。

**为什么需要多路召回？**

| 检索方式 | 优点 | 缺点 |
|---------|------|------|
| 向量检索 | 语义理解好 | 可能漏掉关键词 |
| 文本检索 | 关键词匹配准 | 不理解语义 |
| **多路召回** | **两者优点兼得** | 需要去重和排序 |

---

### 代码实现流程

```
┌─────────────────────────────────────────────────────────────┐
│                     多路召回流程图                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户问题: "数据库性能优化方法"                               │
│       ↓                                                     │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │   向量检索       │    │   文本检索       │                 │
│  │   (语义相似度)   │    │   (关键词匹配)   │                 │
│  ├─────────────────┤    ├─────────────────┤                 │
│  │ 1. Embedding    │    │ 1. 分词         │                 │
│  │    向量化       │    │ 2. 关键词匹配    │                 │
│  │ 2. 向量相似度计算│    │ 3. 返回Top-K    │                 │
│  │ 3. 返回Top-K    │    │                 │                 │
│  └────────┬────────┘    └────────┬────────┘                 │
│           ↓                      ↓                          │
│       结果A [doc1, doc2]    结果B [doc2, doc3]              │
│           └──────────┬──────────┘                          │
│                      ↓                                      │
│              合并去重 [doc1, doc2, doc3]                     │
│                      ↓                                      │
│           ┌─────────────────┐                               │
│           │   重排序 Reranker │                               │
│           │   计算问题-文档相关性 │                            │
│           │   重新排序         │                               │
│           └────────┬────────┘                               │
│                   ↓                                         │
│           最终结果 [doc2, doc1, doc3]                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 核心代码实现

#### 1. 向量检索

```python
# retriever_util.py 第 115-118 行
async def search_vector_result_gaussdb(self, query, topk=3, version=""):
    """向量检索：基于语义相似度"""
    results = await self.gaussdb.search_vector(query, topk, version)
    return results
```

**内部实现**（伪代码）：

```python
async def search_vector(self, query, topk, version):
    # 1. 将查询转为向量（Embedding）
    query_embedding = await embedding_model.query_embedding(query)
    
    # 2. 在向量数据库中搜索相似向量
    # SQL: SELECT * FROM knowledge_base ORDER BY embedding <-> query_embedding LIMIT topk
    results = vector_db.search(
        embedding=query_embedding,
        topk=topk,
        filter={"version": version}
    )
    
    return results
```

**示例**：

```
用户问题: "怎么让数据库跑得更快"
向量检索理解语义 → 找到 "数据库性能优化指南"
```

---

#### 2. 文本检索

```python
# retriever_util.py 第 120-123 行
def search_text_result_gaussdb(self, query, topk=3, version=""):
    """文本检索：基于关键词匹配"""
    results = self.gaussdb.search_text(query, topk, version)
    return results
```

**内部实现**（伪代码）：

```python
def search_text(self, query, topk, version):
    # 1. 分词
    keywords = jieba.cut(query)  # ["数据库", "性能", "优化"]
    
    # 2. 构建 SQL 查询
    # SQL: SELECT * FROM knowledge_base 
    #      WHERE text LIKE '%数据库%' OR text LIKE '%性能%' OR text LIKE '%优化%'
    #      ORDER BY relevance LIMIT topk
    results = text_db.search(
        keywords=keywords,
        topk=topk,
        filter={"version": version}
    )
    
    return results
```

**示例**：

```
用户问题: "ACID特性"
文本检索匹配关键词 → 找到包含 "ACID" 的文档
```

---

#### 3. 合并去重

```python
# retriever_util.py 第 125-133 行
def get_reranker_pairs(self, query, vector_result, text_result):
    """合并向量检索和文本检索结果，去重"""
    # 1. 合并并去重
    dedup_list = list(set(vector_result + text_result))
    
    # 2. 构建 Reranker 需要的 pairs
    column_list = self.gaussdb.cols
    pairs = []
    for result in dedup_list:
        pair = [query, result[column_list.index('text')]]  # [问题, 文档内容]
        pairs.append(pair)
    
    return pairs, dedup_list
```

**示例**：

```
向量检索结果: [doc1, doc2, doc3]
文本检索结果: [doc2, doc3, doc4]
合并去重后:   [doc1, doc2, doc3, doc4]
```

---

#### 4. 重排序 Reranker

```python
# retriever_util.py 第 135-152 行
async def get_sorted_results(self, query, vector_result, text_result):
    """使用 Reranker 重新排序"""
    # 1. 合并去重
    dedup_list = list(set(vector_result + text_result))
    
    # 2. 构建 pairs: [[问题, 文档1], [问题, 文档2], ...]
    pairs = []
    for result in dedup_list:
        pair = [query, result[column_list.index('text')]]
        pairs.append(pair)
    
    if not pairs:
        return [], []
    
    # 3. 调用 Reranker 计算相关性分数
    scores = await self.reranker.compute_score(pairs)
    # 返回: [0.95, 0.82, 0.76, 0.43] 每个文档的相关性分数
    
    # 4. 按分数排序
    zipped = zip(scores, dedup_list)
    sort_zipped = sorted(zipped, key=lambda x: x[0], reverse=True)
    sort_result = zip(*sort_zipped)
    sorted_scores, sorted_answer_list = [list(x) for x in sort_result]
    
    return sorted_scores, sorted_answer_list
```

**Reranker 原理**：

```
输入: pairs = [
    ["数据库性能优化方法", "数据库性能优化指南..."],
    ["数据库性能优化方法", "SQL调优技巧..."],
    ["数据库性能优化方法", "索引设计原则..."],
]

Reranker 模型计算相关性:
→ [0.95, 0.82, 0.76]

按分数排序:
→ ["数据库性能优化指南...", "SQL调优技巧...", "索引设计原则..."]
```

---

### 完整调用链

```python
# data_transformer.py 第 183-256 行
async def search(question, user_id, session_id, vector_topk, text_topk, rerank_topk, 
                 kb_id, version, lang, history_len):
    
    # 1. 确定知识库
    if kb_id == 0:
        table_name = kb_config.KT_TABLE_NAME + "_" + lang
    else:
        table_name = CUSTOM_KB_PREFIX + str(kb_id)
    
    # 2. 获取数据库实例
    gaussdb = get_db_instance(table_name, kb_config.KT_TABLE_CONFIG)
    
    # 3. 创建检索器
    retriever = BaseRetriever(gaussdb, global_vars.reranker_model)
    
    # 4. 【第一路】向量检索
    vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)
    
    # 5. 【第二路】文本检索
    text_result = retriever.search_text_result_gaussdb(question, text_topk, version)
    
    # 6. 【重排序】合并去重 + Reranker
    reranker_scores, reranker_result = await retriever.reranker_search_result(
        question, vector_result, text_result, rerank_topk)
    
    # 7. 组装结果
    search_res = []
    for index, answer in enumerate(reranker_result):
        knowledge_dict = {
            'knowledge_id': answer[column_list.index('uuid')],
            'content': answer[column_list.index('text')],
            'title': answer[column_list.index('title')],
            'source': answer[column_list.index('source')],
            'score': reranker_scores[index],
            ...
        }
        search_res.append(knowledge_dict)
    
    return {
        'search_res': search_res,
        'vector_search_time': xxx,
        'text_search_time': xxx,
        'rerank_search_time': xxx,
        'question_id': str(uuid.uuid4())
    }
```

---

### 多路召回优势

```
┌─────────────────────────────────────────────────────────────┐
│                     多路召回优势                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户问题: "怎么让数据库跑得更快"                            │
│                                                             │
│  向量检索 → "数据库性能优化指南" ✓                          │
│           → "SQL调优最佳实践" ✓                            │
│                                                             │
│  文本检索 → "数据库性能优化指南" ✓                          │
│           → "索引设计原则" ✓                               │
│                                                             │
│  合并去重 → ["数据库性能优化指南", "SQL调优最佳实践",        │
│             "索引设计原则"]                                  │
│                                                             │
│  Reranker → 按相关性排序                                     │
│           1. "数据库性能优化指南" (0.95)                     │
│           2. "SQL调优最佳实践" (0.88)                        │
│           3. "索引设计原则" (0.82)                           │
│                                                             │
│  优势: 既找到语义相关的，又找到关键词匹配的，                │
│        最后按相关性排序，准确率更高！                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## HyDE 查询优化详解

### 什么是 HyDE？

> **HyDE** = **H**ypothetical **D**ocument **E**mbeddings（假设性文档嵌入）

**核心思想**：

当用户问题与文档用词差异大时（**查询-文档语义鸿沟**），让 LLM 先生成一个"假设性回答"，再用这个回答去检索。

---

### 为什么需要 HyDE？

**问题场景**：

```
用户问题: "怎么让数据库跑得更快"

文档内容: "数据库性能优化方法包括：1. SQL调优 2. 索引优化 3. 参数调优..."

问题: 用户说"跑得更快"，文档说"性能优化"，用词不同，向量检索可能找不到！
```

**HyDE 解决方案**：

```
用户问题: "怎么让数据库跑得更快"
    ↓
LLM 生成假设性回答:
"要让数据库跑得更快，可以从以下几个方面优化：
 1. SQL语句调优
 2. 索引优化
 3. 数据库参数调优
 4. 硬件升级..."
    ↓
用假设性回答检索 → 找到 "数据库性能优化方法" 文档 ✓
```

---

### HyDE 实现流程

```
┌─────────────────────────────────────────────────────────────┐
│                     HyDE 流程图                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户问题: "怎么让数据库跑得更快"                            │
│       ↓                                                     │
│  直接检索: 无结果 ❌                                        │
│       ↓                                                     │
│  ┌─────────────────────────────────────┐                    │
│  │         HyDE 查询优化                │                    │
│  ├─────────────────────────────────────┤                    │
│  │                                     │                    │
│  │  1. 生成假设性回答                   │                    │
│  │     Prompt: "请回答这个问题：        │                    │
│  │             怎么让数据库跑得更快"    │                    │
│  │     LLM生成: "数据库性能优化方法..." │                    │
│  │                                     │                    │
│  │  2. 查询改写                         │                    │
│  │     Prompt: "将问题改写为3个相关查询"│                    │
│  │     LLM生成: ["数据库性能优化",       │                    │
│  │              "SQL调优方法",          │                    │
│  │              "索引优化技巧"]         │                    │
│  │                                     │                    │
│  │  3. 用生成的查询重新检索              │                    │
│  │     检索: "数据库性能优化方法"       │                    │
│  │     结果: ✓ 找到相关文档             │                    │
│  │                                     │                    │
│  └─────────────────────────────────────┘                    │
│       ↓                                                     │
│  LLM生成最终答案                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 核心代码实现

```python
# data_transformer.py 第 596-677 行
async def query_opt_process(question, user_id, session_id, vector_topk, text_topk, rerank_topk,
                            kb_id, version, lang, history_len, history, model_name):
    """HyDE 查询优化流程"""
    
    # ========== 1. 提示用户无相关知识 ==========
    yield {'type': 'progress', 'data': '知识库无相关知识'}
    yield {'type': 'progress', 'data': '进行查询优化'}
    
    query_list = []
    
    # ========== 2. HyDE：生成假设性回答 ==========
    hyde_messages = get_hyde_prompt(question, [], lang)
    
    hyde_result = ""
    async for item in generate_answer(hyde_messages, model_name):
        hyde_result += item
    
    if hyde_result:
        query_list.append(hyde_result)  # 加入查询列表
    
    yield {'type': 'progress', 'data': '假设性回答生成完成'}
    
    # ========== 3. 查询改写 ==========
    query_trans_messages = get_query_transform_prompt(question, [], lang)
    
    query_trans_result = ""
    async for item in generate_answer(query_trans_messages, model_name):
        query_trans_result += item
    
    # 解析改写的查询（格式：1. xxx\n2. xxx\n3. xxx）
    query_trans_results = query_trans_result.split('\n')
    for sub_query in query_trans_results:
        # 提取 "1. " 后面的内容
        query_match = re.search(r'^\d+\.\s+', sub_query)
        if query_match:
            query_list.append(sub_query[query_match.span()[1]:].strip())
    
    yield {'type': 'progress', 'data': f'查询优化后相关问题生成完成，数量为{len(query_list)}'}
    
    # ========== 4. 用优化后的查询重新检索 ==========
    score_list = []
    res_list = []
    
    for query in query_list:
        # 用每个查询去检索
        res_dict = await search(query, user_id, session_id, vector_topk, text_topk, 
                               rerank_topk, kb_id, version, lang, history_len)
        search_res = res_dict.get('search_res', [])
        
        for answer in search_res:
            score_list.append(answer['score'])
            res_list.append(answer)
    
    yield {'type': 'progress', 'data': f'查询优化检索完成，相关知识数量为{len(res_list)}'}
    
    # ========== 5. 按分数排序，取 Top-K ==========
    if res_list:
        zipped = zip(score_list, res_list)
        sort_zipped = sorted(zipped, key=lambda x: x[0], reverse=True)
        sort_result = zip(*sort_zipped)
        _, sorted_list = [list(x) for x in sort_result]
        sorted_list = sorted_list[:rerank_topk]
    
    # ========== 6. LLM 生成最终答案 ==========
    yield {'type': 'progress', 'data': '开始生成答案'}
    async for item in llm_generation(question, sorted_list, model_name, history, lang):
        yield item
```

---

### Prompt 设计

#### HyDE Prompt

```python
def get_hyde_prompt(question, history, lang):
    """生成假设性回答的 Prompt"""
    
    if lang == "zh":
        prompt = f"""请回答以下问题，提供详细的解释：

问题：{question}

请给出全面的回答："""
    else:
        prompt = f"""Please answer the following question with detailed explanation:

Question: {question}

Please provide a comprehensive answer:"""
    
    return [{"role": "user", "content": prompt}]
```

**示例**：

```
输入: "怎么让数据库跑得更快"

LLM生成假设性回答:
"要让数据库跑得更快，可以从以下几个方面进行优化：

1. SQL语句调优：优化慢查询，避免全表扫描
2. 索引优化：为常用查询字段创建索引
3. 数据库参数调优：调整内存、连接数等参数
4. 硬件升级：增加内存、使用SSD等
5. 架构优化：读写分离、分库分表等

具体方法如下：..."
```

#### 查询改写 Prompt

```python
def get_query_transform_prompt(question, history, lang):
    """查询改写的 Prompt"""
    
    if lang == "zh":
        prompt = f"""请将以下问题改写为3个不同的查询，用于在知识库中搜索相关信息。
每个查询占一行，格式为：1. 查询内容

原问题：{question}

改写后的查询："""
    else:
        prompt = f"""Please rewrite the following question into 3 different queries 
for searching in a knowledge base. Each query on a new line, format: 1. query content

Original question: {question}

Rewritten queries:"""
    
    return [{"role": "user", "content": prompt}]
```

**示例**：

```
输入: "怎么让数据库跑得更快"

LLM改写为:
1. 数据库性能优化方法
2. SQL调优技巧
3. 数据库索引优化
```

---

### HyDE 效果对比

```
┌─────────────────────────────────────────────────────────────┐
│                     HyDE 效果对比                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【不用 HyDE】                                               │
│  用户问题: "怎么让数据库跑得更快"                            │
│  直接检索: 无结果 ❌                                        │
│  原因: "跑得更快" 和 "性能优化" 向量距离远                   │
│                                                             │
│  【用 HyDE】                                                 │
│  用户问题: "怎么让数据库跑得更快"                            │
│    ↓                                                        │
│  LLM生成假设性回答: "数据库性能优化方法包括..."              │
│    ↓                                                        │
│  用假设性回答检索: 找到 "数据库性能优化指南" ✓              │
│    ↓                                                        │
│  生成最终答案: "要让数据库跑得更快，可以..."                 │
│                                                             │
│  优势: 弥合了用户用词和文档用词的语义鸿沟                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 一句话总结

> **多路召回** = 向量检索（语义）+ 文本检索（关键词）+ Reranker（重排序），提升召回率和准确率。
> 
> **HyDE** = 用户问题 → LLM生成假设性回答 → 用回答检索，解决查询-文档语义鸿沟问题，让检索更智能！
