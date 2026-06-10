# HTTP 框架封装详解 - _service_impl.py

## 文件概述

`_service_impl.py` 是 GaussMaster 的 HTTP 框架封装层，实现了与具体 Web 框架（FastAPI）的解耦。其核心设计理念是：**通过抽象层使得业务代码不直接依赖 FastAPI，便于未来迁移到其他框架（如 Flask）**。

```
核心组件
├── HttpService 类          → HTTP 服务封装
├── request_mapping()       → 路由注册装饰器
├── standardized_api_output() → API 响应标准化装饰器
├── standardized_event_stream_output() → SSE 流式响应装饰器
└── _RequestMappingTable   → 路由映射表（全局静态变量）
```

---

## 1. _RequestMappingTable - 路由映射表

### 本质

```python
_RequestMappingTable = dict()  # 全局静态字典
```

### 数据结构

```
_RequestMappingTable: Dict[Tuple[str, str], Tuple[函数, options]]
                    = Dict[(路由路径, HTTP方法), (处理函数, 装饰器选项)]

示例：
{
    ('/v1/api/app/intelligent-interaction', 'POST'): (intelligent_interaction_chat, {'api': True}),
    ('/v1/api/clusters', 'GET'): (get_clusters, {'api': True}),
    ('/v1/api/ask_gauss', 'POST'): (ask_gauss, {'api': True}),
    ...
}
```

### 关键特点

| 特点 | 说明 |
|------|------|
| **全局静态** | 模块级变量，所有 HttpService 实例共享 |
| **延迟注册** | 路由在模块导入时通过 `@request_mapping` 装饰器注册，此时 FastAPI app 还未创建 |
| **与框架解耦** | 路由信息存储在独立表中，启动时才绑定到 FastAPI |

### 注册机制

路由注册发生在 **模块导入时**，而非服务启动时：

```python
# core.py 模块导入时执行
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
def intelligent_interaction_chat(query: PlanModel):
    return dba.interact(**plan_model)
```

此时 `intelligent_interaction_chat` 函数被装饰，但 `self.app` 还不存在。

---

## 2. request_mapping() - 路由注册装饰器

### 函数签名

```python
def request_mapping(rule, method, **kwargs):
    """To record to a static mapping dict."""
    def decorator(f):
        _RequestMappingTable[(rule, method)] = (f, kwargs)
        return f
    return decorator
```

### 执行流程

```
@request_mapping("/v1/api/test", method='POST', api=True)
              │
              ▼
1. 装饰器工厂调用
   request_mapping("/v1/api/test", method='POST', api=True)
              │
              ▼
2. 返回 decorator 函数
   def decorator(f):
       _RequestMappingTable[("/v1/api/test", 'POST')] = (f, {'api': True})
       return f
              │
              ▼
3. 装饰器应用
   intelligent_interaction_chat = decorator(intelligent_interaction_chat)
              │
              ▼
4. 结果
   _RequestMappingTable[("/v1/api/test", 'POST')] = (intelligent_interaction_chat, {'api': True})
```

### 核心设计意图

**为什么不用直接注册到 FastAPI？**

```
传统方式（直接注册）                    当前方式（延迟注册）
─────────────────                    ──────────────────────
模块导入时 app 还不存在                  模块导入时只需要一个字典
  ↓                                       ↓
无法注册 → 需要在 start_listen 后注册      所有路由先存到全局表
  ↓                                       ↓
                                          服务启动时再批量绑定
```

---

## 3. HttpService.attach() - 路由绑定

### 函数签名

```python
def attach(self, func, rule, method, **options):
    """Attach a rule to the backend app."""
    is_api = options.pop('api', False)
    rule = rule.replace('<', '{').replace('>', '}')
    if is_api:
        self.app.add_api_route(rule, func, methods=[method], **options)
    else:
        self.app.add_route(rule, func, methods=[method], **options)
    self.rule_num += 1
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `func` | Callable | 处理函数 |
| `rule` | str | 路由路径，支持 FastAPI 格式 `{param}` |
| `method` | str | HTTP 方法（GET/POST/PUT/DELETE） |
| `options` | dict | 额外选项，`api=True` 表示 API 路由 |

### 路由格式转换

```python
# Flask 风格 → FastAPI 风格
"<name>"   → "{name}"
"<int:id>" → "{id}"  (类型提示由函数参数指定)
```

### 执行示例

```python
# 注册前
rule = "/v1/api/clusters/<cluster_name>/<int:id>"
rule = rule.replace('<', '{').replace('>', '}')
# 转换后
rule = "/v1/api/clusters/{cluster_name}/{id}"

# 调用 FastAPI 的 add_api_route
self.app.add_api_route(rule, func, methods=['GET'], **options)
```

### is_api 参数的作用

```python
if is_api:
    self.app.add_api_route(...)  # OpenAPI 文档会包含此路由
