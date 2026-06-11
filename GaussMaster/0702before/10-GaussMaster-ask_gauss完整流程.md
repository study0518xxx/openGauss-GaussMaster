# GaussMaster ask\_gauss 完整流程详解

## 流程概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ask_gauss 完整流程                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 参数校验                                                                 │
│       ↓                                                                     │
│  2. 敏感词检测                                                               │
│       ├── 敏感 → 返回安全警告                                                 │
│       └── 正常 → 继续                                                        │
│       ↓                                                                     │
│  3. 直接检索 (search)                                                        │
│       ├── 向量检索 (语义相似度)                                               │
│       ├── 文本检索 (关键词匹配)                                               │
│       └── 重排序 (Reranker)                                                  │
│       ↓                                                                     │
│  4. 判断检索结果                                                             │
│       ├── 有结果 → LLM生成答案 (llm_generation)                               │
│       └── 无结果 → 查询优化 (query_opt_process) → HyDE技术重新检索             │
│       ↓                                                                     │
│  5. 保存记录到数据库                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

***

## 详细流程

### 1. 入口函数 ask\_gauss

**位置**: `data_transformer.py` 第 448 行

```python
async def ask_gauss(question, user_id, session_id, switch, vector_topk, text_topk, 
                    rerank_topk, kb_id, version, model_name, lang, history_len, model_config):
    """RAG 端到端问答流程"""
```

**主要步骤**:

```python
# 1. 参数校验（省略详细校验代码）
if not question:
    raise ValueError('question can not be empty.')
...

# 2. 敏感词检测
if global_vars.DFA_DETECTOR.is_unsafe_text(question):
    # 返回安全警告
    yield {'type': 'answer', 'data': '无法回答安全敏感话题！'}
    return

# 3. 直接检索
yield {'type': 'progress', 'data': '问题检索中...'}
res_dict = await search(question, user_id, session_id, vector_topk, text_topk,
                        rerank_topk, kb_id, version, lang, history_len)
search_res = res_dict['search_res']

# 4. 判断检索结果
if not search_res:
    # 无结果 → 查询优化
    async for item in query_opt_process(...):
        yield item
else:
    # 有结果 → LLM生成
    async for item in llm_generation(question, search_res, model_name, history, lang):
        yield item

# 5. 保存记录
gaussdb_vector.insert_qa_record(qa_dict)
```

***

### 2. 敏感词检测

**位置**: `ask_gauss` 第 476-488 行

```python
# 判断用户问题是否包含敏感的关键词
if (global_vars.configs.get(SECTION_SAFETY, 'safety_check').strip().upper() == 'TRUE'
        and global_vars.DFA_DETECTOR.is_unsafe_text(question)):
    
    # 返回安全警告，结束流程
    if lang == "zh":
        security_warn_zh = '作为一个 GaussDB 专家，我无法回答与 GaussDB 无关的安全敏感话题！'
        yield {'type': 'answer', 'data': security_warn_zh}
    ...
    return  # 直接返回，不再执行后续流程
```

**作用**: 安全防护，防止用户询问敏感话题

***

### 3. 直接检索 search

**位置**: `data_transformer.py` 第 183-256 行

```python
async def search(question, user_id, session_id, vector_topk, text_topk, rerank_topk, 
                 kb_id, version, lang, history_len):
    """多路召回：向量检索 + 文本检索 + 重排序"""
```

**核心流程**:

