# 03 - Function Call 工具链

## 工具注册系统

### 架构设计
使用**自研 Registry 装饰器模式**，不是 LangChain 的 `@tool`。

```python
# GaussMaster/multiagents/tools/__init__.py
base_tools = Registry()  # 全局工具注册表

# GaussMaster/common/plugins/registry.py
class Registry(dict):
    def __call__(self, name, description=None, params=None, roles=None):
        """装饰器工厂：注册工具名、描述、参数 schema、可用角色"""
        return self.register(name, description, params, roles)
```

### 参数定义
```python
# GaussMaster/common/plugins/param.py
class Param:
    def __init__(self, name, description=None, param_type=None, 
                 default_value=None, required=True):
        self.name = name
        self.description = description
        self.type = param_type
        self.default_value = default_value
        self.required = required
```

### 工具定义示例
```python
@base_tools(
    name="risk_analysis",
    description="预测指标趋势，判断未来是否会出现异常",
    params=[
        Param(name="metric", description="指标名称，如cpu_usage", 
              param_type="str", required=True),
        Param(name="warning_hours", description="预测小时数", 
              param_type="int", required=False)
    ]
)
@validate_return_format
def risk_analysis(metric: str, warning_hours: int = 24) -> dict:
    """实际调用 DBMind API"""
    params = {"metric": metric, "warning_hours": warning_hours}
    return call_dbmind_api("risk_analysis", params)
```

## 21 个注册工具

| 工具名 | 功能 | 必填参数 |
|--------|------|---------|
| `risk_analysis` | 指标趋势预测 | metric |
| `cluster_diagnosis` | 集群健康诊断 | start_time(可选) |
| `slow_sql_rca` | 慢 SQL 根因分析 | — |
| `index_recommendation` | 索引建议 | — |
| `get_metric_range_sequence` | 指标时序数据 | metric, instance, start_time, end_time |
| `get_top_sqls` | Top-N SQL | — |
| `get_locking_sql` | 锁 SQL 查询 | start_time, end_time |
| `get_database_info` | 数据库详情 | — |
| `get_knob_warning` | 动态参数建议 | — |
| `get_instance_status` | 实例状态 | — |
| `get_all_cluster` | 集群列表 | — |
| `get_guc_parameter` | GUC 参数查询 | name |
| `summary_alarms` | 告警摘要 | start_time, end_time |
| `metric_diagnosis` | 指标诊断 | metric, start_time, end_time |
| `data_directory` | 数据目录信息 | — |
| `knob_recommendation_details` | 参数建议详情 | — |
| `knob_recommendation_snapshots` | 参数快照对比 | — |
| `memory_check` | 内存检查 | — |
| `status_overview` | 状态概览 | — |
| `collect_stat_activity_workloads` | 当前执行 SQL | database(可选), schema(可选) |
| `collect_history_statement` | 历史 SQL 列表 | start_time, end_time |

## DeepSeek 函数调用流程

### 核心决策：不用原生 Function Call API

原因：DeepSeek、ChatGLM、Baichuan、Qwen 的原生 function calling 行为不一致，无法统一处理。

### 两阶段提示工程方案

**阶段 1：工具选择**
```python
# GaussMaster/llms/executor.py
async def infer_tool_name(question, user_id, session_id, llm):
    # 把 21 个工具的 name + description + 参数 schema 拼成 JSON，放进 system prompt
    tools_des = '\n'.join([json.dumps(tool) for tool in detail_without_param_dict_list])
    
    message_input = [
        {"role": "system", "content": tools_des_prompt},
        {"role": "user", "content": question},
    ]
    
    tool_name, _ = await llm.invoke(message_input)
    return tool_name.strip()
```

**阶段 2：参数提取**
```python
async def infer_arguments(question, target_tool_des, llm, session_id, user_id):
    prompt = construct_extract_tool_params_prompt(
        user_question=question,
        tools_description=target_tool_des,
        qa_history=qa_record_history,
        time_args=propose_prompt_dict
    )
    
    result, _ = await llm.invoke([{"role": "user", "content": prompt}])
    arguments, success = output_parser.parse_params(result)
    return arguments
```

### 完整工具调用流程

