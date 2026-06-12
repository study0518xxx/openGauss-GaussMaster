# GaussMaster RAG 完整流程详解

## 一、整体架构概览

```
用户问题
  │
  ▼
ask_gauss() ──────────────────────────────────────────────────────────┐
  │                                                                    │
  ├─ [1] 参数验证                                                      │
  │   • question, user_id, session_id, model_name, version, lang...    │
  │                                                                    │
  ├─ [2] 安全检查 ────────────────────┐                                │
  │   • DFA敏感词检测                  │ 安全敏感问题 ──► 直接拒答      │
  │   • 政治、恐怖、个人信息等          │                                │
  │                                   ▼                                │
  ├─ [3] 直接检索 ────► search() ──────────────────────────────────┐   │
  │   │                                                             │   │
  │   ├─ 向量检索 (search_vector)                                   │   │
  │   ├─ 文本检索 (search_text)                                     │   │
  │   └─ 重排序 (reranker)                                          │   │
  │                               ▼                                 │   │
  ├─ [4] 检索结果判断 ────────────────────────────────────────────┐ │   │
  │   │ 有结果 ──────► llm_generation() ──────────┐               │ │   │
  │   │ 无结果 ──────► query_opt_process()────────┘               │ │   │
  │   │                                                             │ │   │
  │   ├─ LLM 流式生成答案                                           │ │   │
  │   └─ 返回完整响应 + 记录QA                                      │ │   │
  └───────────────────────────────────────────────────────────────┘ │   │
                                                                    │   │
                                                                    ▼   ▼
```

## 二、核心调用链路

### 2.1 `ask_gauss()` 主流程

**文件位置**: `server/web/data_transformer.py` (L448-L566)

**入口参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| question | str | 用户问题 |
| user_id | str | 用户标识 |
| session_id | str | 会话标识 |
| switch | bool | 是否使用检索增强 |
| vector_topk | int | 向量检索返回数量 [1,10] |
| text_topk | int | 文本检索返回数量 [1,10] |
| rerank_topk | int | 重排后返回数量 [1,10] |
| kb_id | int | 知识库ID (0=系统知识库) |
| version | str | GaussDB版本号 |
| model_name | str | LLM模型名 |
| lang | str | 语言 (zh/en) |
| history_len | int | 历史对话长度 [0,3] |
| model_config | dict | 模型配置 |

**流程步骤**:

```python
# [1] 参数验证 (L451-L473)
# 检查所有参数合法性，不合法则抛出 ValueError

# [2] 安全检查 (L476-L488)
if safety_check and DFA_DETECTOR.is_unsafe_text(question):
    yield 拒答消息 ("作为一个 GaussDB 专家，我无法回答与 GaussDB 无关的安全敏感话题！")

# [3] 直接检索 (L514-L518)
yield "问题检索中..."
res_dict = await search(question, user_id, session_id, vector_topk, text_topk,
                        rerank_topk, kb_id, version, lang, history_len)

# [4] 分支判断 (L527-L550)
if not search_res:
    # 无结果 ──► 查询优化
    await query_opt_process(...)
else:
    # 有结果 ──► 直接生成
    await llm_generation(...)

# [5] 完成并记录 (L551-L566)
yield complete_dict (包含 time, question_id, answer_id)
gaussdb_vector.insert_qa_record(qa_dict)  # 记录QA到数据库
```

---

### 2.2 `search()` 检索流程

**文件位置**: `server/web/data_transformer.py` (L183-L256)

这是 **RAG 核心检索阶段**，包含三个子步骤：

#### 阶段 1: 向量检索

```python
vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)
```

**底层实现**: `common/metadatabase/dao/gaussdb_vector.py` (L177-L198)

**执行流程**:
1. 调用在线 Embedding 模型将问题转换为 1024 维向量
2. 使用 GSDiskANN 向量索引进行近似最近邻搜索
3. 按 L2 距离排序，返回 topk 结果

