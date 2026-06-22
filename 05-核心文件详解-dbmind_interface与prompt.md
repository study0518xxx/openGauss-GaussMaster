# 05-核心文件详解 - dbmind_interface与prompt

> 本文档详解工具实现层（dbmind_interface.py）和 Prompt 工程（prompt.py）。

---

## 1. dbmind_interface.py - 工具实现层

**路径**: `GaussMaster/multiagents/tools/dbmind_interface.py`

**作用**: 定义所有可用的运维工具，通过 `@base_tools` 装饰器注册到系统。

### 1.1 装饰器机制

```python
@base_tools(
    name="summary_alarms",              # 工具唯一名称
    description="获取指定时间范围内的告警信息",  # 工具描述（给LLM看）
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
def summary_alarms(start_time, end_time):
    ...
```

**装饰器作用**:
1. 将函数注册到 `global_vars.tools_registry`
2. 自动生成工具描述（JSON Schema）
3. 记录参数定义

### 1.2 核心工具详解

#### summary_alarms - 告警汇总

```python
@base_tools(
    name="summary_alarms",
    description="summary_alarms工具的功能是获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间，格式为YYYY-MM-DD HH:mm:ss", param_type="str"),
        Param(name="end_time", description="结束时间，格式为YYYY-MM-DD HH:mm:ss", param_type="str")
    ]
)
@validate_return_format
def summary_alarms(start_time, end_time):
    """
    【告警汇总】获取指定时间范围内的所有告警
    
    参数:
        start_time: str  # 开始时间
        end_time: str    # 结束时间
    
    返回:
        List[dict]  # 格式化的告警列表
    """
    # 1. 时间转换
    start_at, end_at = transfer_date_2_timestamp(start_time, end_time)
    
    # 2. 获取集群列表
    instance_list = get_cluster_list().get(current_instance.get())
    
    # 3. 批量获取告警
    final_alarms = fetch_all_alarms(start_at, end_at, ip_list)
    
    # 4. 格式化输出
    target = generate_alarm_output(final_alarms, ip_list)
    return target
```

#### slow_sql_rca - 慢SQL根因分析

```python
@base_tools(
    name="slow_sql_rca",
    description="slow_sql_rca工具的功能是对慢SQL进行诊断和根因分析",
    params=[
        Param(name="query", description="慢SQL语句", param_type="str"),
        Param(name="db_name", description="数据库名", param_type="str")
    ]
)
def slow_sql_rca(query, db_name, **kwargs):
    """
    【慢SQL根因分析】分析慢SQL的原因
    
    参数:
        query: str    # SQL语句
        db_name: str  # 数据库名
    
    返回:
        dict  # 根因和建议
    """
    params = {"db_name": db_name, "query": query}
    params.update(kwargs)
    
    url = urljoin(configs.get(DBMIND, "api_prefix"), "app/slow-sql-rca")
    response = dbmind_request("get", url, params=params)
    
    if response.status_code == 200 and "data" in response.json():
        result = response.json()
        roots = result.get("data")[-1][0][0]  # 根因
        advice = result.get("data")[-1][1][0]  # 建议
        return formatter_table(["慢SQL根因", "诊断建议"], list(zip(roots, advice)))
    
    return [formatter_str(f"工具执行异常{response.status_code}")]
```

### 1.3 工具列表汇总

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

## 2. prompt.py - Prompt 工程

**路径**: `GaussMaster/llms/prompt.py`

**作用**: 定义所有 Prompt 模板，是 LLM 行为的"遥控器"。

### 2.1 工具匹配 Prompt

```python
TOOL_DES_ZH = """你是一名丰富经验的内容匹配专家。
可用的第三方工具名称以及描述如下：
{functions}
你的目标是：根据用户的问题，在第三方的工具中找到解决该问题最相关的工具。
你需要严格遵守的规则是：
1.工具名应该是英文字母和下划线的组合，请你直接输出最相关的工具名，不可以输出除了工具名之外的任何信息。
2.不可输出不存在的工具名；
3.如果你找到了最相关的工具，不可更改工具名；
4.如果用户提问的问题与工具的描述都不相关，输出：'用户提问的问题无法用第三方工具解答。'
"""
```

**用途**: 让 LLM 选择最合适的工具

### 2.2 工具交互 Prompt

```python
TOOL_INTERACT_ZH = """你是一个极有帮助的数据库智能运维助手。
时间设定：今年设定为{year}年，今天的日期设定为{date}，当前时间是{current}，{weekday}。
你的目标是：求助于提供给你的第三方工具，解答用户的问题。
可使用工具：{functions}

核心规则：
1.仔细分析用户问题中是否完整提供了第三方工具的所有'必要参数'
2.如果'必要参数'有缺失，一次性向用户询问所有缺失信息
3.按格式输出缺失参数：(1)缺失的参数1：描述...
4.获取所有'必要参数'后，直接调用工具，不要询问用户确认
5.涉及日期时，必须结合时间设定推断，不可编造日期
6.涉及时间时，转换为'YYYY-MM-DD HH:mm:ss'格式

如果你想使用工具，使用该格式：
```json
{
    "name": "工具名",
    "arguments": {
        "参数1": "值1",
        "参数2": "值2"
    }
}
```

如果你想直接回复，使用该格式：
```json
{
    "action": "Final Answer",
    "action_input": "你的回复"
}
```
"""
```

**用途**: 让 LLM 提取参数并生成 function_call

### 2.3 输出格式指导

```python
FORMAT_INSTRUCTIONS = """When responding to me, please output a response in one of two formats:

**Option 1:** Use this if you want the human to use a tool.
Markdown code snippet formatted in the following schema:
```json
{
    "action": string, \\ The action to take. Must be one of {tool_names}
    "action_input": string \\ The input to the action
}
```

**Option #2:** Use this if you want to respond directly to the human.
Markdown code snippet formatted in the following schema:
```json
{
    "action": "Final Answer",
    "action_input": string \\ You should put what you want to return to use here
}
```
"""
```

---

## 3. 设计要点

### 3.1 为什么这样设计 Prompt？

| 设计点 | 原因 |
|--------|------|
| 结构化工具描述 | LLM 能准确理解每个工具的功能和参数 |
| JSON输出格式 | 便于程序解析和执行 |
| 时间上下文注入 | 解决 LLM 不知道"今天"的问题 |
| 中英文双语 | 支持国际化 |
| 严格规则约束 | 防止 LLM 输出无关内容 |

### 3.2 Prompt 优化技巧

1. **明确角色设定**: "你是一名丰富经验的内容匹配专家"
2. **严格规则约束**: "不可输出除了工具名之外的任何信息"
3. **示例引导**: 提供 JSON 格式示例
4. **边界情况处理**: "如果无法解答，输出..."

---

*本文档基于 openGauss-GaussMaster v1.0.0*
