# 第五步：Demo 与原项目 GaussMaster 对比

## 总体结论

**核心逻辑一一对应，基础设施全部降级。** Demo 保留了原项目最关键的 5 步流程（分块→向量化→检索→工具调用→SSE 流式），但为了本地可跑，把数据库、工具、安全层等重依赖全换了轻量替代。

---

## 一、核心流程完全一致的模块

| 层 | Demo 文件 | 原项目文件 | 相同点 |
|----|---------|----------|--------|
| 文档分块 | `loader.py`（~65 行） | `utils/split_util_md.py`（776 行自研） | chunk_size=500、标题驱动层次化分块、overlap=50 |
| 向量化 | `embedder.py`（~45 行） | `utils/retriever_util.py:OnlineEmbedding` | BGE-large-zh、1024 维、L2 归一化 |
| 向量检索 | `retriever.py`（~100 行） | `gaussdb_vector.py:GaussDB` | 相似度搜索、topk=3 |
| 工具注册 | `tools/registry.py`（~130 行） | `common/plugins/registry.py` + `common/plugins/param.py` | Param 类、@register 装饰器、validate_params() 确定性校验 |
| 工具调用 | `agent.py`（~110 行） | `llms/executor.py` + `multiagents/agents/dba.py` | 阶段一选工具→阶段二填参数→校验→执行→总结 |
| 对话记忆 | `memory.py`（~34 行） | `global_vars.py:SESSION_QA_HISTORY` + `dao_interaction_memory.py` | max_rounds=3、pop(0) 淘汰、注入 prompt |
| Web 层 | `main.py`（~120 行） | `controllers/core.py` 完整 Web 层 | text/event-stream、keep-alive、no-cache |
| 意图路由 | `main.py:is_tool_query()` | LLM 分类 | 工具类走 Agent，知识类走 RAG |
| LLM 调用 | `llm_client.py`（~75 行） | `server/web/data_transformer.py:generate_answer()` | stream=True、OpenAI 兼容格式 |

---

## 二、Demo 不做的东西

| 原项目有 | Demo 替代方案 | 放弃原因 |
|---------|-------------|---------|
| **openGauss + GSDiskANN** 向量数据库 | Chroma（`chromadb.PersistentClient`） | 开箱即用，不用装数据库 |
| **BM25 全文检索** + 向量混合检索 | 仅向量检索 | BM25 依赖 openGauss 的 `###` 操作符 |
| **21 个真实 DBMind 工具**（CPU、磁盘、死锁、复制延迟…） | 3 个模拟工具（`get_cpu_usage`、`get_slow_queries`、`get_connections`），返回假数据 | 无法连接真实数据库集群 |
| **多 Agent 协同诊断**（DBA Agent + 安全 Agent + 优化 Agent） | 单 Agent（`agent.py`） | Demo 问题复杂度不需要 |
| **HyDE 查询改写 + 多路召回降级策略** | 单路向量检索 + 距离阈值拒答 | 简化检索管道 |
| **DFA 敏感词过滤 + XLNet 安全检测** | `RELEVANCE_THRESHOLD = 0.5` 距离阈值 | Demo 不面向真实用户 |
| **盘古大模型 / 多模型切换** | 仅 DeepSeek（`deepseek-v4-flash`） | 降低 API 成本 |
| **Vue.js 前端** | 无前端，纯 `curl` + Swagger `/docs` | 聚焦后端逻辑 |
| **MetaDatabase + qa_record** 问答历史持久化 | `memory.py` 纯内存，重启丢失 | 简化存储 |
| **AES 加密存储**（API Key 等敏感配置） | `.env` 明文 | Demo 无生产敏感数据 |
| **用户管理 / RBAC 权限 / 多会话** | 单人使用，无用户概念 | 不涉及 |
| **HTTP 嵌入服务**（内网多服务共享 BGE 模型） | `sentence-transformers` 本地加载 | Demo 只有自己 |

---

## 三、逐模块详细对比

### 3.1 文档分块

```
原项目: split_util_md.py (776 行自研)
  支持: Markdown 标题驱动、代码块保护、表格保护、latex 公式保护
  分块器: 自研的 PrioritySplitter

Demo: loader.py (65 行)
  支持: Markdown 标题驱动、代码块保护（LangChain 内置）
  分块器: LangChain RecursiveCharacterTextSplitter
  separators = ["\n## ", "\n### ", "\n", " ", ""]
  chunk_size=500, chunk_overlap=50
```

### 3.2 向量化