**SQL 示例**:
```sql
SELECT * FROM knowledge_table
WHERE version='5.0'
ORDER BY text_vector <-> '[0.1, 0.2, ..., 0.1024]'
LIMIT vector_topk
```

**关键技术**:
- **距离度量**: L2 距离 (`<->` 运算符)
- **索引类型**: GSDiskANN (华为自研向量索引)
- **向量维度**: 1024 维
- **索引配置**: `pq_nseg=1024, pq_nclus=16, queue_size=100, num_parallels=30`

---

#### 阶段 2: 文本检索

```python
text_result = retriever.search_text_result_gaussdb(question, text_topk, version)
```

**底层实现**: `common/metadatabase/dao/gaussdb_vector.py` (L200-L213)

**执行流程**:
1. 使用 BM25 算法进行全文检索
2. 在配置的 bm25_field 字段上搜索
3. 按相关性分数降序排序，返回 topk 结果

**SQL 示例**:
```sql
SELECT /*+ no tablescan("knowledge_table")*/ *
FROM knowledge_table
WHERE version='5.0'
ORDER BY bm25_fields ### '用户问题' desc
LIMIT text_topk
```

**关键技术**:
- **检索算法**: BM25 (最佳匹配25)
- **BM25字段**: 由 `kb_config.KT_TABLE_CONFIG.bm25_field` 配置
- **Hint**: `no tablescan` 强制使用索引扫描

---

#### 阶段 3: 重排序

```python
reranker_scores, reranker_result = await retriever.reranker_search_result(
    question, vector_result, text_result, rerank_topk
)
```

**底层实现**: `utils/retriever_util.py` (L154-L164)

**执行流程**:
1. **去重合并**: `dedup_list = list(set(vector_result + text_result))`
2. **构造配对**: `pairs = [[question, result['text']] for result in dedup_list]`
3. **调用重排模型**: `scores = await reranker.compute_score(pairs)`
4. **降序排序**: `sorted(zip(scores, dedup_list), reverse=True)`
5. **过滤负分**: 跳过 score < 0 的结果
6. **截取 topk**: 返回前 rerank_topk 个结果

**重排模型**:
- 类型: OnlineReranker (在线服务)
- 输入: (query, text) pairs
- 输出: 相关性分数 (越高越相关)

---

### 2.3 `query_opt_process()` 查询优化流程

**文件位置**: `server/web/data_transformer.py` (L596-L676)

**触发条件**: 当直接检索无结果时触发

**流程图**:
```
用户问题
  │
  ├─ [1] HyDE (假设性文档嵌入) ───────────────────┐
  │   • LLM 生成假设性答案                         │
  │   • 作为新的检索查询                           │
  │                                               ▼
  ├─ [2] 查询转换 (Query Transformation) ────────────┐
  │   • LLM 生成 3 个子问题                           │
  │   • 分解原始问题                                  │
  │                                                  ▼
  ├─ [3] 多路检索 ─────────────────────────────────────┐│
  │   • 对每个优化后的查询执行 search()                ││
  │   • 合并所有检索结果                               ││
  │                                                    ▼│
  ├─ [4] 结果排序 ──────────────────────────────────────┘
  │   • 按重排分数降序排序
  │   • 截取 rerank_topk
  │
  └─ [5] LLM 生成答案
```

**详细步骤**:

**步骤 1: HyDE (假设性文档嵌入)** (L602-L615)
```python
# 构造 HyDE 提示词
hyde_messages = get_hyde_prompt(question, [], lang)
# 示例: "你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】来生成【中文答案】"

# 生成假设性答案
hyde_result = ""
async for item in generate_answer(hyde_messages, model_name):
    hyde_result += item
query_list.append(hyde_result)
```

**步骤 2: 查询转换** (L616-L631)
```python
# 构造查询转换提示词
query_trans_messages = get_query_transform_prompt(question, [], lang)
# 示例: "生成3个相关的【子问题】，将【原始问题】分解成可以独立回答的【子问题】"

# 生成子问题
query_trans_result = await generate_answer(query_trans_messages, model_name)
query_trans_results = query_trans_result.split('\n')
for sub_query in query_trans_results:
    # 解析有序列表格式: "1. 问题内容"
    query_match = re.search(r'^\d+\.(\s+)', sub_query)
    if query_match:
        query_list.append(sub_query[query_match.span()[1]:].strip())
```

