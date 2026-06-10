# GaussMaster 核心文件函数详解

## 目录

- [core.py - 控制器层](#corepy---控制器层)
- [dba.py - DBA Agent](#dbapy---dba-agent)
- [executor.py - 工具调用执行器](#executorpy---工具调用执行器)
- [dbmind_interface.py - 工具实现](#dbmind_interfacepy---工具实现)
- [prompt.py - Prompt工程](#promptpy---prompt工程)
- [data_transformer.py - 数据转换层](#data_transformerpy---数据转换层)

---

## core.py - 控制器层

**路径**: `GaussMaster/controllers/core.py`

**作用**: HTTP API路由定义，系统的入口层

### 核心装饰器

| 装饰器 | 作用 |
|--------|------|
| `@request_mapping` | 注册HTTP路由 |
| `@standardized_api_output` | 统一JSON响应格式 |
| `@standardized_event_stream_output` | 流式SSE响应 |
| `@ParameterChecker.define_rules` | 参数校验 |

### 核心函数

#### 1. intelligent_interaction_chat()

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
@switch_llm_context_decorator
def intelligent_interaction_chat(query: PlanModel):
    """
    【智能交互入口】工具调用流程的主入口
    
    功能:
    1. 接收用户问题
    2. 添加当前LLM模型名到参数
    3. 调用 dba.interact() 进入Agent流程
    
    请求参数:
        query: PlanModel {
            query: str          # 用户问题
            user_id: str        # 用户ID
            session_id: str     # 会话ID
            mode: str           # 交互模式
            history_len: int    # 历史长度
        }
    
    调用链:
        core.py → dba.interact() → DBA.interaction() → DBA.interact_with_tool()
    """
    plan_model = dict(query)
    plan_model.update({'model_name': current_llm.get()})
    return dba.interact(**plan_model)
```

**逻辑详解**:
1. 接收前端传来的 `PlanModel` 参数
2. 从 `current_llm` 获取当前使用的LLM模型名
3. 调用 `dba.interact()` 进入Agent处理流程
4. 返回流式生成器，支持SSE实时输出

---

#### 2. ask_gauss()

```python
@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    """
    【智能问答入口】RAG知识问答流程的主入口
    
    功能:
    1. 接收用户问题和检索参数
    2. 调用 data_transformer.ask_gauss() 进入RAG流程
    
    请求参数:
        search_params: SearchParams {
            question: str       # 用户问题
            user_id: str
            session_id: str
            vector_topk: int   # 向量检索Top-K
            text_topk: int     # 文本检索Top-K
            rerank_topk: int   # 重排序Top-K
            kb_id: int         # 知识库ID
            model_name: str
            lang: str
            history_len: int
        }
    
    调用链:
        core.py → data_transformer.ask_gauss() → search() → llm_generation()
    """
    return data_transformer.ask_gauss(
        search_params.question,
        search_params.user_id,
        search_params.session_id,
        search_params.switch,
        search_params.vector_topk,
        search_params.text_topk,
        search_params.rerank_topk,
        search_params.kb_id,
        search_params.version,
        search_params.model_name,
        search_params.lang,
        search_params.history_len,
        search_params.model_config
    )
```

**逻辑详解**:
1. 接收前端传来的 `SearchParams` 参数
2. 解包参数并传递给 `data_transformer.ask_gauss()`
3. 返回流式生成器

---

#### 3. register_cluster()

```python
@request_mapping(api_prefix + "/clusters/register", method='POST', api=True)
@standardized_api_output
def register_cluster(cluster: Cluster):
    """
    【集群注册】将openGauss集群注册到GaussMaster
    
    功能:
    1. 接收集群连接信息
    2. 调用 data_transformer.register_cluster() 保存到数据库
    
    请求参数:
        cluster: Cluster {
            cluster_name: str   # 集群名称
            host: str           # 主机地址
            port: int           # 端口
            username: str       # 用户名
            password: str       # 密码
        }
    """
    return data_transformer.register_cluster(cluster)
```

---

#### 4. get_clusters() / put_clusters()

```python
@request_mapping(api_prefix + "/clusters", method='GET', api=True)
@standardized_api_output
def get_clusters():
    """【获取集群列表】获取所有托管的集群状态"""
    return retrieve_clusters_status()

@request_mapping(api_prefix + "/clusters", method='PUT', api=True)
@standardized_api_output
def put_clusters(user_id, session_id, instance):
    """【更新会话集群】为指定会话设置默认集群"""
    return update_session_cluster(user_id, session_id, instance)
```

---

#### 5. get_llms() / set_user_session_llm()

```python
@request_mapping(api_prefix + "/llms", method='GET', api=True)
def get_llms():
    """【获取模型列表】获取所有可用的LLM"""
    return get_all_models()

@request_mapping(api_prefix + "/llms", method='PUT', api=True)
def set_user_session_llm(name, user_id, session_id):
    """【切换模型】为指定用户会话切换LLM"""
    return switch_llm(name, user_id, session_id)
```

---

## dba.py - DBA Agent

**路径**: `GaussMaster/multiagents/agents/dba.py`

**作用**: DBA Agent实现，对话管理和工具调用的核心

### 模块级函数

#### 1. interact()

```python
async def interact(user_id, session_id, query, mode, model_name, history_len=1, lang='zh'):
    """
    【对话交互入口】创建DBA实例并启动交互流程
    
    参数:
        user_id: str        # 用户ID
        session_id: str     # 会话ID
        query: str          # 用户问题
        mode: str           # 交互模式 ('tool_interaction' / 'fault_diagnostic')
        model_name: str     # LLM模型名
        history_len: int    # 历史记录长度（默认1）
        lang: str           # 语言（默认'zh'）
    
    功能:
    1. 创建DBA实例
    2. 调用 dba.interaction() 生成器
    3. 流式yield每个步骤的输出
    4. 最后yield [DONE_FLAG]标记结束
    
    调用链:
        interact() → DBA.__init__() → DBA.interaction() → DBA.interact_with_tool()
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
    async for step_output in dba.interaction():
        yield step_output
    yield [DONE_FLAG]
```

**逻辑详解**:
1. 接收core.py传来的参数
2. 实例化 `DBA` 类
3. 调用 `dba.interaction()` 进入主交互流程
4. 使用 `async for` 流式输出每个步骤
5. 最后输出 `[DONE_FLAG]` 标记结束

---

#### 2. instantiate_llm()

```python
def instantiate_llm(model_name: str):
    """
    【实例化LLM】根据模型名创建LLM对象
    
    参数:
        model_name: str  # 模型名称
    
    功能:
    1. 从 global_vars.llm_config 获取模型配置
    2. 获取模型类型和API地址
    3. 从 llm_registry 获取对应的LLM类并实例化
    
    返回:
        llm: BaseLLM子类实例
    
    异常:
        ValueError: 如果模型未注册
    """
    llm_config = global_vars.llm_config
    model_params = llm_config.get('online_llm').get(model_name, None)
    if not model_params:
        raise ValueError(f"The model {model_name} is not registered.")
    
    model_type = model_params.get('api_type')
    api_url = model_params.get('api_url')
    llm = llm_registry.get(model_type)(model_name, api_url)
    return llm
```

**逻辑详解**:
1. 从全局配置中获取模型参数
2. 如果模型不存在，抛出异常
3. 获取模型类型（Pangu/ChatGLM/Llama等）
4. 从注册表获取对应的类并实例化

---

### DBA 类

#### __init__()

```python
def __init__(self, question, user_id, session_id, mode, llm_name, history_len, lang):
    """
    【初始化DBA Agent】
    
    属性:
        self.question: str              # 用户问题
        self.mode: str                  # 交互模式
        self.embedding: EmbeddingModel  # Embedding模型（用于向量检索）
        self.memory: dict               # 内存存储（线程隔离）
        self.alarm: dict                # 告警数据缓存
        self.user_id: str               # 用户ID
        self.session_id: str            # 会话ID
        self.llm: BaseLLM               # LLM实例
        self.history_len: int           # 历史长度
        self.lang: str                  # 语言
    """
    self.question = question
    self.mode = mode
    self.embedding = global_vars.embedding_model
    self.memory = global_vars.MEMORY
    self.alarm = {}
    self.user_id = user_id
    self.session_id = session_id
    self.llm = instantiate_llm(llm_name)
    self.history_len = history_len
    self.lang = lang
```

---

#### interaction()

```python
@stream_exception_catcher
async def interaction(self):
    """
    【主交互流程】根据mode选择不同的处理方式
    
    功能:
    1. 快捷场景判断（直接调用工具，不需要LLM推断）
    2. 工具交互模式：调用 interact_with_tool()
    3. 故障诊断模式：暂不支持
    
    快捷场景:
        - "当前数据库运行状况" → 直接调用 summary_alarms（最近1小时）
        - "当前有哪些告警" → 同上
    
    流式输出:
        - 每个步骤通过 yield 返回
        - 使用 formatter_progress() 显示进度
        - 使用 formatter_str() 显示文本结果
    """
    # 快捷场景：直接调用工具
    if self.question in ['当前数据库运行状况', '当前有哪些告警']:
        tz = adjust_timezone(global_vars.configs.get('TIMEZONE', 'tz'))
        end_time = datetime.now(tz)
        start_time = end_time - timedelta(minutes=60)  # 默认最近1小时
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

**逻辑详解**:
1. **快捷场景判断**：如果是固定问题，直接调用工具，不走LLM推断
2. **工具交互模式**：调用 `interact_with_tool()` 进入标准流程
3. **流式输出**：使用 `yield` 返回每个步骤的结果

---

#### interact_with_tool()

```python
async def interact_with_tool(self):
    """
    【工具交互核心】完整的工具调用流程（5步）
    
    流程:
    1. 检查意图状态（SESSION_TOOL_HISTORY）
    2. 如果没有意图，推断工具名（infer_tool_name）
    3. 校验工具有效性（check_has_valid_tool）
    4. 检查是否需要参数（check_is_no_param_tool）
    5. 提取参数（infer_arguments）
    6. 验证参数完整性（verify_arguments）
    7. 调用工具（call_tool）
    
    多轮对话支持:
        - 通过 SESSION_TOOL_HISTORY 保持当前工具意图
        - 追问时不需要重新推断工具
    
    流式输出:
        - '工具匹配中...'
        - '提取参数中...'
        - '工具调用中...'
        - 工具执行结果
    """
    # ====== 步骤1: 检查意图状态 ======
    intention_tool = global_vars.SESSION_TOOL_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, None)
    
    # ====== 步骤2: 如果没有意图，需要推断 ======
    if intention_tool is None:
        # 2.1 匹配工具
        yield [formatter_progress('工具匹配中...')]
        matched_tool = await infer_tool_name(
            self.question, self.user_id, self.session_id, self.llm
        )
        
        # 2.2 校验工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            content_resp = '用户提问的问题无法用第三方工具解答。'
            await self.save_assistant_resp(content_resp=content_resp)
            yield [formatter_str(content_resp)]
            return
        
        # 2.3 检查是否需要参数
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            # 无参工具，直接调用
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(matched_tool)
            yield tool_result
            content_resp = f'将为您调用工具{matched_tool}'
            await self.save_assistant_resp(
                content_resp=content_resp, 
                tool_name=matched_tool
            )
            return
        
        intention_tool = matched_tool
    
    # ====== 步骤3: 提取参数 ======
    yield [formatter_progress('提取参数中...')]
    qa_record_history = await self.get_qa_history()
    content_resp, function_call = await infer_arguments(
        self.question,
        intention_tool,
        qa_record_history,
        self.llm
    )
    
    # ====== 步骤4: 调用工具 ======
    if function_call:
        is_complete_params, correct_params, need_prams = verify_arguments(function_call)
        
        if is_complete_params:
            # 参数完整，调用工具
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(intention_tool, correct_params)
            await self.save_assistant_resp(
                content_resp=content_resp,
                tool_name=intention_tool,
                tool_params=correct_params
            )
            yield tool_result
        else:
            # 参数不完整，提示用户提供
            content_resp = f'缺少参数{",".join(list(need_prams.keys()))}，请一次性提供完整'
            await self.save_assistant_resp(
                content_resp=content_resp,
                intent_tool=intention_tool
            )
            yield [formatter_str(content_resp)]
    else:
        # function_call为空
        await self.save_assistant_resp(
            content_resp=content_resp,
            intent_tool=intention_tool
        )
        yield [formatter_str(content_resp)]
```

**逻辑详解**:
1. **意图状态检查**：先看 `SESSION_TOOL_HISTORY` 是否有未完成的工具
2. **工具推断**：如果没有，调用 `infer_tool_name()` 让LLM推断
3. **工具校验**：检查工具是否在注册表中
4. **无参工具**：如果不需要参数，直接调用
5. **参数提取**：调用 `infer_arguments()` 让LLM提取参数
6. **参数验证**：检查参数是否完整
7. **工具执行**：调用 `call_tool()` 执行具体工具

---

#### get_qa_history()

```python
async def get_qa_history(self):
    """
    【获取对话历史】双层存储机制
    
    存储层级:
        1. 内存层: SESSION_QA_HISTORY（快速访问）
        2. 持久层: SQLite数据库（长期存储）
    
    流程:
        1. 先从内存获取
        2. 如果没有，从SQLite查询
        3. 解密敏感信息（question/answer/function_call）
        4. 存入内存缓存
    
    返回:
        List[InteractionMemory]  # 对话历史列表
    """
    # 1. 从内存获取
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
        header = qa_records.get('header')
        qa_rows = list(reversed(qa_records.get('rows')))
        
        for qa in qa_rows:
            qa_params = dict(zip(header, qa))
            qa_params.update({
                'question': Encryption.decrypt(qa_params.get('question')),
                'answer': Encryption.decrypt(qa_params.get('answer')),
                'function_call': Encryption.decrypt(qa_params.get('function_call'))
                if qa_params.get('function_call') else None
            })
            history.append(InteractionMemory(**qa_params))
        
        # 4. 存入内存缓存
        global_vars.SESSION_QA_HISTORY[self.user_id] = {self.session_id: history}
        return history
    
    return qa_list
```

**逻辑详解**:
1. **内存优先**：先从 `SESSION_QA_HISTORY` 获取，速度快
2. **数据库回源**：内存没有则从SQLite查询
3. **解密处理**：使用 `Encryption.decrypt()` 解密敏感字段
4. **缓存更新**：查询结果存入内存，下次直接命中

---

#### generate_record_and_save()

```python
async def generate_record_and_save(self, answer, function_call: str = None):
    """
    【保存对话记录】双层存储 + 加密
    
    存储:
        1. 内存: SESSION_QA_HISTORY（快速访问）
        2. SQLite: tb_interaction_memory（持久化）
    
    加密:
        - question: AES256加密
        - answer: AES256加密
        - function_call: AES256加密
    
    参数:
        answer: str              # 回答内容
        function_call: str       # 工具调用记录（JSON字符串）
    """
    # 1. 创建QA记录
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
    
    # 2. 保存到内存
    add_to_local_memory(
        global_vars.SESSION_QA_HISTORY,
        self.history_len,
        qa_record
    )
    
    # 3. 保存到SQLite（加密存储）
    await insert_interaction_memory(
        qa_record_id=qa_record.qa_record_id,
        user_id=qa_record.user_id,
        session_id=qa_record.session_id,
        question=Encryption.encrypt(qa_record.question),
        created_at=qa_record.created_at,
        llm_name=qa_record.llm_name,
        answer=Encryption.encrypt(qa_record.answer),
        function_call=Encryption.encrypt(qa_record.function_call) 
        if qa_record.function_call else None
    )
```

**逻辑详解**:
1. **创建记录**：生成唯一ID和时间戳
2. **内存存储**：添加到 `SESSION_QA_HISTORY`
3. **数据库存储**：使用 `Encryption.encrypt()` 加密后存入SQLite

---

#### save_assistant_resp()

```python
async def save_assistant_resp(self, content_resp, intent_tool: str = None, 
                              tool_name: str = None, tool_params: dict = None):
    """
    【保存助手响应】更新意图状态并保存记录
    
    功能:
    1. 更新 SESSION_TOOL_HISTORY（意图状态保持）
    2. 构建 function_call 记录
    3. 调用 generate_record_and_save() 保存
    
    参数:
        content_resp: str       # 响应内容
        intent_tool: str        # 意图工具名（用于多轮对话保持）
        tool_name: str          # 实际调用的工具名
        tool_params: dict       # 工具参数
    """
    # 1. 更新意图状态（关键！用于多轮对话）
    global_vars.SESSION_TOOL_HISTORY.update({
        self.user_id: {self.session_id: intent_tool}
    })
    
    # 2. 如果有工具调用，构建function_call记录
    if tool_name:
        function_call = {
            'tool_name': tool_name,
            'arguments': tool_params if tool_params else {}
        }
        await self.generate_record_and_save(
            content_resp, 
            json.dumps(function_call)
        )
        function_call['question'] = self.question
    else:
        await self.generate_record_and_save(content_resp, None)
```

**逻辑详解**:
1. **意图保持**：更新 `SESSION_TOOL_HISTORY`，下次追问时直接用
2. **记录构建**：如果有工具调用，构建JSON格式的记录
3. **保存调用**：调用 `generate_record_and_save()` 完成保存

---

## executor.py - 工具调用执行器

**路径**: `GaussMaster/llms/executor.py`

**作用**: 工具调用的核心逻辑，控制意图识别→参数提取→工具执行的完整流程

### 核心函数

#### 1. infer_tool_name()

```python
@timer_decorator
async def infer_tool_name(question: str, user_id, session_id, llm):
    """
    【步骤1】意图识别：根据用户问题推断应该使用哪个工具
    
    流程:
    1. 获取所有工具的描述列表
    2. 构建意图识别Prompt（TOOL_DES_ZH）
    3. 检查 SESSION_TOOL_HISTORY（意图状态保持）
    4. 如果没有，调用LLM推断工具名
    
    参数:
        question: str       # 用户问题
        user_id: str        # 用户ID
        session_id: str     # 会话ID
        llm: BaseLLM        # LLM实例
    
    返回:
        tool_name: str      # 工具名称
    
    Prompt示例:
        系统: "你是一名内容匹配专家。可用工具：{functions}"
        用户: "帮我查看数据库状态"
        
        LLM返回: "summary_alarms"
    """
    # 1. 获取工具描述
    if llm.llm_type == LLMType.PANGUCLOUD:
        _, detail_without_param_dict_list = base_tools.detail_dict_list
        tools_des = '\n'.join([
            json.dumps(tool_des, ensure_ascii=False) 
            for tool_des in detail_without_param_dict_list
        ])
        tools_des = tools_des.replace('{', '{{').replace('}', '}}')
    else:
        _, detail_without_param_str_list = base_tools.detail_str_list
        tools_des = '\n'.join(detail_without_param_str_list)
    
    # 2. 构建Prompt
    tools_des_prompt = (
        TOOL_DES_ZH.format(functions=tools_des) 
        if LANGUAGE == 'zh' 
        else TOOL_INTERACT_EN.format(functions=tools_des)
    )
    
    message_input = [
        {LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: tools_des_prompt},
        {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question},
    ]
    
    # 3. 检查意图状态（多轮对话关键）
    tool_name = global_vars.SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)
    
    # 4. 调用LLM推断
    if tool_name is None:
        tool_name, _ = await llm.invoke(message_input)
        tool_name = tool_name.strip()
    
    return tool_name
```

**逻辑详解**:
1. **工具描述获取**：从 `base_tools` 获取所有工具的JSON描述
2. **Prompt构建**：使用 `TOOL_DES_ZH` 模板，插入工具列表
3. **意图状态检查**：先看 `SESSION_TOOL_HISTORY` 是否有未完成的意图
4. **LLM推断**：如果没有，调用LLM让模型选择最合适的工具

---

#### 2. infer_arguments()

```python
@timer_decorator
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    