# HTTP 服务封装详解

## 1. 概述

这段代码展示了一个 **HTTP 服务封装** 的实现，主要用于统一 API 响应格式。

**核心文件：** `common/http_service_impl.py`

---

## 2. 核心概念：装饰器 (Decorator)

### 什么是装饰器？

装饰器是 Python 中的一种特殊函数，可以在不修改原函数代码的情况下，为函数添加额外功能。

**简单比喻：**
- 原函数 = 一杯白开水
- 装饰器 = 给白开水加糖、加柠檬
- 装饰后的函数 = 一杯柠檬水

### 装饰器的工作原理

```python
@装饰器
def 原函数():
    pass
```

等价于：

```python
原函数 = 装饰器(原函数)
```

---

## 3. 代码逐行解析

### 3.1 导入 `@wraps`

```python
from functools import wraps
```

`@wraps` 的作用是保留原函数的元信息（如函数名、文档字符串等），避免装饰后函数信息丢失。

---

### 3.2 装饰器函数定义

```python
def standardized_api_output(f):
```

这是一个装饰器函数，接收一个函数 `f` 作为参数。

---

### 3.3 保留函数元信息

```python
@wraps(f)
```

这行确保装饰后的函数仍然保留原函数的名称和文档。

---

### 3.4 包装函数

```python
def wrapper(*args, **kwargs):
```

`wrapper` 是实际替代原函数的新函数：
- `*args`：接收任意数量的位置参数
- `**kwargs`：接收任意数量的关键字参数

---

### 3.5 异常处理

```python
try:
    data = f(*args, **kwargs)
    # 成功时返回
    return JsonResponse(content={'success': True, 'data': data})
except Exception as e:
    # 失败时返回错误信息
    return JsonResponse(content={'success': False, 'msg': str(e)})
```

**执行流程：**
1. 调用原函数 `f`，获取返回数据 `data`
2. 如果成功，返回统一的 JSON 格式：`{'success': True, 'data': 数据}`
3. 如果发生异常，捕获异常并返回：`{'success': False, 'msg': 错误信息}`

---

### 3.6 返回包装函数

```python
return wrapper
```

装饰器最终返回 `wrapper` 函数，替代原函数。

---

## 4. 使用示例

```python
@request_mapping("/api/ask_gauss", method='POST')
@standardized_api_output
def ask_gauss(params):
    return data_transformer.ask_gauss(...)
```

### 多个装饰器的执行顺序

当有多个装饰器时，**从下往上** 依次执行：

1. `@standardized_api_output` 先包装 `ask_gauss`
2. `@request_mapping` 再包装上一步的结果

### 调用流程

```
用户请求 → @request_mapping → @standardized_api_output → ask_gauss() → 返回统一JSON
```

---

## 5. 统一响应格式

### 成功响应

```json
{
    "success": true,
    "data": { ... }
}
```

### 失败响应

```json
{
    "success": false,
    "msg": "错误信息"
}
```

### 为什么要统一格式？

| 优点 | 说明 |
|------|------|
| 前端处理简单 | 前端只需要判断 `success` 字段即可 |
| 错误处理一致 | 所有接口错误都使用相同格式 |
| 便于调试 | 统一的错误信息格式，方便日志分析 |
| 可扩展性 | 后续可以轻松添加新字段（如 `code`、`timestamp`） |

---

## 6. 完整代码

```python
from functools import wraps

# 统一JSON响应格式
def standardized_api_output(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            data = f(*args, **kwargs)
            # 统一包装 {success: true, data: xxx}
            return JsonResponse(content={'success': True, 'data': data})
        except Exception as e:
            return JsonResponse(content={'success': False, 'msg': str(e)})
    return wrapper

# 使用示例
@request_mapping("/api/ask_gauss", method='POST')
@standardized_api_output
def ask_gauss(params):
    return data_transformer.ask_gauss(...)
```

---

## 7. 总结

| 概念 | 说明 |
|------|------|
| 装饰器 | 在不修改原函数的情况下，添加额外功能 |
| `@wraps` | 保留原函数的元信息 |
| `*args, **kwargs` | 接收任意参数，保持函数通用性 |
| try-except | 捕获异常，统一错误处理 |
| JsonResponse | 返回标准化的 JSON 响应 |

这个封装模式在实际开发中非常常见，可以让你的 API 接口更加规范和易于维护。