```
原项目: OnlineEmbedding (HTTP 服务)
  方式: 内网部署 HTTP 嵌入服务，多服务共享
  模型: BAAI/bge-large-zh-v1.5
  维度: 1024

Demo: Embedder (本地加载)
  方式: sentence-transformers 本地跑模型
  模型: 同上
  维度: 同上
  首次运行下载 1.3GB 模型，之后缓存
```

### 3.3 向量存储

```
原项目: openGauss + GSDiskANN 插件
  SQL: SELECT * FROM kb ORDER BY vector <-> query_vec LIMIT 3
  索引: GSDiskANN 磁盘优化的 ANN 索引
  持久化: openGauss 表

Demo: Chroma
  方式: chromadb.PersistentClient(path="./chroma_db")
  距离: metadata={"hnsw:space": "cosine"}
  索引: HNSW 图索引
  持久化: chroma_db/ 目录
```

### 3.4 工具注册表

```
原项目: common/plugins/registry.py + common/plugins/param.py
  装饰器: @base_tools(name=..., description=..., params=[...])
  校验: inspect.signature + has_correct_params()
  权限: 角色-工具权限映射
  环境: dev/test/staging 环境切换

Demo: tools/registry.py
  装饰器: @registry.register(name=..., description=..., params=[...])
  校验: validate_params()（多余丢弃、缺失提示）
  权限: 无
  环境: 无
```

### 3.5 两阶段工具调用

```
原项目: llms/executor.py + multiagents/agents/dba.py
  准确率: 63维→(21维+3维) 拆分后 95%+
  重试: 3 次重试 + 降级策略
  日志: MetaDatabase qa_record 完整记录

Demo: agent.py
  准确率: 3维→(3维+1维) 拆分（原理相同）
  重试: 无
  日志: print() 控制台
```

---

## 四、面试应该怎么说

**标准话术**（每个模块 1-2 分钟）：

| 打开哪个文件 | 讲什么 |
|------------|--------|
| `loader.py` | "分块核心逻辑和 GaussMaster 一样——chunk_size=500、优先按标题切。原项目是 776 行自研分块器，Demo 用的是 LangChain 现成的，但参数和思路完全一致。" |
| `embedder.py` | "都用 BGE-large-zh，1024 维。原项目内网部署了 HTTP 嵌入服务给多服务共享，Demo 本地 sentence-transformers 跑。L2 归一化让余弦退化成点积——这一点原项目和 Demo 一样。" |
| `retriever.py` | "检索流程一样——向量化查询→相似度搜索→返回 Top-3。原项目底层是 openGauss 的 `<->` L2 距离算子加 GSDiskANN 索引，Demo 用 Chroma 的 HNSW+cosine，概念完全等价。" |
| `tools/registry.py` | "工具注册表从原项目 1:1 搬过来的。Param 类、@register 装饰器、validate_params()——多余丢弃、缺失提示——原项目还加了角色权限映射，Demo 砍掉了。" |
| `agent.py` | "两阶段工具调用是 GaussMaster 的核心。21 个工具 × 3 个参数 = 63 维，一次让 LLM 选准确率只有 60%。拆成两阶段——先选工具（21 维）再填参数（3 维），准确率提到 95%+。Demo 只有 3 个工具但原理一模一样。" |
| `main.py` + SSE | "FastAPI 三个路由，SSE 流式输出用的 `text/event-stream` + `keep-alive` + `no-cache`——三个 header 和 GaussMaster 源码完全一致。" |
| 安全防护 | "原项目有三层——DFA 敏感词 → XLNet 语义安全 → 内容审核。Demo 用 `RELEVANCE_THRESHOLD=0.5` 距离阈值加一层 LLM 自查，简化但思路相通——在检索结果进 LLM 之前先过滤。" |

---

## 五、数字速查卡

| 概念 | Demo | 原项目 | 记忆要点 |
|------|------|--------|---------|
| 块大小 | 500 | 500 | `PROPER_BLOCK_LENGTH` |
| 重叠 | 50 | 50 | 块间过渡不截断 |
| 向量维度 | 1024 | 1024 | BGE-large-zh |
| 检索条数 | topk=3 | topk=3 | 送 LLM 的上下文块数 |
| 记忆轮数 | 3 | 3 | `history_len` / `max_rounds` |
| 距离阈值 | 0.5 | - | 向量检索相关性判定 |
| 工具数量 | 3 | 21 | 模拟 vs 生产 |
| 两阶段准确率 | - | 60%→95% | 63维拆成21+3维 |
