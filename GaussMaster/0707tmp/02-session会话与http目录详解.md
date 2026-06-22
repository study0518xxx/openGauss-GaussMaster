# Session 会话与 HTTP 目录详解

## 一、Session 会话管理

### 1.1 什么是 Session？

在 GaussMaster 中，**Session = 一次独立的对话上下文**。每次用户打开聊天窗口，就会产生一个新的 session\_id。

### 1.2 Session 的数据结构

```python
# global_vars.py
SESSION_QA_HISTORY = {}          # {user_id: {session_id: [qa记录]}}
SESSION_TOOL_HISTORY = defaultdict(dict)  # {user_id: {session_id: 工具名}}
user_session_instance = defaultdict(dict) # {user_id: {session_id: 数据库实例}}
user_session_llm = defaultdict(dict)      # {user_id: {session_id: LLM模型}}
```

### 1.3 Session 的生命周期

```
用户打开聊天窗口
    │
    ▼
生成 session_id (UUID)
    │
    ▼
┌─────────────────────────────────────────┐
│ 新 Session 初始化                        │
│ • user_session_instance[user][session]  │
│ • user_session_llm[user][session]       │
│ • SESSION_QA_HISTORY[user][session] = []│
│ • SESSION_TOOL_HISTORY[user][session] = None│
└─────────────────────────────────────────┘
    │
    ▼
多轮对话（保持同一个 session_id）
    │
    ▼
用户关闭窗口 / 超时
    │
    ▼
内存中的 Session 数据保留（直到进程重启）
但长期记忆已存入数据库
```

### 1.4 为什么需要 Session？

| 场景            | 没有 Session | 有 Session      |
| ------------- | ---------- | -------------- |
| 用户A问"查看慢SQL"  | 系统匹配工具     | 系统匹配工具         |
| 用户A说"昨天的"     | 系统不知道在说什么  | 系统知道在补充慢SQL的参数 |
| 用户B同时问"查看CPU" | 和用户A混淆     | 完全隔离，互不影响      |

**核心作用**：隔离不同用户的对话上下文，保持多轮对话的连续性。

***

## 二、HTTP 目录详解

### 2.1 目录结构

```
common/http/
├── __init__.py
├── _service_impl.py      # HTTP服务封装（FastAPI）
├── dbmind_request.py     # DBMind接口请求
├── requests_utils.py     # HTTP请求工具
└── ssl.py                # SSL配置
```

### 2.2 \_service\_impl.py - HTTP服务封装

**设计目标**：解耦 Web 框架和业务接口，方便从 Flask 迁移到 FastAPI。

```python
class HttpService:
    def __init__(self, name=__name__):
        self.app = FastAPI(title=name, openapi_url=None, docs_url=None, redoc_url=None)
```

**核心功能**：

#### ① 路由注册

```python
def request_mapping(rule, method, **kwargs):
    """装饰器：将函数注册到路由表"""
    def decorator(f):
        _RequestMappingTable[(rule, method)] = (f, kwargs)
        return f
    return decorator

# 使用示例（controllers/core.py）
@request_mapping('/ask_gauss', methods=['POST'], api=True)
async def ask_gauss(...):
    ...
```

#### ② 统一响应格式

```python
def standardized_api_output(f):
    """统一API响应格式：{success: True/False, data: ...}"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            data = await f(*args, **kwargs)
            return JSONResponse(content={'success': True, 'data': data})
        except Exception as e:
            return JSONResponse(content={'success': False, 'msg': 'Internal server error.'})
    return wrapper
```

#### ③ SSE 流式输出

```python
def standardized_event_stream_output(f):
    """Server-Sent Events 流式输出"""
    async def wrapper(*args, **kwargs):
        generator = f(*args, **kwargs)
        
        async def standardize_generator():
            async for item in generator:
                yield f"data:{json.dumps({'success': True, 'data': item})}\n\n"
        
        return StreamingResponse(standardize_generator(), media_type="text/event-stream")
    return wrapper
```

**为什么用 SSE？**

- LLM 生成是流式的，需要逐字返回给用户
- SSE 比 WebSocket 简单，适合单向推送
- HTTP/1.1 兼容性好

