# GaussMaster 核心文件详解

## 目录

1. [llms/executor.py - LLM调用执行器](#1-llmsexecutorpy---llm调用执行器)
2. [multiagents/agents/dba.py - DBA Agent对话管理](#2-multiagentsagentsdba-py---dba-agent对话管理)
3. [multiagents/tools/dbmind_interface.py - 工具接口实现](#3-multiagentstoolsdbmind_interfacepy---工具接口实现)
4. [llms/prompt.py - Prompt工程](#4-llmspromptpy---prompt工程)
5. [common/http/_service_impl.py - HTTP服务封装](#5-commonhttp_service_implpy---http服务封装)

---

## 1. llms/executor.py - LLM调用执行器

**文件路径**: `GaussMaster/llms/executor.py`

**核心作用**: 整个工具调用系统的发动机，控制用户问题→意图识别→参数提取→工具执行的全流程。

### 1.1 核心函数一览

| 函数名 | 作用 | 是否调用LLM |
|-------|------|------------|
| `llm_call()` | LLM调用入口 | ✅ |
| `infer_tool_name()` | 意图识别（推断用哪个工具） | ✅ |
| `infer_arguments()` | 参数提取（从问题中提取参数） | ✅ |
| `check_has_valid_tool()` | 工具是否存在 | ❌ |
| `check_is_no_param_tool()` | 工具是否需要参数 | ❌ |
| `verify_arguments()` | 验证参数是否完整正确 | ❌ |
| `call_tool()` | 执行工具 | ❌ |

### 1.2 5步调用流程详解

```python
# ====== 步骤1: 意图识别 ======
@timer_decorator
async def infer_tool_name(question: str, user_id, session_id, llm):
    """
    根据用户问题推断应该使用哪个工具
    """
    # 1. 获取所有工具的描述
    if llm.llm_type == LLMType.PANGUCLOUD:
        # 盘古云模型：JSON格式的工具描述
        tools_des = '\n'.join([json.dumps(tool_des) for tool_des in detail_dict_list])
    else:
        # 其他模型：字符串格式的工具描述
        tools_des = '\n'.join(detail_str_list)

    # 2. 构建意图识别Prompt
    tools_des_prompt = (TOOL_DES_ZH.format(functions=tools_des) if LANGUAGE == 'zh'
                        else TOOL_INTERACT_EN.format(functions=tools_des))

    # 3. 检查会话历史中是否有未完成的意图
    tool_name = global_vars.SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)

    # 4. 如果没有，则调用LLM推断工具名
    if tool_name is None:
        message_input = [
            {ROLE: SYSTEM, CONTENT: tools_des_prompt},  # 系统提示词
            {ROLE: USER, CONTENT: question},              # 用户问题
        ]
        tool_name, _ = await llm.invoke(message_input)
    return tool_name.strip()

# ====== 步骤2: 工具校验 ======
def check_has_valid_tool(tool_name):
    """检查工具是否在支持列表中"""
    target_tool = global_vars.tools_registry.get(tool_name, None)
    return target_tool is not None

# ====== 步骤3: 参数校验 ======
def check_is_no_param_tool(tool_name):
    """检查工具是否需要参数"""
    target_tool = global_vars.tools_registry.get(tool_name, None)
    if target_tool and len(target_tool.__param_dict_list__) == 0:
        return True  # 无参工具
    return False

# ====== 步骤4: 参数提取 ======
@timer_decorator
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """
    从用户问题中提取工具参数
    """
    # 1. 获取目标工具的详细描述（包含参数定义）
    target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__

    # 2. 构建时间参数（用于时间推断）
    tz = adjust_timezone(configs.get('TIMEZONE', 'tz'))
    propose_prompt_dict = {
        "year": str(datetime.now(tz).year),
        "date": str(datetime.now(tz).date()),
        "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),
        "weekday": f"星期{WEEK_ZH[datetime.now(tz).weekday()]}" if LANGUAGE == 'zh'
                    else WEEK_CN[datetime.now(tz).weekday()]
    }

    # 3. 根据不同模型使用不同的Prompt策略
    if llm.llm_type in [LLMType.PANGUCLOUD, LLMType.PANGU]:
        # 盘古/盘古云：使用结构化Prompt
        propose_prompt = TOOL_INTERACT_ZH.format(**propose_prompt_dict)

        # 构建对话历史
        message_inputs = [{ROLE: SYSTEM, CONTENT: propose_prompt}]
        history = []
        for qa in qa_record_history:
            history.append({ROLE: USER, CONTENT: qa.question})
            history.append({ROLE: ASSISTANT, CONTENT: qa.answer, FUNCTION_CALL: qa.function_call})
        message_inputs.extend(history)
        message_inputs.append({ROLE: USER, CONTENT: question})

        # 调用LLM提取参数
        content_resp, function_call = await llm.invoke(message_inputs)
    else:
        # 其他模型：使用文本抽取Prompt
        prompt = construct_extract_tool_params_prompt(
            user_question=question,
            tools_description=target_tool_des,
            qa_history=qa_record_history,
            time_args=propose_prompt_dict
        )
        result, _ = await llm.invoke([{ROLE: USER, CONTENT: prompt}])

        # 解析LLM返回的参数
        arguments, success = output_parser.parse_params(result)
        if success:
            content_resp = f'将调用工具{intention_tool}'
            function_call = {'name': intention_tool, 'arguments': arguments}
        else:
            content_resp = f'工具参数解析失败：{result}'
            function_call = {}

    return content_resp, function_call

# ====== 步骤5: 参数验证与执行 ======
def verify_arguments(function_call: dict = None):
    """验证参数是否完整正确"""
    func_name = function_call.get('name')
    try:
        arguments = json.loads(function_call.get('arguments'))
    except TypeError:
        arguments = function_call.get('arguments')
    return has_correct_params(arguments, global_vars.tools_registry.get(func_name))

@timer_decorator
def call_tool(tool_name: str, params=None):
    """执行工具"""
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

### 1.3 意图状态保持机制

```python
# 关键设计：SESSION_TOOL_HISTORY
# 用于在多轮对话中记住当前正在使用的工具

tool_name = global_vars.SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)
if tool_name is None:
    # 新对话，需要推断工具
    tool_name = await infer_tool_name(...)
else:
    # 继续上次的工具调用，只需提取参数
    content_resp, function_call = await infer_arguments(...)
```

**意图状态保持的价值**：
```
用户: "帮我查看数据库状态"
       ↓ infer_tool_name() → summary_alarms
       ↓ 保存到 SESSION_TOOL_HISTORY

用户: "是哪个集群的问题？" （追问）
       ↓ SESSION_TOOL_HISTORY 有值 → 直接 infer_arguments()
       ↓ 无需重新推断工具
```

### 1.4 多模型适配

```python
# 不同模型使用不同的处理策略
if llm.llm_type == LLMType.PANGUCLOUD:
    # JSON格式的工具描述
    tools_des = json.dumps(tool_des, ensure_ascii=False)

elif llm.llm_type == LLMType.PANGU:
    # 字符串格式，需要去除占位符
    propose_prompt = propose_prompt.replace("<unused1><unused0>", "")

else:
    # 其他模型（ChatGLM, Llama等）
    # 使用专门的参数提取Prompt
    prompt = construct_extract_tool_params_prompt(...)
```

---

## 2. multiagents/agents/dba.py - DBA Agent对话管理

**文件路径**: `GaussMaster/multiagents/agents/dba.py`

**核心作用**: 对话入口，管理多轮对话、意图状态、答案保存。

### 2.1 对话入口函数

```python
async def interact(user_id, session_id, query, mode, model_name, history_len=1, lang='zh'):
    """
    对话交互入口
    生成器模式，支持流式输出
    """
    dba = DBA(
        user_id=user_id,
        session_id=session_id,
        question=query,
        mode=mode,
        llm_name=model_name,
        history_len=history_len,
        lang=lang
    )
    # async for 支持流式输出
    async for step_output in dba.interaction():
        yield step_output  # 每个步骤的输出
    yield [DONE_FLAG]  # 结束标记
```

### 2.2 DBA Agent 类结构

```python
class DBA(BaseAgent):
    def __init__(self, question, user_id, session_id, mode, llm_name, history_len, lang):
        self.question = question           # 用户问题
        self.mode = mode                   # 交互模式
        self.embedding = global_vars.embedding_model  # Embedding模型
        self.memory = global_vars.MEMORY  # 内存存储
        self.alarm: dict = {}             # 告警数据
        self.user_id = user_id            # 用户ID
        self.session_id = session_id      # 会话ID
        self.llm = instantiate_llm(llm_name)  # LLM实例
        self.history_len = history_len     # 历史长度
        self.lang = lang                  # 语言
```

### 2.3 主交互流程

```python
@stream_exception_catcher
async def interaction(self):
    """主交互流程"""
    # 快捷场景：直接调用工具
    if self.question in ['当前数据库运行状况', '当前有哪些告警']:
        # 默认查询最近1小时
        tz = adjust_timezone(configs.get('TIMEZONE', 'tz'))
        end_time = datetime.now(tz)
        start_time = end_time - timedelta(minutes=60)

        res = call_tool('summary_alarms', params={
            'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S')
        })
        yield res

    # 标准工具交互流程
    elif self.mode == InteractionType.TOOL_INTERACTION:
        async for step in self.interact_with_tool():
            yield step

    # 故障诊断模式（暂不支持）
    elif self.mode == InteractionType.FAULT_DIAGNOSTIC:
        yield [formatter_str("暂不支持此模式")]
```

### 2.4 工具交互完整流程

```python
async def interact_with_tool(self):
    """与第三方工具交互"""
    # 1. 检查会话意图状态
    intention_tool = global_vars.SESSION_TOOL_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, None)

    if intention_tool is None:
        # 2. 上一个意图已完成，需要处理新意图
        # 2.1 匹配工具
        yield [formatter_progress('工具匹配中...')]
        matched_tool = await infer_tool_name(
            self.question,
            self.user_id,
            self.session_id,
            self.llm
        )

        # 2.2 校验工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            yield [formatter_str('用户提问的问题无法用第三方工具解答。')]
            return

        # 2.3 检查是否需要参数
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            # 无参工具，直接调用
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(matched_tool)
            yield tool_result
            return

        intention_tool = matched_tool

    # 3. 提取参数
    yield [formatter_progress('提取参数中...')]
    qa_record_history = await self.get_qa_history()
    content_resp, function_call = await infer_arguments(
        self.question,
        intention_tool,
        qa_record_history,
        self.llm
    )

    # 4. 调用工具
    if function_call:
        is_complete_params, correct_params, need_prams = verify_arguments(function_call)
        if is_complete_params:
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(intention_tool, correct_params)
            yield tool_result
        else:
            # 参数不完整，要求用户提供
            yield [formatter_str(f'缺少参数{",".join(list(need_prams.keys()))}，请一次性提供完整')]
    else:
        yield [formatter_str(content_resp)]
```

### 2.5 双层存储的对话记忆

```python
async def get_qa_history(self):
    """
    两层存储：
    1. 内存（SESSION_QA_HISTORY）：快速访问
    2. SQLite（tb_interaction_memory）：持久化
    """
    # 1. 先从内存获取
    qa_list = global_vars.SESSION_QA_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, [])[:self.history_len]

    if not qa_list:
        # 2. 内存没有，从SQLite查询
        raw_qa_records = await select_interaction_memory(
            self.user_id,
            self.session_id,
            self.history_len
        )
        qa_records = sqlalchemy_query_jsonify(raw_qa_records)

        # 3. 解密并构建历史
        history = []
        for qa in reversed(qa_records.get('rows')):
            qa_params = dict(zip(header, qa))
            qa_params.update({
                'question': Encryption.decrypt(qa_params.get('question')),
                'answer': Encryption.decrypt(qa_params.get('answer')),
                'function_call': Encryption.decrypt(qa_params.get('function_call'))
            })
            history.append(InteractionMemory(**qa_params))

        # 4. 存入内存缓存
        global_vars.SESSION_QA_HISTORY[self.user_id] = {self.session_id: history}

    return history
```

### 2.6 答案加密保存

```python
async def generate_record_and_save(self, answer, function_call: str = None):
    """生成QA记录并加密保存"""
    qa_record = InteractionMemory(
        qa_record_id=str(uuid.uuid4().hex),
        user_id=self.user_id,
        session_id=self.session_id,
        question=self.question,
        answer=answer,
        llm_name=self.llm.name,
        function_call=function_call,
        created_at=int(time.time() * 1000)
    )

    # 1. 保存到本地内存
    add_to_local_memory(
        global_vars.SESSION_QA_HISTORY,
        self.history_len,
        qa_record
    )

    # 2. 保存到SQLite（加密存储）
    await insert_interaction_memory(
        qa_record_id=qa_record.qa_record_id,
        user_id=self.user_id,
        session_id=self.session_id,
        # 加密存储敏感信息
        question=Encryption.encrypt(qa_record.question),
        answer=Encryption.encrypt(qa_record.answer),
        function_call=Encryption.encrypt(qa_record.function_call) if qa_record.function_call else None
    )
```

---

## 3. multiagents/tools/dbmind_interface.py - 工具接口实现

**文件路径**: `GaussMaster/multiagents/tools/dbmind_interface.py`

**核心作用**: 15+数据库运维工具的实现，通过装饰器注册到工具系统。

### 3.1 工具注册机制（装饰器模式）

```python
# 使用 @base_tools 装饰器注册工具
@base_tools(
    name="summary_alarms",              # 工具唯一名称
    description="获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
@validate_return_format
def summary_alarms(start_time, end_time):
    """具体实现"""
    ...
```

### 3.2 工具注册表

| 工具名称 | 功能 | 必要参数 |
|---------|------|---------|
| `summary_alarms` | 告警汇总 | start_time, end_time |
| `cluster_diagnosis` | 集群诊断 | start_time(可选) |
| `slow_sql_rca` | 慢SQL根因分析 | query, db_name |
| `index_recommendation` | 索引推荐 | sql, db_name |
| `risk_analysis` | 风险预测 | metric, warning_hours |
| `metric_diagnosis` | 指标诊断 | metric_name, alarm_cause, start_time, end_time |
| `get_top_sqls` | Top SQL查询 | 无 |
| `get_locking_sql` | 锁等待SQL | 无 |
| `get_instance_status` | 实例状态 | 无 |
| `get_database_info` | 数据库列表 | 无 |
| `get_guc_parameter` | GUC参数查询 | name |
| `collect_stat_activity_workloads` | 活跃SQL | database, schema(可选) |
| `collect_history_statement` | 历史SQL | start_time, end_time |
| `knob_recommendation_details` | 参数推荐详情 | 无 |
| `memory_check` | 内存检查 | latest_hours(可选) |
| `status_overview` | 状态总览 | 无 |

### 3.3 典型工具实现分析

#### summary_alarms（告警汇总）

```python
@base_tools(
    name="summary_alarms",
    description="summary_alarms工具的功能是获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
@validate_return_format
def summary_alarms(start_time, end_time):
    """获取所有告警"""
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

#### slow_sql_rca（慢SQL根因分析）

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
    # 1. 构建请求参数
    params = {"db_name": db_name, "query": query}
    params.update(kwargs)

    # 2. 调用DBMind API
    url = urljoin(configs.get(DBMIND, "api_prefix"), "app/slow-sql-rca")
    response = dbmind_request("get", url, params=params)

    # 3. 解析结果
    if response.status_code == 200 and "data" in response.json():
        result = response.json()
        roots = result.get("data")[-1][0][0]  # 根因
        advice = result.get("data")[-1][1][0]   # 建议
        return formatter_table(["慢SQL根因", "诊断建议"], list(zip(roots, advice)))

    return [formatter_str(f"工具执行异常{response.status_code}")]
```

### 3.4 工具输出格式化

```python
# 统一使用 formatter_xxx 函数格式化输出
from GaussMaster.utils.ui_output_util import (
    formatter_str,       # 字符串输出
    formatter_table,     # 表格输出
    formatter_graph,      # 图形输出（用于时序数据）
    formatter_alarm,     # 告警输出
    formatter_list,      # 列表输出
    formatter_filter,    # 过滤选择输出
    formatter_title      # 标题输出
)

# 示例
target.append(formatter_str("当前数据库状态正常"))
target.append(formatter_table(headers=["指标", "值"], rows=[["CPU", "30%"]]))
target.append(formatter_graph(timestamps, values, title="CPU使用率"))
```

### 3.5 DBMind API 调用封装

```python
from GaussMaster.common.http.dbmind_request import dbmind_request

# GET 请求
response = dbmind_request("get", url, params=params)

# POST 请求
response = dbmind_request("post", url, params=params, data=json.dumps(body_params))
```

---

## 4. llms/prompt.py - Prompt工程

**文件路径**: `GaussMaster/llms/prompt.py`

**核心作用**: 定义LLM交互所需的各种Prompt模板，包括工具描述、参数提取等。

### 4.1 Prompt模板一览

| 模板名称 | 用途 | 语言 |
|---------|------|------|
| `FORMAT_INSTRUCTIONS` | LLM输出格式指导 | 英文 |
| `FORMAT_INSTRUCTIONS_ZH` | LLM输出格式指导 | 中文 |
| `PREFIX` | 系统前缀（角色设定） | 英文 |
| `PREFIX_ZH` | 系统前缀（角色设定） | 中文 |
| `TOOL_DES_ZH` | 工具匹配Prompt | 中文 |
| `TOOL_DES_EN` | 工具匹配Prompt | 英文 |
| `TOOL_INTERACT_ZH` | 工具交互Prompt（含参数提取） | 中文 |
| `TOOL_INTERACT_EN` | 工具交互Prompt（含参数提取） | 英文 |

### 4.2 工具匹配Prompt（TOOL_DES_ZH）

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

**设计要点**：
- 明确要求只输出工具名（不含其他字符）
- 明确不可用的边界情况
- 约束输出格式，便于程序解析

### 4.3 工具交互Prompt（TOOL_INTERACT_ZH）

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
"""
```

**设计要点**：
- **时间上下文**：提供当前时间，解决"今天"、"昨天"等模糊时间
- **参数完整性检查**：确保收集到所有必要参数
- **一次性询问**：避免多次往返，提高效率
- **格式约束**：便于LLM理解和遵循

### 4.4 中文VS英文Prompt对比

```python
# 中文版：详细规则 + 友好语气
TOOL_INTERACT_ZH = """
如果你想使用工具，使用该格式...
如果你想直接回复，使用该格式...
"""

# 英文版：简洁直接
FORMAT_INSTRUCTIONS = """
When responding to me, please output a response in one of two formats:
**Option 1:** Use this if you want the human to use a tool.
**Option #2:** Use this if you want to respond directly to the human.
"""
```

### 4.5 Prompt参数注入

```python
# 时间参数动态注入
propose_prompt_dict = {
    "year": str(datetime.now(tz).year),           # 2025
    "date": str(datetime.now(tz).date()),          # 2025-01-15
    "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),  # 2025-01-15 14:30:00
    "weekday": f"星期{WEEK_ZH[datetime.now(tz).weekday()]}"  # 星期三
}

propose_prompt = TOOL_INTERACT_ZH.format(**propose_prompt_dict)
```

---

## 5. common/http/_service_impl.py - HTTP服务封装

**文件路径**: `GaussMaster/common/http/_service_impl.py`

**核心作用**: 封装FastAPI，提供统一的响应格式、路由管理、流式输出能力。

### 5.1 HttpService 封装类

```python
class HttpService:
    """
    Web服务封装层

    设计目的：
    1. 解耦业务代码和Web框架
    2. 统一API响应格式
    3. 统一异常处理
    4. 支持平滑迁移（Flask → FastAPI）
    """

    def __init__(self, name=__name__):
        # 内部使用 FastAPI
        self.app = FastAPI(
            title=name,
            openapi_url=None,  # 禁用OpenAPI文档
            docs_url=None,
            redoc_url=None
        )
        self._server = None

        # 统一异常处理
        @self.app.exception_handler(StarletteHTTPException)
        async def exception_handler(_, exc):
            return JSONResponse(
                content={'success': False, 'msg': str(exc.detail)},
                status_code=exc.status_code
            )

        # 语言中间件
        @self.app.middleware("http")
        async def set_language_middleware(request: Request, call_next):
            accept_language = request.headers.get('Accept-Language', global_vars.LANGUAGE)
            global_vars.LANGUAGE = parse_accept_language(accept_language)
            response = await call_next(request)
            return response
```

### 5.2 统一响应格式装饰器

```python
def standardized_api_output(f):
    """
    统一JSON响应格式
    所有返回自动包装为 {success: true/false, data/msg: xxx}
    """
    class ToleratedEncoder(json.JSONEncoder):
        """处理NaN、Infinity等非法JSON值"""
        def default(self, o):
            return str(o)

    class ToleratedJSONResponse(JSONResponse):
        def render(self, content) -> bytes:
            return json.dumps(
                content,
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                sort_keys=True,
                separators=(",", ":"),
                cls=ToleratedEncoder
            ).encode("utf-8")

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            data = f(*args, **kwargs)
            # 成功：{success: true, data: xxx}
            return ToleratedJSONResponse(content={'success': True, 'data': data})
        except HTTPException as e:
            raise e
        except Exception as e:
            logging.getLogger('uvicorn.error').exception(e)
            # 失败：{success: false, msg: xxx}
            return ToleratedJSONResponse(
                content={'success': False, 'msg': 'Internal server error.'}
            )

    # 支持异步函数
    if inspect.iscoroutinefunction(f):
        return async_wrapper
    return wrapper
```

### 5.3 流式响应装饰器

```python
def standardized_event_stream_output(f):
    """
    统一SSE流式响应格式
    用于LLM流式输出
    """
    @wraps(f)
    async def wrapper(*args, **kwargs):
        generator = f(*args, **kwargs)

        async def standardize_generator():
            try:
                async for item in generator:
                    # 标准化SSE格式
                    yield f"data:{json.dumps({'success': True, 'data': item})}\n\n"
            except Exception as e:
                logging.getLogger('uvicorn.error').exception(e)
                yield f"data:{json.dumps({'success': False, 'msg': 'Internal server error.'})}\n\n"

        return StreamingResponse(
            standardize_generator(),
            media_type="text/event-stream"
        )

    return wrapper
```

### 5.4 路由注册机制

```python
# 全局路由表
_RequestMappingTable = dict()

def request_mapping(rule, method, **kwargs):
    """记录路由到静态映射表"""
    def decorator(f):
        _RequestMappingTable[(rule, method)] = (f, kwargs)
        return f
    return decorator

# 使用示例
@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    return data_transformer.ask_gauss(...)
```

### 5.5 SSL/TLS安全配置

```python
def start_listen(self, host, port, ssl_keyfile=None, ssl_certfile=None,
                 ssl_keyfile_password=None, ssl_ca_file=None):
    # ...配置代码...

    if config.is_ssl:
        # 禁用不安全协议
        config.ssl.options |= (
            ssl.OP_NO_SSLv2 |    # 禁用SSLv2
            ssl.OP_NO_SSLv3 |   # 禁用SSLv3
            ssl.OP_NO_TLSv1 |   # 禁用TLSv1.0
            ssl.OP_NO_TLSv1_1   # 禁用TLSv1.1
        )
        # 强制TLS >= 1.2（RFC 7540）

        # 使用强加密套件
        config.ssl.set_ciphers('DHE+AESGCM:ECDHE+AESGCM')
```

### 5.6 封装层价值分析

| 封装内容 | 没有封装 | 有封装 |
|---------|---------|--------|
| 响应格式 | 每个接口自己包装 | `@standardized_api_output` 自动处理 |
| 异常处理 | 每个接口try-catch | 统一捕获 |
| 流式输出 | 每个接口处理SSE格式 | `@standardized_event_stream_output` |
| 换框架 | 所有代码重写 | 只需改HttpService |
| 代码量 | N × 重复逻辑 | N × 装饰器 |

---

## 面试核心问答

### Q1: 工具调用流程是怎样的？

```
用户问题
   ↓
infer_tool_name() → 意图识别（LLM判断用哪个工具）
   ↓
check_has_valid_tool() → 工具存在性校验
   ↓
check_is_no_param_tool() → 是否需要参数
   ↓
infer_arguments() → 参数提取（LLM从问题中提取参数）
   ↓
verify_arguments() → 参数完整性校验
   ↓
call_tool() → 执行工具
   ↓
返回结果给用户
```

### Q2: 为什么要用意图状态保持？

```
场景：多轮对话
用户: "帮我查看告警"
       ↓ 推断工具: summary_alarms
       ↓ 保存到 SESSION_TOOL_HISTORY

用户: "是哪个集群的问题？" （追问）
       ↓ SESSION_TOOL_HISTORY 有值
       ↓ 直接提取参数，无需重新推断工具
       ↓ 更高效
```

### Q3: 多层存储的对话记忆是如何工作的？

```
访问顺序：
1. SESSION_QA_HISTORY（内存）→ 快速访问
   ↓ 没有
2. tb_interaction_memory（SQLite）→ 持久化存储
   ↓
解密 + 构建历史对象 → 返回
```

### Q4: Prompt为什么要区分中英文？

```
1. 用户群体不同：
   - 中文用户 → 中文Prompt更容易理解指令
   - 英文用户 → 英文Prompt更精确

2. LLM对不同语言的响应质量不同：
   - 中文LLM（盘古）→ 中文Prompt效果更好
   - 英文LLM（Llama）→ 英文Prompt效果更好
```

### Q5: HTTP封装层解决了什么问题？

```
1. 统一响应格式：{success, data/msg}
2. 统一异常处理：try-catch只写一次
3. 解耦：业务代码不依赖FastAPI
4. 流式输出：SSE格式统一处理
```

---

*本文档由代码分析生成，基于 openGauss-GaussMaster v1.0.0*
