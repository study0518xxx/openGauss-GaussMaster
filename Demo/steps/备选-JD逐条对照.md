# 面试要求逐条对照：GaussMaster 项目 + 补充解释

> JD 来源：AI Agent 开发工程师

---

## 要求 2：熟悉至少一种主流工程开发语言

### 项目体现

**Python 工程级开发**。GaussMaster 后端全部使用 Python，包括：

| 模块 | 用到的 Python 能力 |
|------|-------------------|
| FastAPI + Uvicorn | 自研 `HttpService` 抽象层封装，`@request_mapping` 装饰器解耦框架 |
| asyncio | 全异步——RAG 检索、LLM 调用、工具执行全部 `async/await` |
| psycopg2 + SQLAlchemy | 双数据库连接（psycopg2 直连向量库，SQLAlchemy ORM 连元数据库） |
| Registry 装饰器模式 | 工具注册（`@registry.register`）、LLM 注册（`@llm_registry`） |
| 自定义类继承体系 | `BaseLLM` → `Pangu`/`Chatglm`/`Baichuan`/`Llama3` 多态适配 |

### 补充解释（如果面试官问"为什么不选其他语言"）

> Python 在 AI 生态里库最全——`sentence-transformers`、`openai`、`chromadb`、`langchain-text-splitters` 都是 Python 优先。asyncio 的协程模型天然适合 LLM 调用的 IO 密集场景（等 API 返回时不阻塞其他请求）。如果做高并发 API 网关层，可以考虑 Go 或 Node.js，但核心 AI 逻辑层 Python 是最优解。

---

## 要求 3：大模型接口与请求模型

### 项目体现

**Chat Completions**（最基础的 LLM 调用）：

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
    temperature=0.7,
    stream=False
)
```

**流式响应（SSE）**：

```python
# LLM API 层 — stream=True 逐 token 收
response = self.client.chat.completions.create(stream=True)
for chunk in response:
    yield chunk.choices[0].delta.content