**步骤 3: 多路检索** (L645-L651)
```python
for query in query_list:
    res_dict = await search(query, ...)  # 对每个优化查询执行完整检索
    search_res = res_dict.get('search_res', [])
    for answer in search_res:
        score_list.append(answer['score'])
        res_list.append(answer)
```

**步骤 4: 结果排序** (L658-L671)
```python
# 按分数降序排序
zipped = zip(score_list, res_list)
sort_zipped = sorted(zipped, key=lambda x: x[0], reverse=True)
sort_result = zip(*sort_zipped)
_, sorted_list = [list(x) for x in sort_result]
sorted_list = sorted_list[:rerank_topk]
```

---

### 2.4 `llm_generation()` 答案生成流程

**文件位置**: `server/web/data_transformer.py` (L569-L584)

```python
# [1] 返回检索结果给前端
yield {'type': 'refrences', 'data': json.dumps(search_res, ensure_ascii=False)}

# [2] 构造推理提示词
status, messages = create_infer_prompt_direct(question, search_res, history, lang)

# [3] 流式生成答案
answer = ""
async for item in generate_answer(messages, model_name):
    answer += item
    yield {'type': 'answer', 'data': answer}
```

**提示词构造** (`utils/prompt_util.py` L517-L529):

**System Prompt (中文)**:
```
你是中文 GaussDB 数据库专家，给定【原始问题】和检索出来【相关上下文】，
你的任务是根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。
特别地，作为 GaussDB 数据库专家，你的职责是确保返回的【答案】与 GaussDB 数据库
的高度相关性、内容的安全性以及合法性。

让我们一步一步的思考，按照下面的步骤完成这个任务。
##步骤1## 判断【相关上下文】是否能够解答【原始问题】，不能则直接返回不相关；反之执行步骤2。
##步骤2## 从【相关上下文】中提取出相关内容，生成全面可靠的【答案】，返回【答案】。
```

**User Prompt (中文)**:
```
请根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。
> 【原始问题】：{question}
> 【相关上下文】：{context1}\n{context2}\n...
> 【答案】：
```

**LLM 调用方式**:

1. **本地模型**:
```python
async for item in global_vars.local_llm.invoke(messages):
    yield item
```

2. **在线模型**:
```python
url = global_vars.llm_config['online_llm'][model_name]['api_url']
headers = {"Accept": "text/event-stream", "Connection": "keep-alive"}
params = {'messages': messages}
# 流式请求
llm_generator = await thread_request_from_llm(url, headers, params)
```

---

## 三、数据库层面

### 3.1 表结构配置

**知识表 (KT_TABLE)**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| uuid | TEXT | 唯一标识 (UUID) |
| text | TEXT | 文本内容 (用于向量化的字段) |
| text_vector | floatvector(1024) | 1024维向量 |
| field | TEXT | 分类字段 |
| sub_field | TEXT | 子分类字段 |
| source | TEXT | 来源 |
| version | TEXT | GaussDB版本 |
| product_format | TEXT | 产品格式 |
| title | TEXT | 标题 |
| context | TEXT | 上下文 |
| keyword | TEXT | 关键词 |
| link | TEXT | 链接 |
| visualize | TEXT | 可视化标识 |
| prev_uuid | TEXT | 前一个片段UUID |
| next_uuid | TEXT | 后一个片段UUID |

### 3.2 索引类型

**向量索引**: GSDiskANN (华为自研近似最近邻索引)
```sql
CREATE INDEX ON knowledge_table
USING gsdiskann(text_vector l2)
WITH (
    pq_nseg=1024,
    pq_nclus=16,
    queue_size=100,
    num_parallels=30,
    enable_pq=true
)
```

