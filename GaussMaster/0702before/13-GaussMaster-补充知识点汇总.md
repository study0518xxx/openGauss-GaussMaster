# GaussMaster 补充知识点汇总

## 目录

- [search_vector 返回结果详解](#search_vector-返回结果详解)
- [向量检索与文本检索去重原理](#向量检索与文本检索去重原理)
- [设计模式详解汇总](#设计模式详解汇总)
- [面试问答补充](#面试问答补充)

---

## search_vector 返回结果详解

### 返回格式

`search_vector` 返回的是一个 **列表，每个元素是一个元组（Tuple）**，代表一条数据库记录。

```python
# 返回结果示例
[
    ('uuid_1', 'title_1', 'content_1', 'source_1', 'v1.0', ..., [0.023, ...]),  # 文档1
    ('uuid_2', 'title_2', 'content_2', 'source_2', 'v1.0', ..., [0.015, ...]),  # 文档2
    ('uuid_3', 'title_3', 'content_3', 'source_3', 'v1.0', ..., [0.031, ...]),  # 文档3
]
```

### 字段说明

假设表结构：

```sql
CREATE TABLE knowledge_base (
    uuid TEXT,        -- 0: 唯一ID
    title TEXT,       -- 1: 标题
    text TEXT,        -- 2: 内容
    source TEXT,      -- 3: 来源
    version TEXT,     -- 4: 版本
    prev_uuid TEXT,   -- 5: 上一段UUID
    next_uuid TEXT,   -- 6: 下一段UUID
    text_vector VECTOR(1024)  -- 7: 向量
);
```

| 索引 | 字段名 | 示例值 | 说明 |
|------|--------|--------|------|
| 0 | uuid | `'doc-001'` | 文档唯一标识 |
| 1 | title | `'数据库性能优化指南'` | 文档标题 |
| 2 | text | `'优化数据库性能的方法包括...'` | 文档内容 |
| 3 | source | `'official-docs.pdf'` | 来源文件 |
| 4 | version | `'v1.0'` | 版本号 |
| 5 | prev_uuid | `'doc-000'` | 上一段（可选）|
| 6 | next_uuid | `'doc-002'` | 下一段（可选）|
| 7 | text_vector | `[0.023, -0.156, ...]` | 1024维向量 |

---

## 向量检索与文本检索去重原理

### 关键：查询的是同一张表

```
┌─────────────────────────────────────────────────────────────┐
│                     知识库表结构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   表名: knowledge_base                                      │
│                                                             │
│   ┌─────────┬─────────┬─────────┬─────────┬──────────┐     │
│   │  uuid   │  title  │  text   │  source │ text_vector│    │
│   ├─────────┼─────────┼─────────┼─────────┼──────────┤     │
│   │ doc-001 │ 标题1   │ 内容1   │ 来源1   │ [向量1]   │     │
│   │ doc-002 │ 标题2   │ 内容2   │ 来源2   │ [向量2]   │     │
│   │ doc-003 │ 标题3   │ 内容3   │ 来源3   │ [向量3]   │     │
│   └─────────┴─────────┴─────────┴─────────┴──────────┘     │
│                                                             │
│   同一行数据，既有文本内容，也有对应的向量！                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 去重代码

```python
# retriever_util.py 第 137 行
dedup_list = list(set(vector_result + text_result))
```

### 为什么能去重？

因为 `vector_result` 和 `text_result` 中的元素是**同一类型的元组**，Python 的 `set()` 可以根据内容去重：

```python
# 示例
vector_result = [
    ('doc-001', '标题1', '内容1', ...),  # 文档1
    ('doc-002', '标题2', '内容2', ...),  # 文档2
]

text_result = [
    ('doc-002', '标题2', '内容2', ...),  # 文档2（和上面相同）
    ('doc-003', '标题3', '内容3', ...),  # 文档3
]

# 合并
combined = vector_result + text_result

# 去重
dedup_list = list(set(combined))
# [
#     ('doc-001', '标题1', '内容1', ...),
#     ('doc-002', '标题2', '内容2', ...),  # 重复的 doc-002 被去掉了
#     ('doc-003', '标题3', '内容3', ...),
# ]
```

---

## 设计模式详解汇总

### 1. 装饰器模式 (Decorator Pattern)

**定义**：在不改变原函数代码的情况下，动态地给函数添加额外功能。

**项目应用**：

```python
# 基础函数（原味奶茶）
def intelligent_interaction_chat(query):
    return dba.interact(**query)

# 加装饰：路由注册（加珍珠）
@request_mapping("/v1/api/app/intelligent-interaction", method='POST')
def intelligent_interaction_chat(query):
    return dba.interact(**query)

# 再加装饰：参数校验（加椰果）
@request_mapping("/v1/api/app/intelligent-interaction", method='POST')
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
def intelligent_interaction_chat(query):
    return dba.interact(**query)

# 再加装饰：流式输出（加奶盖）
@request_mapping("/v1/api/app/intelligent-interaction", method='POST')
@standardized_event_stream_output
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
def intelligent_interaction_chat(query):
    return dba.interact(**query)
```

**优点**：
- 不修改原代码（符合"开闭原则"）
- 功能可组合（多个装饰器可以叠加）
- 代码复用（装饰器可以在多个函数上使用）

---

### 2. 工厂模式 (Factory Pattern)

**定义**：不直接创建对象，而是通过"工厂"来创建，把对象的创建和使用分离。

**项目应用**：

```python
# llms/dba.py
def instantiate_llm(model_name: str):
    """工厂函数：根据模型名创建对应的 LLM 实例"""
    llm_config = global_vars.llm_config
    model_params = llm_config.get('online_llm').get(model_name)
    
    model_type = model_params.get('api_type')  # "pangu" / "chatglm" / "llama"
    api_url = model_params.get('api_url')
    
    # 工厂：根据类型创建对应实例
    llm = llm_registry.get(model_type)(model_name, api_url)
    return llm

# 使用
pangu_llm = instantiate_llm("pangu_cloud_sigma_unify_plugin_38b")
chatglm_llm = instantiate_llm("chatglm3-6b")
```

**优点**：
- 解耦（创建逻辑和使用逻辑分离）
- 易扩展（加新类型只需改工厂，不用改使用方）
- 统一管理（可以在工厂里加日志、校验等）

---

### 3. 注册表模式 (Registry Pattern)

**定义**：用一个中心化的"注册表"来管理对象，需要时从注册表里查找。

**项目应用**：

```python
# multiagents/tools/__init__.py
from GaussMaster.common.plugins.registry import Registry

base_tools = Registry()  # 创建注册表

# dbmind_interface.py
@base_tools(
    name="summary_alarms",           # 键
    description="获取告警信息",
    params=[...]
)
def summary_alarms(start_time, end_time):
    ...                             # 值（函数）

# 使用：从注册表查找工具
tool_func = base_tools.get("summary_alarms")  # 获取函数
tool_func(start_time="2024-01-01", end_time="2024-01-02")  # 调用
```

**优点**：
- 动态管理（运行时注册和查找）
- 解耦（使用方不需要知道具体实现）
- 可扩展（新工具自动注册，无需修改使用方）

---

### 4. 策略模式 (Strategy Pattern)

**定义**：定义一系列算法，把它们封装起来，并且使它们可以互相替换。

**项目应用**：

```python
# llms/llm_base.py
class BaseLLM(ABC):
    """策略基类：定义统一接口"""
    
    @abstractmethod
    async def invoke(self, messages):
        """所有LLM都必须实现这个方法"""
        pass

# llms/pangu_llm.py
class PanguLLM(BaseLLM):
    """策略1：盘古模型"""
    async def invoke(self, messages):
        response = await call_pangu_api(messages)
        return response

# llms/chatglm_llm.py
class ChatGLMLLM(BaseLLM):
    """策略2：ChatGLM模型"""
    async def invoke(self, messages):
        response = await call_chatglm_api(messages)
        return response

# 使用：统一调用，不同实现
async def call_llm(llm: BaseLLM, messages):
    return await llm.invoke(messages)

# 可以灵活切换策略
pangu = PanguLLM("pangu-38b", "https://pangu.com")
chatglm = ChatGLMLLM("chatglm3-6b", "https://chatglm.com")

result1 = await call_llm(pangu, messages)      # 用盘古
result2 = await call_llm(chatglm, messages)    # 用ChatGLM
```

**优点**：
- 消除if-else（代码更简洁）
- 易于扩展（加新策略只需加类，不用改调用方）
- 可替换（运行时动态切换算法）

---

### 5. 代理模式 (Proxy Pattern)

**定义**：为其他对象提供一个代理，以控制对这个对象的访问。

**项目应用**：

```python
# common/http/_service_impl.py
class HttpService:
    """代理模式：封装 FastAPI，对外提供统一接口"""
    
    def __init__(self, name=__name__):
        # 真实对象：FastAPI
        self.app = FastAPI(title=name)
    
    def attach(self, func, rule, method, **options):
        """代理方法：将路由附加到真实对象"""
        self.app.add_api_route(rule, func, methods=[method])
    
    def start_listen(self, host, port, **ssl_options):
        """代理方法：启动真实服务"""
        config = uvicorn.Config(self.app, host=host, port=port)
        server = uvicorn.Server(config)
        server.run()

# 使用：通过代理操作，不直接操作 FastAPI
service = HttpService("GaussMaster")
service.attach(get_clusters, "/v1/api/clusters", "GET")
service.start_listen("0.0.0.0", 8080)
```

**优点**：
- 解耦（业务代码不依赖具体框架）
- 可替换（可以换 Flask/Django 而不用改业务代码）
- 增强功能（可以在代理里加日志、权限控制等）

---

## 面试问答补充

### Q: embedding_function 是什么？

**A**: `embedding_function` 不是具体的函数，而是一个**实现了 `BaseEmbedding` 接口的对象**（如 `OnlineEmbedding` 实例）。它封装了文本向量化的能力，通过**依赖注入**的方式传入 `GaussDB`，让数据库操作和向量化逻辑解耦。

**调用链**：
```
BaseEmbedding (接口)
    ↓
OnlineEmbedding (实现类)
    ↓
global_vars.embedding_model (全局实例)
    ↓
GaussDB(embedding_function, ...) (注入)
    ↓
self.embedding_function.query_embedding(query) (使用)
```

---

### Q: 向量检索查询的是哪个数据库？

**A**: 查询的是**支持向量存储和相似度计算的数据库**：

| 数据库类型 | 说明 | 向量支持 |
|-----------|------|---------|
| **openGauss** | 华为开源数据库 | ✅ 通过 `gsdiskann` 扩展 |
| **PostgreSQL** | 开源关系型数据库 | ✅ 通过 `pgvector` 扩展 |
| **GaussDB** | 华为云数据库 | ✅ 原生支持 |
| **SQLite** | 轻量级数据库 | ❌ 不支持向量（只存元数据）|

**表结构**：
```sql
CREATE TABLE knowledge_base (
    uuid TEXT PRIMARY KEY,
    title TEXT,
    text TEXT,
    source TEXT,
    version TEXT,
    text_vector VECTOR(1024),  -- 向量字段
    ...
);
```

---

### Q: reranker_scores 和 reranker_result 分别代表什么？

**A**: 

| 变量 | 类型 | 含义 |
|------|------|------|
| `reranker_scores` | `List[float]` | 每个文档的相关性分数（0-1之间） |
| `reranker_result` | `List[Tuple]` | 排序后的文档列表 |

**示例**：
```python
# 假设检索到5个文档
sorted_scores = [0.95, 0.88, 0.76, 0.43, -0.12]
sorted_answer_list = [doc_A, doc_B, doc_C, doc_D, doc_E]

# 过滤负分后
res_score_list = [0.95, 0.88, 0.76, 0.43]  # doc_E 被过滤
res_ans_list = [doc_A, doc_B, doc_C, doc_D]

# 取 topk=3
reranker_scores = [0.95, 0.88, 0.76]
reranker_result = [doc_A, doc_B, doc_C]
```

**分数含义**：
| 分数范围 | 含义 |
|---------|------|
| 0.9 - 1.0 | 高度相关 |
| 0.7 - 0.9 | 比较相关 |
| 0.5 - 0.7 | 一般相关 |
| 0.3 - 0.5 | 弱相关 |
| < 0.3 | 可能不相关 |
| < 0 | 被过滤掉 |

---

## 一句话总结

> **search_vector** 返回元组列表（包含 uuid、title、text、source、向量等），向量和文本能去重是因为查询的是**同一张表**，返回的是**相同格式的元组**。项目中使用了**装饰器、工厂、注册表、策略、代理**5种设计模式，让代码更灵活、易扩展！