# HTTP 传输层 — StreamingResponse 逐 chunk 推
return StreamingResponse(generate(), media_type="text/event-stream",
                         headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
```

**Function Calling / Tool Calling**：GaussMaster **故意没用**原生 API，而是用提示工程实现——因为要统一适配 6 种模型。详见要求 4。

**上下文管理**：3 轮滑动窗口 `ConversationMemory`，`history.pop(0)` 淘汰。RAG 管道从 `qa_record` 表读历史，Agent 管道从 `SESSION_QA_HISTORY` 内存缓存读。

### 补充解释（项目中未涉及的）

**错误重试**：调用 LLM API 时最常见的错误是 429（限流）和 5xx（服务端错误）。标准做法是**指数退避重试**：

```python
import asyncio

async def call_llm_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await llm.chat(messages)
        except RateLimitError:
            wait = 2 ** attempt  # 等 1s → 2s → 4s
            await asyncio.sleep(wait)
        except ServerError:
            if attempt == max_retries - 1:
                raise  # 最后一次还失败就抛异常
            await asyncio.sleep(1)
```

**限流与成本控制**：

| 策略 | 做法 |
|------|------|
| 客户端限流 | `asyncio.Semaphore(n)` 限制并发请求数 |
| Token 预算 | 每次请求前估算 prompt token 数，超限截断 |
| 缓存 | 相同问题短期内不重复调 LLM，直接返回缓存答案 |
| 模型降级 | 高峰期用便宜的模型（如 DeepSeek），核心诊断用贵的模型（如盘古） |

**结构化输出**：OpenAI 的 `response_format={"type": "json_object"}` 可强制 LLM 输出合法 JSON。但 GaussMaster 没用——因为要兼容不支持此特性的模型（ChatGLM3、百川），改用 prompt 约束 + JSON 解析 + 校验兜底。

---

## 要求 4：AI Agent 核心机制

### 项目体现

**规划（Planning）**：GaussMaster 的 Agent 不是自由探索——是**诊断树引导的确定性路径**。每个故障类型对应一棵诊断树，树节点是具体工具，树路径是验证过的排查步骤。

```
诊断树示例（CPU 过高场景）:
  get_cpu_usage → 如果 > 80% →
    ├─ get_slow_queries → 如果有慢 SQL → explain_analyze → 索引建议
    └─ get_connections → 如果连接数 > 80% → 连接池建议
```

对比 LangGraph 的 ReAct 循环（LLM 每一步自由决定调哪个工具），诊断树的优势是**路径可预测、不会跳步骤**。

**反思（Reflection）**：GaussMaster 的多 Agent 协同诊断中，主 DBA Agent 调工具拿到结果后，会启动专家 Agent 交叉审查——相当于 "反思" 机制。比如慢 SQL 分析结果出来后，索引专家 Agent 会检查建议是否合理。

**工具调用**：两阶段方案（先选工具名，再填参数）。21 个工具 × 3 个参数 = 63 维搜索空间 → 拆成 21 维 + 3 维 → 准确率 60% → 95%+。

```
阶段一 prompt: "工具列表: get_cpu_usage(查CPU), get_slow_queries(查慢SQL)...
               用户: 查一下 db_001 的 CPU
               请只输出工具名"
阶段二 prompt: "工具 schema: get_cpu_usage 参数: instance(str,必填)
               用户: 查一下 db_001 的 CPU
               请输出 JSON: {\"instance\": \"db_001\"}"
```

**工作流编排**：RAG 管道本身就是编排——安全检测 → 混合检索 → reranker → HyDE 降级 → LLM 生成。每步的输出是下一步的输入。

**记忆机制**：

| 记忆类型 | GaussMaster 实现 |
|---------|-----------------|
| 短期记忆 | `SESSION_QA_HISTORY` 内存缓存，3 轮滑动窗口 |
| 长期记忆 | `qa_record` 表（RAG 管道）、`tb_interaction_memory` 表（Agent 管道，AES-256 加密） |
| 工具记忆 | `SESSION_TOOL_HISTORY` 记录 "当前会话正在调哪个工具" |

**上下文管理**：检索到的文档块 + 对话历史 + system prompt + 用户问题 → 拼接成完整 prompt。每块标注 `prev_uuid` / `next_uuid` 用于相邻扩展。

### 补充解释（项目中未涉及的）

**多智能体协作的常见模式**：

| 模式 | 说明 | 举例 |
|------|------|------|
| 顺序执行 | Agent A → Agent B → Agent C | 先分析 → 再诊断 → 最后总结 |
| 辩论 | 两个 Agent 各自给出意见，第三个裁决 | 安全审查 Agent vs 优化 Agent |
| 分层 | 主 Agent 分配任务，子 Agent 执行 | Manager → Worker 模式 |
| 投票 | 多个 Agent 独立判断，多数胜出 | 代码审查场景 |

**ReAct 循环**（LangChain/LangGraph 的默认模式）：
```
Thought: 用户问 CPU 过高 → 我需要先查 CPU 使用率
Action: get_cpu_usage("db_001")
Observation: CPU 78.5%
Thought: 接近阈值，需要查慢 SQL
Action: get_slow_queries(limit=5)
Observation: 2 条慢 SQL
Thought: 慢 SQL 是根因，可以给出建议了
Final Answer: db_001 CPU 78.5%，发现 2 条慢 SQL...
```

每一步 LLM 自己决定下一步做什么。优点是灵活，缺点是不可控——可能跳步骤、重复调同一个工具。GaussMaster 改成了诊断树引导，牺牲灵活性换取稳定性。

---

## 要求 5：RAG 基本原理和常见优化

### 项目体现

全部覆盖：

| 概念 | GaussMaster 实现 |
|------|-----------------|
| **embedding** | BGE-large-zh 微调版，1024 维，10.6 万 GaussDB 语料 |
| **向量数据库** | openGauss 自身（`floatvector(1024)` + GSDiskANN 磁盘索引 + PQ 压缩） |
| **chunking** | 自研 DNN 语义分块，变长，保护代码块和表格，元信息增强 |
| **metadata** | 每块存 `version`、`prev_uuid`、`next_uuid`、`source`、`title` |
| **rerank** | BGE-reranker 微调版，交叉打分，score < 0 过滤 |
| **hybrid search** | 向量检索（L2 距离 Top-10）+ BM25 全文检索（Top-10）→ 合并去重 |
| **query rewrite** | HyDE（假设文档嵌入）+ 查询改写（拆 3 个子问题）两级降级 |

详细内容见 step1 和 step2 面试 QA。

### 补充解释（项目中未涉及的）

**其他 chunking 策略**：

| 策略 | 做法 | 适用 |
|------|------|------|
| 固定大小 | 每 500 字一刀 | 简单，但会截断句子 |
| 递归分块 | LangChain `RecursiveCharacterTextSplitter` | 通用，按分隔符优先级 |
| 语义分块 | 用 embedding 找 "语义断点" | 句子完整，但计算量大 |
| 句子级 | 每句一块 | 精度高，但块太小 |
| Agentic 分块 | LLM 判断哪里该切 | 最智能，最慢最贵 |

**其他 rerank 方案**：

| 方案 | 做法 | 代表 |
|------|------|------|
| 交叉编码器 | 把 [query, doc] 拼一起打分 | BGE-reranker、Cohere Rerank |
| LLM 打分 | 让 LLM 读候选块，输出相关性评分 | RankGPT |
| 多向量 | 文档用多个向量表示（如 ColBERT） | 精度高，存储大 |
| 列表式 | 一次性对所有候选排序 | RankLLaMA |

**常见 RAG 评估指标**：

| 指标 | 含义 | 计算 |
|------|------|------|
| Recall@K | Top-K 结果中包含正确答案的比例 | 命中数 / 总查询数 |
| MRR | 第一个正确答案排名的倒数平均 | mean(1/rank) |
| NDCG | 考虑排名位置的归一化折扣累积增益 | 前面答对权重更高 |
| Faithfulness | LLM 回答是否基于检索内容（不编造） | 需人工或 LLM 评估 |
| Answer Relevance | LLM 回答和问题的相关度 | 用 embedding 算相似度 |

---

## 要求 6：主流大模型 API 调用

### 项目体现

| 模型 | 调用方式 | GaussMaster 适配 |
|------|---------|-----------------|
| 盘古 | 专有 API，`function_call` 字段 | `Pangu` 适配器类 |
| 盘古云 | 自定义标记 `<unused2>...<unused3>` | `PanguCloud` 适配器类 |
| DeepSeek | OpenAI 兼容 `/chat/completions` | 通用 HTTP 路径 |
| Qwen | OpenAI 兼容 `/chat/completions` | 通用 HTTP 路径 |
| ChatGLM3 | 纯文本，无 function_call | `Chatglm` 适配器类 |
| 百川 2 | SSE 流式 | `Baichuan` 适配器类 |
| Llama3 | 简单 POST + JSON | `Llama3` 适配器类 |

**模型注册表统一管理**：

```python
llm_registry = Registry()

@llm_registry(name='Pangu')
class Pangu(BaseLLM): ...

@llm_registry(name='Chatglm')
class Chatglm(BaseLLM): ...
```

换模型只需改配置文件的 `api_type` 字段，不改业务代码。

### 补充解释（主流模型 API 对比）

| 模型 | API 格式 | Function Call | 流式 | 备注 |
|------|---------|--------------|------|------|
| OpenAI | `/chat/completions` | 原生支持 | ✅ | 行业标准格式 |
| Claude | `/messages` | 原生 tool_use | ✅ | Anthropic，格式不同 |
| Gemini | `generateContent` | 原生 functionCall | ✅ | Google，格式不同 |
| DeepSeek | OpenAI 兼容 | 支持 | ✅ | 性价比高 |
| Qwen | OpenAI 兼容 | 支持 | ✅ | 阿里通义 |
| 开源模型 | 自部署 | 取决于推理框架 | 取决于框架 | vLLM/TGI/Ollama |

**选模型的核心考量**：

| 维度 | 考虑 |
|------|------|
| 效果 | 你的场景下哪个模型答得好？用评估集跑一遍 |
| 成本 | GPT-4 一个字多少钱 vs DeepSeek 一个字多少钱 |
| 延迟 | 首 token 延迟（流式场景）vs 总生成时间 |
| 合规 | 银行数据能不能出内网？能的话用 API，不能的话私有化部署 |
| 生态 | API 格式是否 OpenAI 兼容？SDK 是否成熟？ |

---

## 要求 7：问题拆解能力——业务流程 → Agent 可执行的任务

### 项目体现

数据库运维场景的拆解实例——"CPU 使用率过高"：

```
用户意图: "CPU 使用率过高"
  │
  拆解为 Agent 可执行的任务序列:
  │
  ├─ 任务1: 获取 CPU 使用率
  │    工具: get_cpu_usage(instance)
  │    输出: {cpu_percent: 78.5, status: "warning"}
  │
  ├─ 任务2: (如果 cpu_percent > 80%) 获取慢 SQL 列表
  │    工具: get_slow_queries(limit=5)
  │    输出: [{sql: "...", duration: 12.3}, ...]
  │
  ├─ 任务3: (如果有慢 SQL) 分析执行计划
  │    工具: explain_analyze(sql)
  │    输出: 执行计划文本
  │
  ├─ 任务4: 检查连接数
  │    工具: get_connections()
  │    输出: {total: 120, active: 45}
  │
  └─ 任务5: 综合诊断 + 生成建议
       输入: 以上所有工具的输出
       输出: "db_001 CPU 78.5%，发现 2 条慢 SQL，建议..."
```

每个 "任务" = 一个工具调用。任务间的依赖关系 = 诊断树的边。

### 补充解释（拆解方法论）

**把业务流程拆成 Agent 任务的通用步骤**：

```
第 1 步: 画业务流程
  用户想做什么？输入什么？输出什么？

第 2 步: 识别 "决策点"
  哪些步骤需要判断？(如 "CPU > 80% 吗？")

第 3 步: 识别 "数据获取点"
  哪些步骤需要调外部系统拿数据？

第 4 步: 每个数据获取点 → 一个 Tool
  定义: 工具名、参数、返回值格式

第 5 步: 每个决策点 → 状态转移条件
  定义: if 条件 → 走 A 路径 else → 走 B 路径

第 6 步: 确定 Agent 自由度
  哪些步骤 LLM 自由决策？哪些必须按预定义路径？
```

**什么时候用框架，什么时候自己写**：

| 场景 | 推荐 | 理由 |
|------|------|------|
| 简单 RAG 问答 | 直接用 API | 不需要框架，20 行代码搞定 |
| 单 Agent + 几个工具 | 自己写 | 逻辑简单，框架反而增加复杂度 |
| 多 Agent 协作 | LangGraph / CrewAI | 状态管理、消息传递框架帮你做了 |
| 动态工具选择（开放域） | LangGraph ReAct | 你不知道下一步调什么工具，让 LLM 决定 |
| 确定性工作流（封闭域） | 自己写诊断树 | 步骤已知，LLM 只负责信息提取，不需要框架 |
| 生产环境高稳定性 | 自研或轻框架 | 框架的黑盒行为难调试，自研全程可控 |

GaussMaster 属于最后两种——诊断路径已知（封闭域），生产环境要求高稳定性 → **自研诊断树 + 提示工程，不用 LangGraph**。

---

## 要求 8：代码质量意识

### 项目体现

**分层架构**：

```
controllers/     ← 路由层，只做参数校验和响应格式化
server/web/      ← 业务逻辑层，RAG 管道、Agent 编排
common/          ← 通用层，工具注册表、数据库连接、配置
utils/           ← 工具层，分块、嵌入、检索、提示模板
multiagents/     ← Agent 层，DBA Agent、专家 Agent
```

**异常处理**：Agent 管道 `interact_with_tool()` 中，工具不存在 → 返回明确错误；参数不足 → 提示缺失项；JSON 解析失败 → 重试。

**安全**：DFA + XLNet 双层输入输出检测；Agent 管道 AES-256 加密存储对话历史。

**幂等性**：知识库入库先清空旧集合再重建；工具调用 `SESSION_TOOL_HISTORY` 记录状态防止重复调用。

### 补充解释（应该做但项目中未深挖的）

**日志规范**：

```python
import logging

logger = logging.getLogger("gaussmaster")

# 不要这样:
print("调用 LLM 失败")

# 要这样:
logger.error("LLM call failed", extra={
    "model": model_name,
    "latency_ms": elapsed,
    "error_type": type(e).__name__,
    "user_id": user_id,
    "session_id": session_id,
})
```

关键打点位置：每次 LLM 调用（延迟、token 数、成功/失败）、每次检索（命中数、距离、耗时）、每次工具执行（工具名、参数、耗时、结果）。

**监控指标**：

| 指标 | 含义 | 告警阈值示例 |
|------|------|------------|
| LLM 调用成功率 | 成功次数 / 总次数 | < 99% 告警 |
| LLM P99 延迟 | 99% 的请求在多少 ms 内完成 | > 10s 告警 |
| 检索命中率 | 有结果返回的比例 | < 80% 告警 |
| 工具调用成功率 | 成功执行 / 总调用 | < 99% 告警 |
| 安全拦截率 | 拦截次数 / 总请求 | > 5% 需排查是否误拦 |

**接口规范**：

```python
# 统一的响应格式
{
    "code": 0,           # 0 = 成功，非 0 = 错误码
    "message": "ok",
    "data": {
        "answer": "...",
        "sources": [...],
        "mode": "rag",
        "latency_ms": 1234
    }
}
```

**测试策略**：

| 测试类型 | 测什么 | 工具 |
|---------|--------|------|
| 单元测试 | 每个函数独立测（如 `validate_params()`） | pytest |
| 集成测试 | 检索管道完整链路（加载→分块→向量化→检索） | pytest + 测试用 Chroma |
| E2E 测试 | 启动服务 → curl 发请求 → 检查响应 | pytest + httpx |
| 评估测试 | 已知 QA 对 → 跑检索 → 算 Recall@3 | 自建评估脚本 |

**权限控制**：Agent 工具应分角色——普通用户只能查（`get_cpu_usage`），管理员才能改（`set_config`）。GaussMaster 原项目有角色-工具权限映射，Demo 未实现。
