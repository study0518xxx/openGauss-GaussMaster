# GaussMaster 装饰器与参数校验详解

## 目录

- [装饰器执行顺序](#装饰器执行顺序)
- [define_rules 详解](#define_rules-详解)
- [standardized_api_output 详解](#standardized_api_output-详解)
- [同步 vs 异步函数](#同步-vs-异步函数)
- [server/web 目录分析](#serverweb-目录分析)

---

## 装饰器执行顺序

### 装饰器本质

装饰器实际上是一个**函数包装器**，执行顺序遵循**"就近原则"**：

```python
@decorator_a      # 第3个执行（最外层）
@decorator_b      # 第2个执行（中间层）
@decorator_c      # 第1个执行（最内层）
def func():
    pass
```

**等价于**：
```python
func = decorator_a(decorator_b(decorator_c(func)))
```

### 以 intelligent_interaction_chat 为例

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)      # 第4个
@standardized_event_stream_output                                                          # 第3个
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)                         # 第2个
@switch_llm_context_decorator                                                              # 第1个
def intelligent_interaction_chat(query: PlanModel):
    ...
```

### 包装过程（启动时）

```
原始函数: intelligent_interaction_chat
    ↓
@switch_llm_context_decorator 包装 → 得到 wrapper_c
    ↓
@ParameterChecker.define_rules 包装 → 得到 wrapper_b
    ↓
@standardized_event_stream_output 包装 → 得到 wrapper_a
    ↓
@request_mapping 注册路由

最终: intelligent_interaction_chat = wrapper_a
```

### 请求处理时的执行顺序（运行时）

```
请求到达
    ↓
standardized_event_stream_output 开始
    ↓ 调用
ParameterChecker.define_rules 开始（校验参数）
    ↓ 调用
switch_llm_context_decorator 开始（设置上下文）
    ↓ 调用
intelligent_interaction_chat 执行（业务逻辑）
    ↓ 返回
switch_llm_context_decorator 结束
    ↓ 返回
ParameterChecker.define_rules 结束
    ↓ 返回
standardized_event_stream_output 结束（包装为SSE返回）
    ↓
客户端收到流式响应
```

### 俄罗斯套娃类比

```
调用顺序（从外到内打开）:
    大娃(decorator_a) → 打开看到
        中娃(decorator_b) → 打开看到
            小娃(decorator_c) → 打开看到
                核心(原始函数)
            ← 小娃包装返回
        ← 中娃包装返回
    ← 大娃包装返回
```

---

## define_rules 详解

### 为什么需要多层嵌套函数？

`define_rules` 是一个**带参数的装饰器工厂**，需要三层嵌套：

```
define_rules(**rules)     # 第1层：接收规则参数
    ↓ 返回
decorator(f)              # 第2层：接收被装饰的函数
    ↓ 返回
wrapper(*args, **kwargs)  # 第3层：实际包装逻辑
```

### 完整代码解析

```python
class ParameterChecker:
    @staticmethod
    def define_rules(**rules):           # ← 第1层：接收规则参数
        """Used to determine whether the input parameters are legal."""
        customized_rules = {}
        inspect_params_dict = {}

        # ========== 辅助函数定义（闭包，可以访问 rules）==========
        
        def can_pass_inspection(parameter_pairs, rules=rules):
            """校验参数是否通过检查"""
            for parameter, value in parameter_pairs.items():
                if parameter not in rules:
                    continue
                # 根据 rules[parameter] 的不同类型进行校验
                if rules[parameter] == ParameterChecker.UINT2:
                    if not (0 <= value <= 65535):
                        return False, parameter
                elif rules[parameter] == ParameterChecker.STRING:
                    if not check_string_valid(value):
                        return False, parameter
                # ... 更多校验规则
            return True, None

        def value_filter(parameter_pairs):
            """过滤参数"""
            return parameter_pairs

        # ========== 真正的装饰器 ==========
        
        def decorator(f):                # ← 第2层：接收被装饰函数
            @wraps(f)
            def wrapper(*args, **kwargs): # ← 第3层：同步包装器
                success, parameter = can_pass_inspection(kwargs)
                if not success:
                    raise ValueError(f'Incorrect value for parameter {parameter}.')
                return f(*args, **value_filter(kwargs))

            @wraps(f)
            async def async_wrapper(*args, **kwargs): # ← 第3层：异步包装器
                success, parameter = can_pass_inspection(kwargs)
                if not success:
                    raise ValueError(f'Incorrect value for parameter {parameter}.')
                return await f(*args, **value_filter(kwargs))

            # 根据被装饰函数类型返回不同的包装器
            if inspect.iscoroutinefunction(f):
                return async_wrapper
            return wrapper

        return decorator  # 返回第2层的装饰器
```

### decorator 函数详解

```python
def decorator(f):                # ← 第2层：接收被装饰的函数
    @wraps(f)
    def wrapper(*args, **kwargs): # ← 第3层：包装函数
        # 1. 校验参数
        success, parameter = can_pass_inspection(kwargs)
        if not success:
            raise ValueError(f'Incorrect value for parameter {parameter}.')
        
        # 2. 调用原函数
        return f(*args, **value_filter(kwargs))

    @wraps(f)
    async def async_wrapper(*args, **kwargs): # 异步版本
        success, parameter = can_pass_inspection(kwargs)
        if not success:
            raise ValueError(f'Incorrect value for parameter {parameter}.')
        return await f(*args, **value_filter(kwargs))

    # 智能选择：根据函数类型返回对应的包装器
    if inspect.iscoroutinefunction(f):
        return async_wrapper
    return wrapper
```

| 部分 | 说明 |
|------|------|
| `@wraps(f)` | 保留原函数的元信息（函数名、文档字符串等） |
| `*args` | 接收所有位置参数 |
| `**kwargs` | 接收所有关键字参数 |
| `inspect.iscoroutinefunction(f)` | 检测函数是否是异步函数 |

### 调用时执行哪些函数？

| 函数 | 装饰阶段 | 调用阶段 | 说明 |
|------|---------|---------|------|
| `define_rules` | ✅ 执行 | ❌ 不执行 | 只执行一次 |
| `can_pass_inspection` | ❌ 只定义 | ✅ 执行 | 每次调用都执行 |
| `value_filter` | ❌ 只定义 | ✅ 执行 | 每次调用都执行 |
| `set_rule` | ❌ 只定义 | ❌ 不执行 | 辅助函数，未被调用 |
| `inspect_search_params` | ❌ 只定义 | ❌ 不执行 | 辅助函数，未被调用 |
| `decorator` | ✅ 执行 | ❌ 不执行 | 只执行一次 |
| `wrapper` / `async_wrapper` | ❌ 只定义 | ✅ 执行 | 每次调用都执行 |

### 执行流程图解

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         阶段一：装饰阶段（模块导入时）                      │
│                              只执行一次                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  @define_rules(query=ParameterChecker.QUERY_MODEL)                      │
│       ↓                                                                 │
│  调用 define_rules(**rules)                                             │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  内部执行：                            │                                │
│  │  1. 初始化 customized_rules = {}      │                                │
│  │  2. 初始化 inspect_params_dict = {}   │                                │
│  │  3. 定义 can_pass_inspection()        │  ← 只定义，不执行！            │
│  │  4. 定义 value_filter()               │  ← 只定义，不执行！            │
│  │  5. 定义 set_rule()                   │  ← 只定义，不执行！            │
│  │  6. 定义 inspect_search_params()      │  ← 只定义，不执行！            │
│  │  7. 定义 decorator(f)                 │  ← 只定义，不执行！            │
│  │  8. 返回 decorator                    │                                │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  调用 decorator(intelligent_interaction_chat)                           │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  内部执行：                            │                                │
│  │  1. 定义 wrapper()                    │  ← 只定义，不执行！            │
│  │  2. 定义 async_wrapper()              │  ← 只定义，不执行！            │
│  │  3. 检测 f 是异步函数                  │                                │
│  │  4. 返回 async_wrapper                │  ← 原始函数被替换为包装器        │
│  └─────────────────────────────────────┘                                │
│                                                                         │
│  结果：intelligent_interaction_chat = async_wrapper                     │
│       （原始函数被包装器替换）                                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         阶段二：调用阶段（HTTP请求时）                     │
│                           每次请求都执行                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  HTTP请求到达：POST /v1/api/app/intelligent-interaction                 │
│       ↓                                                                 │
│  调用 intelligent_interaction_chat(query=plan_model)                    │
│       ↓                                                                 │
│  实际执行的是 async_wrapper(*args, **kwargs)                            │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  async_wrapper 内部执行：              │                                │
│  │                                     │                                │
│  │  1. success, parameter =            │  ← ✅ 执行 can_pass_inspection │
│  │     can_pass_inspection(kwargs)     │     （校验参数）                │
│  │                                     │                                │
│  │  2. if not success:                 │                                │
│  │       raise ValueError(...)         │  ← 校验失败抛出异常             │
│  │                                     │                                │
│  │  3. return await f(                 │  ← ✅ 执行 value_filter        │
│  │       *args,                        │     （过滤参数）                │
│  │       **value_filter(kwargs)        │                                │
│  │     )                               │                                │
│  │                                     │                                │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  返回结果给客户端                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## standardized_api_output 详解

### 作用

统一所有API的返回格式，处理异常：

```python
def standardized_api_output(f):
    class ToleratedEncoder(json.JSONEncoder):
        """允许编码更多类型和异常值"""
        def default(self, o):
            return str(o)  # 将未知类型转为字符串

    class ToleratedJSONResponse(JSONResponse):
        def render(self, content) -> bytes:
            return json.dumps(
                content,
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                sort_keys=True,
                separators=(",", ":"),
                cls=ToleratedEncoder
            ).encode("utf-8")

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            data = f(*args, **kwargs)  # 执行原函数
            return ToleratedJSONResponse(content={'success': True, 'data': data})  # 成功格式
        except HTTPException as e:
            raise e
        except Exception as e:
            logging.getLogger('uvicorn.error').exception(e)
            return ToleratedJSONResponse(content={'success': False, 'msg': f'Internal server error.'})  # 失败格式

    @wraps(f)
    async def async_wrapper(*args, **kwargs):
        """异步版本"""
        try:
            data = await f(*args, **kwargs)
            return ToleratedJSONResponse(content={'success': True, 'data': data})
        except HTTPException as e:
            raise e
        except Exception as e:
            logging.getLogger('uvicorn.error').exception(e)
            return ToleratedJSONResponse(content={'success': False, 'msg': f'Internal server error.'})

    if inspect.iscoroutinefunction(f):
        return async_wrapper
    return wrapper
```

### 响应格式

```json
// 成功
{
  "success": true,
  "data": {...}
}

// 失败
{
  "success": false,
  "msg": "错误信息"
}
```

---

## 同步 vs 异步函数

### 核心区别

| 特性 | 同步函数 `def` | 异步函数 `async def` |
|------|---------------|---------------------|
| **定义** | `def func():` | `async def func():` |
| **返回值** | 直接返回结果 | 返回一个 **协程对象** (coroutine) |
| **调用方式** | `func()` | `await func()` 或 `asyncio.run(func())` |
| **执行方式** | 阻塞执行 | 非阻塞，可以挂起等待 |
| **适用场景** | CPU密集型、简单操作 | IO密集型（网络、文件、数据库） |

### 示例对比

```python
import asyncio
import time

# ========== 同步版本 ==========
def fetch_data_sync():
    print("同步：开始获取数据")
    time.sleep(2)  # 模拟网络请求，阻塞2秒
    print("同步：获取数据完成")
    return "data"

def main_sync():
    print("=== 同步执行 ===")
    result = fetch_data_sync()  # 直接调用，阻塞等待
    print(f"结果: {result}")

# ========== 异步版本 ==========
async def fetch_data_async():
    print("异步：开始获取数据")
    await asyncio.sleep(2)  # 模拟网络请求，非阻塞挂起
    print("异步：获取数据完成")
    return "data"

async def main_async():
    print("=== 异步执行 ===")
    result = await fetch_data_async()  # 需要 await
    print(f"结果: {result}")
```

### 调用规则

```python
# 规则1：async 调用 async，需要 await
async def func_a():
    return await func_b()  # ✅ 正确

# 规则2：sync 调用 async，需要事件循环
def func_c():
    return asyncio.run(func_a())  # ✅ 正确

# 规则3：async 调用 sync，直接调用
async def func_d():
    return func_e()  # ✅ 正确，不需要 await
```

---

## server/web 目录分析

### 实际内容

| 文件 | 实际职责 | 与HTTP/Web的关系 |
|------|---------|----------------|
| `data_transformer.py` | RAG检索、知识库管理、数据源管理 | ❌ **业务逻辑**，不是HTTP相关 |
| `context_manager.py` | 用户会话上下文管理（当前实例、当前LLM） | ⚠️ 与Web请求上下文相关 |
| `jsonify_utils.py` | 数据库查询结果转JSON | ❌ 工具函数 |

### 目录命名问题

```
server/web/ 这个目录名容易误解，实际内容：

❌ 不是 HTTP/Web 框架相关
❌ 不是 路由处理
❌ 不是 请求/响应处理

✅ 是 业务逻辑层（RAG问答、知识库管理）
✅ 是 会话上下文管理
✅ 是 数据转换工具
```

### 真正的Web/HTTP层

```
GaussMaster/
├── common/http/           ← ✅ 真正的HTTP层
│   ├── _service_impl.py   # HttpService、request_mapping、响应封装
│   └── ...
│
└── server/web/            ← ⚠️ 实际是业务逻辑层（目录名有误导）
    ├── data_transformer.py
    └── context_manager.py
```

### 修正后的分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     修正后的分层架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  common/http/        ← 真正的Web/HTTP层（框架封装）            │
│  - _service_impl.py  - HttpService、路由、响应格式              │
│                                                             │
│  controllers/        ← 控制器层（API入口）                    │
│  - core.py           - 路由函数，调用业务层                     │
│                                                             │
│  server/web/         ← 业务逻辑层（目录名有误导）              │
│  - data_transformer.py - RAG问答、知识库管理                   │
│  - context_manager.py  - 用户会话上下文                        │
│                                                             │
│  multiagents/        ← AI Agent核心层                        │
│  - agents/dba.py     - DBA Agent                            │
│  - tools/            - 运维工具                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

*本文档基于 openGauss-GaussMaster v1.0.0*