**文本索引**: BM25
```sql
CREATE INDEX ON knowledge_table
USING bm25(bm25_field1, bm25_field2)
WITH (num_parallels=30)
```

---

## 四、完整调用时序图

```
时间轴 ─────────────────────────────────────────────────────────────►

[用户]
  │
  ▼ ask_gauss(question, user_id, session_id, ...)
      │
      ├─ [1] 参数验证
      ├─ [2] 安全检查 ──► (敏感) 拒答并返回
      │
      ▼ [3] search(question, vector_topk, text_topk, rerank_topk, ...)
          │
          │ ┌─ BaseRetriever.search_vector_result_gaussdb()
          │ │   ├─ embedding_function.query_embedding(question)
          │ │   │   └─ 调用在线Embedding服务，返回1024维向量
          │ │   │
          │ │   └─ gaussdb.search_vector()
          │ │       └─ SQL: SELECT * FROM table ORDER BY vector <-> ... LIMIT topk
          │ │           └─ 使用 GSDiskANN 向量索引
          │ │
          │ ├─ BaseRetriever.search_text_result_gaussdb()
          │ │   └─ gaussdb.search_text()
          │ │       └─ SQL: SELECT * FROM table ORDER BY bm25 ### 'query' desc LIMIT topk
          │ │           └─ 使用 BM25 全文索引
          │ │
          │ └─ BaseRetriever.reranker_search_result()
          │     ├─ dedup_list = list(set(vector_result + text_result))
          │     ├─ pairs = [[query, result['text']] for result in dedup_list]
          │     ├─ scores = await reranker.compute_score(pairs)
          │     │   └─ 调用在线重排模型
          │     ├─ sorted_list = sorted(zip(scores, dedup_list), reverse=True)
          │     └─ 过滤负分，截取 topk
          │
      ▼ [4] 检索结果判断
          │
          ├─ 有结果 ──► llm_generation()
          │   │
          │   ├─ yield {'type': 'refrences', 'data': json.dumps(search_res)}
          │   │
          │   ├─ create_infer_prompt_direct(question, search_res, history, lang)
          │   │   ├─ get_infer_prompt()
          │   │   │   ├─ System: "你是中文GaussDB专家..."
          │   │   │   └─ User: "请根据【相关上下文】生成【答案】..."
          │   │   └─ construct_messages()
          │   │       └─ 添加历史对话到 messages
          │   │
          │   └─ generate_answer(messages, model_name)
          │       ├─ if local_llm:
          │       │   └─ local_llm.invoke(messages)
          │       └─ else:
          │           └─ online_llm.stream_request(url, headers, params)
          │
          └─ 无结果 ──► query_opt_process()
              │
              ├─ [1] HyDE
              │   ├─ get_hyde_prompt(question, lang)
              │   ├─ generate_answer(hyde_messages, model_name)
              │   └─ 生成假设性答案，如"GaussDB支持分布式部署，包括..."
              │
              ├─ [2] QueryTransform
              │   ├─ get_query_transform_prompt(question, lang)
              │   ├─ generate_answer(query_trans_messages, model_name)
              │   └─ 生成3个子问题
              │
              ├─ [3] 多路检索
              │   └─ for query in query_list:
              │       └─ await search(query, ...)  # 对每个子问题执行完整检索
              │
              ├─ [4] 合并排序
              │   └─ sorted(zip(score_list, res_list), reverse=True)[:rerank_topk]
              │
              └─ [5] llm_generation(question, sorted_list, model_name, history, lang)
```

---

## 五、Prompt 模板体系

### 5.1 HyDE 提示词

**System (中文)**:
```
你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】来生成【中文答案】，
请包含尽可能多的关键细节。
```

**User (中文)**:
```
请根据用户提出的【原始问题】来生成【中文答案】。答案的长度不超过100。
【原始问题】：{question}
```

### 5.2 查询转换提示词

**System (中文)**:
```
你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】生成3个相关的【子问题】。
目标是将【原始问题】分解成一系列可以独立回答的【子问题】。
```

