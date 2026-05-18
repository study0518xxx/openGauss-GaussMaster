# GaussMaster 核心文件函数详解（续）

## executor.py - 工具调用执行器（续）

### 2. infer_arguments()（续）

```python
@timer_decorator
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """
    【步骤4】参数提取：从用户问题中提取工具参数
    
    流程:
    1. 获取目标工具的详细描述（带参数定义）
    2. 构建时间参数（当前时间、日期等）
    3. 根据不同模型使用不同的Prompt策略
    4. 调用LLM提取参数
    5. 解析返回结果
    
    参数:
        question: str                   # 用户问题
        intention_tool: str             # 意图工具名
        qa_record_history: List         # 对话历史
        llm: BaseLLM                    # LLM实例
    
    返回:
        content_resp: str               # 响应内容
        function_call: dict             # {name: tool_name, arguments: {...}}
    
    Prompt示例:
        系统: "时间设定：今年2025年，今天2025-01-15..."
        用户: "帮我查看昨天的告警"
        
        LLM返回: {name: "summary_alarms", arguments: {start_time: "...", end_time: "..."}}
    """
    # 1. 获取工具详细描述（带参数）
    if llm.llm_type == LLMType.PANGUCLOUD:
        target_tool_des = json.dumps(base_tools.get(intention_tool).__detail_with_param_dict__)
        target_tool_des = target_tool_des.replace('{', '{{').replace('}', '}}')
    else:
        target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__
    
    # 2. 构建时间参数
    tz = adjust_timezone(global_vars.configs.get('TIMEZONE', 'tz'))
    propose_prompt_dict = {
        "year": str(datetime.now(tz).year),
        "date": str(datetime.now(tz).date()),
        "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),
        "weekday": f"星期{WEEK_ZH[datetime.now(tz).weekday()]}" if LANGUAGE == 'zh'
        else WEEK_CN[datetime.now(tz).weekday()]
    }
    
    # 3. 盘古/盘古云模型特殊处理
    if llm.llm_type in [LLMType.PANGUCLOUD, LLMType.PANGU]:
        propose_prompt_dict['functions'] = target_tool_des
        propose_prompt = (
            TOOL_INTERACT_ZH.format(**propose_prompt_dict)
            if LANGUAGE == 'zh'
            else TOOL_INTERACT_EN.format(**propose_prompt_dict)
        )
        
        # 清理特殊标记
        if llm.llm_type != LLMType.PANGUCLOUD:
            propose_prompt = propose_prompt.replace("<unused1><unused0>", "")
        
        # 构建消息（包含历史对话）
        message_inputs = [{LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: propose_prompt}]
        history = []
        for qa in qa_record_history:
            question_dict = {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: qa.question}
            history.append(question_dict)
            answer_dict = {LLMMsgKey.ROLE: LLMRole.ASSISTANT, LLMMsgKey.CONTENT: qa.answer}
            if qa.function_call:
                answer_dict[LLMMsgKey.FUNCTION_CALL] = qa.function_call
            history.append(answer_dict)
        message_inputs.extend(history)
        message_inputs.append({LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question})
        
        content_resp, function_call = await llm.invoke(message_inputs)
    
    # 4. 其他模型使用专门的参数提取Prompt
    else:
        prompt = construct_extract_tool_params_prompt(
            user_question=question,
            tools_description=target_tool_des,
            qa_history=qa_record_history,
            time_args=propose_prompt_dict
        )
        message_inputs = [{LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: prompt}]
        result, _ = await llm.invoke(message_inputs)
        
        # 解析参数
        arguments, success = output_parser.parse_params(result)
        if success:
            content_resp = f'将调用工具{intention_tool}'
            function_call = {'name': intention_tool, 'arguments': arguments} if arguments else {}
        else:
            content_resp = f'工具参数解析失败，请重新提供参数：{result}'
            function_call = {}
    
    return content_resp, function_call
```

**逻辑详解**:
1. **获取工具描述**：从 `base_tools` 获取带参数定义的工具描述
2. **时间参数**：构建当前时间、日期、星期等上下文信息
3. **模型适配**：
   - 盘古/盘古云：使用结构化Prompt，支持function_call
   - 其他模型：使用专门的参数提取Prompt
4. **历史对话**：将历史QA记录加入Prompt，支持多轮对话
5. **参数解析**：使用 `output_parser.parse_params()` 解析LLM返回

---

### 3. check_has_valid_tool()

```python
def check_has_valid_tool(tool_name):
    """
    【步骤2】工具校验：检查工具是否在注册表中
    
    参数:
        tool_name: str  # 工具名称
    
    返回:
        bool  # True: 工具存在, False: 工具不存在
    
    逻辑:
        从 global_vars.tools_registry 查找工具
    """
    target_tool = global_vars.tools_registry.get(tool_name, None)
    return target_tool is not None
```

---

### 4. check_is_no_param_tool()