#### ④ 语言中间件

```python
@app.middleware("http")
async def set_language_middleware(request: Request, call_next):
    accept_language = request.headers.get('Accept-Language', global_vars.LANGUAGE)
    global_vars.LANGUAGE = parse_accept_language(accept_language)
    response = await call_next(request)
    return response
```

**作用**：根据请求头自动切换中英文。

***

### 2.3 dbmind\_request.py - DBMind 接口请求

**DBMind = openGauss 的数据库运维平台**，GaussMaster 通过 REST API 调用 DBMind。

```python
class AutoSession(requests.Session):
    """自动管理认证和重试的 Session"""
    
    instance_session_pairs = dict()  # 单例池
    
    def request(self, method, url, **kwargs):
        if not self.token:
            self.login()  # 懒加载登录
        response = super().request(method, url, **kwargs)
        
        if response.status_code == 401:
            self.login()  # Token过期，重新登录
            response = super().request(method, url, **kwargs)
        
        return response
```

**核心机制**：

- **单例 Session**：每个 DBMind 实例复用一个 Session
- **懒加载登录**：首次请求时才认证
- **自动重试**：401 时自动刷新 Token

***

### 2.4 requests\_utils.py - HTTP 请求工具

```python
MAX_REQUEST_RETRIES = 3          # 最大重试次数
RETRY_BACKOFF_FACTOR = 1         # 退避因子
RETRY_ON_STATUS = [408, 429, 500, 502, 503, 504]  # 需要重试的状态码

def create_requests_session():
    """创建带重试策略的 Session"""
    retry_strategy = Retry(
        total=MAX_REQUEST_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_ON_STATUS
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
```

***

### 2.5 ssl.py - SSL 配置

```python
class SSLContext:
    def __init__(self, cert, key, ca=None, key_pwd=None):
        self.ssl_certfile = cert
        self.ssl_keyfile = key
        self.ssl_ca_file = ca
        self.ssl_keyfile_password = key_pwd

def configure_psycopg2_ssl():
    """配置 psycopg2 的 SSL 连接"""
    if ssl_enabled:
        psycopg2.connect = functools.partial(
            psycopg2.connect,
            sslmode='verify-ca',
            sslcert=cert_file,
            sslkey=key_file,
            sslrootcert=ca_file
        )
```

***

## 三、Session 与 HTTP 的关系

```
用户浏览器
    │ HTTP POST /ask_gauss
    │ {user_id: "u1", session_id: "s1", question: "查看慢SQL"}
    ▼
┌─────────────────────────────────────────┐
│ FastAPI (HttpService)                   │
│ • 路由匹配 /ask_gauss                   │
│ • 语言中间件设置 LANGUAGE               │
│ • standardized_event_stream_output      │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ controllers/core.py                     │
│ • 参数校验                              │
│ • 调用 data_transformer.ask_gauss()     │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ context_manager.py                      │
│ • set_current_instance(u1, s1)          │
│ • switch_to_user_session_llm_context()  │
│ • 设置当前数据库实例和LLM模型            │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ dba.py                                  │
│ • 读取 SESSION_TOOL_HISTORY[u1][s1]     │
│ • 读取 SESSION_QA_HISTORY[u1][s1]       │
│ • 执行 Agent 逻辑                       │
└─────────────────────────────────────────┘
```

***

## 四、面试要点

1. **Session 怎么保证多用户隔离？**
   - 通过 `user_id + session_id` 两级 key
   - 内存字典隔离，不同用户完全独立
2. **为什么用 SSE 而不是 WebSocket？**
   - SSE 是单向推送，实现简单
   - LLM 生成是服务端→客户端的单向流
   - 不需要客户端主动发送消息
3. **HttpService 的设计模式？**
   - 适配器模式：解耦业务代码和 Web 框架
   - 装饰器模式：统一响应格式、流式输出
   - 单例模式：DBMind Session 复用
4. **DBMind 接口的认证机制？**
   - 首次请求懒加载登录
   - Token 过期自动刷新
   - 单例 Session 减少认证开销

