# 04-核心文件详解 - executor与dba

> 本文档详解 GaussMaster 最核心的两个文件：executor.py（工具调用执行器）和 dba.py（DBA Agent）。

---

## 1. executor.py - 工具调用执行器

**路径**: `GaussMaster/llms/executor.py`

**作用**: 实现工具调用的6步流程，是 Agent 的核心引擎。

### 1.1 文件结构

```python
# 核心函数
async def infer_tool_name(...)      # Step 1: 意图识别
async def infer_arguments(...)      # Step 4: 参数提取
def check_has_valid_tool(...)       # Step 2: 工具校验
def check_is_no_param_tool(...)     # Step 3: 参数检查
def verify_arguments(...)           # Step 5: 参数验证
def call_tool(...)                  # Step 6: 工具执行

# 通用函数
async def llm_call(...)             # 通用LLM调用
```

### 1.2 infer_tool_name() - 意图识别

```python
@timer_decorator
async def infer_tool_name(question, user_id, session_id, llm):
    """
    【Step 1】意图识别：从用户问题中识别需要调用的工具
    
    流程:
    1. 获取所有工具描述（无参数版本）
    2. 构建工具匹配Prompt
    3. 调用LLM选择工具
    4. 解析返回的工具名
    
    参数:
        question: str       # 用户问题
        user_id: str        # 用户ID
        session_id: str     # 会话ID
        llm: BaseLLM        # LLM实例
    
    返回:
        matched_tool: str   # 匹配的工具名
    """
    # 1. 获取所有工具描述
    _, detail_without_param_str_list = base_tools.detail_str_list
    tools_des = '\n'.join(detail_without_param_str_list)
    
    # 2. 构建Prompt
    prompt = TOOL_DES_ZH.format(functions=tools_des)
    
    # 3. 调用LLM
    message_inputs = [
        {LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: prompt},
        {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question}
    ]
    response, _ = await llm.invoke(message_inputs)
    
    # 4. 解析工具名
    matched_tool = response.strip()
    
    # 5. 如果LLM无法识别，返回提示
    if '用户提问的问题无法用第三方工具解答' in matched_tool:
        return None
    
    return matched_tool
```

**关键逻辑**:
- 工具描述来自 `base_tools.detail_str_list`，是动态生成的
- 不同模型（盘古/ChatGLM等）使用不同的Prompt策略
- 返回 `None` 表示无法识别意图

---

### 1.3 infer_arguments() - 参数提取

```python
@timer_decorator
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """
    【Step 4】参数提取：从用户问题中提取工具参数
    
    流程:
    1. 获取目标工具的详细描述（带参数定义）
    2. 构建时间参数（当前时间、日期等）
    3. 根据不同模型使用不同的Prompt策略
    4. 调用LLM提取参数
    5. 解析返回结果
    """
    # 1. 获取工具详细描述
    if llm.llm_type == LLMType.PANGUCLOUD:
        target_tool_des = json.dumps(base_tools.get(intention_tool).__detail_with_param_dict__)
    else:
        target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__
    
    # 2. 构建时间参数（解决LLM不知道"今天"的问题）
    tz = adjust_timezone(global_vars.configs.get('TIMEZONE', 'tz'))
    propose_prompt_dict = {
        "year": str(datetime.now(tz).year),
        "date": str(datetime.now(tz).date()),
        "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),
        "weekday": f"星期{WEEK_ZH[datetime.now(tz).weekday()]}"
    }
    
    # 3. 盘古/盘古云模型特殊处理
    if llm.llm_type in [LLMType.PANGUCLOUD, LLMType.PANGU]:
        propose_prompt_dict['functions'] = target_tool_des
        propose_prompt = TOOL_INTERACT_ZH.format(**propose_prompt_dict)
        
        # 构建消息（包含历史对话）
        message_inputs = [{LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: propose_prompt}]
        history = []
        for qa in qa_record_history:
            history.append({LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: qa.question})
            answer_dict = {LLMMsgKey.ROLE: LLMRole.ASSISTANT, LLMMsgKey.CONTENT: qa.answer}
            if qa.function_call:
                answer_dict[LLMMsgKey.FUNCTION_CALL] = qa.function_call
            history.append(answer_dict)
        message_inputs.extend(history)
        message_inputs.append({LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question})
        
        content_resp, function_call = await llm.invoke(message_inputs)
    else:
        # 其他模型使用专门的参数提取Prompt
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

**关键逻辑**:
- **时间上下文注入**：告诉LLM"今天是2025-01-15"，解决时间理解问题
- **历史对话注入**：将多轮对话历史加入Prompt，支持上下文理解
- **模型适配**：盘古模型支持原生function_call，其他模型需要手动解析

---

### 1.4 其他辅助函数

```python
def check_has_valid_tool(tool_name):
    """【Step 2】检查工具是否在注册表中"""
    target_tool = global_vars.tools_registry.get(tool_name, None)
    return target_tool is not None

def check_is_no_param_tool(tool_name):
    """【Step 3】检查工具是否需要参数"""
    target_tool = global_vars.tools_registry.get(tool_name, None)
    if target_tool and len(target_tool.__param_dict_list__) == 0:
        return True
    return False

def verify_arguments(function_call: dict = None):
    """【Step 5】验证参数是否完整"""
    func_name = function_call.get('name')
    arguments = json.loads(function_call.get('arguments'))
    return has_correct_params(arguments, global_vars.tools_registry.get(func_name))

def call_tool(tool_name: str, params=None):
    """【Step 6】执行工具"""
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

---

## 2. dba.py - DBA Agent

**路径**: `GaussMaster/multiagents/agents/dba.py`

**作用**: 对话入口，管理多轮对话和意图状态。