```
┌─────────────────────────────────────────────────────────────┐
│                        search 流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 确定知识库表名                                           │
│     ├── kb_id == 0 → 使用默认知识库                          │
│     └── kb_id != 0 → 使用自定义知识库                        │
│       ↓                                                     │
│  2. 创建检索器 BaseRetriever                                 │
│       ↓                                                     │
│  3. 向量检索 (语义相似度)                                     │
│     vector_result = await retriever.search_vector_result_gaussdb(
│         question, vector_topk, version)                     │
│       ↓                                                     │
│  4. 文本检索 (关键词匹配)                                     │
│     text_result = retriever.search_text_result_gaussdb(
│         question, text_topk, version)                       │
│       ↓                                                     │
│  5. 重排序 (Reranker)                                        │
│     reranker_scores, reranker_result = await retriever.reranker_search_result(
│         question, vector_result, text_result, rerank_topk)  │
│       ↓                                                     │
│  6. 组装结果                                                 │
│     return {'search_res': [...], 'question_id': 'xxx'}      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键代码**:

```python
# 1. 确定知识库
if kb_id == 0:
    table_name = kb_config.KT_TABLE_NAME + "_" + lang  # 默认知识库
else:
    table_name = CUSTOM_KB_PREFIX + str(kb_id)        # 自定义知识库

# 2. 获取数据库实例
gaussdb = get_db_instance(table_name, kb_config.KT_TABLE_CONFIG)

# 3. 创建检索器
retriever = BaseRetriever(gaussdb, global_vars.reranker_model)

# 4. 向量检索（语义相似度）
vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)

# 5. 文本检索（关键词匹配）
text_result = retriever.search_text_result_gaussdb(question, text_topk, version)

# 6. 重排序（Reranker）
reranker_scores, reranker_result = await retriever.reranker_search_result(
    question, vector_result, text_result, rerank_topk)

# 7. 组装返回结果
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

**多路召回说明**:

| 检索方式     | 原理              | 作用              |
| -------- | --------------- | --------------- |
| **向量检索** | Embedding 语义相似度 | 找到语义相关的文档       |
| **文本检索** | 关键词匹配           | 找到包含关键词的文档      |
| **重排序**  | Reranker 模型     | 对合并结果重新排序，提升准确率 |

***

### 4. 判断检索结果并处理

**位置**: `ask_gauss` 第 526-560 行

```python
# 获取历史对话
history = get_history_chat(user_id, session_id, history_len)
search_res = res_dict['search_res']

# 判断是否有检索结果
if not search_res:
    # ========== 无结果：查询优化（HyDE）==========
    async for item in query_opt_process(question, user_id, session_id, vector_topk, 
                                        text_topk, rerank_topk, kb_id, version, 
                                        lang, history_len, history, model_name):
        yield item
else:
    # ========== 有结果：LLM生成答案 ==========
    async for item in llm_generation(question, search_res, model_name, history, lang):
        yield item
```

***

### 5. LLM 生成答案 llm\_generation

**位置**: `data_transformer.py` 第 569-584 行

```python
async def llm_generation(question, search_res, model_name, history, lang):
    """LLM 生成答案（流式输出）"""
```

**流程**:

```python
# 1. 返回参考资料（可解释性）
yield {'type': 'refrences', 'data': json.dumps(search_res, ensure_ascii=False)}
yield {'type': 'progress', 'data': '检索完成'}

# 2. 构建 Prompt（包含检索结果和历史对话）
status, messages = create_infer_prompt_direct(question, search_res, history, lang)

# 3. 流式生成答案
yield {'type': 'progress', 'data': '答案生成中...'}
answer = ""
async for item in generate_answer(messages, model_name):
    answer += item
    yield {'type': 'answer', 'data': answer}  # 实时返回

yield {'type': 'progress', 'data': '答案生成完成'}
```

**输出格式**:

```json
// 参考资料
{"type": "refrences", "data": "[{...}, {...}]"}

// 进度提示
{"type": "progress", "data": "检索完成"}
{"type": "progress", "data": "答案生成中..."}

// 答案（流式，逐字返回）
{"type": "answer", "data": "根"}
{"type": "answer", "data": "根据"}
{"type": "answer", "data": "根据知"}
...

// 完成标记
{"type": "complete", "data": {"time": 2.5, "question_id": "xxx", "answer_id": "xxx"}}
```

***

### 6. 查询优化 query\_opt\_process（HyDE）

