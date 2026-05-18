# GaussMaster core.py 详解

## 文件概述

**路径**: `GaussMaster/controllers/core.py`

**作用**: 定义所有 HTTP API 路由，是系统的**入口层**（Controller层）

**核心职责**:

1. 接收 HTTP 请求
2. 参数校验
3. 调用业务层（dba.py / data\_transformer）
4. 返回统一格式的响应

***

## 文件结构

```python
# 1. 导入依赖
import asyncio
import logging
from typing import List, Optional
from fastapi import UploadFile
from pydantic import BaseModel

# 2. 导入内部模块
from GaussMaster.common.http import request_mapping, standardized_api_output
from GaussMaster.common.http._service_impl import standardized_event_stream_output
from GaussMaster.multiagents.agents import dba
from GaussMaster.server.web import data_transformer

# 3. 定义 API 前缀
latest_version = 'v1'
api_prefix = '/%s/api' % latest_version  # /v1/api

# 4. 定义 Pydantic 模型（请求参数）
class Cluster(BaseModel): ...
class PlanModel(BaseModel): ...
class SearchParams(BaseModel): ...

# 5. 定义路由函数（按功能分组）
# - 智能交互
# - 集群管理
# - 诊断报告
# - LLM管理
# - 知识库管理
# - 数据源管理
# - 反馈
```

***

## 核心装饰器详解

### 1. @request\_mapping - 路由注册

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
def intelligent_interaction_chat(query: PlanModel):
    ...
```

| 参数       | 说明      | 示例                                    |
| -------- | ------- | ------------------------------------- |
| `rule`   | URL路径   | `/v1/api/app/intelligent-interaction` |
| `method` | HTTP方法  | `GET` / `POST` / `PUT` / `DELETE`     |
| `api`    | 是否API接口 | `True`（用于权限控制）                        |

**实际效果**:

```
POST http://localhost:8080/v1/api/app/intelligent-interaction
→ 调用 intelligent_interaction_chat() 函数
```

***

### 2. @standardized\_api\_output - 统一JSON响应

```python
@standardized_api_output
def get_clusters():
    return retrieve_clusters_status()
    # 自动包装为: {"success": true, "data": {...}}
```

**响应格式**:

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

***

### 3. @standardized\_event\_stream\_output - 流式响应（SSE）

```python
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    ...
    # 流式返回，适合LLM输出
```

**SSE格式**:

```
data: {"success": true, "data": "GaussMaster是..."}
data: {"success": true, "data": "一款数据库运维工具"}
data: {"success": true, "data": "[DONE]"}
```

**适用场景**: LLM流式输出、长文本生成

***

### 4. @ParameterChecker.define\_rules - 参数校验

```python
@ParameterChecker.define_rules(
    query=ParameterChecker.QUERY_MODEL,
    user_id=ParameterChecker.NAME,
    session_id=ParameterChecker.NAME
)
def intelligent_interaction_chat(query: PlanModel):
    ...
```

**校验规则**:

| 规则              | 说明     |
| --------------- | ------ |
| `QUERY_MODEL`   | 查询模型校验 |
| `NAME`          | 名称格式校验 |
| `CLUSTER_MODEL` | 集群模型校验 |
| `STRING`        | 字符串校验  |
| `INT32`         | 整数校验   |
| `TIMESTAMP`     | 时间戳校验  |

***

### 5. @switch\_llm\_context\_decorator - LLM上下文切换

```python
@switch_llm_context_decorator
def intelligent_interaction_chat(query: PlanModel):
    plan_model.update({'model_name': current_llm.get()})
    ...
```

**作用**: 切换当前线程的LLM上下文

***

## 路由分类详解

### 一、智能交互（核心）

#### 1. /app/intelligent-interaction - 智能交互

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output  # 流式输出
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
@switch_llm_context_decorator
def intelligent_interaction_chat(query: PlanModel):
    """
    智能交互入口
    
    请求参数:
    {
        "query": "帮我查看数据库状态",      # 用户问题
        "user_id": "user1",               # 用户ID
        "session_id": "sess1",            # 会话ID
        "mode": "tool_interaction",       # 交互模式
        "history_len": 1                  # 历史长度
    }
    
    调用链:
    core.py → dba.interact() → DBA.interaction() → DBA.interact_with_tool()
    """
    plan_model = dict(query)
    plan_model.update({'model_name': current_llm.get()})
    return dba.interact(**plan_model)  # ← 调用Agent
```

**这是最重要的接口！** 所有智能对话都走这里。

***

#### 2. /ask\_gauss - 智能问答

```python
@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    """
    智能问答（带RAG检索）
    
    请求参数:
    {
        "question": "如何优化慢SQL？",
        "user_id": "user1",
        "session_id": "sess1",
        "vector_topk": 6,       # 向量检索Top-K
        "text_topk": 6,         # 文本检索Top-K
        "rerank_topk": 3,       # 重排序Top-K
        "kb_id": 0,             # 知识库ID
        "model_name": "pangu_cloud...",
        "lang": "zh",
        "history_len": 1
    }
    """
    return data_transformer.ask_gauss(...)  # ← 走data_transformer
```