### 2.1 类结构

```python
class DBA(BaseAgent):
    def __init__(self, ...):
        # 意图状态：记住当前要用的工具
        self.intention_tool = None
        # 对话历史：内存 + SQLite 双层存储
        self.memory = global_vars.MEMORY
    
    async def interaction(self, ...):
        """对话入口"""
        if mode == 'tool_interaction':
            async for item in self.interact_with_tool(...):
                yield item
        else:
            async for item in self.interact_with_llm(...):
                yield item
    
    async def interact_with_tool(self, ...):
        """工具调用主流程"""
        ...
    
    async def interact_with_llm(self, ...):
        """纯LLM对话（不调用工具）"""
        ...
```

### 2.2 interact_with_tool() - 工具调用主流程

```python
async def interact_with_tool(self, question, user_id, session_id, mode, llm):
    """
    【工具调用主流程】
    
    流程:
    1. 检查是否有未完成的意图（多轮对话）
    2. 如果没有，推断工具名
    3. 校验工具
    4. 检查是否需要参数
    5. 提取参数
    6. 校验参数完整性
    7. 执行工具或追问用户
    """
    # 1. 获取对话历史
    qa_record_history = await self.get_qa_history(user_id, session_id)
    
    # 2. 检查是否有未完成的意图
    intention_tool = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)
    
    if intention_tool is None:
        # 首次提问，推断工具
        matched_tool = await infer_tool_name(question, user_id, session_id, llm)
        
        if matched_tool is None:
            # 无法识别意图，直接LLM回答
            async for item in self.interact_with_llm(question, user_id, session_id, llm):
                yield item
            return
        
        intention_tool = matched_tool
        SESSION_TOOL_HISTORY[user_id] = {session_id: intention_tool}
    
    # 3. 校验工具
    if not check_has_valid_tool(intention_tool):
        yield {'type': 'answer', 'data': '工具不存在'}
        return
    
    # 4. 检查是否需要参数
    if check_is_no_param_tool(intention_tool):
        # 无参工具，直接执行
        tool_result = call_tool(intention_tool)
        yield {'type': 'tool_result', 'data': tool_result}
        # 清空意图
        SESSION_TOOL_HISTORY[user_id][session_id] = None
        return
    
    # 5. 提取参数
    content_resp, function_call = await infer_arguments(
        question, intention_tool, qa_record_history, llm
    )
    
    # 6. 校验参数
    is_complete, correct_params, need_params = verify_arguments(function_call)
    
    if not is_complete:
        # 参数不完整，追问用户
        content_resp = f'缺少参数{",".join(list(need_params.keys()))}，请一次性提供完整'
        await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
        yield {'type': 'answer', 'data': content_resp}
        return
    
    # 7. 执行工具
    tool_result = call_tool(intention_tool, correct_params)
    
    # 8. 保存结果
    await self.save_assistant_resp(
        content_resp=content_resp,
        function_call=function_call,
        tool_result=tool_result
    )
    
    # 9. 清空意图（对话完成）
    SESSION_TOOL_HISTORY[user_id][session_id] = None
    
    yield {'type': 'tool_result', 'data': tool_result}
```

---

### 2.3 多轮对话状态管理

```python
# global_vars.py
SESSION_TOOL_HISTORY = {}  # {user_id: {session_id: tool_name}}

# 示例对话流：
# 用户：查看告警
#   → intention_tool = None
#   → infer_tool_name() → "summary_alarms"
#   → SESSION_TOOL_HISTORY[user1][sess1] = "summary_alarms"
#   → 需要参数，追问用户
# 
# 用户：昨天到今天
#   → intention_tool = "summary_alarms"（从SESSION_TOOL_HISTORY获取）
#   → 跳过意图识别，直接提取参数
#   → 参数完整，执行工具
#   → SESSION_TOOL_HISTORY[user1][sess1] = None（清空）
```

---

### 2.4 双层存储机制

```python
async def get_qa_history(self, user_id, session_id):
    """获取对话历史（内存 + SQLite）"""
    # 1. 先查内存
    qa_list = SESSION_QA_HISTORY.get(user_id, {}).get(session_id, [])
    
    if not qa_list:
        # 2. 内存没有，查数据库
        raw_records = await select_interaction_memory(user_id, session_id)
        
        # 3. 解密、构建历史
        for record in raw_records:
            qa = QARecord(
                question=Encryption.decrypt(record.question),
                answer=Encryption.decrypt(record.answer),
                function_call=Encryption.decrypt(record.function_call)
            )
            qa_list.append(qa)
        
        # 4. 写入内存缓存
        SESSION_QA_HISTORY[user_id] = {session_id: qa_list}
    
    return qa_list
```

---

## 3. 核心调用链总结

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
```

---

## 4. 面试重点

### Q: Function Calling 怎么实现？

**答**: 6步流程：
1. `infer_tool_name()` - 意图识别，选择工具
2. `check_has_valid_tool()` - 校验工具是否存在
3. `check_is_no_param_tool()` - 检查是否需要参数
4. `infer_arguments()` - 参数提取（注入时间上下文）
5. `verify_arguments()` - 参数校验
6. `call_tool()` - 执行工具

### Q: 多轮对话怎么实现？

**答**: 
- 使用 `SESSION_TOOL_HISTORY` 保存每个会话的当前意图
- 首次提问时推断工具并保存
- 追问时直接从SESSION_TOOL_HISTORY获取意图，跳过识别步骤
- 对话完成后清空意图

### Q: 为什么注入时间上下文？

**答**: LLM不知道"昨天"是哪天，需要告诉它当前时间（"今天是2025-01-15"），才能正确理解时间范围。

---

*本文档基于 openGauss-GaussMaster v1.0.0*
