# 03-Agent流程详解

> 本文档详解 GaussMaster 的 Agent 工具调用流程，即智能运维交互的核心机制。

---

## 1. Agent 是什么？

**Agent（智能体）** 是能够感知环境、做出决策并执行动作的自主系统。

在 GaussMaster 中，Agent 负责：
- 理解用户意图
- 选择合适的运维工具
- 提取工具参数
- 执行工具并返回结果

---

## 2. Agent 整体流程

```
用户提问: "帮我查看昨天的告警"
    │
    ▼
┌─────────────────────────────┐
│ Step 1: infer_tool_name()   │  ← 意图识别，选择工具
│  "summary_alarms"           │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Step 2: check_has_valid_tool() │  ← 校验工具是否存在
│  True                       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Step 3: check_is_no_param_tool() │  ← 检查是否需要参数
│  False (需要参数)            │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Step 4: infer_arguments()   │  ← 参数提取
│  {start_time, end_time}     │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Step 5: verify_arguments()  │  ← 参数校验
│  参数完整 → 执行             │
│  参数缺失 → 追问用户         │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Step 6: call_tool()         │  ← 执行工具
│  调用DBMind API             │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ 格式化输出 → 返回给用户      │
└─────────────────────────────┘
```

---

## 3. 六步流程详解

### Step 1: 意图识别 (infer_tool_name)

**目标**：从用户问题中识别需要调用的工具。

**Prompt 示例**：
```
你是一名丰富经验的内容匹配专家。
可用的第三方工具名称以及描述如下：
- summary_alarms: 获取指定时间范围内的告警信息
- cluster_diagnosis: 对集群进行诊断
- slow_sql_rca: 对慢SQL进行根因分析
...

你的目标是：根据用户的问题，在第三方的工具中找到解决该问题最相关的工具。
用户提问：帮我查看昨天的告警

请直接输出最相关的工具名：
```

**LLM 输出**：`summary_alarms`

**代码**：
```python
async def infer_tool_name(question, user_id, session_id, llm):
    # 获取所有工具描述
    _, detail_without_param_str_list = base_tools.detail_str_list
    tools_des = '\n'.join(detail_without_param_str_list)
    
    # 构建Prompt
    prompt = TOOL_DES_ZH.format(functions=tools_des)
    
    # 调用LLM
    message_inputs = [
        {LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: prompt},
        {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question}
    ]
    response, _ = await llm.invoke(message_inputs)
    
    # 解析工具名
    matched_tool = response.strip()
    return matched_tool
```

---

### Step 2: 工具校验 (check_has_valid_tool)

**目标**：检查识别的工具是否在注册表中。

```python
def check_has_valid_tool(tool_name):
    target_tool = global_vars.tools_registry.get(tool_name, None)
    return target_tool is not None
```

**如果工具不存在**：返回 "用户提问的问题无法用第三方工具解答。"

---

### Step 3: 参数检查 (check_is_no_param_tool)

**目标**：检查工具是否需要参数。

```python
def check_is_no_param_tool(tool_name):
    target_tool = global_vars.tools_registry.get(tool_name, None)
    if target_tool and len(target_tool.__param_dict_list__) == 0:
        return True
    return False
```

**如果无参**：直接执行工具，跳过参数提取步骤。

---

### Step 4: 参数提取 (infer_arguments)

**目标**：从用户问题中提取工具所需的参数。

**Prompt 示例**：
```
你是一个极有帮助的数据库智能运维助手。
时间设定：今年设定为2025年，今天的日期设定为2025-01-15，当前时间是2025-01-15 10:30:00，星期三。

可使用工具：summary_alarms(start_time: 开始时间, end_time: 结束时间)

核心规则：
1. 仔细分析用户问题中是否完整提供了所有必要参数
2. 如果必要参数有缺失，一次性向用户询问所有缺失信息
3. 获取所有必要参数后，直接调用工具

用户提问：帮我查看昨天的告警

请输出JSON格式：
{
    "name": "summary_alarms",
    "arguments": {
        "start_time": "2025-01-14 00:00:00",
        "end_time": "2025-01-14 23:59:59"
    }
}
```

**代码**：
```python
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    # 获取工具详细描述（带参数）
    target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__
    
    # 构建时间参数
    propose_prompt_dict = {
        "year": str(datetime.now().year),
        "date": str(datetime.now().date()),
        "current": str(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "weekday": f"星期{WEEK_ZH[datetime.now().weekday()]}"
    }
    
    # 构建Prompt
    propose_prompt_dict['functions'] = target_tool_des
    propose_prompt = TOOL_INTERACT_ZH.format(**propose_prompt_dict)
    
    # 调用LLM
    message_inputs = [
        {LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: propose_prompt},
        {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question}
    ]
    content_resp, function_call = await llm.invoke(message_inputs)
    
    return content_resp, function_call
```

