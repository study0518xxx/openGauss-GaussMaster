# GaussMaster 整体架构与主流程总览

## 1. 系统概述

GaussMaster 是一个面向 openGauss 数据库的智能运维助手系统，基于 RAG（检索增强生成）和 Agent 架构，提供数据库知识问答、故障诊断、工具调用等能力。

### 1.1 核心定位

- **数据库智能助手**：专注于 openGauss 数据库领域的知识问答和运维支持
- **多 Agent 架构**：支持工具调用、故障诊断、报告生成等多种交互模式
- **RAG 增强**：通过向量检索和文本检索结合，提供准确的知识回答
- **企业级部署**：支持 SSL/TLS、多租户、权限控制等企业级特性

### 1.2 技术栈

| 层级 | 技术选型 |
|------|----------|
| Web 框架 | FastAPI + Uvicorn |
| 向量数据库 | openGauss + pgvector 扩展 |
| 元数据库 | SQLAlchemy + PostgreSQL |
| LLM 支持 | Pangu、ChatGLM、Llama、Baichuan 等 |
| 向量化 | 在线 Embedding 服务 |
| 重排序 | 在线 Reranker 服务 |
| 配置管理 | YAML + ConfigParser |

## 2. 整体架构图

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e1f5fe', 'primaryTextColor': '#01579b', 'primaryBorderColor': '#0288d1', 'lineColor': '#0288d1', 'secondaryColor': '#fff3e0', 'tertiaryColor': '#e8f5e9'}, 'flowchart': { 'curve': 'basis', 'padding': 15 }, 'sequence': { 'mirrorActors': false, 'bottomMarginAdj': 10, 'actorFontSize': 14, 'messageFontSize': 13, 'noteFontSize': 12, 'linkSpacing': 50, 'boxTextMargin': 5, 'messageMargin': 40, 'width': 150, 'height': 65, 'boxMargin': 10, 'useMaxWidth': true }}}%%
graph TB
    Client[客户端] --> SSL[SSL/TLS]
    SSL --> HTTP[FastAPI服务]
    HTTP --> Core[Core控制器]
    Core --> DT[数据转换器]
    
    DT --> RAG[RAG引擎]
    DT --> Agent[Agent引擎]
    
    RAG --> Retriever[检索器]
    RAG --> LLM[LLM模块]
    Agent --> LLM
    Agent --> Tools[工具注册表]
    Agent --> Memory[记忆系统]
    
    Retriever --> VectorDB[(向量数据库)]
    Memory --> MetaDB[(元数据库)]
    Tools --> DBMind[DBMind平台]
    LLM --> LLMService[LLM服务]
    Retriever --> Embed[Embedding服务]
```

## 3. 核心流程总览

### 3.1 请求处理主流程

**RAG 模式流程：**

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e3f2fd', 'primaryTextColor': '#0d47a1', 'primaryBorderColor': '#1976d2'}}}%%
sequenceDiagram
    participant C as 客户端
    participant API as FastAPI
    participant DT as 数据转换器
    participant RAG as RAG引擎
    participant LLM as LLM服务
    participant DB as 向量库

    C->>API: POST /ask_gauss
    API->>DT: 调用ask_gauss()
    DT->>RAG: search()检索
    RAG->>DB: 向量检索+文本检索
    DB-->>RAG: 返回候选
    RAG->>RAG: Reranker重排
    RAG-->>DT: 返回结果
    DT->>LLM: 生成回答
    LLM-->>DT: 流式输出
    DT-->>API: 返回
    API-->>C: SSE流式输出
```

**Agent 模式流程：**

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#fff3e0', 'primaryTextColor': '#e65100', 'primaryBorderColor': '#f57c00'}}}%%
sequenceDiagram
    participant C as 客户端
    participant API as FastAPI
    participant DT as 数据转换器
    participant Agent as Agent引擎
    participant DBMind as DBMind

    C->>API: POST /intelligent
    API->>DT: 调用interact()
    DT->>Agent: interact()交互
    Agent->>Agent: 意图识别
    Agent->>DBMind: 工具调用
    DBMind-->>Agent: 返回结果
    Agent-->>DT: 处理结果
    DT-->>API: 返回
    API-->>C: SSE流式输出
```

### 3.2 系统启动流程

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f5e9', 'primaryTextColor': '#1b5e20', 'primaryBorderColor': '#388e3c'}}}%%
sequenceDiagram
    participant U as 用户
    participant M as Main进程
    participant C as 配置模块
    participant L as LLM管理器
    participant A as Agent
    participant H as HTTP服务

    U->>M: startup.py启动
    M->>C: 加载配置
    C-->>M: 配置加载完成
    M->>L: 初始化Embedding
    L-->>M: 初始化完成
    M->>A: 初始化Agent
    A-->>M: Agent就绪
    M->>H: 启动HTTP服务
    H-->>M: 服务启动成功
    M-->>U: 启动完成
```

