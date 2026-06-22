# 06-Memory机制详解

> 本文档详解 GaussMaster 的 Memory（记忆）机制，包括双层存储、意图状态保持和加密存储。

---

## 1. Memory 是什么？

**Memory（记忆）** 是 Agent 系统的"大脑"，负责：
- 保存多轮对话历史
- 保持当前意图状态
- 支持上下文理解

---

## 2. 双层存储架构

```
┌─────────────────────────────────────────┐
│           第一层：内存缓存                │
│  SESSION_QA_HISTORY = {}                │
│  SESSION_TOOL_HISTORY = {}              │
│  • 速度快（微秒级）                      │
│  • 重启丢失                              │
│  • 适合高频访问                          │
└─────────────────────────────────────────┘
                    │
                    ▼ 异步写入
┌─────────────────────────────────────────┐
│           第二层：SQLite持久化            │
│  tb_interaction_memory 表               │
│  • 速度较慢（毫秒级）                    │
│  • 持久保存                              │
│  • 适合长期存储                          │
└─────────────────────────────────────────┘
```

### 2.1 内存层

```python
# global_vars.py

# 对话历史缓存 {user_id: {session_id: [QARecord, ...]}}
SESSION_QA_HISTORY = {}

# 意图状态缓存 {user_id: {session_id: tool_name}}
SESSION_TOOL_HISTORY = {}
```

**特点**：
- 读写速度极快（微秒级）
- 服务重启后数据丢失
- 适合存储当前活跃会话

### 2.2 SQLite 层

```python
# common/metadatabase/schema/interaction_memory.py

class InteractionMemory(ResultDbBase):
    __tablename__ = 'tb_interaction_memory'
    
    qa_record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False)
    question = Column(TEXT, nullable=False)      # 加密存储
    answer = Column(TEXT, nullable=True)        # 加密存储
    llm_name = Column(String(64), nullable=True)
    function_call = Column(TEXT, nullable=True) # 加密存储
    created_at = Column(BigInteger, nullable=False)
```

**特点**：
- 持久化存储
- AES256 加密敏感字段
- 支持按用户和会话查询

---

## 3. 意图状态保持

### 3.1 问题场景

```
用户：查看告警
系统：请提供时间范围

用户：昨天          ← 这里需要保持"查看告警"的意图
系统：调用 summary_alarms 查询昨天告警
```

### 3.2 实现机制

```python
# global_vars.py
SESSION_TOOL_HISTORY = {}  # 保存每个会话的当前工具意图

# dba.py - interact_with_tool()
async def interact_with_tool(self, question, user_id, session_id, ...):
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
    
    # 提取参数并执行...
    
    # 对话完成后清空意图
    SESSION_TOOL_HISTORY[user_id][session_id] = None
```

### 3.3 状态流转

```
┌─────────────┐
│   无意图     │
└──────┬──────┘
       │ 用户提问
       ▼
┌─────────────┐
│  意图识别中  │ ← infer_tool_name()
└──────┬──────┘
       │ 识别成功
       ▼
┌─────────────┐
│  等待参数    │ ← SESSION_TOOL_HISTORY 保存意图
└──────┬──────┘
       │ 用户提供参数
       ▼
┌─────────────┐
│  执行工具    │ ← call_tool()
└──────┬──────┘
       │ 执行完成
       ▼
┌─────────────┐
│   无意图     │ ← 清空 SESSION_TOOL_HISTORY
└─────────────┘
```

---

## 4. 对话历史管理

### 4.1 读取流程

```python
async def get_qa_history(self, user_id, session_id):
    """获取对话历史（先查内存，再查数据库）"""
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

### 4.2 写入流程

```python
async def save_qa_record(self, user_id, session_id, question, answer, function_call):
    """保存对话记录（内存 + 数据库）"""
    # 1. 加密敏感信息
    encrypted_question = Encryption.encrypt(question)
    encrypted_answer = Encryption.encrypt(answer)
    encrypted_function_call = Encryption.encrypt(json.dumps(function_call))
    
    # 2. 写入数据库
    await insert_interaction_memory(
        user_id=user_id,
        session_id=session_id,
        question=encrypted_question,
        answer=encrypted_answer,
        function_call=encrypted_function_call,
        created_at=time.time()
    )
    
    # 3. 更新内存缓存
    qa_record = QARecord(question=question, answer=answer, function_call=function_call)
    if user_id not in SESSION_QA_HISTORY:
        SESSION_QA_HISTORY[user_id] = {}
    if session_id not in SESSION_QA_HISTORY[user_id]:
        SESSION_QA_HISTORY[user_id][session_id] = []
    SESSION_QA_HISTORY[user_id][session_id].append(qa_record)
```

---

## 5. 加密机制

### 5.1 AES256-CBC 加密

```python
# common/security.py

class Encryption:
    @staticmethod
    def encrypt(plain_text: str) -> str:
        """AES256-CBC 加密"""
        # 1. 生成随机IV
        iv = os.urandom(16)
        # 2. 创建加密器
        cipher = AES.new(key, AES.MODE_CBC, iv)
        # 3. 填充并加密
        padded_data = pad(plain_text.encode(), AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        # 4. 返回 base64(iv + encrypted)
        return base64.b64encode(iv + encrypted).decode()
    
    @staticmethod
    def decrypt(cipher_text: str) -> str:
        """AES256-CBC 解密"""
        # 1. 解码base64
        data = base64.b64decode(cipher_text)
        # 2. 提取IV
        iv = data[:16]
        encrypted = data[16:]
        # 3. 解密
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = cipher.decrypt(encrypted)
        # 4. 去填充
        return unpad(padded, AES.block_size).decode()
```

### 5.2 加密字段

| 字段 | 说明 |
|------|------|
| `question` | 用户问题 |
| `answer` | 系统回答 |
| `function_call` | 工具调用记录 |

---

## 6. 核心代码位置

| 函数/类 | 文件 | 职责 |
|---------|------|------|
| `SESSION_QA_HISTORY` | `global_vars.py` | 内存对话历史 |
| `SESSION_TOOL_HISTORY` | `global_vars.py` | 内存意图状态 |
| `InteractionMemory` | `schema/interaction_memory.py` | 数据库表定义 |
| `get_qa_history()` | `agents/dba.py` | 读取对话历史 |
| `save_qa_record()` | `agents/dba.py` | 保存对话记录 |
| `Encryption` | `common/security.py` | 加密解密 |

---

## 7. 面试重点

### Q: 多轮对话怎么实现？

**答**: 
- 使用 `SESSION_TOOL_HISTORY` 保存每个会话的当前意图
- 首次提问时推断工具并保存到 SESSION_TOOL_HISTORY
- 追问时直接从 SESSION_TOOL_HISTORY 获取意图，跳过识别步骤
- 对话完成后清空意图

### Q: 双层存储的优势？

**答**:
- 内存层：速度快，适合高频访问
- SQLite层：持久化，适合长期存储
- 结合两者，平衡速度和可靠性

### Q: 为什么加密存储？

**答**: 对话历史可能包含敏感信息（如数据库密码、SQL语句），使用 AES256-CBC 加密保护数据安全。

---

*本文档基于 openGauss-GaussMaster v1.0.0*
