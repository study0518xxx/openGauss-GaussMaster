# query_opt_process 详解

## 一句话解释

**用 LLM 生成"假设性答案"和"子问题"，然后用这些增强的查询去检索知识库，提高召回率。**

---

## 完整流程图

```
用户问题: "如何优化数据库性能？"
              │
              ▼
┌─────────────────────────────────────────┐
│  Step 1: HyDE 生成假设性答案            │
│  ┌───────────────────────────────────┐  │
│  │ LLM 生成一个"假答案"               │  │
│  │ "优化数据库性能需要：1.创建索引..." │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  Step 2: Query Transform 分解子问题      │
│  ┌───────────────────────────────────┐  │
│  │ LLM 分解成多个子问题：              │  │
│  │ 1. 如何创建索引？                   │  │
│  │ 2. 如何配置缓存？                   │  │
│  │ 3. 如何分析慢查询？                 │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  Step 3: 多查询检索                      │
│  ┌───────────────────────────────────┐  │
│  │ 原始问题 + 假设答案 + 3个子问题     │  │
│  │ = 5 个查询同时检索知识库            │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  Step 4: 合并结果排序                    │
│  返回最相关的 top-k 条知识               │
└─────────────────────────────────────────┘
              │
              ▼
         LLM 生成最终答案
```

---

## 核心代码解析

### Step 1: HyDE 生成假设性答案

**位置：** `GaussMaster/server/web/data_transformer.py` 第 609-612 行

```python
hyde_messages = get_hyde_prompt(question, [], lang)
hyde_result = ""
async for item in generate_answer(hyde_messages, model_name):
    hyde_result += item
if hyde_result:
    query_list.append(hyde_result)  # 把假设答案加入查询列表
```

**HyDE Prompt 模板：**
```
你是 GaussDB 数据库专家，
请根据用户问题生成一个详细的中文答案。

用户问题: {question}
```

**为什么叫 HyDE？**
- **Hypothetical Document Embeddings**（假设性文档嵌入）
- 不直接搜问题，而是让 LLM 先写一个"假答案"
- 用这个"假答案"去检索，往往能找到更多相关知识

---

### Step 2: Query Transform 分解子问题

**位置：** `GaussMaster/server/web/data_transformer.py` 第 616-629 行

```python
query_trans_messages = get_query_transform_prompt(question, [], lang)
query_trans_result = ""
async for item in generate_answer(query_trans_messages, model_name):
    query_trans_result += item

# 按行分割，提取子问题
query_trans_results = query_trans_result.split('\n')
for sub_query in query_trans_results:
    query_list.append(sub_query.strip())  # 多个子问题加入查询列表
```

**Query Transform Prompt 模板：**
```
你是 GaussDB 数据库专家，
请将用户问题分解成 3 个相关的子问题。

用户问题: {question}
```

---

### Step 3: 多查询检索

**位置：** `GaussMaster/server/web/data_transformer.py` 第 645-651 行

```python
for query in query_list:
    res_dict = await search(query, ...)  # 每个查询都去检索
    for answer in res_dict.get('search_res', []):
        score_list.append(answer['score'])
        res_list.append(answer)
```

**所有查询的检索结果合并：**

```
原始问题 → 检索结果 A (score: 0.9)
假设答案 → 检索结果 B (score: 0.8)
子问题1  → 检索结果 C (score: 0.7)
子问题2  → 检索结果 D (score: 0.6)
子问题3  → 检索结果 E (score: 0.5)
                    ↓
            合并去重，按 score 排序
                    ↓
         取 top-k 作为上下文
```

---

### Step 4: 生成最终答案

**位置：** `GaussMaster/server/web/data_transformer.py` 第 673-674 行

```python
async for item in llm_generation(question, sorted_list, model_name, history, lang):
    yield item
```

---

## 为什么需要查询优化？

| 原始问题 | 假设答案 | 分解后的子问题 |
|----------|----------|----------------|
| "如何优化性能" | "优化性能包括：1.索引优化..." | "如何创建索引" |
| 问题笼统 | 答案具体 | 问题细化 |

**好处：**
1. **召回率更高** - 假设答案可能包含原问题没提到的关键词
2. **覆盖面更广** - 子问题覆盖不同角度
3. **语义理解更深** - LLM 理解了问题本质

---

## 核心函数列表

| 函数 | 位置 | 作用 |
|------|------|------|
| `query_opt_process` | data_transformer.py:596 | 查询优化主函数 |
| `get_hyde_prompt` | prompt_util.py:361 | 构建 HyDE 提示词 |
| `get_query_transform_prompt` | prompt_util.py:375 | 构建查询转换提示词 |
| `generate_answer` | - | 调用 LLM 生成答案 |
| `search` | - | 检索知识库 |

---

## Prompt 模板

### HyDE 系统提示词（中文）

```python
HYDE_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的
【原始问题】来生成【中文答案】，请包含尽可能多的关键细节。"""
```

### Query Transform 系统提示词（中文）

```python
QUERY_TRANSFORM_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户
提出的【原始问题】生成3个相关的【子问题】。目标是将【原始问题】分解成一系列可以
独立回答的【子问题】。"""
```

---

## 总结

| 阶段 | 作用 | 输出 |
|------|------|------|
| **HyDE** | LLM 生成假设性答案 | "假答案"文本 |
| **Query Transform** | LLM 分解成子问题 | 3 个子问题 |
| **多查询检索** | 每个查询都去搜知识库 | 多个检索结果 |
| **合并排序** | 去重 + 按分数排序 | top-k 结果 |
| **LLM 生成** | 基于检索结果生成答案 | 最终回答 |

**一句话：`query_opt_process` 就是用 LLM "脑补" 增强查询能力，让检索更准更全！**