**User (中文)**:
```
请根据用户提出的【原始问题】生成3个相关的【子问题】。通过换行符来分割这些【子问题】。
【原始问题】：{question}
```

### 5.3 推理提示词

**System (中文)**:
```
你是中文 GaussDB 数据库专家，给定【原始问题】和检索出来【相关上下文】，
你的任务是根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。

让我们一步一步的思考，按照下面的步骤完成这个任务。
##步骤1## 判断【相关上下文】是否能够解答【原始问题】，不能则直接返回不相关；反之执行步骤2。
##步骤2## 从【相关上下文】中提取出相关内容，生成全面可靠的【答案】，返回【答案】。
```

**User (中文)**:
```
请根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。
> 【原始问题】：{question}
> 【相关上下文】：{context}
> 【答案】：
```

---

## 六、返回结果格式

### 6.1 检索结果格式

```python
{
    'search_res': [
        {
            'knowledge_id': 'uuid',
            'content': '文本内容',
            'field': '字段',
            'sub_field': '子字段',
            'source': '来源',
            'version': '版本',
            'product_format': '产品格式',
            'title': '标题',
            'visualize': '可视化',
            'link': '链接',
            'context': '上下文',
            'keyword': '关键词',
            'confidence': '置信度',
            'Top No.': 0,
            'score': 0.95,  # 重排分数
            'media': ''
        },
        ...
    ],
    'vector_search_time': 0.123456,  # 向量检索耗时(秒)
    'text_search_time': 0.234567,    # 文本检索耗时(秒)
    'rerank_search_time': 0.345678,  # 重排耗时(秒)
    'total_time': 0.456789,          # 总耗时(秒)
    'question_id': 'uuid'
}
```

### 6.2 流式返回格式

```python
# 进度消息
{'type': 'progress', 'data': '问题检索中...'}

# 检索结果引用
{'type': 'refrences', 'data': '[{...}, {...}]'}

# 答案流式生成
{'type': 'answer', 'data': 'GaussDB支持...'}

# 完成消息
{
    'type': 'complete',
    'data': {
        'time': 1.234567,
        'question_id': 'uuid',
        'answer_id': 'uuid'
    }
}
```

---

## 七、关键配置参数

### 7.1 检索参数

| 参数 | 范围 | 默认值 | 说明 |
|------|------|--------|------|
| vector_topk | [1, 10] | 3 | 向量检索返回数量 |
| text_topk | [1, 10] | 3 | 文本检索返回数量 |
| rerank_topk | [1, 10] | 5 | 重排后返回数量 |
| history_len | [0, 3] | 1 | 历史对话轮数 |

### 7.2 系统配置

| 配置项 | 说明 |
|--------|------|
| KB_TABLE_NAME | 知识库管理表名 |
| KT_TABLE_NAME | 知识内容表名前缀 |
| QA_TABLE_NAME | QA记录表名 |
| DS_TABLE_NAME | 数据源表名 |
| CUSTOM_KB_PREFIX | 自定义知识库表名前缀 |

### 7.3 向量索引配置

| 参数 | 值 | 说明 |
|------|-----|------|
| pq_nseg | 1024 | 向量维度 |
| pq_nclus | 16 | 聚类中心数 |
| queue_size | 100 | 队列大小 |
| num_parallels | 30 | 并行度 |
| enable_pq | true | 启用乘积量化 |

---

## 八、核心文件清单

| 文件路径 | 职责 |
|---------|------|
| `server/web/data_transformer.py` | RAG 主流程：ask_gauss, search, llm_generation, query_opt_process |
| `utils/retriever_util.py` | 检索器：BaseRetriever, OnlineEmbedding, OnlineReranker |
| `common/metadatabase/dao/gaussdb_vector.py` | 数据库操作：GaussDB, 向量检索, 文本检索 |
| `utils/prompt_util.py` | Prompt 模板：get_hyde_prompt, get_infer_prompt 等 |
| `common/configs/kb_config.py` | 知识库配置：表名、表结构 |
| `constants.py` | 常量定义：支持版本、语言、KB前缀等 |
