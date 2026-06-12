# DBA 工具调用流程详解

---

## 一、概述

`interact_with_tool` 是 DBA Agent 的核心工具交互方法，负责处理用户问题与第三方工具的匹配和调用流程。

---

## 二、工具调用流程

### 完整流程图

```
用户提问
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. 检查会话意图 (SESSION_TOOL_HISTORY)                 │
│    ├─ intention_tool 不为 None → 直接进入参数提取      │
│    └─ intention_tool 为 None → 需要匹配新工具          │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (新意图)
┌─────────────────────────────────────────────────────────┐
│ 2. 工具匹配                                            │
│    └─ infer_tool_name() → 推断应该调用哪个工具         │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ 3. 工具有效性验证                                      │
│    ├─ check_has_valid_tool() → 检查工具是否有效        │
│    └─ 无效 → 返回"无法用第三方工具解答"                 │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (有效)
┌─────────────────────────────────────────────────────────┐
│ 4. 无参工具判断                                        │
│    ├─ check_is_no_param_tool() → 是否无需参数         │
│    └─ 是 → 直接调用工具并返回结果                      │
└──────────────────────────┬──────────────────────────────┘
                           ▼ (需要参数)
┌─────────────────────────────────────────────────────────┐
│ 5. 参数提取                                            │
│    └─ infer_arguments() → 从问题中提取工具参数         │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ 6. 参数验证                                            │
│    ├─ verify_arguments() → 检查参数是否完整            │
│    ├─ 完整 → 调用工具                                  │
│    └─ 不完整 → 提示用户补充参数                        │
└─────────────────────────────────────────────────────────┘
```

---

## 三、核心代码解析

### 3.1 会话意图检查

```python
intention_tool = global_vars.SESSION_TOOL_HISTORY.get(self.user_id, {}).get(self.session_id, None)
```

**作用**：检查当前会话是否有未完成的工具调用意图。

| 场景 | intention_tool 值 | 后续流程 |
|------|------------------|---------|
| 首次提问或上一意图已完成 | `None` | 需要重新匹配工具 |
| 正在进行工具调用 | 工具名称 | 继续参数提取流程 |

### 3.2 工具匹配

```python
yield [formatter_progress('工具匹配中...')]
matched_tool = await infer_tool_name(self.question, self.user_id, self.session_id, self.llm)
```

**作用**：使用 LLM 分析用户问题，推断应该调用哪个工具。

**输出**：工具名称（如 `gs_sql_execute`, `gs_vacuum` 等）

### 3.3 工具有效性验证

```python
is_valid = check_has_valid_tool(matched_tool)
if not is_valid:
    content_resp = '用户提问的问题无法用第三方工具解答。'
    await self.save_assistant_resp(content_resp=content_resp)
    yield [formatter_str(content_resp)]
    return
```

**作用**：验证匹配到的工具是否在系统注册的工具列表中。

### 3.4 无参工具判断

```python
no_need_param = check_is_no_param_tool(matched_tool)
if no_need_param:
    yield [formatter_progress('工具调用中...')]
    tool_result = call_tool(matched_tool)
    yield tool_result
    content_resp = f'将为您调用工具{matched_tool}'
    await self.save_assistant_resp(content_resp=content_resp, tool_name=matched_tool)
    return
```

**作用**：判断工具是否不需要参数即可调用。

**示例**：`gs_database_status` 可能不需要参数即可获取数据库状态。

### 3.5 参数提取

```python
yield [formatter_progress('提取参数中...')]
qa_record_history = await self.get_qa_history()
content_resp, function_call = await infer_arguments(self.question, intention_tool, qa_record_history, self.llm)
```

**作用**：使用 LLM 从用户问题中提取工具所需的参数。

**输入**：用户问题、工具名称、历史对话

**输出**：
- `content_resp`：自然语言回复（如确认提问）
- `function_call`：函数调用信息（包含参数）

### 3.6 参数验证与调用

```python
if function_call:
    is_complete_params, correct_params, need_prams = verify_arguments(function_call)
    if is_complete_params:
        yield [formatter_progress('工具调用中...')]
        tool_result = call_tool(intention_tool, correct_params)
        await self.save_assistant_resp(content_resp=content_resp, tool_name=intention_tool,
                                       tool_params=correct_params)
        yield tool_result
    else:
        content_resp = f'缺少参数{",".join(list(need_prams.keys()))}，请一次性提供完整'
        await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
        yield [formatter_str(content_resp)]
```

**作用**：验证参数完整性，决定是否调用工具或提示用户补充参数。

---

## 四、关键函数说明

| 函数 | 作用 | 返回值 |
|------|------|-------|
| `infer_tool_name()` | 推断应该调用的工具 | 工具名称字符串 |
| `check_has_valid_tool()` | 验证工具是否有效 | `True`/`False` |
| `check_is_no_param_tool()` | 判断工具是否无需参数 | `True`/`False` |
| `infer_arguments()` | 从问题中提取参数 | `(回复内容, 函数调用信息)` |
| `verify_arguments()` | 验证参数完整性 | `(是否完整, 正确参数, 缺失参数)` |
| `call_tool()` | 调用具体工具 | 工具执行结果 |

---

## 五、状态管理机制

### SESSION_TOOL_HISTORY 结构

```python
SESSION_TOOL_HISTORY = {
    "user_id": {
        "session_id": "当前工具名称"
    }
}
```

**作用**：跨对话轮次保存当前工具调用意图，支持多轮参数补充。

**示例流程**：
```
轮次1: 用户问 "执行SQL" → intention_tool = None → 匹配工具 → intention_tool = "gs_sql_execute"
轮次2: 用户补充 "SELECT * FROM users" → intention_tool = "gs_sql_execute" → 直接提取参数
```

---

## 六、消息格式

### 进度消息
```python
yield [formatter_progress('工具匹配中...')]
```

### 文本消息
```python
yield [formatter_str(content_resp)]
```

### 工具结果
```python
yield tool_result  # 工具执行结果，可能包含表格、图表等
```

---

## 七、设计要点

### 1. 状态持久化
通过 `SESSION_TOOL_HISTORY` 实现跨轮次的意图追踪

### 2. 渐进式参数收集
支持用户分多次提供工具参数

### 3. 错误处理
- 工具不存在时给出明确提示
- 参数不完整时提示用户补充

### 4. 异步流程
使用 `yield` 实现流式输出，提升用户体验

---

## 八、典型场景示例

### 场景1：简单工具调用
```
用户: 检查数据库状态
Agent: 工具匹配中... → 匹配到 gs_database_status
Agent: 工具调用中... → 返回数据库状态信息
```

### 场景2：需要参数的工具调用
```
用户: 执行SQL
Agent: 工具匹配中... → 匹配到 gs_sql_execute
Agent: 提取参数中... → 需要 SQL 语句
Agent: 缺少参数 sql，请一次性提供完整
用户: SELECT * FROM users WHERE id=1
Agent: 提取参数中... → 参数完整
Agent: 工具调用中... → 返回查询结果
```

---

**文档版本**：v1.0  
**生成时间**：2026-06-12  
**适用项目**：openGauss-GaussMaster