```
interact_with_tool():
1. 检查会话意图（缓存中是否有未完成的工具？）
2. 若无 → LLM 匹配工具名称 (infer_tool_name)
3. 验证工具是否存在（查 Registry）
4. 检查是否为无参数工具 → 直接执行
5. 若需参数 → LLM 推断参数 (infer_arguments)
6. verify_arguments() → inspect.signature 校验
7. 参数完整 → call_tool() 执行
8. 参数不完整 → 提示用户补充缺失参数
9. 保存 QA 记录到元数据库
```

## 四层保障机制

| 层 | 方法 | 作用 |
|----|------|------|
| Schema 约束 | `Param(name, type, required)` 结构化定义 | 明确工具接口 |
| 提示工程 | 专用 prompt 模板约束输出格式 | 引导 LLM 在限定范围内选择 |
| 参数校验 | `inspect.signature` 与函数签名比对 | 多余参数丢弃，缺失参数退回 |
| 两阶段分离 | 选工具和填参数分开 | 降低单次推理难度，准确率 >95% |

## 参数校验源码

```python
# GaussMaster/multiagents/tools/utils.py
def has_correct_params(given_params: dict, func):
    arguments, _, var_keyword_name = parse_func_params(func)
    target_params = copy.deepcopy(given_params)
    need_params = dict(filter(lambda item: item[1] is False, arguments.items()))
    
    for given_key in given_params.keys():
        if given_key not in arguments:
            target_params.pop(given_key)  # 移除多余参数
        elif given_key in need_params:
            need_params.pop(given_key)    # 标记为已满足
    
    if need_params:
        return False, {}, need_params      # 缺少参数
    return True, target_params, {}          # 参数完整
```

## 会话状态管理（两层缓存）

### 第一层：SESSION_TOOL_HISTORY — 记住"正在调哪个工具"

```python
# GaussMaster/global_vars.py
SESSION_TOOL_HISTORY = defaultdict(dict)  # {user_id: {session_id: "risk_analysis"}}
```

只记一个值：当前会话正在交互的工具名。作用是**避免重复推断**。

```
用户第1轮: "CPU飙高了"
  → LLM 选了 risk_analysis，但缺参数 warning_hours
  → SESSION_TOOL_HISTORY[A][S1] = "risk_analysis"
  → 返回"请补充预测小时数"

用户第2轮: "48小时"
  → 先查 SESSION_TOOL_HISTORY → 拿到 "risk_analysis"
  → 跳过 LLM 工具匹配，直接走参数填充
  → 填完 → 调工具 → 清掉 SESSION_TOOL_HISTORY
```

源码位置：

```python
# executor.py:61 — 读缓存
tool_name = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)
if tool_name is None:
    tool_name, _ = await llm.invoke(message_input)  # 缓存没有才调 LLM
```

---

### 第二层：SESSION_QA_HISTORY + get_qa_history() — 记住"刚才聊了什么"

这是你提到的漏写的部分。工具调用过程中，每轮对话都会被记录，下次请求时作为上下文注入 LLM。

#### 数据结构

```python
# global_vars.py:27
SESSION_QA_HISTORY = {}  # {user_id: {session_id: [InteractionMemory, ...]}}
```

每一条是 `InteractionMemory` 对象：

```python
class InteractionMemory:
    qa_record_id  # 唯一ID
    user_id       # 谁
    session_id    # 哪个会话
    question      # 用户问了什么（明文）
    answer        # LLM 答了什么（明文）
    llm_name      # 用了哪个模型
    function_call # 调了什么工具+参数（JSON字符串，如 '{"name":"risk_analysis",...}')
    created_at    # unix毫秒时间戳
```

#### 读取：两级优先级

```python
# dba.py:197-222
async def get_qa_history(self):
    """
    get qa history from local memory or metadatabase
        1. get qa history from local memory
        2. if there is no record in local memory, search from metadatabase
    """
    # 第一优先：翻进程内存
    qa_list = SESSION_QA_HISTORY.get(user_id, {}).get(session_id, [])[:history_len]
    if qa_list:
        return qa_list  # ← 命中，零数据库查询

    # 第二优先：查 MetaDatabase
    raw_records = await select_interaction_memory(user_id, session_id, history_len)
    # AES-256-CBC 解密每条记录
    # 回填进程内存，加速下次访问
    SESSION_QA_HISTORY[user_id] = {session_id: history}
    return history
```

**核心逻辑**：内存优先 → 未命中才查 `tb_interaction_memory` → 解密 → 回填缓存。服务重启后内存清空，首次请求从 MetaDatabase 恢复。

