# Funcall（函数调用）机制详解

## 1. 概述

**Funcall** 是指大语言模型（LLM）调用外部工具/函数的能力。在 GaussMaster 项目中，Funcall 机制使得 AI Agent 能够根据用户问题自动推断并调用相应的工具来完成任务。

**核心文件：** `GaussMaster/llms/executor.py`

---

## 2. 为什么需要 Funcall？

| 问题 | 解决方案 |
|------|----------|
| LLM 知识有限，无法直接执行操作 | 通过 Funcall 调用外部工具扩展能力 |
| LLM 不知道当前数据库状态 | 调用数据库查询工具获取信息 |
| LLM 无法完成复杂诊断任务 | 调用专业诊断工具执行 |

---

## 3. Funcall 完整流程

```
用户问题
    ↓
┌─────────────────────────────┐
│  1. infer_tool_name         │  ← 推断使用哪个工具
│     (推断工具名称)            │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│  2. check_has_valid_tool    │  ← 验证工具是否存在
│     (检查工具有效性)          │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│  3. check_is_no_param_tool  │  ← 检查是否需要参数
│     (检查是否无参工具)        │
└─────────────────────────────┘
    ↓ (如果有参数)
┌─────────────────────────────┐
│  4. infer_arguments         │  ← 推断工具参数
│     (推断参数)               │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│  5. verify_arguments        │  ← 验证参数是否正确
│     (验证参数)               │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│  6. call_tool               │  ← 执行工具调用
│     (调用工具)               │
└─────────────────────────────┘
    ↓
返回结果给用户
```

---

## 4. 核心数据结构：function_call

```python
function_call = {
    'name': 'get_cluster_info',      # 工具名称
    'arguments': {                    # 工具参数
        'cluster_name': 'prod_db',
        'time_range': '24h'
    }
}
```

---

## 5. 核心函数详解

### 5.1 infer_tool_name - 推断工具名称

**位置：** `llms/executor.py` 第 42-65 行

**作用：** 根据用户问题推断应该使用哪个工具

```python
@timer_decorator
async def infer_tool_name(question: str, user_id, session_id, llm):
    """
    infer tool_name according to question
    """
    # 获取工具描述列表
    if llm.llm_type == LLMType.PANGUCLOUD:
        _, detail_without_param_dict_list = base_tools.detail_dict_list
        tools_des = '\n'.join([json.dumps(tool_des, ensure_ascii=False)
                               for tool_des in detail_without_param_dict_list])
    else:
        _, detail_without_param_str_list = base_tools.detail_str_list
        tools_des = '\n'.join(detail_without_param_str_list)

    # 构建提示词
    tools_des_prompt = (TOOL_DES_ZH.format(functions=tools_des) if LANGUAGE == 'zh'
                        else TOOL_INTERACT_EN.format(functions=tools_des))

    # 调用 LLM 推断工具名称
    message_input = [
        {LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: tools_des_prompt},
        {LLMMsgKey.ROLE: LLMRole.USER, LLMMsgKey.CONTENT: question},
    ]
    tool_name, _ = await llm.invoke(message_input)
    return tool_name.strip()
```

**关键点：**
- 将所有可用工具的描述发送给 LLM
- 让 LLM 根据用户问题选择最合适的工具

---

### 5.2 check_has_valid_tool - 验证工具存在

**位置：** `llms/executor.py` 第 81-87 行

**作用：** 检查推断出的工具是否在工具注册表中

```python
def check_has_valid_tool(tool_name):
    """
    check whether the question can be tackled by given tools
    :return: 1. whether the question can be tackled by given tools,
             2. target_tool detail description
    """
    target_tool = global_vars.tools_registry.get(tool_name, None)
    return target_tool is not None
```

---

### 5.3 check_is_no_param_tool - 检查无参工具

**位置：** `llms/executor.py` 第 68-78 行

**作用：** 检查工具是否需要参数

```python
def check_is_no_param_tool(tool_name):
    """
    check whether the tool need params
    :param tool_name: tool name inferred by llm
    :return: 1: is no_param tool 2: response content 3: tool_dict
    """
    target_tool = global_vars.tools_registry.get(tool_name, None)
    if target_tool and len(target_tool.__param_dict_list__) == 0:
        return True
    return False
```

---

### 5.4 infer_arguments - 推断工具参数

**位置：** `llms/executor.py` 第 115-177 行

**作用：** 确定了工具后，推断该工具需要什么参数

```python
@timer_decorator
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """
    With the tool_name ready, start inferring the parameters of intention_tool
    """
    # 获取目标工具的详细描述（包含参数信息）
    if llm.llm_type == LLMType.PANGUCLOUD:
        target_tool_des = json.dumps(base_tools.get(intention_tool).__detail_with_param_dict__)
    else:
        target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__

    # 构建时间参数
    propose_prompt_dict = {
        "year": str(datetime.now(tz).year),
        "date": str(datetime.now(tz).date()),
        "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),
        "weekday": f"星期{WEEK_ZH[datetime.now(tz).weekday()]}" if LANGUAGE == 'zh'
                   else WEEK_CN[datetime.now(tz).weekday()]
    }

    # 构建提示词并调用 LLM
    message_inputs = [{LLMMsgKey.ROLE: LLMRole.SYSTEM, LLMMsgKey.CONTENT: propose_prompt}]
    # 添加历史对话
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

    # 调用 LLM 获取参数
    content_resp, function_call = await llm.invoke(message_inputs)
    return content_resp, function_call
```

