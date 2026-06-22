# 02 - RAG 问答链

## 总体流程

```
用户提问
  → 安全检测（DFA 敏感词 + XLNet 微调分类器）
  → 向量检索（BGE-large 微调，1024 维，L2 距离）
  → 文本检索（BM25 全文检索，关键词兜底）
  → 重排序（BGE-reranker 微调，过滤 score<0 的结果）
  → 如果有结果 → LLM 生成答案（SSE 流式输出）
  → 如果无结果 → HyDE（LLM 编假设答案再检索）+ 查询改写（拆 3 个子问题分别检索）
```

## 检索管道源码位置

核心检索逻辑在 `GaussMaster/server/web/data_transformer.py` 的 `search()` 函数：

```python
# 三阶段混合检索
retriever = BaseRetriever(gaussdb, global_vars.reranker_model)

# 阶段1：向量检索
vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)

# 阶段2：BM25 文本检索
text_result = retriever.search_text_result_gaussdb(question, text_topk, version)

# 阶段3：重排序
reranker_scores, reranker_result = await retriever.reranker_search_result(
    question, vector_result, text_result, rerank_topk)
```

## 安全检测（双层）

| 层 | 方法 | 覆盖场景 |
|----|------|---------|
| 显式检测 | DFA 敏感词检测器（Trie 树，2 万+词库） | "drop table" 等显式危险命令 |
| 隐式检测 | 微调 XLNet 模型（<500ms 分类时间） | 隐式风险操作、数据隐私、偏见 |
| 提示安全 | 自动注入安全指南到提示模板 | 判断问题与 GaussDB 的相关性 |

安全检查同时应用于输入问题和生成的答案。

## 降级策略（无结果时）

当检索结果为空时，执行两步查询优化：

**1. HyDE（假设文档嵌入）**
> 让 LLM 生成一个假设性答案，用这个"假答案"作为查询向量重新检索。

```python
hyde_messages = get_hyde_prompt(question, [], lang)
hyde_result = await generate_answer(hyde_messages, model_name)
# 用 hyde_result 做向量嵌入，重新检索
```

**2. 查询改写**
> 让 LLM 将原始问题拆分为 3 个子问题，分别检索。

```python
query_trans_messages = get_query_transform_prompt(question, [], lang)
query_trans_result = await generate_answer(query_trans_messages, model_name)
# 对每个子问题分别检索
```

## 提示模板体系

所有提示模板在 `GaussMaster/utils/prompt_util.py`，包含中英文双语版本：

| 模板 | 用途 |
|------|------|
| `INFER_SYSTEM_TMPL` | 主 QA 提示（判断相关性 → 提取答案） |
| `HYDE_SYSTEM_TMPL` | HyDE 假设文档生成 |
| `QUERY_TRANSFORM_SYSTEM_TMPL` | 问题拆分为 3 个子问题 |
| `MULTI_QUERY_SYSTEM_TMPL` | 多视角查询生成 |
| `QUERY_ROUTER_SYSTEM_TMPL` | 问题分类（敏感/不相关/GaussDB） |
| `DOCUMENT_COMPRESS_SYSTEM_TMPL` | 文档压缩/关键词提取 |

## 与 LangChain RAG 的差异

| 方面 | LangChain 典型做法 | GaussMaster 实际做法 |
|------|-------------------|-------------------|
| 检索器 | `VectorStoreRetriever` | 自研 `BaseRetriever` + `GaussDB` 类 |
| 嵌入 | `OpenAIEmbeddings` / `HuggingFaceEmbeddings` | 自研 `OnlineEmbedding`（HTTP 服务） |
| 向量存储 | Chroma / Pinecone / Milvus | openGauss（floatvector + GSDiskANN） |
| 文档分割 | `RecursiveCharacterTextSplitter` | 自研 DNN 语义分块（表格/代码不切割） |
| 重排序 | `ContextualCompressionRetriever` | 自研 `OnlineReranker`（HTTP 服务） |
| 查询优化 | `MultiQueryRetriever` | 自研 HyDE + 查询改写 |

## 知识库构建流程

1. **多源解析**：不同文档类型（.md, .docx）用不同解析逻辑，保留 Markdown 层级标题
2. **语义分块**：DNN 模型分块，块大小可变，单个表格/代码片段不被切割
3. **文字去重**：文本内容哈希值全局去重
4. **元信息增强**：每块标注版本号、前后块 UUID（用于相邻拼接）
