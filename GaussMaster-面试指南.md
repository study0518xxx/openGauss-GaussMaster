# GaussMaster 面试指南

## 目录

- [面试者项目介绍](#面试者项目介绍)
- [面试官20问](#面试官20问)

---

## 面试者项目介绍

### 1分钟版本（电梯演讲）

> "我参与开发了一个基于大语言模型的数据库智能运维平台 GaussMaster。它通过 RAG 检索增强生成和 Function Calling 技术，让 DBA 可以用自然语言与数据库交互，实现告警查询、慢SQL诊断、索引推荐等运维操作。项目采用 Multi-Agent 架构，包含 DBA Agent、Reporter Agent 等多个角色协作，支持多轮对话和流式输出。我主要负责核心 Agent 逻辑、工具调用链路和 API 接口开发。"

---

### 3分钟版本（标准介绍）

#### 项目背景

"GaussMaster 是华为开源的数据库智能运维 Copilot 平台，目标是降低数据库运维门槛，让普通开发者也能像专业 DBA 一样管理 openGauss 数据库。"

#### 核心功能

"系统主要提供两大能力：

1. **智能交互（Tool Calling）**：用户用自然语言描述需求，系统自动识别意图、提取参数、调用运维工具。比如用户说'查看昨天的告警'，系统会自动调用 summary_alarms 工具查询。

2. **智能问答（RAG）**：基于向量检索+大模型生成，回答数据库相关知识问题。支持多路召回（向量+文本）和 Reranker 重排序。"

#### 技术架构

"项目采用分层架构：

- **Controller 层**：HTTP API 入口，负责路由和参数校验
- **Agent 层**：Multi-Agent 核心，DBA Agent 负责工具调用决策
- **LLM 层**：封装多种大模型（盘古、ChatGLM等），统一调用接口
- **工具层**：15+ 运维工具，通过装饰器自动注册

关键技术包括：Function Calling、RAG、向量数据库、SSE 流式输出、双层存储（内存+SQLite）。"

#### 我的贡献

"我在项目中主要负责：

1. 设计 DBA Agent 的工具调用链路（意图识别→参数提取→工具执行）
2. 实现多轮对话的状态保持机制（SESSION_TOOL_HISTORY）
3. 开发 HTTP API 接口和参数校验装饰器
4. 优化 Prompt 工程，提升工具识别准确率"

---

### 5分钟版本（详细展开）

#### 项目背景与目标

"随着大模型技术的发展，我们思考如何将 AI 能力应用到数据库运维领域。传统运维需要 DBA 记忆大量命令和参数，学习成本高。GaussMaster 的目标是让运维像聊天一样简单——用户用自然语言描述需求，AI 自动完成操作。"

#### 核心挑战与解决方案

**挑战1：如何让 LLM 准确识别运维意图？**

"我们采用 Function Calling 技术。首先将所有运维工具（告警查询、慢SQL诊断、索引推荐等）用 JSON Schema 描述，然后通过 Prompt 工程让 LLM 做选择题——从工具列表中选出最匹配的一个。"

**挑战2：如何处理多轮对话？**

"比如用户先说'查看告警'，系统问'请提供时间范围'，用户回答'昨天'。这里需要保持'查看告警'这个意图。我们用 SESSION_TOOL_HISTORY 字典保存每个会话的当前意图，追问时不再重新识别。"

**挑战3：如何保证响应速度？**

"LLM 推理较慢，我们采用 SSE（Server-Sent Events）流式输出，用户可以看到'工具匹配中...'、'提取参数中...'的实时进度，提升体验。"

#### 技术亮点

1. **Multi-Agent 架构**：不同 Agent 负责不同任务，DBA Agent 处理工具调用，Reporter Agent 生成诊断报告

2. **双层存储**：内存缓存（SESSION_QA_HISTORY）+ SQLite 持久化，平衡速度和可靠性

3. **自研 HTTP 框架**：基于 FastAPI 封装，通过装饰器实现路由注册和统一响应格式，业务代码与框架解耦

4. **向量化检索**：支持 Embedding + 向量数据库 + Reranker 重排序，提升 RAG 准确率

#### 项目成果

"项目已开源，支持 15+ 运维工具，覆盖告警、SQL诊断、集群管理、参数调优等场景。在实际测试中，工具识别准确率超过 90%，平均响应时间 < 3秒。"

---

## 面试官20问

### 基础问题（1-5）

#### Q1：请介绍一下 GaussMaster 是什么项目？

**参考答案**：

GaussMaster 是华为开源的基于大语言模型的数据库智能运维平台，主要解决数据库运维门槛高的问题。它提供两大核心能力：

1. **智能交互**：通过 Function Calling 技术，让用户用自然语言调用运维工具（如告警查询、慢SQL诊断）
2. **智能问答**：基于 RAG 技术，回答数据库相关知识问题

技术栈包括 Python、FastAPI、向量数据库、LLM（盘古/ChatGLM等），采用 Multi-Agent 架构设计。

---

#### Q2：项目的核心架构是怎样的？

**参考答案**：

项目采用分层架构：

```
┌─────────────────────────────────────┐
│  Controller 层 (core.py)            │  HTTP API 入口，路由定义
├─────────────────────────────────────┤
│  Agent 层 (multiagents/)            │  DBA Agent、Reporter Agent
├─────────────────────────────────────┤
│  LLM 层 (llms/)                     │  大模型封装，统一调用接口
├─────────────────────────────────────┤
│  工具层 (tools/)                    │  15+ 运维工具实现
├─────────────────────────────────────┤
│  数据层 (metadatabase/)             │  SQLite + 向量数据库
└─────────────────────────────────────┘
```

核心流程：HTTP请求 → Controller → Agent决策 → LLM推理 → 工具执行 → 返回结果

---

#### Q3：什么是 Function Calling？项目中怎么实现的？

**参考答案**：

Function Calling 是大模型的一种能力，让模型可以识别何时需要调用外部工具，并生成调用参数。

**实现流程**（5步）：

1. **工具注册**：用 `@base_tools` 装饰器将函数注册到系统，自动生成 JSON Schema
2. **意图识别**：`infer_tool_name()` 让 LLM 从工具列表中选择最匹配的
3. **参数提取**：`infer_arguments()` 让 LLM 从用户问题中提取参数
4. **参数校验**：`verify_arguments()` 检查参数是否完整
5. **工具执行**：`call_tool()` 调用实际函数

**Prompt 示例**：
```
你是一名内容匹配专家。可用工具：
- summary_alarms: 获取告警信息
- slow_sql_rca: 慢SQL诊断
...

请根据用户问题，输出最相关的工具名。
```

---

#### Q4：RAG 是什么？项目中怎么实现的？

**参考答案**：

RAG（Retrieval-Augmented Generation，检索增强生成）是一种结合向量检索和大模型生成的技术，解决大模型知识不足和幻觉问题。

**实现流程**：

1. **文档向量化**：将知识库文档切分，用 Embedding 模型转为向量，存入向量数据库
2. **检索**：用户提问时，先进行向量检索（语义相似度）+ 文本检索（关键词匹配）
3. **重排序**：用 Reranker 模型对检索结果重新排序
4. **生成**：将检索结果作为上下文，让 LLM 生成答案

**代码位置**：`server/web/data_transformer.py` 中的 `search()` 和 `llm_generation()`

---

#### Q5：项目中有哪些 Agent？分别做什么？

**参考答案**：

目前主要有：

1. **DBA Agent**（`dba.py`）：核心 Agent，负责工具调用流程
   - 意图识别 → 参数提取 → 工具执行 → 结果返回
   - 支持多轮对话

2. **Reporter Agent**：生成诊断报告（代码中提及，具体实现待完善）

3. **Repairer Agent**：执行修复操作（规划中）

DBA Agent 是核心，通过 `interact_with_tool()` 方法实现完整的工具调用链路。

---

### 进阶问题（6-12）

#### Q6：如何实现多轮对话？

**参考答案**：

多轮对话的关键是**意图状态保持**。

**实现机制**：

```python
# global_vars.py
SESSION_TOOL_HISTORY = {}  # 保存每个会话的当前工具意图

# dba.py - interact_with_tool()
intention_tool = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)

if intention_tool is None:
    # 首次提问，需要推断工具
    matched_tool = await infer_tool_name(question, user_id, session_id, llm)
    intention_tool = matched_tool
    # 保存意图
    SESSION_TOOL_HISTORY[user_id] = {session_id: intention_tool}
else:
    # 追问，直接使用保存的意图
    pass
```

**示例对话**：
```
用户：查看告警
系统：请提供时间范围
用户：昨天          ← 追问，保持"查看告警"意图
系统：调用 summary_alarms 查询昨天告警
```

---

#### Q7：工具调用链路是怎样的？

**参考答案**：

完整的工具调用链路（5步）：

```
用户提问
    ↓
1. infer_tool_name()      ← 意图识别，选择工具
    ↓
2. check_has_valid_tool() ← 校验工具是否存在
    ↓
3. check_is_no_param_tool() ← 检查是否需要参数
    ↓
4. infer_arguments()      ← 参数提取
    ↓
5. verify_arguments()     ← 参数校验
    ↓
6. call_tool()            ← 执行工具
    ↓
返回结果
```

**代码位置**：`executor.py`

---

#### Q8：为什么使用 SQLite 而不是 openGauss？

**参考答案**：

**SQLite 用途**：
- 存储会话历史（tb_interaction_memory）
- 存储集群配置、知识库元数据
- 轻量级，无需额外部署

**不用 openGauss 的原因**：
1. **元数据量小**：会话历史、配置等数据量不大，SQLite 足够
2. **部署简单**：SQLite 内嵌，无需独立数据库服务
3. **解耦设计**：GaussMaster 管理 openGauss，不应该依赖被管理的对象
4. **向量数据库独立**：RAG 使用专门的向量数据库（如 Milvus），不是关系型数据库

---

#### Q9：装饰器 `@request_mapping`、`@standardized_api_output` 分别做什么？

**参考答案**：

**`@request_mapping`**：
- 注册 HTTP 路由
- 将 URL 路径和函数绑定
- 示例：`@request_mapping("/v1/api/clusters", method='GET')`

**`@standardized_api_output`**：
- 统一 API 响应格式
- 包装返回值为 `{"success": true, "data": ...}`
- 捕获异常，返回统一错误格式 `{"success": false, "msg": ...}`

**执行顺序**：
```python
@request_mapping(...)          # 最外层：注册路由
@standardized_api_output       # 中间层：统一响应
@ParameterChecker.define_rules # 最内层：参数校验
def func():
    pass
```

---

#### Q10：SSE 流式输出是怎么实现的？

**参考答案**：

SSE（Server-Sent Events）是一种服务器向客户端推送实时数据的技术。

**实现方式**：

```python
# _service_impl.py
def standardized_event_stream_output(f):
    @wraps(f)
    async def wrapper(*args, **kwargs):
        generator = f(*args, **kwargs)
        
        async def standardize_generator():
            async for item in generator:
                # 格式化为 SSE 格式
                yield f"data:{json.dumps({'success': True, 'data': item})}\n\n"
        
        return StreamingResponse(standardize_generator(), media_type="text/event-stream")
    
    return wrapper
```

**使用场景**：
- LLM 生成答案时逐字返回
- 工具调用过程实时显示进度（"工具匹配中..."、"提取参数中..."）

---

#### Q11：工具是如何注册和发现的？

**参考答案**：

**注册方式**：使用 `@base_tools` 装饰器

```python
# dbmind_interface.py
@base_tools(
    name="summary_alarms",
    description="获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
def summary_alarms(start_time, end_time):
    ...
```

**注册过程**：
1. 装饰器将函数注册到 `global_vars.tools_registry`
2. 自动生成工具描述（JSON Schema）
3. LLM 通过 `base_tools.detail_str_list` 获取所有工具描述

**发现方式**：
```python
# executor.py - infer_tool_name()
_, detail_without_param_str_list = base_tools.detail_str_list
tools_des = '\n'.join(detail_without_param_str_list)
# 将 tools_des 放入 Prompt，让 LLM 选择
```

---

#### Q12：双层存储机制是什么？

**参考答案**：

**双层存储**：内存 + SQLite

```python
# 第一层：内存缓存（快速访问）
SESSION_QA_HISTORY = {}

# 第二层：SQLite 持久化（长期存储）
# tb_interaction_memory 表
```

**读取流程**：
```python
async def get_qa_history(self):
    # 1. 先查内存
    qa_list = SESSION_QA_HISTORY.get(user_id, {}).get(session_id, [])
    
    if not qa_list:
        # 2. 内存没有，查数据库
        raw_records = await select_interaction_memory(user_id, session_id)
        # 3. 解密、构建历史
        # 4. 写入内存缓存
        SESSION_QA_HISTORY[user_id] = {session_id: history}
    
    return qa_list
```

**优势**：
- 内存快，但重启丢失
- SQLite 持久化，但较慢
- 结合两者，平衡速度和可靠性

---

### 高级问题（13-20）

#### Q13：如果 LLM 识别错了工具怎么办？

**参考答案**：

**问题场景**：用户说"查看数据库状态"，LLM 可能识别为 `cluster_diagnosis` 或 `status_overview`。

**解决方案**：

1. **Prompt 优化**：在 Prompt 中明确工具的区别
   ```
   cluster_diagnosis: 对集群进行全面诊断（深度检查）
   status_overview: 查看集群整体状态概览（快速查看）
   ```

2. **兜底机制**：如果工具执行失败，提示用户重新描述

3. **用户确认**：对于关键操作，可以让用户确认后再执行

4. **日志分析**：收集错误案例，持续优化 Prompt

---

#### Q14：如何处理参数提取失败的情况？

**参考答案**：

**场景**：用户说"查看告警"，但没有提供时间范围。

**处理流程**：

```python
# infer_arguments() 返回不完整参数
content_resp, function_call = await infer_arguments(...)

# verify_arguments() 检查完整性
is_complete, correct_params, need_params = verify_arguments(function_call)

if not is_complete:
    # 参数不完整，提示用户提供
    content_resp = f'缺少参数{",".join(list(need_params.keys()))}，请一次性提供完整'
    # 保存当前意图，等待追问
    await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
```

**用户体验**：
```
用户：查看告警
系统：缺少参数 start_time、end_time，请提供时间范围
用户：昨天到今天
系统：调用工具查询...
```

---

#### Q15：项目的性能瓶颈在哪里？如何优化？

**参考答案**：

**性能瓶颈**：

1. **LLM 推理延迟**：大模型生成耗时（2-5秒）
2. **向量检索**：大规模知识库检索耗时
3. **工具执行**：数据库查询、API 调用耗时

**优化方案**：

| 瓶颈 | 优化方案 |
|------|---------|
| LLM 延迟 | SSE 流式输出，先返回进度提示 |
| 向量检索 | 建立索引、缓存热点数据 |
| 工具执行 | 异步执行、并行调用 |
| 整体 | 引入缓存层（Redis）、预加载 |

---

#### Q16：如何扩展一个新的运维工具？

**参考答案**：

**步骤**：

1. **实现工具函数**（`dbmind_interface.py`）
   ```python
   @base_tools(
       name="new_tool",
       description="工具描述",
       params=[Param(name="param1", description="参数1", param_type="str")]
   )
   def new_tool(param1):
       # 实现逻辑
       return result
   ```

2. **系统自动注册**：装饰器自动将工具注册到 `tools_registry`

3. **Prompt 自动更新**：`infer_tool_name()` 会自动获取新工具描述

4. **无需修改其他代码**：系统通过反射调用工具

---

#### Q17：项目中使用了哪些设计模式？

**参考答案**：

| 设计模式 | 应用场景 | 代码位置 |
|---------|---------|---------|
| **装饰器模式** | 路由注册、参数校验、响应格式化 | `@request_mapping`、`@define_rules` |
| **工厂模式** | LLM 实例化 | `instantiate_llm()` |
| **注册表模式** | 工具注册 | `base_tools = Registry()` |
| **策略模式** | 不同 LLM 的调用策略 | `BaseLLM` 子类 |
| **代理模式** | HTTP 服务封装 | `HttpService` |

---

#### Q18：如何保证系统的安全性？

**参考答案**：

**安全措施**：

1. **参数校验**：`@ParameterChecker.define_rules` 防止非法输入
2. **SQL 注入防护**：使用 ORM，不拼接 SQL
3. **敏感信息加密**：对话历史中的密码等字段 AES256 加密
4. **访问控制**：API 权限控制（`api=True`）
5. **敏感词过滤**：`DFA_DETECTOR` 检测不安全内容

---

#### Q19：项目的部署架构是怎样的？

**参考答案**：

**部署组件**：

```
┌─────────────────────────────────────┐
│  GaussMaster 服务                    │  Python + FastAPI
│  - HTTP API 服务                      │
│  - Multi-Agent 核心                   │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  向量数据库（Milvus/其他）            │  存储知识库向量
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  LLM 服务                            │  盘古/ChatGLM API
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  DBMind 服务                         │  openGauss 运维工具集
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  openGauss 数据库集群                 │  被管理的数据库
└─────────────────────────────────────┘
```

---

#### Q20：如果让你优化这个项目，你会从哪些方面入手？

**参考答案**：

**优化方向**：

1. **性能优化**
   - 引入 Redis 缓存热点数据
   - LLM 调用异步并行化
   - 向量检索优化（索引、分片）

2. **功能扩展**
   - 完善 Reporter Agent、Repairer Agent
   - 支持更多数据库类型（MySQL、PostgreSQL）
   - 增加可视化诊断报告

3. **体验优化**
   - 支持语音输入
   - 增加操作确认机制
   - 优化错误提示

4. **稳定性**
   - 增加限流、熔断机制
   - 完善监控和告警
   - 支持集群部署

---

## 面试技巧总结

### 回答问题的 STAR 法则

- **S**ituation（情境）：项目背景
- **T**ask（任务）：你的职责
- **A**ction（行动）：具体做法
- **R**esult（结果）：取得的成果

### 加分项

1. **提到具体代码文件和函数名**，显示熟悉程度
2. **画出架构图或流程图**，展示理解深度
3. **提及遇到的问题和解决方案**，体现实战经验
4. **对比其他方案**，说明选型原因

### 减分项

1. 只讲概念，不讲实现
2. 说不清楚自己的具体贡献
3. 对项目难点和挑战避而不谈

---

*本文档基于 openGauss-GaussMaster v1.0.0*