---

### 5.5 verify_arguments - 验证参数

**位置：** `llms/executor.py` 第 90-101 行

**作用：** 检查 LLM 返回的参数是否完整且正确

```python
def verify_arguments(function_call: dict = None):
    """
    Check whether the arguments of function_call are correct
    """
    func_name = function_call.get('name')
    try:
        arguments = json.loads(function_call.get('arguments'))
    except TypeError:
        arguments = function_call.get('arguments')
    return has_correct_params(arguments, global_vars.tools_registry.get(func_name))
```

**返回值：** `(是否正确, 正确参数, 缺失参数)`

---

### 5.6 call_tool - 执行工具调用

**位置：** `llms/executor.py` 第 104-112 行

**作用：** 真正执行工具函数

```python
@timer_decorator
def call_tool(tool_name: str, params=None):
    """
    With the tool_name and params ready, start calling the tool
    """
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

---

## 6. Funcall 在 DBA Agent 中的应用

**位置：** `multiagents/agents/dba.py` 第 130-175 行

```python
async def interact_with_tool(self):
    """interact with third party tools"""
    # 1. 检查会话意图
    intention_tool = global_vars.SESSION_TOOL_HISTORY.get(self.user_id, {}).get(self.session_id, None)
    if intention_tool is None:
        # 2. 需要匹配工具
        matched_tool = await infer_tool_name(self.question, self.user_id, self.session_id, self.llm)

        # 3. 验证工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            return '用户提问的问题无法用第三方工具解答。'

        # 4. 检查是否无参工具
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            tool_result = call_tool(matched_tool)
            return tool_result
        intention_tool = matched_tool

    # 5. 推断参数
    content_resp, function_call = await infer_arguments(self.question, intention_tool, qa_record_history, self.llm)

    # 6. 调用工具
    if function_call:
        is_complete_params, correct_params, need_prams = verify_arguments(function_call)
        if is_complete_params:
            tool_result = call_tool(intention_tool, correct_params)
            return tool_result
        else:
            return f'缺少参数{",".join(list(need_prams.keys()))}'
```

---

## 7. PanguCloud 的 Funcall 解析

**位置：** `llms/pangu_cloud.py` 第 72-100 行

### 7.1 输出后处理

```python
def postprocess_output(answer):
    """
    postprocess the output of raw answer
    """
    # 提取 <unused2> 和 <unused3> 标签之间的内容
    pattern = '<unused2>(.*?)<unused3>'
    match = re.search(pattern, answer, re.DOTALL)
    if match:
        function_call = json.loads(analyze_function_call(match.group(1)))
        # 处理时间格式
        target_arguments = copy.deepcopy(source_arguments)
        for key, value in source_arguments.items():
            if isinstance(value, str) and re.match(time_pattern, value):
                target_arguments[key] = value[:10] + " " + value[10:]
        function_call['arguments'] = target_arguments
        answer = answer.replace(match.group(0), "")
    else:
        function_call = {}
    return answer, function_call
```

### 7.2 解析函数调用

```python
def analyze_function_call(call):
    """
    extract the func_name and arguments from function_str
    """
    function_call = dict()
    name, arguments = call.split('|')  # 格式: "函数名|参数JSON"
    function_call['name'] = name
    function_call['arguments'] = json.loads(arguments)
    return json.dumps(function_call)
```

**原始格式：** `函数名|{"param1": "value1", "param2": "value2"}`

---

## 8. Funcall 与 Memory 的结合

**位置：** `multiagents/agents/dba.py` 第 106-128 行

function_call 会被保存到内存中，以便后续对话使用：

```python
qa_record = InteractionMemory(
    question=self.question,
    answer=answer,
    llm_name=self.llm.name,
    function_call=function_call,  # 保存函数调用记录
    created_at=int(time.time() * 1000)
)
```

**保存后，在后续对话中可以：**
- 提供上下文给 LLM，帮助更好地理解对话历史
- 用于审计追踪，了解 AI 执行了哪些操作

---

## 9. 消息格式定义

**位置：** `llms/llm_utils.py`

```python
class LLMMsgKey:
    """llm message key definition"""
    ROLE = "role"
    CONTENT = "content"
    FUNCTION_CALL = 'function'  # 用于传递 function_call 信息

class LLMRole:
    """llm role definition"""
    ASSISTANT = "assistant"
    FUNCTION = "function"
    SYSTEM = "system"
    USER = "user"
```

---

## 10. 总结

| 阶段 | 函数 | 作用 |
|------|------|------|
| 1 | `infer_tool_name` | 根据问题推断使用哪个工具 |
| 2 | `check_has_valid_tool` | 验证工具是否有效 |
| 3 | `check_is_no_param_tool` | 检查是否需要参数 |
| 4 | `infer_arguments` | 推断工具参数 |
| 5 | `verify_arguments` | 验证参数是否正确 |
| 6 | `call_tool` | 执行工具调用 |

整个 Funcall 机制使得 LLM 能够像人一样：
1. **知道该用什么工具**（infer_tool_name）
2. **知道需要什么参数**（infer_arguments）
3. **正确调用并获取结果**（call_tool）
