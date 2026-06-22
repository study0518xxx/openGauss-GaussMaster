# 多 Agent 与工具层面试题

## 一、基础问题

### Q1: 系统的 Agent 架构是怎么设计的？

**回答要点**：
采用 **Multi-Agent 协作架构**，核心角色：

| Agent | 职责 |
|:---|:---|
| **Planner** | 判断用户意图，决定走知识问答还是工具调用 |
| **DBA Agent** | 负责工具匹配、参数提取、调用执行 |
| **Tool Executor** | 实际调用 DBMind 接口，获取运维数据 |

**入口**：`multiagents/agents/dba.py` 的 `interact()` 方法

---

### Q2: 工具是怎么注册和管理的？

**回答要点**：
- 使用 `Registry` 类（`common/plugins/registry.py`）作为工具注册中心
- 继承自 `dict`，支持按 `AgentRoles` 分类
- 注册方式（装饰器）：
  ```python
  @tool_registry(name="slow_sql_rca", description="慢SQL根因分析", params={...})
  def slow_sql_rca(...):
      ...
  ```
- 支持两种格式输出：
  - `detail_with_param`：带参数详情（给 LLM 理解）
  - `detail_without_param`：不带参数（简化展示）

---

### Q3: 工具调用的完整流程是什么？

**回答要点**：
```
用户提问
    │
    ▼
1. 意图识别（Planner）
   - 判断是知识问答还是工具调用
    │
    ▼
2. 工具匹配（infer_tool_name）
   - LLM 从注册的工具列表中匹配最相关的工具
    │
    ▼
3. 参数提取（infer_arguments）
   - LLM 从对话中提取工具所需参数
   - 缺失参数 → 追问用户
    │
    ▼
4. 工具执行（call_tool）
   - 调用 DBMind 接口
   - 获取结果（表格/图表/文本）
    │
    ▼
5. 结果格式化
   - 格式化为前端可渲染的格式（table/graph/str）
```

---

## 二、进阶问题

### Q4: 多轮对话中缺失参数怎么补全？

**回答要点**：
- 使用 `SESSION_TOOL_HISTORY` 记录**未完成的工具意图**
- 流程：
  ```
  用户："帮我查一下慢 SQL"
  系统：匹配到 slow_sql_rca，但缺少时间参数
         → 记录 SESSION_TOOL_HISTORY[user][session] = "slow_sql_rca"
         → 追问："请提供查询的时间范围"
  
  用户："最近一小时"
  系统：读取 SESSION_TOOL_HISTORY，知道是 slow_sql_rca
         → 补全参数 → 调用工具 → 返回结果
  ```
- 本质是一个**状态机记忆**，不是历史记录

---

### Q5: 工具返回的结果有哪些格式？怎么渲染？

**回答要点**：
定义在 `utils/ui_output_util.py`：

| 类型 | 函数 | 用途 |
|:---|:---|:---|
| `str` | `formatter_str()` | 普通文本 |
| `table` | `formatter_table()` | 表格数据 |
| `graph` | `formatter_graph()` | 时序图/折线图 |
| `progress` | `formatter_progress()` | 进度提示 |
| `button` | `formatter_button()` | 可点击按钮 |
| `title` | `formatter_title()` | 标题层级 |
| `status` | `formatter_alarm()` | 状态/告警卡片 |
| `inspection` | `formatter_inspection_button()` | 巡检选项 |

**前端渲染**：根据 `type` 字段选择对应组件渲染

---

### Q6: DBMind 工具调用是怎么实现的？

**回答要点**：
- 通过 `dbmind_request()` 函数（`common/http/dbmind_request.py`）
- 使用 `AutoSession` 自动管理 JWT Token
- 调用流程：
  ```python
  def call_tool(tool_name, params):
      url = construct_url(tool_name, params)
      response = dbmind_request('GET', url)
      return parse_response(response)
  ```
- 结果解析：根据工具类型解析为 table/graph/str 等格式

---

## 三、深挖问题

### Q7: 如果工具调用失败，系统怎么处理？

**回答要点**：
1. **异常捕获**：`call_tool` 捕获异常，返回错误信息
2. **重试机制**：HTTP 层自动重试 3 次
3. **降级策略**：如果 DBMind 不可用，返回友好提示
4. **前端展示**：错误信息格式化为 `formatter_str(content, color='red')`

---

### Q8: 工具注册中心怎么支持动态扩展？

**回答要点**：
- `Registry` 类继承 `dict`，支持运行时注册
- 新工具只需要加装饰器即可，不需要修改核心代码
- 分类管理：按 `AgentRoles` 划分，不同角色只能看到相关工具
- 支持参数自动解析：通过函数签名生成参数定义

---

### Q9: 怎么防止工具被恶意调用？

**回答要点**：
1. **参数校验**：每个工具定义参数类型和范围，调用前校验
2. **权限控制**：通过 `user_id` 和 `session_id` 隔离，只能访问有权限的集群
3. **敏感操作确认**：危险操作（如删除）需要二次确认
4. **审计日志**：所有工具调用记录到数据库，可追溯

---

### Q10: 如果让你扩展新的 Agent 角色，你会怎么做？

**回答要点**：
1. 定义新角色枚举（`AgentRoles`）
2. 实现新 Agent 类，继承基类
3. 注册专属工具到 `Registry` 的对应分类
4. 在 Planner 中增加路由逻辑，将特定意图分配给新 Agent
5. 增加上下文管理变量，隔离不同 Agent 的状态

---

## 四、手写代码题

### 题目：实现一个简单的工具注册中心

```python
class ToolRegistry:
    def __init__(self):
        self._tools = {}
    
    def register(self, name, description, params=None):
        def decorator(func):
            self._tools[name] = {
                'name': name,
                'description': description,
                'params': params or {},
                'func': func
            }
            return func
        return decorator
    
    def get_tool(self, name):
        return self._tools.get(name)
    
    def list_tools(self):
        return [
            {'name': t['name'], 'description': t['description']}
            for t in self._tools.values()
        ]
    
    def call(self, name, **kwargs):
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool {name} not found")
        return tool['func'](**kwargs)


# 使用示例
registry = ToolRegistry()

@registry.register(name="add", description="加法", params={"a": "int", "b": "int"})
def add(a, b):
    return a + b

print(registry.list_tools())
print(registry.call("add", a=1, b=2))
```
