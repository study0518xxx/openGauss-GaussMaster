# 06 - Agent 与 LangChain

## 核心结论

**GaussMaster 没有使用 LangChain 的 Agent。** 全部自研，包括 Agent 基类、工具注册、输出解析、执行循环、提示模板。

---

## 自定义 Agent 架构

### Agent 基类
```python
# GaussMaster/multiagents/agents/base_agent.py
class BaseAgent:
    output_parser: CustomOutputParser
```

### DBA 主 Agent
```python
# GaussMaster/multiagents/agents/dba.py
class DBA(BaseAgent):
    def __init__(self, question, user_id, session_id, mode, llm_name, history_len, lang):
        self.embedding = global_vars.embedding_model
        self.llm = instantiate_llm(llm_name)
        
    async def interaction(self):
        if self.mode == InteractionType.TOOL_INTERACTION:
            async for step in self.interact_with_tool():
                yield step
```

### 工具交互主循环
```python
async def interact_with_tool(self):
    # 1. 检查会话意图
    intention_tool = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)
    
    if intention_tool is None:
        # 2. LLM 匹配工具名
        matched_tool = await infer_tool_name(question, user_id, session_id, llm)
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            yield "无法用第三方工具解答。"
            return
        
        # 3. 无参数工具快捷路径
        if check_is_no_param_tool(matched_tool):
            tool_result = call_tool(matched_tool)
            yield tool_result
            return
        
        intention_tool = matched_tool
    
    # 4. LLM 推断参数
    content_resp, function_call = await infer_arguments(...)
    
    # 5. 验证并执行
    if function_call:
        is_complete, correct_params, need_params = verify_arguments(function_call)
        if is_complete:
            tool_result = call_tool(intention_tool, correct_params)
            yield tool_result
        else:
            yield f"缺少参数 {list(need_params.keys())}"
```

---

## 自定义输出解析器

```python
# GaussMaster/utils/parse.py

# LangChain 风格的 NamedTuple（但自研）
class AgentAction(NamedTuple):
    tool: str
    tool_input: dict
    log: str

class AgentFinish(NamedTuple):
    return_values: str
    log: str

class CustomOutputParser:
    def parse_action(self, output: str) -> Union[AgentAction, AgentFinish]:
        # 正则从 LLM 输出中提取 JSON
        match = re.search(r"({.*})", output, re.DOTALL)
        response = json.loads(match.group(1))
        
        if response["action"] == "Final Answer":
            return AgentFinish(action_input_value, output)
        return AgentAction(action_value, action_input_value, output)
```

和 LangChain 的 `JSONAgentOutputParser` 精神类似，但是自己写的，更可控。

---

## 多 Agent 层次化架构（论文核心创新）

```
                    ┌─────────────────────┐
                    │   DBA 主 Agent       │
                    │   (总管/协调者)      │
                    └──────────┬──────────┘
                               │ 根据告警-专家描述相似度分配
                    ┌──────────┼──────────┐
                    ↓          ↓          ↓
          ┌────────────┐ ┌──────────┐ ┌────────────┐
          │ 资源专家   │ │ 组件专家 │ │ 其他专家   │
          │(指标检查)  │ │(慢SQL)   │ │(按需)     │
          └────────────┘ └──────────┘ └────────────┘
```

### Agent 角色定义
```python
# GaussMaster/multiagents/config/agent_config.py
class AgentRoles(Enum):
    SQLExpert = 'sql_expert'
    StorageExpert = 'storage_expert'
    ClusterExpert = 'cluster_expert'
    PerformanceExpert = 'performance_expert'
    SourceExpert = 'source_expert'
    Repairer = 'repairer'
```

角色通过 `Registry._category` 控制工具可见性——不同 Agent 角色看到不同的工具集。

### 交叉审查协议
Agent 之间在诊断过程中交换信息。例如：资源专家发现 I/O 异常 → 可以建议 DBA 主 Agent 忽略组件专家的结论 → 触发重新分析。

### 诊断树引导编排（与 D-Bot 的区别）
- **D-Bot（之前的方法）**：LLM 在工具使用上灵活但噪声大的探索
- **GaussMaster**：确定性树路径减少探索噪声
  - 树节点 = 特定工具（如 `slow_sql_rca()`）
  - 树路径 = 针对特定异常的经过验证的工具调用管线（如"高 CPU 使用率 → check_cpu → get_top_sqls → slow_sql_rca"）

---

## 提示模板体系（LangChain 风格但非 LangChain）

`GaussMaster/llms/prompt.py` 中包含**看起来像** LangChain ReAct 格式的提示模板：

```python
FORMAT_INSTRUCTIONS = """RESPONSE FORMAT INSTRUCTIONS
...
{{
    "action": string, \\ Must be one of {tool_names}
    "action_input": string
}}

OR:

{{
    "action": "Final Answer",
    "action_input": string
}}"""
```

以及 `PREFIX`/`SUFFIX`/`TEMPLATE_TOOL_RESPONSE` 模板——但这些只是**未用的参考模板**。实际使用的提示在 `prompt.py:113+` 和 `prompt_util.py` 中。

---

## 与 LangChain 的关键差异总结

| 方面 | LangChain 典型做法 | GaussMaster 实际做法 |
|------|-------------------|-------------------|
| 检索器 | `VectorStoreRetriever` | 自研 `BaseRetriever` + `GaussDB` |
| 嵌入 | `OpenAIEmbeddings` / `HuggingFaceEmbeddings` | 自研 `OnlineEmbedding` |
| 向量存储 | Chroma / Pinecone / Milvus | openGauss + GSDiskANN |
| 索引 | IVF_FLAT / HNSW | GSDiskANN（磁盘向量索引 + PQ） |
| 文档分割 | `RecursiveCharacterTextSplitter` | 自研 DNN 语义分块 |
| 重排序 | `ContextualCompressionRetriever` | 自研 `OnlineReranker` |
| Agent | `AgentExecutor` + ReAct / OpenAI Tools | 自研 `DBA.interact_with_tool()` |
| 工具定义 | `@tool` 装饰器 | 自研 `Registry` + `Param` 类 |
| LLM 抽象 | `BaseLLM` → `ChatOpenAI` 等 | 自研 `BaseLLM` + `llm_registry` |
| 查询优化 | `MultiQueryRetriever` | 自研 HyDE + 查询改写 |
| 输出解析 | `StrOutputParser` / `JSONAgentOutputParser` | 自研 `CustomOutputParser` |

---

## 面试话术建议

> "这个项目借鉴了 LangChain 的 Agent + Tool 架构思想，但核心链路全部自研。原因是 LangChain 的三个局限：
> 1. 检索器不支持向量+BM25+reranker 的三路混合检索
> 2. AgentExecutor 的 ReAct 循环在数据库诊断场景不够可控——我们需要诊断树引导的确定性路径
> 3. openGauss 的 GSDiskANN 索引和 BM25 全文索引 LangChain 完全没法用
>
> 所以我们自己实现了 Agent 基类、工具注册表、输出解析器、检索管道。事实证明这个决策是对的——银行生产环境中 34 个场景零人工干预，工具准确率 95%+。"
