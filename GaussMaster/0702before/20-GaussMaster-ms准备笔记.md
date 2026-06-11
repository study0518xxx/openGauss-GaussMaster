# openGauss-GaussMaster 面试准备笔记

## 目录

- [项目核心模块](#项目核心模块)
- [面试热点问题](#面试热点问题)
- [简历描述模板](#简历描述模板)
- [技术细节补充](#技术细节补充)

---

## 项目核心模块

### 模块规模一览

| 模块 | 代码行数 | 占比 | 说明 |
|------|---------|------|------|
| **common** | 5,301 行 | 40% | 公共组件（HTTP、数据库、安全等） |
| **multiagents** | 3,081 行 | 23% | 多Agent系统（核心业务） |
| **utils** | 2,071 行 | 16% | 工具函数（文档处理、检索等） |
| **server** | 1,184 行 | 9% | Web服务层 |
| **llms** | 772 行 | 6% | 大模型集成 |
| **controllers** | 359 行 | 3% | 控制器层（API路由） |

**总规模**: 100 个 Python 文件，13,289 行代码

---

## 面试热点问题

### 问题1️⃣：工具调用流程（Tool Calling）

**面试官可能问**：
> "用户说'帮我查询当前数据库状态'，系统是怎么工作的？"

**标准答案**：

```
1. 用户输入 → LLM 意图识别
   └─→ 分析用户问题，判断需要调用 summary_alarms 工具

2. 参数提取
   └─→ 从问题中提取时间范围（默认最近1小时）

3. 工具调用
   └─→ 调用 DBMind API 获取告警数据

4. 结果格式化
   └─→ 通过 formatter_str/table/graph 格式化输出

5. 返回给用户
```

**代码位置**：[`executor.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py)

**核心函数**：
- `infer_tool_name()` - 意图识别
- `check_has_valid_tool()` - 工具校验
- `check_is_no_param_tool()` - 参数校验
- `infer_arguments()` - 参数提取
- `verify_arguments()` - 参数验证
- `call_tool()` - 工具执行

**可用工具列表**：
- `summary_alarms` - 告警汇总
- `cluster_diagnosis` - 集群诊断
- `slow_sql_rca` - 慢SQL根因分析
- `index_recommendation` - 索引推荐
- `risk_analysis` - 风险预测
- `metric_diagnosis` - 指标诊断
- `get_top_sqls` - Top SQL查询
- `get_instance_status` - 实例状态
- `get_locking_sql` - 锁等待SQL
- `knob_recommendation_details` - 参数推荐
- `memory_check` - 内存检查
- `status_overview` - 状态总览

---

### 问题2️⃣：Agent系统设计

**面试官可能问**：
> "这个项目的 Agent 架构是怎么设计的？和 LangChain 的 Agent 有什么区别？"

**标准答案**：

```
架构设计：
├── BaseAgent（抽象基类）
│   └── output_parser: CustomOutputParser
│
├── DBA Agent（对话交互）
│   ├── 意图识别
│   ├── 工具匹配
│   ├── 参数提取
│   └── 工具调用
│
├── Reporter Agent（诊断报告）
└── Repairer Agent（故障修复）

与 LangChain 的区别：
1. 自研的轻量级 Agent，非 LangChain
2. 装饰器模式的工具注册（更直观）
3. 支持多 Agent 协作（各司其职）
4. 内置对话记忆和意图状态保持
```

**代码位置**：
- [`base_agent.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/base_agent.py) - Agent 基类
- [`dba.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py) - DBA Agent 实现

**工具注册机制**（装饰器模式）：
```python
@base_tools(
    name="summary_alarms",
    description="获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
def summary_alarms(start_time, end_time):
    """具体实现"""
    ...
```

---

### 问题3️⃣：RAG 知识检索

**面试官可能问**：
> "这个项目是怎么实现 RAG 的？向量检索的流程是什么？"

**标准答案**：

```
RAG 流程：
用户问题
   ↓
Embedding 模型向量化 → 生成 query_embedding
   ↓
向量数据库检索 → Top-K 相似文档
   ↓
Reranker 重排序 → 提升检索精度
   ↓
与原始问题拼接 → 构建最终 Prompt
   ↓
LLM 推理生成回答

项目中的实现：
- 知识库文件：gauss_zh.db / gauss_en.db
- 支持自定义知识库上传（API: /serve/knowledge_base/add）
- 向量检索参数：vector_topk, text_topk, rerank_topk
```

**关键代码位置**：
- [`knowledge_base/`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/knowledge_base/) - 知识库文件
- `embedding/` - Embedding 模型
- `reranker/` - Reranker 模型

---

### 问题4️⃣：多轮对话实现

**面试官可能问**：
> "系统是怎么支持多轮对话的？上下文是怎么管理的？"

**标准答案**：

```
实现方案：
1. 会话级别存储
   └─→ user_id + session_id 作为会话唯一标识

2. 两层存储
   └─→ 内存（SESSION_QA_HISTORY）：快速访问
   └─→ SQLite（tb_interaction_memory）：持久化

3. 意图状态保持
   └─→ SESSION_TOOL_HISTORY 记住当前正在使用的工具
   └─→ 多轮对话中保持同一工具的调用

4. 历史记录控制
   └─→ history_len 参数控制回溯长度
   └─→ 加密存储敏感信息（AES256）
```

**数据库表结构**：[`interaction_memory.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/metadatabase/schema/interaction_memory.py)

```python
class InteractionMemory(ResultDbBase):
    qa_record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False)
    question = Column(TEXT, nullable=False)      # 加密存储
    answer = Column(TEXT, nullable=True)        # 加密存储
    llm_name = Column(String(64), nullable=True)
    function_call = Column(TEXT, nullable=True) # 加密存储
    created_at = Column(BigInteger, nullable=False)
```

---

### 问题5️⃣：Prompt Engineering

**面试官可能问**：
> "工具描述是怎么设计 Prompt 的？为什么这样设计？"

**标准答案**：

```
Prompt 设计：

1. 工具描述格式化（prompt.py）
"""工具集
------
助理可以要求用户使用工具查找信息。人类可以使用的工具有：
{{tools}}  // 动态插入工具列表

用户的输入
--------------------
如下是用户的输入（请用MARKDOWN格式中的json块的方式进行回复）
{{{{input}}}}"""  // 用户问题

2. 参数提取提示词（executor.py）
TOOL_INTERACT_ZH.format(
    functions=target_tool_des,  // 工具详情（带参数说明）
    ...
)

设计原因：
1. 结构化工具描述 - LLM 能准确理解每个工具的功能和参数
2. JSON输出格式 - 便于程序解析和执行
3. 中英文双语 - 支持国际化
4. few-shot 示例 - 帮助 LLM 理解参数提取模式
```

**代码位置**：[`prompt.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/prompt.py)

---

### 问题6️⃣：系统安全机制

**面试官可能问**：
> "敏感信息是怎么处理的？有哪些安全措施？"

**标准答案**：

```
1. 密码加密存储（startup.py）
save_config_password(config, section, option, password)  // AES256-CBC

2. 对话内容加密（dba.py）
question=Encryption.encrypt(qa_record.question),
answer=Encryption.encrypt(qa_record.answer),
function_call=Encryption.encrypt(qa_record.function_call),

3. SSL/TLS 加密传输（_service_impl.py）
ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
// 强制 TLS >= 1.2

4. 敏感词检测（safety/word_detect.py）
DFA 算法检测 12 类敏感内容
- 低俗色情 / 账号违规 / 敏感信息 / 暴力恐怖 / 造谣诽谤
- 侮辱英烈 / 谩骂攻击 / 民族宗教 / 赌博诈骗 / 危害未成年
```

---

### 问题7️⃣：FastAPI 封装层设计

**面试官可能问**：
> "为什么要在 FastAPI 外面再封装一层？直接用 FastAPI 不行吗？"

**标准答案**：

```
可以直接用 FastAPI！封装层只是工程最佳实践，不是必须项。

封装层的目的：
1. 解耦：业务代码不依赖具体框架，未来可以换 Django/Starlette
2. 统一规范：所有 API 统一 {success: true/false, data: xxx} 格式
3. 复用逻辑：流式响应、异常处理、日志记录只需写一次
4. 过渡迁移：存量代码多时，避免一次性重写

代码注释明确说明（_service_impl.py 第40-43行）：
"""To decouple web service framework and web service interface,
DBMind implements the class. In this way, DBMind can change to
another web framework easily.
DBMind easily migrated from the flask to the fastapi through this class."""

这是从 Flask 迁移到 FastAPI 的过渡方案。

封装内容：
├── standardized_api_output    // 统一 JSON 响应
├── standardized_event_stream   // 统一 SSE 流式响应
├── request_mapping            // 统一路由装饰器
└── set_language_middleware    // 统一语言处理

如果项目从零开始，可以直接用 FastAPI：
from fastapi import FastAPI
app = FastAPI()

@app.post("/ask_gauss")
async def ask_gauss(params: SearchParams):
    result = await data_transformer.ask_gauss(...)
    return {"success": True, "data": result}
```

---

### 问题8️⃣：SQLite 元数据库用途

**面试官可能问**：
> "SQLite 在项目中起什么作用？为什么不用 MySQL/PostgreSQL？"

**标准答案**：

```
SQLite 用途：存储结构化业务元数据

1. 托管集群信息（tb_managed_cluster）
   - cluster_id, cluster_name, host, port, username, password

2. 对话交互记忆（tb_interaction_memory）
   - qa_record_id, user_id, session_id, question, answer
   - llm_name, function_call, created_at

3. 动态配置参数（dynamic_config.db）
   - category, name, value, tag, annotation

为什么用 SQLite：
- 轻量级，无需额外部署数据库服务
- 文件形式存储，便于迁移备份
- 适合中小型数据量（对话记录、配置信息）
- 支持 SQLAlchemy ORM，操作方便

与向量数据库分工：
- SQLite：结构化数据（精确查询）
- 向量数据库：非结构化知识（相似度检索）
```

---

## 简历描述模板

### 项目经历模板

```
openGauss-GaussMaster 数据库智能运维 Copilot 平台    2025.xx - 至今
开源项目 | 核心开发者

项目描述：
- 基于 LLM 的数据库智能运维系统，支持自然语言交互完成智能问答、故障诊断、
  性能调优等运维任务
- 采用 RAG 架构，整合向量检索与大模型推理，实现精准的专业领域问答
- 设计 Multi-Agent 系统，包含 DBA Agent、诊断 Agent、修复 Agent，实现
  智能化运维决策

技术架构：
- 后端：Python + FastAPI（封装解耦层，支持平滑迁移）+ SQLAlchemy ORM
- AI 层：集成 Pangu/ChatGLM/Llama 等大模型，BGE Embedding 向量化
- 数据：SQLite（元数据管理）+ GaussDB Vector（知识检索）
- 安全：SSL/TLS 传输加密 + AES256 静态加密 + DFA 敏感词检测

核心贡献：
- 实现智能问答模块，支持流式响应和多轮对话记忆
- 设计工具调用系统，自动匹配 15+ 运维工具，参数提取准确率达 XX%
- 构建知识库管理模块，向量化存储专业知识，检索响应<100ms
- 实现多集群管理架构，支持分布式部署和负载均衡

技术亮点：
- 采用 RAG 技术解决大模型幻觉问题，专业领域问答准确率提升 XX%
- 设计 Agent 协作机制，复杂运维任务自动化率提升 XX%
- 端到端加密方案，通过企业级安全审计
```

### 针对不同岗位的侧重点

| 岗位 | 重点突出 |
|------|---------|
| AI 工程师 | LLM 集成、RAG 架构、Embedding、Prompt Engineering |
| 后端开发 | Python 架构、FastAPI 封装、SQLAlchemy、异步编程 |
| 全栈工程师 | 前后端完整实现、Web UI、API 设计、部署运维 |
| AIOps/运维 | 数据库运维场景、故障诊断算法、监控告警系统 |

---

## 技术细节补充

### 1. HTTP 服务封装层详解

**文件**：[`common/http/_service_impl.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/http/_service_impl.py)

**核心类 HttpService**：
```python
class HttpService:
    """解耦 Web 框架和业务逻辑的封装层"""

    def __init__(self, name=__name__):
        self.app = FastAPI(title=name, ...)
        self._server = None

    def attach(self, func, rule, method, **options):
        """统一路由注册"""
        ...

    def start_listen(self, host, port, ssl_keyfile=None, ...):
        """启动 HTTPS 服务（强制 TLS 1.2+）"""
        ...

# 使用示例
@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    return data_transformer.ask_gauss(...)
```

### 2. 工具调用完整流程

**文件**：[`llms/executor.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py)

**5 步流程**：
```python
async def interact_with_tool(self):
    # Step 1: 意图推断
    matched_tool = await infer_tool_name(question, user_id, session_id, llm)

    # Step 2: 工具校验
    is_valid = check_has_valid_tool(matched_tool)
    if not is_valid:
        return "问题无法用工具解答"

    # Step 3: 参数推断
    content_resp, function_call = await infer_arguments(
        question, intention_tool, qa_record_history, llm
    )

    # Step 4: 参数验证
    is_complete, correct_params, need_params = verify_arguments(function_call)

    # Step 5: 工具执行
    tool_result = call_tool(intention_tool, correct_params)
    return tool_result
```

### 3. 多轮对话状态管理

**文件**：[`multiagents/agents/dba.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py)

**状态存储**：
```python
class DBA(BaseAgent):
    def __init__(self, ...):
        # 意图状态：记住当前要用的工具
        self.intention_tool = None

        # 对话历史：内存 + SQLite 双层存储
        self.memory = global_vars.MEMORY

    async def interact_with_tool(self):
        # 检查是否有未完成的意图
        intention_tool = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id)

        if intention_tool is None:
            # 新对话，重新推断意图
            matched_tool = await infer_tool_name(...)
            SESSION_TOOL_HISTORY[user_id][session_id] = matched_tool

        # 继续上次的工具调用，提取参数
        content_resp, function_call = await infer_arguments(...)
```

### 4. 安全机制实现

**密码加密**：[`common/security.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/security.py)
```python
class Encryption:
    @staticmethod
    def encrypt(plain_text: str) -> str:
        # AES256-CBC 加密
        ...

    @staticmethod
    def decrypt(cipher_text: str) -> str:
        # AES256-CBC 解密
        ...
```

**SSL 配置**：[`common/http/_service_impl.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/http/_service_impl.py#L131-L134)
```python
config.ssl.options |= (
    ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 |
    ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
)  # 强制 TLS >= 1.2
config.ssl.set_ciphers('DHE+AESGCM:ECDHE+AESGCM')
```

---

## 面试核心点总结

| 优先级 | 问题 | 准备方向 | 代码位置 |
|-------|------|---------|---------|
| ⭐⭐⭐ | 工具调用流程 | executor.py 的 5 步流程 | [`executor.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py) |
| ⭐⭐⭐ | RAG 架构 | 向量检索 + Reranker | [`knowledge_base/`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/knowledge_base/) |
| ⭐⭐⭐ | Agent 设计 | 装饰器 + 意图识别 + 参数提取 | [`dba.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py) |
| ⭐⭐ | 多轮对话 | 内存 + SQLite + 意图状态 | [`dba.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py) |
| ⭐⭐ | Prompt 工程 | 工具描述 + 参数提取提示词 | [`prompt.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/prompt.py) |
| ⭐⭐ | 安全机制 | AES加密 + SSL + 敏感词 | [`security.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/security.py) |
| ⭐ | 框架封装 | 解耦 + 统一响应格式 | [`_service_impl.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/http/_service_impl.py) |

---

## 需要吃透的核心文件

1. **[`llms/executor.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py)** - LLM 调用执行器
2. **[`multiagents/agents/dba.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py)** - DBA Agent 对话管理
3. **[`multiagents/tools/dbmind_interface.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/tools/dbmind_interface.py)** - 工具接口实现
4. **[`llms/prompt.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/prompt.py)** - Prompt 工程
5. **[`common/http/_service_impl.py`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/common/http/_service_impl.py)** - HTTP 服务封装

---

*本文档用于面试准备，基于 openGauss-GaussMaster v1.0.0*