## 4. 核心模块详解

### 4.1 RAG 模块

RAG（Retrieval-Augmented Generation）是 GaussMaster 的核心能力之一，负责从知识库中检索相关知识并生成回答。

**核心组件：**

| 组件 | 文件路径 | 职责 |
|------|----------|------|
| BaseRetriever | `utils/retriever_util.py` | 检索器基类，实现向量+文本检索+重排序 |
| OnlineEmbedding | `utils/retriever_util.py` | 在线向量化服务封装 |
| OnlineReranker | `utils/retriever_util.py` | 在线重排序服务封装 |
| GaussDB | `common/metadatabase/dao/gaussdb_vector.py` | 向量数据库操作封装 |

**检索流程：**

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart LR
    Q[用户查询] --> E[Query向量化]
    E --> VS[向量检索]
    E --> TS[文本检索]
    VS --> C[结果合并]
    TS --> C
    C --> R[重排序]
    R --> F[分数过滤]
    F --> P[构建Prompt]
    P --> L[LLM生成]
```

### 4.2 Agent 模块

Agent 模块负责工具调用和智能决策，是 GaussMaster 与 DBMind 平台交互的桥梁。

**核心组件：**

| 组件 | 文件路径 | 职责 |
|------|----------|------|
| DBA Agent | `multiagents/agents/dba.py` | 主 Agent，处理工具交互和故障诊断 |
| BaseAgent | `multiagents/agents/base_agent.py` | Agent 基类 |
| LLM Executor | `llms/executor.py` | LLM 调用和工具参数提取 |
| Tools Registry | `multiagents/tools/base_tools.py` | 工具注册中心 |
| DBMind Interface | `multiagents/tools/dbmind_interface.py` | DBMind API 封装 |

**Agent 决策流程：**

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart TD
    Input[用户输入] --> Check{检查意图}
    Check -->|已有意图| Use[使用历史意图]
    Check -->|新意图| Match[工具匹配]
    Match --> Valid{工具有效?}
    Valid -->|无效| Answer[直接回答]
    Valid -->|有效| NoParam{无参?}
    NoParam -->|是| Call[直接调用]
    NoParam -->|否| Extract[参数提取]
    Extract --> Complete{参数完整?}
    Complete -->|是| Call
    Complete -->|否| Ask[询问参数]
    Ask --> Save[保存意图]
    Call --> Result[返回结果]
    Answer --> Result
    Save --> Result
```

### 4.3 Memory 模块

Memory 模块负责管理用户会话历史和 QA 记录，支持多轮对话的上下文理解。

**核心组件：**

| 组件 | 文件路径 | 职责 |
|------|----------|------|
| InteractionMemory | `common/metadatabase/schema/interaction_memory.py` | 交互记录数据模型 |
| DAO Memory | `common/metadatabase/dao/dao_interaction_memory.py` | 记忆数据访问对象 |
| Session History | `global_vars.py` | 全局会话历史缓存 |

**Memory 层级结构：**

```mermaid
%%{init: {'theme': 'base'}}%%
graph TB
    User[User] --> Session[Session]
    Session --> Record1[QA记录1]
    Session --> Record2[QA记录2]
    Session --> Record3[QA记录3]
```

**数据库存储结构：**

```python
class InteractionMemory:
    qa_record_id: str      # 记录唯一ID
    user_id: str           # 用户ID
    session_id: str        # 会话ID
    question: str          # 问题（加密存储）
    answer: str            # 回答（加密存储）
    llm_name: str          # 使用的LLM
    function_call: str     # 工具调用信息（加密）
    created_at: int        # 创建时间戳
```

### 4.4 FastAPI 服务模块

FastAPI 服务模块负责 HTTP 接口的暴露和请求处理。

**核心组件：**

| 组件 | 文件路径 | 职责 |
|------|----------|------|
| HttpService | `common/http/_service_impl.py` | FastAPI 服务封装 |
| Core Controller | `controllers/core.py` | API 路由和控制器 |
| Data Transformer | `server/web/data_transformer.py` | 数据转换和业务逻辑 |
| Context Manager | `server/web/context_manager.py` | 请求上下文管理 |

**API 分层：**

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart TB
    subgraph 问答API
        A1[ask_gauss] --> B1[端到端问答]
        A2[search] --> B2[知识检索]
        A3[infer] --> B3[模型推理]
        A4[intelligent] --> B4[智能交互]
    end
    
    subgraph 知识库API
        C1[knowledge_base] --> D1[知识库CRUD]
        C2[datasource] --> D2[数据源CRUD]
    end
    
    subgraph 集群API
        E1[clusters] --> F1[集群管理]
        E2[llms] --> F2[模型切换]
    end
    
    subgraph 反馈API
        G1[feedback] --> H1[反馈操作]
    end