```python
def check_is_no_param_tool(tool_name):
    """
    【步骤3】参数检查：检查工具是否需要参数
    
    参数:
        tool_name: str  # 工具名称
    
    返回:
        bool  # True: 无参工具, False: 需要参数
    
    逻辑:
        检查工具的 __param_dict_list__ 是否为空
    """
    target_tool = global_vars.tools_registry.get(tool_name, None)
    if target_tool and len(target_tool.__param_dict_list__) == 0:
        return True
    return False
```

---

### 5. verify_arguments()

```python
def verify_arguments(function_call: dict = None):
    """
    【步骤5】参数验证：检查参数是否完整正确
    
    参数:
        function_call: dict  # {name: tool_name, arguments: {...}}
    
    返回:
        (is_complete, correct_params, need_params)
        - is_complete: bool      # 参数是否完整
        - correct_params: dict   # 正确的参数
        - need_params: dict      # 还需要的参数
    
    逻辑:
        调用 has_correct_params() 检查参数完整性
    """
    func_name = function_call.get('name')
    try:
        arguments = json.loads(function_call.get('arguments'))
    except TypeError:
        arguments = function_call.get('arguments')
    return has_correct_params(arguments, global_vars.tools_registry.get(func_name))
```

---

### 6. call_tool()

```python
@timer_decorator
def call_tool(tool_name: str, params=None):
    """
    【步骤6】工具执行：调用具体的工具函数
    
    参数:
        tool_name: str   # 工具名称
        params: dict     # 工具参数（默认空字典）
    
    返回:
        function_result  # 工具执行结果
    
    逻辑:
        从 tools_registry 获取工具函数并执行
    """
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

---

### 7. llm_call()

```python
@timer_decorator
async def llm_call(user_prompt, llm, system_prompt: str = None):
    """
    【通用LLM调用】简单的LLM调用封装
    
    参数:
        user_prompt: str      # 用户提示词
        llm: BaseLLM          # LLM实例
        system_prompt: str    # 系统提示词（可选）
    
    返回:
        response: str  # LLM响应
    
    用途:
        简单的单轮对话，不需要复杂逻辑
    """
    message_inputs = []
    if system_prompt:
        message_inputs.append({LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: system_prompt})
    message_inputs.append({LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: user_prompt})
    response, _ = await llm.invoke(message_inputs)
    return response
```

---

## dbmind_interface.py - 工具实现

**路径**: `GaussMaster/multiagents/tools/dbmind_interface.py`

**作用**: 定义所有可用的运维工具，通过装饰器注册到系统

### 核心装饰器

#### @base_tools

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
2. 生成工具描述（给LLM看的）
3. 记录参数定义

---

### 核心工具函数

#### 1. summary_alarms() - 告警汇总

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
    
    逻辑:
        1. 时间转换
        2. 获取集群列表
        3. 批量获取告警
        4. 格式化输出
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

---

#### 2. cluster_diagnosis() - 集群诊断

```python
@base_tools(
    name="cluster_diagnosis",
    description="cluster_diagnosis工具的功能是对集群进行诊断",
    params=[
        Param(name="start_time", description="开始时间（可选）", param_type="str", required=False)
    ]
)
def cluster_diagnosis(start_time=None):
    """
    【集群诊断】对集群进行全面诊断
    
    参数:
        start_time: str  # 开始时间（可选）
    
    返回:
        dict  # 诊断结果
    """
    ...
```

---

#### 3. slow_sql_rca() - 慢SQL根因分析

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
    
    逻辑:
        调用DBMind的慢SQL诊断API
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

---

#### 4. index_recommendation() - 索引推荐

```python
@base_tools(
    name="index_recommendation",
    description="index_recommendation工具的功能是推荐索引",
    params=[
        Param(name="sql", description="SQL语句", param_type="str"),
        Param(name="db_name", description="数据库名", param_type="str")
    ]
)
def index_recommendation(sql, db_name):
    """【索引推荐】为SQL推荐优化索引"""
    ...
```

---

#### 5. get_top_sqls() - Top SQL查询

```python
@base_tools(
    name="get_top_sqls",
    description="get_top_sqls工具的功能是获取Top SQL",
    params=[]  # 无参工具
)
def get_top_sqls():
    """【Top SQL】获取执行时间最长的SQL"""
    ...
