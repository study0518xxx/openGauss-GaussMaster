# GaussMaster Memory 机制详解

## 目录

- [Memory 概述](#memory-概述)
- [双层存储架构](#双层存储架构)
- [SESSION_QA_HISTORY - 内存缓存](#session_qa_history---内存缓存)
- [SESSION_TOOL_HISTORY - 工具意图保持](#session_tool_history---工具意图保持)
- [tb_interaction_memory - 数据库存储](#tb_interaction_memory---数据库存储)
- [Memory 操作流程](#memory-操作流程)
- [面试重点](#面试重点)

---

## Memory 概述

GaussMaster 实现了**双层 Memory 机制**：

1. **内存层**（快速访问）：`SESSION_QA_HISTORY`、`SESSION_TOOL_HISTORY`
2. **数据库层**（持久化）：`tb_interaction_memory`（SQLite）

```
┌─────────────────────────────────────────────────────────────┐
│                     GaussMaster Memory 架构                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   内存层 (Memory)                    │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                     │   │
│  │  SESSION_QA_HISTORY    SESSION_TOOL_HISTORY         │   │
│  │  {user_id: {session_id: [qa_records]}}              │   │
│  │                                                     │   │
│  │  作用：快速读取对话历史                              │   │
│  │  特点：进程内，重启丢失                              │   │
│  │                                                     │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │ 读写                              │
│  ┌──────────────────────┴──────────────────────────────┐   │
│  │                   数据库层 (SQLite)                  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                     │   │
│  │  tb_interaction_memory                              │   │
│  │  ├─ qa_record_id (PK)                               │   │
│  │  ├─ user_id                                         │   │
│  │  ├─ session_id                                      │   │
│  │  ├─ question (加密)                                  │   │
│  │  ├─ answer (加密)                                    │   │
│  │  ├─ llm_name                                        │   │
│  │  ├─ function_call (加密)                             │   │
│  │  └─ created_at                                      │   │
│  │                                                     │   │
│  │  作用：持久化存储对话历史                            │   │
│  │  特点：进程间共享，重启保留                          │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 双层存储架构

### 为什么需要双层存储？

| 层级 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **内存** | 极快（微秒级） | 进程内、重启丢失 | 频繁读取当前会话历史 |
| **数据库** | 持久化、共享 | 较慢（毫秒级） | 跨会话、长期存储 |

**设计思想**：
- 读：先查内存，没有则查数据库并写入内存
- 写：同时写入内存和数据库
- 兼顾**速度**和**可靠性**

---

## SESSION_QA_HISTORY - 内存缓存

### 定义

```python
# global_vars.py 第 27 行
SESSION_QA_HISTORY = {}
```

### 数据结构

```python
{
    "user_123": {                           # user_id
        "session_456": [                    # session_id
            InteractionMemory(...),         # QA记录1
            InteractionMemory(...),         # QA记录2
            ...
        ]
    }
}
```

### 使用场景

```python
# dba.py - get_qa_history() 第 197-222 行
async def get_qa_history(self):
    """获取对话历史（优先从内存读取）"""
    
    # 1. 先查内存
    qa_list = global_vars.SESSION_QA_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, [])[:self.history_len]
    
    if qa_list:
        # 内存命中，直接返回
        return qa_list
    
    # 2. 内存未命中，查数据库
    raw_qa_records = await select_interaction_memory(
        self.user_id, self.session_id, self.history_len
    )
    
    # 3. 解密、构建历史记录
    history = []
    for qa in qa_rows:
        qa_params = dict(zip(header, qa))
        qa_params.update({
            'question': Encryption.decrypt(qa_params.get('question')),
            'answer': Encryption.decrypt(qa_params.get('answer')),
            'function_call': Encryption.decrypt(qa_params.get('function_call'))
        })
        history.append(InteractionMemory(**qa_params))
    
    # 4. 写入内存缓存（下次直接读取）
    global_vars.SESSION_QA_HISTORY[self.user_id] = {
        self.session_id: history
    }
    
    return history
```

### 流程图解

```
获取对话历史
    ↓
查 SESSION_QA_HISTORY
    ↓
    ├─ 命中 ──→ 直接返回（微秒级）
    │
    └─ 未命中 ──→ 查 tb_interaction_memory
                    ↓
                  解密数据
                    ↓
                  写入 SESSION_QA_HISTORY
                    ↓
                  返回结果
```

---

## SESSION_TOOL_HISTORY - 工具意图保持

### 定义

```python
# global_vars.py 第 29 行
from collections import defaultdict
SESSION_TOOL_HISTORY = defaultdict(dict)
```

### 数据结构

```python
{
    "user_123": {                           # user_id
        "session_456": "summary_alarms"     # session_id → 当前工具意图
    }
}
```

### 作用：多轮对话状态保持

```
用户：查看告警                    ← 第1轮
系统：请提供时间范围
    ↓
SESSION_TOOL_HISTORY["user_123"]["session_456"] = "summary_alarms"
    ↓
用户：昨天到今天                  ← 第2轮（追问）
系统：识别为追问，直接使用保存的意图
    ↓
调用 summary_alarms(start_time="昨天", end_time="今天")
```

### 代码实现

```python
# dba.py - interact_with_tool() 第 107-134 行
async def interact_with_tool(self):
    """工具交互（支持多轮对话）"""
    
    # 1. 检查是否有历史意图
    intention_tool = SESSION_TOOL_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, None)
    
    if intention_tool is None:
        # 2. 首次提问，需要推断工具
        matched_tool = await infer_tool_name(...)
        intention_tool = matched_tool
        # 保存意图到内存
        SESSION_TOOL_HISTORY[self.user_id][self.session_id] = intention_tool
    else:
        # 3. 追问，直接使用保存的意图
        pass
    
    # 4. 提取参数、调用工具
    ...

# dba.py - save_assistant_resp() 第 177-195 行
async def save_assistant_resp(self, content_resp, intent_tool=None, ...):
    """保存助手响应时更新意图"""
    # 更新工具意图
    global_vars.SESSION_TOOL_HISTORY.update({
        self.user_id: {self.session_id: intent_tool}
    })
    ...
```

### 多轮对话示例

```
┌─────────────────────────────────────────────────────────────┐
│                     多轮对话流程                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  第1轮：                                                     │
│  用户：查看昨天的告警                                         │
│       ↓                                                     │
│  系统：infer_tool_name() → summary_alarms                   │
│       ↓                                                     │
│  SESSION_TOOL_HISTORY[user_123][session_456] = "summary_alarms"│
│       ↓                                                     │
│  系统：提取参数 → 调用工具 → 返回结果                        │
│                                                             │
│  第2轮：                                                     │
│  用户：那前天呢？（追问）                                     │
│       ↓                                                     │
│  系统：SESSION_TOOL_HISTORY.get(user_123, session_456)       │
│         → "summary_alarms" （直接获取，不再推断）            │
│       ↓                                                     │
│  系统：提取参数 → 调用工具 → 返回结果                        │
│                                                             │
│  第3轮：                                                     │
│  用户：推荐一下索引（新意图）                                 │
│       ↓                                                     │
│  系统：覆盖 SESSION_TOOL_HISTORY[user_123][session_456]      │
│         = "index_recommendation"                            │
│       ↓                                                     │
│  ...                                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## tb_interaction_memory - 数据库存储

### 表结构

```python
# interaction_memory.py
class InteractionMemory(ResultDbBase):
    """对话历史表结构"""
    
    __tablename__ = "tb_interaction_memory"
    
    qa_record_id = Column(String(64), primary_key=True)   # 记录ID
    user_id = Column(String(64), nullable=False)          # 用户ID
    session_id = Column(String(64), nullable=False)       # 会话ID
    question = Column(TEXT, nullable=False)               # 问题（加密）
    answer = Column(TEXT, nullable=True)                  # 答案（加密）
    llm_name = Column(String(64), nullable=True)          # 使用的模型
    function_call = Column(TEXT, nullable=True)           # 工具调用（加密）
    created_at = Column(BigInteger, nullable=False)       # 创建时间戳
    
    # 索引：加速查询
    idx_history_alarms = Index(
        "idx_interaction_memory",
        user_id,
        session_id
    )
```

### DAO 操作

```python
# dao_interaction_memory.py

# 插入记录
async def insert_interaction_memory(
    qa_record_id,
    user_id,
    session_id,
    question,
    created_at,
    llm_name=None,
    answer=None,
    function_call=None
):
    with get_session() as session:
        session.add(InteractionMemory(...))

# 查询记录
async def select_interaction_memory(user_id: str, session_id: str, limit: int):
    with get_session() as session:
        result = session.query(InteractionMemory) \
            .filter(InteractionMemory.user_id == user_id) \
            .filter(InteractionMemory.session_id == session_id) \
            .order_by(desc(InteractionMemory.created_at)) \
            .limit(limit)
        return result

# 添加到本地内存
def add_to_local_memory(local_qa: dict, length: int, qa: InteractionMemory):
    qa_list = local_qa.get(qa.user_id, {}).get(qa.session_id, [])
    qa_list.append(qa)
    while len(qa_list) > length:
        qa_list.pop(0)  # 超出长度限制，移除最早的
```

### 数据加密

```python
# 敏感字段加密存储
question = Encryption.encrypt(question)
answer = Encryption.encrypt(answer)
function_call = Encryption.encrypt(function_call)

# 读取时解密
question = Encryption.decrypt(qa_params.get('question'))
answer = Encryption.decrypt(qa_params.get('answer'))
```

---

## Memory 操作流程

### 完整流程图

```
用户提问
    ↓
┌─────────────────────────────────────────────────────────────┐
│                     DBA.interaction()                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 获取对话历史                                             │
│     get_qa_history()                                        │
│       ↓                                                     │
│     SESSION_QA_HISTORY.get(user_id, session_id)            │
│       ↓                                                     │
│     ├─ 命中 → 返回内存中的历史                               │
│     └─ 未命中 → select_interaction_memory() 查数据库         │
│                 ↓                                           │
│               解密数据                                       │
│                 ↓                                           │
│               写入 SESSION_QA_HISTORY                        │
│                 ↓                                           │
│               返回历史                                       │
│                                                             │
│  2. 检查工具意图                                             │
│     SESSION_TOOL_HISTORY.get(user_id, session_id)          │
│       ↓                                                     │
│     ├─ 有值 → 追问，直接使用保存的意图                       │
│     └─ 无值 → 首次提问，infer_tool_name() 推断               │
│                 ↓                                           │
│               SESSION_TOOL_HISTORY[user_id][session_id] = tool│
│                                                             │
│  3. 调用 LLM / 工具                                          │
│     ...                                                     │
│                                                             │
│  4. 保存结果                                                 │
│     save_assistant_resp()                                   │
│       ↓                                                     │
│     ├─ 更新 SESSION_TOOL_HISTORY（新意图）                   │
│     ├─ 更新 SESSION_QA_HISTORY（追加新记录）                 │
│     └─ insert_interaction_memory()（写入数据库）             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
    ↓
返回给用户
```

---

## 面试重点

### Q1: GaussMaster 的 Memory 机制是怎样的？

**答**：

GaussMaster 采用**双层 Memory 架构**：

1. **内存层**：
   - `SESSION_QA_HISTORY`：缓存对话历史，加速读取
   - `SESSION_TOOL_HISTORY`：保持当前工具意图，支持多轮对话

2. **数据库层**：
   - `tb_interaction_memory`（SQLite）：持久化存储所有对话记录
   - 敏感字段（question、answer、function_call）加密存储

**读写策略**：
- 读：先查内存，未命中则查数据库并写入内存
- 写：同时更新内存和数据库
- 兼顾速度和可靠性

---

### Q2: 为什么要用双层存储？直接查数据库不行吗？

**答**：

**性能考虑**：
- 内存读取：微秒级
- 数据库读取：毫秒级（慢100-1000倍）
- 对话历史需要频繁读取，内存缓存大幅提升响应速度

**可靠性考虑**：
- 纯内存：进程重启数据丢失
- 纯数据库：速度慢，无法支持高并发
- 双层：速度 + 可靠性兼得

**实际场景**：
- 同一用户的连续提问，内存命中率极高
- 服务重启后，首次查询从数据库加载，后续从内存读取

---

### Q3: SESSION_TOOL_HISTORY 的作用是什么？

**答**：

**作用**：保持多轮对话的工具意图状态。

**场景示例**：
```
用户：查看告警（第1轮）
系统：推断工具为 summary_alarms，保存到 SESSION_TOOL_HISTORY

用户：昨天到今天（第2轮，追问）
系统：从 SESSION_TOOL_HISTORY 获取意图，不再重新推断
      直接提取参数调用 summary_alarms
```

**如果不保存意图**：
- 每轮都要重新推断工具，增加 LLM 调用开销
- 用户追问时可能识别错工具，体验差

---

### Q4: 数据安全怎么保证？

**答**：

**加密存储**：
- question、answer、function_call 使用 AES256 加密
- 数据库中存储密文，即使泄露也无法直接读取

**访问控制**：
- 通过 user_id 和 session_id 隔离不同用户数据
- 只能查询自己的对话历史

**SQL 注入防护**：
- 使用 SQLAlchemy ORM，参数化查询
- 敏感字符转义处理

---

## 一句话总结

> GaussMaster 的 Memory 采用**双层架构**：内存层（`SESSION_QA_HISTORY`、`SESSION_TOOL_HISTORY`）提供快速访问，数据库层（`tb_interaction_memory`）保证持久化。`SESSION_TOOL_HISTORY` 实现多轮对话状态保持，敏感数据加密存储，兼顾性能、可靠性和安全性！