else:
    self.app.add_route(...)       # 内部路由，不暴露在文档
```

---

## 4. HttpService.route() - 路由装饰器

### 函数签名

```python
def route(self, rule, **options):
    def decorator(f):
        self.attach(f, rule, **options)
        return f
    return decorator
```

### 使用场景

`route()` 是 `attach()` 的装饰器版本，用于在类内部定义路由：

```python
class HttpService:
    def route(self, rule, **options):
        # 这个方法返回一个装饰器
        def decorator(f):
            self.attach(f, rule, **options)
            return f
        return decorator

# 使用方式
service = HttpService()

@service.route("/test", method='GET')
def test_handler():
    return "ok"
```

### 两种注册方式的对比

```
方式一：装饰器注册（route）
────────────────────────────────
@service.route("/path", method='GET')
def handler():
    pass

方式二：直接调用（attach）
────────────────────────────────
def handler():
    pass
service.attach(handler, "/path", 'GET')
```

---

## 5. HttpService.start_listen() - 服务启动

### 函数签名

```python
def start_listen(self, host, port,
                 ssl_keyfile=None, ssl_certfile=None,
                 ssl_keyfile_password=None, ssl_ca_file=None):
```

### 完整执行流程图

```
start_listen(host, port, ssl_config...)
                    │
                    ▼
┌─────────────────────────────────────────┐
│  1. 创建 Server 内部类                    │
│     class Server(uvicorn.Server):        │
│         ├── install_signal_handlers()    │
│         └── run_in_thread()              │
└──────────────────┬────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  2. 从 _RequestMappingTable 批量注册路由  │
│                                         │
│  for (rule, method), (f, options) in   │
│              _RequestMappingTable.items():│
│      self.attach(f, rule, method, **options)│
└──────────────────┬────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  3. 创建 uvicorn.Config                 │
│     config = uvicorn.Config(            │
│         self.app,                       │
│         host=host,                      │
│         port=port,                      │
│         ssl_keyfile=...,                │
│         ssl_certfile=...,               │
│         ...                             │
│     )                                   │
└──────────────────┬────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  4. 加载配置并启用 SSL                   │
│     config.load()                        │
│     if config.is_ssl:                   │
│         # 禁用不安全的 SSL 版本          │
│         ssl.OP_NO_SSLv2 | SSLv3 | TLSv1 │
└──────────────────┬────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  5. 创建 Server 实例并启动               │
│     self._server = Server(config)       │
│                                         │
│     if sys.version_info >= (3, 7):      │
│         self._server.run_in_thread()    │
│     else:                               │
│         self._server.run()              │
└─────────────────────────────────────────┘
```

### run_in_thread() 详解

```python
@contextlib.contextmanager
def run_in_thread(self):
    # 1. 创建守护线程
    thread = threading.Thread(target=self.run, name='WebServiceThread')
    thread.daemon = True  # 进程退出时自动终止

    # 2. 启动线程
    thread.start()

    # 3. 阻塞等待退出信号
    try:
        while not this_service.need_to_exit:
            time.sleep(0.001)  # 避免 CPU 忙等待
        yield  # 线程继续执行到这里
    finally:
        # 4. 清理工作
        thread.join(5)  # 最多等待 5 秒
        _RequestMappingTable.clear()  # 清空路由表
```

### 线程模型

```
主线程                                    WebServiceThread
  │                                           │
  │  start_listen()                           │
  ├────────────────────────────────────────▶  │
  │                                           │
  │  run_in_thread() 进入阻塞                 │
  │  ◀──────────────────────────── wait ─────│
  │                                           │
  │  处理其他事务...                          │  uvicorn.run()
  │                                           │    ↓
  │                                           │  监听 HTTP 请求
  │                                           │    ↓
  │                                           │  处理路由
  │                                           │
  │  shutdown() 触发                          │
  ├────────────────────────────────────────▶  │
  │                                           │
  │  need_to_exit = True                     │  退出循环
  │  ◀──────────────────────────── yield ────│
  │                                           │
  │  thread.join(5)                          │
  │  等待线程结束                             │
```

---

## 6. HttpService 初始化详解

### __init__ 方法

```python
def __init__(self, name=__name__):
    # 1. 创建 FastAPI 实例
    self.app = FastAPI(
        title=name,
        openapi_url=None,    # 禁用 OpenAPI 文档
        docs_url=None,       # 禁用 Swagger UI
        redoc_url=None       # 禁用 ReDoc
    )

    # 2. 初始化服务器引用
    self._server = None
    self.need_to_exit = False

    # 3. 注册异常处理器
    @self.app.exception_handler(StarletteHTTPException)
    async def exception_handler(_, exc):
        return JSONResponse(
            content={'success': False, 'msg': str(exc.detail)},
            status_code=exc.status_code
        )

    # 4. 路由计数器
    self.rule_num = 0

    # 5. 注册语言中间件
    @self.app.middleware("http")
    async def set_language_middleware(request: Request, call_next):
        accept_language = request.headers.get('Accept-Language', global_vars.LANGUAGE)
        global_vars.LANGUAGE = parse_accept_language(accept_language)
        response = await call_next(request)
        return response