```

---

### 工具列表汇总

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

## prompt.py - Prompt工程

**路径**: `GaussMaster/llms/prompt.py`

**作用**: 定义所有Prompt模板

### 核心Prompt模板

#### 1. TOOL_DES_ZH - 工具匹配Prompt

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

**用途**: 让LLM选择最合适的工具

---

#### 2. TOOL_INTERACT_ZH - 工具交互Prompt

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

**用途**: 让LLM提取参数并生成function_call

---

#### 3. FORMAT_INSTRUCTIONS - 输出格式指导

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

## data_transformer.py - 数据转换层

**路径**: `GaussMaster/server/web/data_transformer.py`

**作用**: RAG知识问答的核心实现

### 核心函数

#### 1. ask_gauss()

```python
async def ask_gauss(question, user_id, session_id, switch, vector_topk, text_topk,
                    rerank_topk, kb_id, version, model_name, lang, history_len, model_config):
    """
    【RAG知识问答】端到端问答流程
    
    流程:
    1. 参数校验
    2. 敏感词检测
    3. RAG检索（search）
    4. LLM生成答案（llm_generation）
    5. 保存到数据库
    
    参数: ...
    
    返回: 流式生成器
    """
    # 1. 参数校验
    if not question:
        raise ValueError('question can not be empty.')
    
    # 2. 敏感词检测
    if (global_vars.configs.get(SECTION_SAFETY, 'safety_check').strip().upper() == 'TRUE'
            and global_vars.DFA_DETECTOR.is_unsafe_text(question)):
        yield {'type': 'answer', 'data': '无法回答安全敏感话题！'}
        return
    
    # 3. 初始化QA记录
    answer_id = str(uuid.uuid4())
    qa_dict = {...}
    
    # 4. RAG检索
    yield {'type': 'progress', 'data': '问题检索中...'}
    res_dict = await search(...)
    search_res = res_dict['search_res']
    
    # 5. 生成答案
    if not search_res:
        # 无检索结果，进入查询优化
        async for item in query_opt_process(...):
            yield item
    else:
        # 有检索结果，LLM生成
        async for item in llm_generation(question, search_res, model_name, history, lang):
            yield item
    
    # 6. 保存记录
    gaussdb_vector.insert_qa_record(qa_dict)
```

---

#### 2. search() - RAG检索

```python
async def search(question, user_id, session_id, vector_topk, text_topk, rerank_topk,
                 kb_id, version, lang, history_len):
    """
    【RAG检索】向量检索 + 文本检索 + 重排序
    
    流程:
    1. 确定知识库表名
    2. 向量检索（语义相似度）
    3. 文本检索（关键词匹配）
    4. 重排序（Reranker）
    5. 组装结果
    
    返回:
        {
            'search_res': [...],           # 检索结果
            'vector_search_time': float,   # 向量检索耗时
            'text_search_time': float,     # 文本检索耗时
            'rerank_search_time': float,   # 重排序耗时
            'question_id': str
        }
    """
    # 1. 确定知识库
    if kb_id == 0:
        table_name = kb_config.KT_TABLE_NAME + "_" + lang
    else:
        table_name = CUSTOM_KB_PREFIX + str(kb_id)
    
    # 2. 获取数据库实例
    gaussdb = get_db_instance(table_name, kb_config.KT_TABLE_CONFIG)
    
    # 3. 创建检索器
    retriever = BaseRetriever(gaussdb, global_vars.reranker_model)
    
    # 4. 向量检索
    vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)
    
    # 5. 文本检索
    text_result = retriever.search_text_result_gaussdb(question, text_topk, version)
    
    # 6. 重排序
    reranker_scores, reranker_result = await retriever.reranker_search_result(
        question, vector_result, text_result, rerank_topk
    )
    
    # 7. 组装结果
    search_res = []
    for index, answer in enumerate(reranker_result):
        knowledge_dict = {
            'knowledge_id': answer[column_list.index('uuid')],
            'content': answer[column_list.index('text')],
            'title': answer[column_list.index('title')],
            'source': answer[column_list.index('source')],
            'score': reranker_scores[index],
        }
        search_res.append(knowledge_dict)
    
    return {...}
```

---

#### 3. llm_generation()

```python
async def llm_generation(question, search_res, model_name, history, lang):
    """
    【LLM生成答案】
    
    流程:
    1. 返回参考资料
    2. 构建Prompt
    3. 调用LLM生成
    """
    # 1. 返回参考资料
    yield {'type': 'refrences', 'data': json.dumps(search_res, ensure_ascii=False)}
    yield {'type': 'progress', 'data': '检索完成'}
    
    # 2. 构建Prompt
    status, messages = create_infer_prompt_direct(question, search_res, history, lang)
    
    # 3. 调用LLM
    yield {'type': 'progress', 'data': '答案生成中...'}
    answer = ""
    async for item in generate_answer(messages, model_name):
        answer += item
        yield {'type': 'answer', 'data': answer}
```

---

## 总结

### 核心调用链

```
┌─────────────────────────────────────────────────────────────┐
│                    工具调用流程（dba.interact）               │
├─────────────────────────────────────────────────────────────┤
│ core.py → dba.interact() → DBA.interaction()               │
│    ↓                                                       │
│ DBA.interact_with_tool()                                   │
│    ↓                                                       │
│ infer_tool_name() → check_has_valid_tool()                │
│ check_is_no_param_tool() → infer_arguments()              │
│ verify_arguments() → call_tool()                          │
│    ↓                                                       │
│ dbmind_interface.py: summary_alarms等                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    RAG问答流程（ask_gauss）                  │
├─────────────────────────────────────────────────────────────┤
│ core.py → data_transformer.ask_gauss()                     │
│    ↓                                                       │
│ search() → 向量检索 + 文本检索 + 重排序                     │
│    ↓                                                       │
│ llm_generation() → create_infer_prompt()                  │
│    ↓                                                       │
│ generate_answer() → LLM生成                                │
└─────────────────────────────────────────────────────────────┘
```

---

*本文档基于 openGauss-GaussMaster v1.0.0*
