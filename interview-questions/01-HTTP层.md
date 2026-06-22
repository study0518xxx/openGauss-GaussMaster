# HTTP 通信层面试题

## 一、基础问题

### Q1: 你们项目的 Web 服务用的什么框架？为什么选择它？

**回答要点**：
- 用的是 **FastAPI**，但做了**一层抽象封装**（`HttpService` 类）
- 选择 FastAPI 的原因：
  - 原生支持异步（`async/await`），性能比 Flask 好，适合 IO 密集型场景
  - 自动数据校验（Pydantic），减少手写校验代码
  - 内置 OpenAPI 文档生成，方便前后端对接
- 通过 `HttpService` 封装，路由注册走自定义装饰器，解耦框架和业务代码，方便后续迁移

---

### Q2: 你们的 API 路由是怎么注册的？和普通 FastAPI 有什么区别？

**回答要点**：
- 使用**装饰器模式 + 全局映射表**：
  ```python
  _RequestMappingTable = dict()

  def request_mapping(rule, method, **kwargs):
      def decorator(f):
          _RequestMappingTable[(rule, method)] = (f, kwargs)
          return f
      return decorator
  ```
- 使用方式：`@request_mapping('/v1/api/ask_gauss', method='POST', api=True)`
- 区别：
  - FastAPI 是启动时直接绑定路由（`@app.post(...)`）
  - 我们是先记录到全局字典，在 `HttpService.start_listen()` 启动时**批量注册**
  - 好处是**解耦**：Controller 模块不需要依赖 FastAPI 实例，可以独立定义和测试

---

### Q3: 普通接口和流式接口的响应格式有什么区别？

**回答要点**：
- 定义了两种装饰器：
  - **普通接口** — `standardized_api_output`：返回 `JSONResponse`
    ```json
    {"success": true, "data": "..."}
    {"success": false, "msg": "Internal server error."}
    ```
  - **流式接口** — `standardized_event_stream_output`：返回 `StreamingResponse`
    ```text
    data:{"success":true,"data":{"type":"progress","data":"检索中..."}}
    data:{"success":true,"data":{"type":"answer","data":"GaussDB是..."}}
    data:{"success":true,"data":{"type":"complete","data":{"time":1.234}}}
    ```

---

## 二、进阶问题

### Q4: SSE 流式输出是怎么实现的？详细讲讲数据流转。

**回答要点**（四层流转）：

1. **LLM 服务层**：请求带 `Accept: text/event-stream` 头，LLM 以 SSE 格式逐 chunk 返回

2. **HTTP 客户端层**：
   ```python
   with session.request(..., stream=True) as response:
       for chunk in response.iter_content(decode_unicode=True):
           yield chunk
   ```

3. **生成器适配层**：requests 的生成器是同步的，FastAPI 需要异步生成器，用 `run_in_executor` 包装：
   ```python
   async def generate_answer(messages, model_name):
       llm_generator = await thread_request_from_llm(url, headers, params)
       while True:
           chunk = await asyncio.get_running_loop().run_in_executor(None, iter_next, llm_generator)
           if chunk == -1:
               break
           yield chunk
   ```

4. **API 标准化层**：
   ```python
   async def standardize_generator():
       async for item in generator:
           yield f"data:{json.dumps({'success': True, 'data': item})}\n\n"
   return StreamingResponse(standardize_generator(), media_type="text/event-stream")
   ```

**关键点**：同步生成器 → 异步生成器转换、SSE 格式规范、异常处理避免流中断

---

### Q5: 为什么用 SSE 而不是 WebSocket？

**回答要点**：
1. **单向推送足够**：场景是服务器 → 客户端推送（LLM 生成结果），不需要客户端 → 服务器的实时交互
2. **基于 HTTP，更简单**：SSE 是标准 HTTP 协议，不需要额外握手、协议升级。前端用 `EventSource` 几行代码接入
3. **自动重连**：SSE 原生支持 `retry` 字段，浏览器自动重连
4. **不适用 SSE 的场景**：双向实时通信（如聊天室、多人协作），用 WebSocket 更合适

---

### Q6: 你们的 HTTP 客户端做了哪些增强？为什么不用原生的 requests？

**回答要点**：
- 封装了 `create_requests_session()` 工厂函数：

1. **自动重试**：
   ```python
   retries = Retry(total=3, connect=3, backoff_factor=1)
   ```
   只对特定状态码重试：`[408, 429, 500, 502, 503, 504]`

2. **SSL 双向认证**：
   - 自定义 `HTTPSAdaptor` 支持密钥密码（requests 原生不支持）
   - `session.mount('https://', https_adaptor)`

3. **统一 Header**：自动注入 `User-Agent`，支持 `timeout` 配置

4. **认证支持**：`session.auth = (username, password)` 基础认证

---

### Q7: `standardized_api_output` 里的 `ToleratedEncoder` 是做什么的？

**回答要点**：
- 处理 JSON 序列化中的**异常值**（NaN、Infinity）
- Python 的 `json.dumps` 默认不支持这些值，会抛 `ValueError`
- 但数据库查询结果、模型输出可能包含这些值
- `ToleratedEncoder` 将 NaN → `null`，Infinity → `"Infinity"`，未知类型 → `str(o)`

---

## 三、深挖问题

### Q8: DBMind 的 Token 自动刷新是怎么设计的？

**回答要点**：
- 封装 `AutoSession` 类，继承 `requests.Session`
- **多实例隔离**：每个 DBMind 集群实例有独立的 `AutoSession`，用 `instance_session_pairs` 缓存
- **懒加载**：首次请求时才登录，不是启动时预登录
- **自动刷新**：401 时自动重试登录，对调用方透明
- **密码加密存储**：从数据库读取的密码是密文，使用时 `Encryption.decrypt()` 解密

---

### Q9: `HttpService` 的 `start_listen` 为什么要用 `run_in_thread` 上下文管理器？

**回答要点**：
- **后台线程运行**：Web 服务不能阻塞主线程
- **优雅关闭**：`need_to_exit` 标志控制退出，`finally` 确保线程 join（最多等 5 秒），清理路由映射表
- **上下文管理器**：保证资源正确释放，Python 3.7+ 支持

---

### Q10: 如果让你优化 HTTP 层，你会怎么做？

**回答要点**：
1. **连接池优化**：目前每次请求新建 Session，改为全局 Session 池复用 TCP 连接
2. **流式性能**：`run_in_executor` 有线程切换开销，如果 LLM 客户端支持异步（如 `httpx.AsyncClient`），直接原生异步
3. **限流熔断**：增加 Rate Limiting 和 Circuit Breaker，防止某个 LLM 服务挂掉影响整体
4. **请求追踪**：增加 `X-Request-ID` 透传，方便日志串联和链路追踪

---

## 四、手写代码题

### 题目1：实现一个 SSE 流式响应装饰器

```python
from functools import wraps
import json
from fastapi.responses import StreamingResponse

def sse_response(f):
    @wraps(f)
    async def wrapper(*args, **kwargs):
        async def event_generator():
            async for item in f(*args, **kwargs):
                yield f"data:{json.dumps(item)}\n\n"
            yield "data:[DONE]\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    return wrapper
```

### 题目2：实现带重试和超时的 HTTP Session

```python
import requests
from requests.adapters import HTTPAdapter, Retry

def create_session(max_retries=3, backoff=1, timeout=10):
    session = requests.Session()
    retries = Retry(
        total=max_retries,
        backoff_factor=backoff,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session
```