**与 intelligent-interaction 的区别**:

| 接口                             | 调用方式                           | 特点             |
| ------------------------------ | ------------------------------ | -------------- |
| `/app/intelligent-interaction` | `dba.interact()`               | 直接调用Agent，工具交互 |
| `/ask_gauss`                   | `data_transformer.ask_gauss()` | 带RAG检索，知识库问答   |

***

### 二、集群管理

#### 3. /clusters - 获取集群列表

```python
@request_mapping(api_prefix + "/clusters", method='GET', api=True)
@standardized_api_output
def get_clusters():
    """获取所有托管的集群状态"""
    return retrieve_clusters_status()
```

#### 4. /clusters - 更新会话集群

```python
@request_mapping(api_prefix + "/clusters", method='PUT', api=True)
@standardized_api_output
def put_clusters(user_id, session_id, instance):
    """为指定会话设置默认集群"""
    return update_session_cluster(user_id, session_id, instance)
```

#### 5. /clusters/register - 注册集群

```python
@request_mapping(api_prefix + "/clusters/register", method='POST', api=True)
@standardized_api_output
def register_cluster(cluster: Cluster):
    """
    注册新的openGauss集群
    
    请求参数:
    {
        "cluster_name": "prod_db",
        "host": "192.168.1.100",
        "port": 5432,
        "username": "dbadmin",
        "password": "****"
    }
    """
    return data_transformer.register_cluster(cluster)
```

***

### 三、诊断报告

#### 6. /summary/report/list - 报告列表

```python
@request_mapping(api_prefix + "/summary/report/list", method='GET', api=True)
async def diagnose_list(instances, current=1, pagesize=20, user_id=None, ...):
    """获取历史诊断报告列表（分页）"""
    return await get_history_report(current, pagesize, user_id, **kwargs)
```

#### 7. /summary/report/content - 报告内容

```python
@request_mapping(api_prefix + "/summary/report/content", method='GET', api=True)
async def diagnose_report(report_id):
    """获取指定报告的详细内容"""
    return await diagnostic_replay(report_id)
```

***

### 四、LLM管理

#### 8. /llms - 获取可用模型

```python
@request_mapping(api_prefix + "/llms", method='GET', api=True)
def get_llms():
    """获取所有可用的LLM列表"""
    return get_all_models()
    # 返回: ["pangu", "chatglm", "llama", "baichuan", ...]
```

#### 9. /llms - 切换模型

```python
@request_mapping(api_prefix + "/llms", method='PUT', api=True)
def set_user_session_llm(name, user_id, session_id):
    """为指定用户会话切换LLM模型"""
    return switch_llm(name, user_id, session_id)
```

***

### 五、知识库管理

#### 10. /serve/knowledge\_base/add - 添加知识库

```python
@request_mapping(api_prefix + "/serve/knowledge_base/add", method='POST', api=True)
async def add_knowledge_base(name, user_id, file, kb_type='QA', ...):
    """
    上传文档创建知识库
    
    支持文件: PDF, Word, Markdown, TXT
    会自动: 解析 → 分块 → 向量化 → 存入向量数据库
    """
    return await data_transformer.add_knowledge(...)
```

#### 11. /serve/knowledge\_base/update - 更新知识库

```python
@request_mapping(api_prefix + "/serve/knowledge_base/update", method='PUT', api=True)
def update_knowledge_base(kl_update_params: KLUpdateParams):
    """更新知识库信息"""
    return data_transformer.update_knowledge(...)
```

#### 12. /serve/knowledge\_base/get - 获取知识库

```python
@request_mapping(api_prefix + "/serve/knowledge_base/get", method='GET', api=True)
def get_knowledge_base(kb_id: int, user_id: str):
    """获取知识库详细信息"""
    return data_transformer.get_knowledge_info(kb_id, user_id)
```

#### 13. /serve/knowledge\_base/delete - 删除知识库

```python
@request_mapping(api_prefix + "/serve/knowledge_base/delete", method='DELETE', api=True)
def delete_knowledge_base(kb_id: int, user_id: str):
    """删除知识库"""
    return data_transformer.delete_knowledge(kb_id, user_id)
```

#### 14. /serve/knowledge\_base/list - 知识库列表

```python
@request_mapping(api_prefix + "/serve/knowledge_base/list", method='GET', api=True)
def list_knowledge_base(user_id: str):
    """获取用户的所有知识库"""
    return data_transformer.list_knowledge(user_id)
```

***

### 六、数据源管理

类似知识库管理，管理数据源（文档集合）

