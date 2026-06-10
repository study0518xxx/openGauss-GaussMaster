# GaussMaster Memory 机制代码详解

## 目录

- [Memory 数据结构定义](#memory-数据结构定义)
- [数据库表结构](#数据库表结构)
- [读取流程：get\_qa\_history](#读取流程get_qa_history)
- [保存流程：generate\_record\_and\_save](#保存流程generate_record_and_save)
- [工具意图保持：SESSION\_TOOL\_HISTORY](#工具意图保持session_tool_history)
- [完整流程图](#完整流程图)

***

## Memory 数据结构定义

### 1. global\_vars.py 中定义

```python
# global_vars.py 第 26-29 行

# 对话历史缓存（内存层）
# 结构: {user_id: {session_id: [InteractionMemory, ...]}}
SESSION_QA_HISTORY = {}

# 工具意图保持（内存层）
# 结构: {user_id: {session_id: "tool_name"}}
SESSION_TOOL_HISTORY = defaultdict(dict)
```

### 2. 数据结构图解

```
SESSION_QA_HISTORY = {
    "user_001": {
        "session_001": [
            InteractionMemory(qa_record_id="xxx", question="查看告警", answer="告警列表...", ...),
            InteractionMemory(qa_record_id="yyy", question="昨天到今天", answer="查询结果...", ...),
        ],
        "session_002": [...]  # 另一个会话
    },
    "user_002": {...}
}

SESSION_TOOL_HISTORY = {
    "user_001": {
        "session_001": "summary_alarms",  # 当前会话的工具意图
        "session_002": "slow_sql_rca",
    }
}
```

***

## 数据库表结构

### InteractionMemory 表

```python
# interaction_memory.py 第 21-39 行

class InteractionMemory(ResultDbBase):
    """对话历史表结构"""
    
    __tablename__ = "tb_interaction_memory"  # 表名
    
    qa_record_id = Column(String(64), primary_key=True)   # 记录ID (PK)
    user_id = Column(String(64), nullable=False)          # 用户ID
    session_id = Column(String(64), nullable=False)       # 会话ID
    question = Column(TEXT, nullable=False)               # 问题（加密存储）
    answer = Column(TEXT, nullable=True)                  # 答案（加密存储）
    llm_name = Column(String(64), nullable=True)         # 使用的模型
    function_call = Column(TEXT, nullable=True)           # 工具调用（加密存储）
    created_at = Column(BigInteger, nullable=False)       # 创建时间戳（毫秒）
    
    # 复合索引，加速 user_id + session_id 查询
    idx_history_alarms = Index(
        "idx_interaction_memory",
        user_id,
        session_id
    )
```

### 表结构图解

```
┌─────────────────────────────────────────────────────────────┐
│              tb_interaction_memory 表                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┬────────────┬────────────┬─────────────┐ │
│  │ qa_record_id │  user_id  │ session_id │  question   │ │
│  │    (PK)      │ (索引)    │  (索引)    │  (加密)     │ │
│  ├──────────────┼────────────┼────────────┼─────────────┤ │
│  │  xxx-001     │ user_001  │ session_001│ 查看告警... │ │
│  │  xxx-002     │ user_001  │ session_001│ 昨天到今天 │ │
│  └──────────────┴────────────┴────────────┴─────────────┘ │
│                                                             │
│  ┌──────────────┬────────────┬────────────┬─────────────┐ │
│  │   answer     │  llm_name │ function_  │ created_at │ │
│  │   (加密)      │           │   call     │            │ │
│  ├──────────────┼────────────┼────────────┼─────────────┤ │
│  │ 告警列表...   │ pangu_38b │    null    │ 1705315200 │ │
│  │ 查询结果...   │ pangu_38b │ {...}     │ 1705315250 │ │
│  └──────────────┴────────────┴────────────┴─────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

***

## 读取流程：get\_qa\_history

### 代码位置

`dba.py` 第 197-222 行

### 代码详解

```python
async def get_qa_history(self):
    """
    get qa history from local memory or metadatabase
        1. get qa history form local memory
        2. if there is no record in local memory, search from metadatabase
    """
    # ========== 步骤1: 先查内存 ==========
    qa_list = global_vars.SESSION_QA_HISTORY.get(
        self.user_id, {}          # 获取 user_id 对应的字典
    ).get(self.session_id, [])   # 获取 session_id 对应的列表
    [:self.history_len]           # 截取历史长度
    
    # ========== 步骤2: 内存命中则直接返回 ==========
    if not qa_list:
        # 内存未命中，查询数据库
        raw_qa_records = await select_interaction_memory(
            self.user_id, self.session_id, self.history_len
        )
        qa_records = sqlalchemy_query_jsonify(raw_qa_records)
    else:
        return qa_list  # ← 直接返回内存中的数据
    
    # ========== 步骤3: 处理数据库返回的数据 ==========
    history = []
    header = qa_records.get('header')          # 列名列表
    qa_rows = list(reversed(qa_records.get('rows')))  # 反转，最新的在前
    
    for qa in qa_rows:
        # 构建字典：{列名: 值}
        qa_params = dict(zip(header, qa))
        
        # ========== 步骤4: 解密敏感字段 ==========
        qa_params.update({
            'question': Encryption.decrypt(qa_params.get('question')),
            'answer': Encryption.decrypt(qa_params.get('answer')),
            'function_call': Encryption.decrypt(qa_params.get('function_call')) if qa_params.get(
                'function_call') else None
        })
        
        # 构建 InteractionMemory 对象
        history.append(InteractionMemory(**qa_params))
    
    # ========== 步骤5: 写入内存缓存 ==========
    global_vars.SESSION_QA_HISTORY[self.user_id] = {self.session_id: history}
    
    return history
```

### 流程图解

```
get_qa_history() 调用
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤1: 查询 SESSION_QA_HISTORY                            │
│  SESSION_QA_HISTORY.get(user_id, {}).get(session_id, [])  │
│                                                             │
│  ├─ 有数据 → 直接返回 qa_list                              │
│  │                                                          │
│  └─ 无数据 → 继续执行步骤2                                  │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤2: 查询数据库                                          │
│  select_interaction_memory(user_id, session_id, limit)      │
│                                                             │
│  SQL: SELECT * FROM tb_interaction_memory                   │
│       WHERE user_id = ? AND session_id = ?                  │
│       ORDER BY created_at DESC LIMIT ?                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤3-4: 处理数据                                          │
│  for qa in qa_rows:                                         │
│      解密 question、answer、function_call                    │
│      构建 InteractionMemory 对象                             │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤5: 写入内存缓存                                        │
│  SESSION_QA_HISTORY[user_id] = {session_id: history}       │
└─────────────────────────────────────────────────────────────┘
    ↓
返回 history 列表
```

***

## 保存流程：generate\_record\_and\_save

### 代码位置

`dba.py` 第 105-128 行

### 代码详解

```python
async def generate_record_and_save(self, answer, function_call: str = None):
    """generate qa record and save to local memory and metadatabase"""
    
    # ========== 步骤1: 构建 InteractionMemory 对象 ==========
    qa_record = InteractionMemory(
        qa_record_id=str(uuid.uuid4().hex),  # 生成唯一ID
        user_id=self.user_id,
        session_id=self.session_id,
        question=self.question,                  # 当前问题
        answer=answer,                          # 当前答案
        llm_name=self.llm.name,               # 使用的模型
        function_call=function_call,           # 工具调用信息
        created_at=int(time.time() * 1000)    # 毫秒级时间戳
    )
    
    # ========== 步骤2: 写入内存 ==========
    add_to_local_memory(
        global_vars.SESSION_QA_HISTORY,  # 内存字典
        self.history_len,                  # 最大历史长度
        qa_record                          # 记录
    )
    
    # ========== 步骤3: 加密并写入数据库 ==========
    await insert_interaction_memory(
        qa_record_id=qa_record.qa_record_id,
        user_id=qa_record.user_id,
        session_id=qa_record.session_id,
        question=Encryption.encrypt(qa_record.question),      # ← 加密
        created_at=qa_record.created_at,
        llm_name=qa_record.llm_name,
        answer=Encryption.encrypt(qa_record.answer),          # ← 加密
        function_call=Encryption.encrypt(qa_record.function_call) if qa_record.function_call else None  # ← 加密
    )
```

### add\_to\_local\_memory 函数

```python
# dao_interaction_memory.py 第 67-72 行

def add_to_local_memory(local_qa: dict, length: int, qa: InteractionMemory):
    """add qa record to local memory"""
    # 获取该用户的会话列表
    qa_list = local_qa.get(qa.user_id, {}).get(qa.session_id, [])
    
    # 追加新记录
    qa_list.append(qa)
    
    # 保持固定长度，移除最早的记录
    while len(qa_list) > length:
        qa_list.pop(0)
```

### 流程图解

```
generate_record_and_save(answer, function_call) 调用
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤1: 构建 InteractionMemory 对象                        │
│  qa_record = InteractionMemory(                           │
│      qa_record_id=uuid,                                   │
│      user_id=self.user_id,                                 │
│      session_id=self.session_id,                           │
│      question=self.question,                                │
│      answer=answer,                                        │
│      ...                                                    │
│  )                                                         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤2: 写入内存 (add_to_local_memory)                     │
│                                                             │
│  local_qa = SESSION_QA_HISTORY                            │
│  qa_list.append(qa_record)  ← 追加新记录                   │
│  while len(qa_list) > history_len:                         │
│      qa_list.pop(0)  ← 移除最早的记录                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤3: 加密并写入数据库 (insert_interaction_memory)        │
│                                                             │
│  加密字段:                                                   │
│  - question = Encryption.encrypt(question)                  │
│  - answer = Encryption.encrypt(answer)                      │
│  - function_call = Encryption.encrypt(function_call)        │
│                                                             │
│  SQL: INSERT INTO tb_interaction_memory (...)               │
└─────────────────────────────────────────────────────────────┘
```

***

## 工具意图保持：SESSION\_TOOL\_HISTORY

### 代码位置

`dba.py` 第 130-155 行（interact\_with\_tool 函数）

### 代码详解

```python
async def interact_with_tool(self):
    """interact with third party tools"""
    
    # ========== 步骤1: 检查是否有保存的工具意图 ==========
    intention_tool = global_vars.SESSION_TOOL_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, None)
    
    if intention_tool is None:
        # ========== 首次提问：需要推断工具 ==========
        
        # 1.1 工具匹配
        yield [formatter_progress('工具匹配中...')]
        matched_tool = await infer_tool_name(
            self.question, self.user_id, self.session_id, self.llm
        )
        
        # 1.2 校验工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            content_resp = '用户提问的问题无法用第三方工具解答。'
            await self.save_assistant_resp(content_resp=content_resp)
            yield [formatter_str(content_resp)]
            return
        
        # 1.3 检查是否需要参数
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(matched_tool)
            yield tool_result
            content_resp = f'将为您调用工具{matched_tool}'
            await self.save_assistant_resp(content_resp=content_resp, tool_name=matched_tool)
            return
        
        intention_tool = matched_tool  # ← 设置当前意图
    
    # ========== 步骤2: 追问：使用保存的工具意图 ==========
    yield [formatter_progress('提取参数中...')]
    qa_record_history = await self.get_qa_history()  # 获取历史
    content_resp, function_call = await infer_arguments(
        self.question, intention_tool, qa_record_history, self.llm
    )
    
    # 3. 调用工具...
```

### save\_assistant\_resp 函数

```python
# dba.py 第 177-195 行

async def save_assistant_resp(self, content_resp, intent_tool: str = None, 
                              tool_name: str = None, tool_params: dict = None):
    """
    save assistant answer to meta_database and vector db
    """
    # ========== 更新工具意图 ==========
    global_vars.SESSION_TOOL_HISTORY.update({
        self.user_id: {self.session_id: intent_tool}  # ← 保持意图
    })
    
    if tool_name:
        # 有工具调用，构建 function_call 信息
        function_call = {
            'tool_name': tool_name,
            'arguments': tool_params if tool_params else {}
        }
        await self.generate_record_and_save(content_resp, json.dumps(function_call))
        function_call['question'] = self.question
    else:
        # 无工具调用，普通问答
        await self.generate_record_and_save(content_resp, None)
```

### 多轮对话示例

```
┌─────────────────────────────────────────────────────────────┐
│                    多轮对话：工具意图保持                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【第1轮】用户：查看告警                                      │
│                                                             │
│  SESSION_TOOL_HISTORY[user_001][session_001] = None        │
│       ↓                                                     │
│  intention_tool = None → 需要推断                            │
│       ↓                                                     │
│  infer_tool_name("查看告警") → "summary_alarms"             │
│       ↓                                                     │
│  SESSION_TOOL_HISTORY.update({user_001: {session_001: "summary_alarms"}})│
│       ↓                                                     │
│  系统：请提供时间范围                                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【第2轮】用户：昨天到今天（追问）                            │
│                                                             │
│  SESSION_TOOL_HISTORY[user_001][session_001] = "summary_alarms"│
│       ↓                                                     │
│  intention_tool = "summary_alarms" → 直接使用，不重新推断     │
│       ↓                                                     │
│  infer_arguments("昨天到今天", "summary_alarms", ...)        │
│       ↓                                                     │
│  调用 summary_alarms(start_time="昨天", end_time="今天")     │
│       ↓                                                     │
│  返回查询结果                                                │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【第3轮】用户：推荐索引（新意图）                            │
│                                                             │
│  SESSION_TOOL_HISTORY.update({user_001: {session_001: "index_recommendation"}})│
│       ↓                                                     │
│  intention_tool = "index_recommendation" → 新意图覆盖旧意图   │
│       ↓                                                     │
│  ...                                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

***

## 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Memory 完整流程                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  【读取流程】                                                           │
│                                                                         │
│  用户提问                                                               │
│      ↓                                                                 │
│  DBA.get_qa_history()                                                  │
│      ↓                                                                 │
│  ┌─────────────────────────────────────┐                              │
│  │ 查 SESSION_QA_HISTORY               │                              │
│  │ 内存命中?                           │                              │
│  └────────────────┬────────────────────┘                              │
│       ├─ 是 ────→ 返回内存数据                                         │
│       │                                                            │
│       └─ 否 ────→ select_interaction_memory() 查数据库                 │
│                      ↓                                               │
│                  解密数据                                              │
│                      ↓                                               │
│                  SESSION_QA_HISTORY[user_id][session_id] = history    │
│                      ↓                                               │
│                  返回 history                                          │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  【保存流程】                                                           │
│                                                                         │
│  助手回答                                                               │
│      ↓                                                                 │
│  DBA.generate_record_and_save(answer, function_call)                    │
│      ↓                                                                 │
│  ┌─────────────────────────────────────┐                              │
│  │ 1. 构建 InteractionMemory 对象      │                              │
│  │ 2. add_to_local_memory()            │                              │
│  │    → SESSION_QA_HISTORY[...].append()│                              │
│  │    → 保持固定长度，移除最早的        │                              │
│  │ 3. insert_interaction_memory()       │                              │
│  │    → 加密敏感字段                    │                              │
│  │    → INSERT INTO tb_interaction_memory│                             │
│  └─────────────────────────────────────┘                              │
│      ↓                                                                 │
│  DBA.save_assistant_resp(...)                                          │
│      ↓                                                                 │
│  ┌─────────────────────────────────────┐                              │
│  │ 更新 SESSION_TOOL_HISTORY           │                              │
│  │ SESSION_TOOL_HISTORY[user_id][session_id] = intent_tool             │
│  └─────────────────────────────────────┘                              │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  【意图保持流程】                                                        │
│                                                                         │
│  用户提问                                                               │
│      ↓                                                                 │
│  DBA.interact_with_tool()                                              │
│      ↓                                                                 │
│  ┌─────────────────────────────────────┐                              │
│  │ 查 SESSION_TOOL_HISTORY             │                              │
│  │ intention_tool = ?                  │                              │
│  └────────────────┬────────────────────┘                              │
│       ├─ None ──→ infer_tool_name() 推断工具                          │
│       │              ↓                                               │
│       │          保存到 SESSION_TOOL_HISTORY                           │
│       │              ↓                                               │
│       │          提取参数、调用工具                                    │
│       │                                                            │
│       └─ 有值 ──→ 直接使用保存的意图（追问场景）                        │
│                      ↓                                               │
│                  提取参数、调用工具                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

***

## 面试问答

### Q: GaussMaster 的 Memory 机制是怎样的？

**答**：

采用**双层 Memory 架构**：

1. **内存层**（快速访问）：
   - `SESSION_QA_HISTORY`：缓存对话历史
   - `SESSION_TOOL_HISTORY`：保持工具意图状态
2. **数据库层**（持久化）：
   - `tb_interaction_memory` 表：加密存储所有对话记录

**读写策略**：

- 读：先查内存，未命中则查数据库，并写入内存缓存
- 写：同时更新内存和数据库

***

### ,Q: 为什么需要 SESSION\_TOOL\_HISTORY？

**答**：

实现**多轮对话的工具意图保持**。

场景：用户说"查看告警" → 系统问"请提供时间范围" → 用户回答"昨天到今天"

如果没有 SESSION\_TOOL\_HISTORY：每次都要重新推断工具，浪费 LLM 调用，且可能推断错误。

有 SESSION\_TOOL\_HISTORY：第1轮保存意图为 `summary_alarms`，第2轮直接使用，无需重新推断。

***

## 一句话总结

> GaussMaster 的 Memory 通过 `SESSION_QA_HISTORY`（内存+数据库双写）实现对话历史缓存，通过 `SESSION_TOOL_HISTORY` 实现多轮对话的工具意图状态保持，敏感数据加密存储，兼顾性能、可靠性和安全性！