```

### 中间件流程

```
HTTP 请求
    │
    ▼
set_language_middleware
    │
    ├─→ 读取 Accept-Language 请求头
    │
    ├─→ 解析并设置全局语言 global_vars.LANGUAGE
    │
    ├─→ call_next(request) → 路由处理函数
    │
    ▼
返回响应（带语言设置）
```

---

## 7. 服务启动完整流程

### 从 startup.py 看启动顺序

```python
# startup.py
_http_service = HttpService()  # 1. 创建服务实例

# 2. 注册控制器模块（触发 core.py 等模块导入）
for c in controllers.get_dbmind_controller():
    _http_service.register_controller_module(c)

# 3. 启动服务
_http_service.start_listen(host, port, **ssl_config)
```

### get_dbmind_controller() 返回值

```python
# controllers/__init__.py
def get_dbmind_controller():
    return ['GaussMaster.controllers.core']
```

### 模块导入链

```
register_controller_module('GaussMaster.controllers.core')
              │
              ▼
__import__('GaussMaster.controllers.core')
              │
              ▼
导入 core.py 模块
              │
              ▼
执行所有 @request_mapping 装饰器
              │
              ▼
_RequestMappingTable 被填充
```

---

## 8. 装饰器组合机制

### core.py 中的典型用法

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
@switch_llm_context_decorator
def intelligent_interaction_chat(query: PlanModel):
    return dba.interact(**plan_model)
```

### 装饰器执行顺序（从外到内）

```
请求 → standardized_event_stream_output (最外层)
              │
              ▼
       ParameterChecker.define_rules
              │
              ▼
       switch_llm_context_decorator
              │
              ▼
       intelligent_interaction_chat() (原始函数)
```

### 响应处理

```python
# standardized_api_output 装饰器
@wraps(f)
def wrapper(*args, **kwargs):
    try:
        data = f(*args, **kwargs)
        return ToleratedJSONResponse(content={'success': True, 'data': data})
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.getLogger('uvicorn.error').exception(e)
        return ToleratedJSONResponse(content={'success': False, 'msg': 'Internal server error.'})
```

---

## 9. 核心设计模式总结

### 延迟绑定模式

```
阶段1: 模块导入时                    阶段2: 服务启动时
─────────────────────              ──────────────────────
@Request_mapping()                  start_listen()
     │                                   │
     ▼                                   ▼
_RequestMappingTable[path] = func    for each (path, func):
                                          self.app.add_api_route()
```

### 框架解耦模式

```
业务代码
    │
    ▼
request_mapping() 装饰器
    │
    ▼
_RequestMappingTable (中间层)
    │
    ▼
HttpService.attach()
    │
    ▼
FastAPI / Flask / 其他框架
```

### 好处

1. **可测试性**：业务函数可以独立于 Web 框架测试
2. **可迁移性**：更换 Web 框架只需修改 HttpService
3. **可维护性**：路由集中管理，一目了然

---

## 10. 流程图总览

```
┌──────────────────────────────────────────────────────────────────┐
│                      HTTP 服务启动完整流程                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  startup.py                                                       │
│      │                                                           │
│      ▼                                                           │
│  HttpService.__init__()                                          │
│      │                                                           │
│      ├─→ FastAPI(app) 创建                                      │
│      ├─→ exception_handler 注册                                  │
│      └─→ middleware 注册                                          │
│      │                                                           │
│      ▼                                                           │
│  register_controller_module('GaussMaster.controllers.core')      │
│      │                                                           │
│      ▼                                                           │
│  __import__('GaussMaster.controllers.core')                      │
│      │                                                           │
│      ▼                                                           │
│  @request_mapping() 装饰器执行                                     │
│      │                                                           │
│      ▼                                                           │
│  _RequestMappingTable 填充完成                                     │
│      │                                                           │
│      ▼                                                           │
│  _http_service.start_listen(host, port)                         │
│      │                                                           │
│      ├─→ 创建 Server(uvicorn.Server)                             │
│      │                                                           │
│      ├─→ for (path, method), (func, opts) in _RequestMappingTable│
│      │       self.attach(func, path, method, **opts)              │
│      │                                                           │
│      ├─→ uvicorn.Config(app, host, port, ssl...)                │
│      │                                                           │
│      ├─→ config.load()                                          │
│      │                                                           │
│      └─→ Server(config).run_in_thread()                         │
│              │                                                   │
│              ▼                                                   │
│         WebServiceThread.start()                                │
│              │                                                   │
│              ▼                                                   │
│         uvicorn 运行并监听请求                                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```