- `add_datasource` - 添加数据源
- `update_datasource` - 更新数据源
- `get_datasource` - 获取数据源
- `delete_datasource` - 删除数据源
- `list_datasource` - 数据源列表

***

### 七、反馈系统

#### 15. /feedback/like - 点赞

```python
@request_mapping(api_prefix + "/feedback/like", method='POST', api=True)
def like(answer_id: str):
    """对回答点赞"""
    return data_transformer.update_like_info(answer_id)
```

#### 16. /feedback/hate - 点踩

```python
@request_mapping(api_prefix + "/feedback/hate", method='POST', api=True)
def hate(answer_id: str):
    """对回答点踩"""
    return data_transformer.update_hate_info(answer_id)
```

#### 17. /feedback - 提交反馈

```python
@request_mapping(api_prefix + "/feedback", method='POST', api=True)
def feedback(answer_id: str, feedback_info: str):
    """提交文字反馈"""
    return data_transformer.update_feedback_info(answer_id, feedback_info)
```

#### 18. /feedback/report - 举报

```python
@request_mapping(api_prefix + "/feedback/report", method='POST', api=True)
def report(answer_id: str, report_type: str, report_info: str):
    """举报不当内容"""
    return data_transformer.update_report_info(answer_id, report_type, report_info)
```

***

## Pydantic 模型定义

### Cluster - 集群模型

```python
class Cluster(BaseModel):
    cluster_name: str    # 集群名称
    host: str           # 主机地址
    port: int           # 端口
    username: str       # 用户名
    password: str       # 密码
```

### PlanModel - 交互计划模型

```python
class PlanModel(BaseModel):
    query: str          # 用户问题
    user_id: str        # 用户ID
    session_id: str     # 会话ID
    mode: str           # 交互模式
    history_len: int = 1  # 历史长度（默认1）
```

### SearchParams - 搜索参数模型

```python
class SearchParams(BaseModel):
    question: str           # 问题
    user_id: str            # 用户ID
    session_id: str         # 会话ID
    switch: bool = True     # 是否切换上下文
    vector_topk: int = 6    # 向量检索Top-K
    text_topk: int = 6      # 文本检索Top-K
    rerank_topk: int = 3    # 重排序Top-K
    kb_id: int = 0          # 知识库ID
    version: str = None     # 版本
    model_name: str = "pangu_cloud_sigma_unify_plugin_38b"  # 模型名
    lang: str = "zh"        # 语言
    history_len: int = 1    # 历史长度
    model_config: dict = {} # 模型配置
    search_res: List[Optional[dict]] = []  # 搜索结果
    question_id: str = None  # 问题ID
```

***

## 调用链总结

### 核心调用链

```
用户HTTP请求
    ↓
FastAPI路由匹配
    ↓
core.py 路由函数
    ↓
    ├──→ dba.()              # 智能交互
    │       ↓
    │   DBA.interaction()
    │       ↓
    │   DBA.interact_with_tool()
    │       ↓
    │   executor.py (5步流程)
    │
    ├──→ data_transformer.ask_gauss() # 智能问答
    │       ↓
    │   RAG检索 + LLM生成
    │
    └──→ data_transformer.xxx()       # 其他功能
```

### 两种调用方式对比

| 方式            | 接口                       | 适用场景        |
| ------------- | ------------------------ | ----------- |
| **直接调用Agent** | `dba.interact()`         | 工具交互、多轮对话   |
| **走数据转换层**    | `data_transformer.xxx()` | RAG问答、知识库管理 |

***

## 面试重点

### Q1: core.py 的作用是什么？

```
答：core.py 是系统的Controller层，负责：
1. 定义HTTP API路由（@request_mapping）
2. 参数校验（@ParameterChecker）
3. 调用业务层（dba.py / data_transformer）
4. 统一响应格式（@standardized_api_output / @standardized_event_stream_output）
```

### Q2: 为什么有的接口用 dba.interact()，有的用 data\_transformer？

```
答：
- dba.interact()：直接调用Agent，适合工具交互、多轮对话
- data_transformer.xxx()：走数据转换层，适合RAG检索、知识库管理

intelligent-interaction 用 dba.interact() 因为需要工具调用
ask_gauss 用 data_transformer 因为需要RAG检索
```

### Q3: 流式输出和普通JSON响应的区别？

```
答：
- 普通JSON：@standardized_api_output，一次性返回完整结果
- 流式SSE：@standardized_event_stream_output，适合LLM生成，逐字返回

流式输出使用 generator yield，前端可以实时显示
```

***

## 一句话总结

```
core.py = HTTP路由层 = API大门
    ↓
接收请求 → 参数校验 → 调用业务层 → 统一响应
    ↓
核心接口：/app/intelligent-interaction（智能交互）
         /ask_gauss（智能问答）
         /clusters/*（集群管理）
         /llms（模型管理）
         /serve/knowledge_base/*（知识库管理）
```

***

*本文档基于 openGauss-GaussMaster v1.0.0*