---

### Step 5: 参数校验 (verify_arguments)

**目标**：检查提取的参数是否完整。

```python
def verify_arguments(function_call: dict = None):
    func_name = function_call.get('name')
    arguments = json.loads(function_call.get('arguments'))
    return has_correct_params(arguments, global_vars.tools_registry.get(func_name))
```

**返回**：
- `is_complete`: 参数是否完整
- `correct_params`: 正确的参数
- `need_params`: 还需要的参数

**如果参数不完整**：
```python
if not is_complete:
    content_resp = f'缺少参数{",".join(list(need_params.keys()))}，请一次性提供完整'
    # 保存当前意图，等待用户追问
    await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
```

---

### Step 6: 工具执行 (call_tool)

**目标**：调用具体的工具函数。

```python
def call_tool(tool_name: str, params=None):
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

**示例**：
```python
# 调用 summary_alarms
call_tool("summary_alarms", {
    "start_time": "2025-01-14 00:00:00",
    "end_time": "2025-01-14 23:59:59"
})
# 返回：告警列表
```

---

## 4. 多轮对话实现

### 4.1 意图状态保持

**问题**：用户先说"查看告警"，系统问"请提供时间范围"，用户回答"昨天"。如何保持"查看告警"这个意图？

**解决**：使用 `SESSION_TOOL_HISTORY` 保存每个会话的当前意图。

```python
# global_vars.py
SESSION_TOOL_HISTORY = {}  # {user_id: {session_id: tool_name}}

# dba.py
async def interact_with_tool(self):
    # 检查是否有未完成的意图
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

### 4.2 对话示例

```
用户：查看告警
系统：缺少参数 start_time、end_time，请提供时间范围

用户：昨天到今天
系统：[调用 summary_alarms] → 返回告警列表

用户：这些告警严重吗？
系统：意图已清空，重新识别 → 回答告警严重程度
```

---

## 5. 工具注册机制

### 5.1 装饰器注册

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
    """具体实现"""
    ...
```

### 5.2 注册过程

1. 装饰器将函数注册到 `global_vars.tools_registry`
2. 自动生成工具描述（JSON Schema）
3. LLM 通过 `base_tools.detail_str_list` 获取所有工具描述

### 5.3 可用工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `summary_alarms` | 告警汇总 | start_time, end_time |
| `cluster_diagnosis` | 集群诊断 | start_time(可选) |
| `slow_sql_rca` | 慢SQL根因分析 | query, db_name |
| `index_recommendation` | 索引推荐 | sql, db_name |
| `risk_analysis` | 风险预测 | metric, warning_hours |
| `metric_diagnosis` | 指标诊断 | metric_name, alarm_cause, start_time, end_time |
| `get_top_sqls` | Top SQL | 无 |
| `get_locking_sql` | 锁等待SQL | 无 |
| `get_instance_status` | 实例状态 | 无 |
| `get_database_info` | 数据库列表 | 无 |
| `get_guc_parameter` | GUC参数查询 | name |
| `collect_stat_activity_workloads` | 活跃SQL | database |
| `collect_history_statement` | 历史SQL | start_time, end_time |
| `knob_recommendation_details` | 参数推荐 | 无 |
| `memory_check` | 内存检查 | latest_hours(可选) |
| `status_overview` | 状态总览 | 无 |

---

## 6. 核心代码位置

| 函数/类 | 文件 | 职责 |
|---------|------|------|
| `interact_with_tool()` | `multiagents/agents/dba.py` | Agent主流程 |
| `infer_tool_name()` | `llms/executor.py` | 意图识别 |
| `infer_arguments()` | `llms/executor.py` | 参数提取 |
| `verify_arguments()` | `llms/executor.py` | 参数校验 |
| `call_tool()` | `llms/executor.py` | 工具执行 |
| `@base_tools` | `multiagents/tools/dbmind_interface.py` | 工具注册装饰器 |

---

## 7. 与 RAG 流程的对比

| 维度 | Agent流程 | RAG流程 |
|------|-----------|---------|
| **输入** | 运维指令 | 知识问题 |
| **处理** | 意图识别+工具调用 | 检索+生成 |
| **输出** | 工具执行结果 | 文本答案 |
| **核心** | 工具集 | 知识库 |
| **示例** | "查看昨天告警" | "GaussDB是什么？" |

---

*本文档基于 openGauss-GaussMaster v1.0.0*