#### 写入：同时写内存和数据库

每次工具调用结束，`dba.py:105` 执行：

```python
async def generate_record_and_save(self, answer, function_call=None):
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
    # 写入进程内存（滑动窗口，超过 history_len 淘汰最旧的）
    add_to_local_memory(SESSION_QA_HISTORY, self.history_len, qa_record)
    
    # 写入 MetaDatabase（AES-256-CBC 加密，持久化）
    await insert_interaction_memory(
        qa_record_id=qa_record.qa_record_id,
        user_id=qa_record.user_id,
        question=Encryption.encrypt(qa_record.question),
        answer=Encryption.encrypt(qa_record.answer),
        function_call=Encryption.encrypt(qa_record.function_call) if qa_record.function_call else None,
        ...
    )
```

`add_to_local_memory` 的滑动窗口逻辑：

```python
# dao_interaction_memory.py:67-72
def add_to_local_memory(local_qa, length, qa):
    qa_list = local_qa.get(qa.user_id, {}).get(qa.session_id, [])
    qa_list.append(qa)               # 追加新记录
    while len(qa_list) > length:     # 超过 history_len（默认3）
        qa_list.pop(0)               # 淘汰最旧的一条
```

#### 历史怎么注入 LLM prompt

在 `infer_arguments()` 中，`qa_record_history` 就是通过 `get_qa_history()` 拿到的：

```python
# executor.py:116-177
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    # qa_record_history 来自 get_qa_history() 的返回值
    # 被拼入 prompt，让 LLM 知道"上一轮发生了什么"
    prompt = construct_extract_tool_params_prompt(
        user_question=question,
        tools_description=target_tool_des,
        qa_history=qa_record_history,   # ← 注入历史上下文
        time_args=propose_prompt_dict
    )
```

对于盘古系列的模型，历史消息还会以标准的对话格式注入：

```python
# executor.py:150-158
history = []
for qa in qa_record_history:
    history.append({"role": "user", "content": qa.question})
    answer_dict = {"role": "assistant", "content": qa.answer}
    if qa.function_call:
        answer_dict["function"] = qa.function_call  # 带上工具的调用详情
    history.append(answer_dict)
message_inputs.extend(history)  # 拼到 LLM 消息列表里
```

---

### 完整工具调用流程（含历史记录）

```
interact_with_tool():                          ← dba.py:130
│
├─ ① 检查 SESSION_TOOL_HISTORY[user][session] (内存)
│     └─ 有 → 跳过步骤②③，直接用缓存工具名
│
├─ ② get_qa_history()                          ← dba.py:197
│     ├─ SESSION_QA_HISTORY[user][session] (内存优先)
│     └─ select_interaction_memory() (MetaDatabase兜底 → 回填缓存)
│     └─ return [InteractionMemory, ...]
│
├─ ③ LLM 匹配工具名称 (infer_tool_name)         ← executor.py:43
│
├─ ④ 验证工具是否存在 → Registry.get(tool_name)
│
├─ ⑤ 检查是否为无参数工具 → 直接 call_tool()
│
├─ ⑥ LLM 推断参数 (infer_arguments)            ← executor.py:116
│     └─ qa_record_history 注入 LLM prompt
│     └─ 盘古 → 原生 function_call
│     └─ 其他 → prompt + output_parser.parse_params()
│
├─ ⑦ verify_arguments() → inspect.signature 校验
│
├─ ⑧ call_tool() 执行
│
└─ ⑨ generate_record_and_save()               ← dba.py:105
      ├─ add_to_local_memory(SESSION_QA_HISTORY)  → 进程内存
      └─ insert_interaction_memory()              → MetaDatabase (AES加密)
```

---

### 两张记忆表对比

| | SESSION_TOOL_HISTORY | SESSION_QA_HISTORY |
|---|---|---|
| **存什么** | 当前工具名（一个字符串） | 完整对话记录（InteractionMemory 列表） |
| **用途** | 避免重复推断工具名 | 注入 LLM prompt 做多轮上下文 |
| **生命周期** | 一轮工具调用结束就清 | 滑动窗口，最多 history_len 条 |
| **持久化** | 仅内存，重启丢失 | 内存 + MetaDatabase 双写 |
| **何时写** | LLM 选出工具后 | 工具调用结束后 |
| **何时读** | 每次请求开头 | 每次请求开头（`get_qa_history()`） |