**位置**: `data_transformer.py` 第 596 行+

当直接检索无结果时，使用 **HyDE（Hypothetical Document Embeddings）** 技术优化查询：

```
┌─────────────────────────────────────────────────────────────┐
│                    query_opt_process 流程                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 提示用户无相关知识                                       │
│     yield {'type': 'progress', 'data': '知识库无相关知识'}    │
│       ↓                                                     │
│  2. HyDE：让 LLM 生成假设性回答                               │
│     hyde_answer = llm_call(get_hyde_prompt(question))        │
│       ↓                                                     │
│  3. 用假设性回答重新检索                                      │
│     search_res = await search(hyde_answer, ...)              │
│       ↓                                                     │
│  4. 生成最终答案                                             │
│     async for item in llm_generation(...):                  │
│         yield item                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**HyDE 原理**:

```
用户问题: "什么是ACID特性？"
    ↓
直接检索: 可能找不到（用户用词和文档用词不同）
    ↓
HyDE: 让 LLM 生成假设性回答
    "ACID是数据库事务的四个特性：原子性、一致性、隔离性、持久性..."
    ↓
用假设性回答检索: 能找到相关文档
    ↓
生成最终答案
```

***

### 7. 保存记录

**位置**: `ask_gauss` 第 565-566 行

```python
try:
    ...
    async for item in llm_generation(...):
        yield item
    ...
except Exception as e:
    raise Exception(f'can not get gauss qa result, because: {e}.')
finally:
    # 无论成功失败，都保存记录
    gaussdb_vector.insert_qa_record(qa_dict)
```

***

## 完整流程图

```
用户提问
    ↓
┌─────────────────┐
│   ask_gauss     │
│   参数校验       │
└────────┬────────┘
         ↓
┌─────────────────┐
│   敏感词检测     │
│   DFA_DETECTOR  │
└────────┬────────┘
         ↓
    ┌────┴────┐
    ↓         ↓
  敏感      正常
    ↓         ↓
返回警告    继续
         ↓
┌─────────────────┐
│   search        │
│   多路召回       │
├─────────────────┤
│ 1. 向量检索      │
│ 2. 文本检索      │
│ 3. 重排序        │
└────────┬────────┘
         ↓
    ┌────┴────┐
    ↓         ↓
  无结果    有结果
    ↓         ↓
┌────────┐  ┌─────────────────┐
│ query_ │  │  llm_generation │
│ opt_   │  │  LLM生成答案     │
│ process│  ├─────────────────┤
│ (HyDE) │  │ 1. 返回参考资料  │
├────────┤  │ 2. 构建Prompt   │
│ 1.生成 │  │ 3. 流式生成      │
│ 假设回答│  └────────┬────────┘
│ 2.重新 │           ↓
│ 检索   │      返回答案给用户
│ 3.生成 │           ↓
│ 答案   │    ┌─────────────┐
└───┬────┘    │  保存记录   │
    │         │  insert_qa  │
    └────┬────┘  │  _record  │
         └───────┴───────────┘
```

***

## 关键函数总结

| 函数                    | 位置                       | 作用            |
| --------------------- | ------------------------ | ------------- |
| `ask_gauss()`         | data\_transformer.py:448 | RAG 主流程，协调各环节 |
| `search()`            | data\_transformer.py:183 | 多路召回检索        |
| `llm_generation()`    | data\_transformer.py:569 | LLM 流式生成答案    |
| `query_opt_process()` | data\_transformer.py:596 | HyDE 查询优化     |
| `generate_answer()`   | data\_transformer.py:416 | 调用 LLM 生成     |

***

## 一句话总结

> `ask_gauss` 是完整的 RAG 流程：**敏感词检测 → 多路检索 → 判断结果 → 有结果直接生成 / 无结果 HyDE 优化 → 保存记录**。其中 `search` 实现了向量+文本+重排序的多路召回，是提升准确率的关键！