```

## 5. 数据流架构

### 5.1 文档入库数据流

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#f3e5f5', 'primaryTextColor': '#4a148c', 'primaryBorderColor': '#7b1fa2'}}}%%
sequenceDiagram
    participant U as 用户
    participant API as API层
    participant D as 文档解析
    participant S as 文本分片
    participant E as Embedding
    participant V as 向量库
    participant M as 元数据库

    U->>API: 上传文档
    API->>D: 解析文档
    D-->>API: 原始内容
    API->>S: 文本分片
    S-->>API: 分片列表
    API->>E: 向量化
    E-->>API: 向量
    API->>V: 批量插入
    API->>M: 更新记录
    V-->>API: 完成
    M-->>API: 完成
    API-->>U: 入库成功
```

### 5.2 问答数据流

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e0f2f1', 'primaryTextColor': '#004d40', 'primaryBorderColor': '#00796b'}}}%%
sequenceDiagram
    participant C as 客户端
    participant API as API
    participant S as 安全检查
    participant R as 检索模块
    participant V as 向量库
    participant L as LLM
    participant M as 元数据库

    C->>API: 提问
    API->>S: 敏感词检测
    alt 包含敏感词
        S-->>API: 拒绝
    else 安全
        API->>R: 向量化
        R->>V: 向量检索
        R->>V: 文本检索
        V-->>R: 候选结果
        R->>R: 重排序
        alt 有结果
            R-->>API: 返回上下文
            API->>L: 生成回答
            L-->>API: 流式输出
        else 无结果
            API->>API: 查询优化
            API->>R: 再次检索
            R-->>API: 优化结果
            API->>L: 生成回答
        end
        API->>M: 保存记录
    end
    API-->>C: SSE响应
```

## 6. 配置体系

### 6.1 配置文件结构

```
gaussmaster.conf          # 主配置文件
model_config.yaml         # LLM 模型配置

# 配置分类：
[LOG]                     # 日志配置
[WEB_SERVICE]             # Web 服务配置
[VECTOR]                  # 向量数据库配置
[DBMIND]                  # DBMind 连接配置
[SAFETY]                  # 安全检查配置
```

### 6.2 配置加载流程

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart LR
    Start[启动] --> LoadConf[加载配置]
    LoadConf --> Validate[配置验证]
    Validate --> SSL[SSL配置]
    Validate --> DB[数据库配置]
    Validate --> LLM[LLM配置]
```

## 7. 安全架构

### 7.1 安全机制

| 层级 | 机制 | 实现 |
|------|------|------|
| 传输层 | SSL/TLS | Uvicorn SSL 配置 |
| 应用层 | 敏感词检测 | DFA 算法 |
| 数据层 | 加密存储 | AES256-CBC |
| 访问层 | 密码强度检查 | 正则验证 |

### 7.2 敏感数据处理

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart LR
    Input[用户输入] --> DFA[DFA检测]
    DFA -->|安全| Process[正常处理]
    DFA -->|敏感| Reject[拒绝回答]
```

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart LR
    QA[QA记录] --> Encrypt[加密存储]
    Encrypt --> DB[数据库]
    DB --> Decrypt[解密读取]
```

## 8. 扩展性设计

### 8.1 LLM 扩展

```python
# LLM 注册表模式
llm_registry = {
    'pangu': PanguLLM,
    'pangu_cloud': PanguCloudLLM,
    'chatglm': ChatGLM,
    'llama': Llama,
    'baichuan': Baichuan
}
```

### 8.2 工具扩展

```python
# 工具装饰器模式
@base_tools(
    name="tool_name",
    description="工具描述",
    params=[Param(...)]
)
def tool_function(**kwargs):
    pass
```

## 9. 部署架构

### 9.1 单机部署

```mermaid
%%{init: {'theme': 'base'}}%%
graph LR
    Client[客户端] --> Nginx[Nginx]
    Nginx --> GM[GaussMaster]
    GM --> VectorDB[(Vector DB)]
    GM --> MetaDB[(Meta DB)]
    GM --> DBMind[DBMind]
    GM --> LLM[LLM Service]
```

### 9.2 组件依赖

| 组件 | 依赖 | 说明 |
|------|------|------|
| GaussMaster | openGauss | 向量存储 |
| GaussMaster | PostgreSQL | 元数据存储 |
| GaussMaster | DBMind | 运维数据 |
| GaussMaster | LLM Service | 推理服务 |
| GaussMaster | Embedding | 向量化服务 |

## 10. 总结

GaussMaster 采用分层架构设计，核心特点：

1. **模块化设计**：各模块职责清晰，便于维护和扩展
2. **RAG + Agent 双引擎**：知识问答和工具调用能力兼备
3. **企业级特性**：SSL、加密、敏感词检测等安全机制完善
4. **多模型支持**：通过注册表模式支持多种 LLM
5. **流式响应**：支持 SSE 流式输出，提升用户体验

后续文档将详细展开各模块的具体实现和流程细节。
