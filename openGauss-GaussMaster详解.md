# openGauss-GaussMaster 项目详解

## 目录

- [项目概述](#项目概述)
- [核心定位](#核心定位)
- [系统架构](#系统架构)
- [核心功能模块](#核心功能模块)
- [技术实现细节](#技术实现细节)
- [部署架构](#部署架构)
- [应用场景](#应用场景)
- [API接口](#api接口)
- [配置说明](#配置说明)
- [技术栈](#技术栈)

---

## 项目概述

**openGauss-GaussMaster** 是华为开源的 **数据库智能运维Copilot平台**，基于大语言模型（LLM）和人工智能技术，为数据库管理员（DBA）提供一站式的智能运维解决方案。

GaussMaster的核心目标是：**通过自然语言交互，实现数据库的智能问答、根因诊断、故障巡检、预测调优等全生命周期运维管理**。

### 开源信息

- **开源许可证**: Mulan PSL v2
- **版权所有**: Huawei Technologies Co.,Ltd.
- **项目版本**: 1.0.0

---

## 核心定位

### 解决什么问题？

传统数据库运维面临的挑战：

1. **运维复杂性**：数据库系统庞大，运维人员需要掌握大量专业知识
2. **故障定位困难**：数据库出现问题时，定位根因耗时长、难度大
3. **巡检工作繁琐**：日常巡检需要人工检查大量指标，效率低下
4. **调优门槛高**：性能调优需要深厚的数据库内核知识

### GaussMaster的解决方案

GaussMaster通过AI技术，将上述复杂运维工作智能化、自动化，让普通用户也能像资深DBA一样高效运维数据库。

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                 │
│                    (Web UI / API)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GaussMaster 服务层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  智能问答    │  │  工具交互    │  │  多Agent     │           │
│  │  (Q&A)      │  │  (Tools)    │  │  (Agent)     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  向量检索    │  │  知识库管理  │  │  会话管理    │           │
│  │  (Vector)   │  │  (KB)        │  │  (Session)   │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   DBMind服务    │ │   向量数据库    │ │   大模型服务    │
│ (openGauss管控) │ │ (知识检索)      │ │ (LLM推理)       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   openGauss     │ │   Embedding     │ │   Reranker      │
│   数据库实例    │ │   模型服务      │ │   模型服务      │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 架构分层

| 层级 | 组件 | 说明 |
|------|------|------|
| **表现层** | Web UI / REST API | 用户交互接口 |
| **服务层** | GaussMaster Core | 核心业务逻辑处理 |
| **模型层** | LLM + Embedding + Reranker | AI模型推理 |
| **数据层** | 向量数据库 + 元数据库 | 知识存储与检索 |
| **管控层** | DBMind | openGauss实例管理 |
| **数据库层** | openGauss | 目标数据库 |

---

## 核心功能模块

### 1. 智能问答系统 (Intelligent Q&A)

**模块位置**: `GaussMaster/llms/`

**功能描述**:
- 基于知识库的智能问答
- 支持中英文双语
- 流式响应输出
- 多轮对话记忆

**支持的大模型**:

| 模型名称 | 类型 | 说明 |
|---------|------|------|
| 盘古智子 (Pangu) | 华为云模型 | 默认模型 |
| ChatGLM3 | 智谱AI | 中英双语 |
| Baichuan2 | 百川智能 | 中文优化 |
| Llama3 | Meta | 多语言 |
| Qwen | 阿里通义 | 中文优化 |
| DeepSeek | 深度求索 | 高性价比 |

**核心文件**:
- `llms/base/BaseLLM.py` - 大模型基类
- `llms/executor.py` - 模型调用执行器
- `llms/llm_utils.py` - LLM工具函数

### 2. 工具交互系统 (Tool Interaction)

**模块位置**: `GaussMaster/multiagents/tools/`

**功能描述**:
- 智能理解用户意图
- 自动匹配合适工具
- 参数提取与验证
- 工具调用执行

**可用工具**:
- `summary_alarms` - 告警汇总
- `query_cluster_status` - 集群状态查询
- 诊断报告生成
- 配置参数查询

**核心流程**:

```
用户提问 → 意图识别 → 工具匹配 → 参数提取 → 工具调用 → 结果返回
```

### 3. 多Agent系统 (Multi-Agent)

**模块位置**: `GaussMaster/multiagents/`

**Agent类型**:

| Agent | 职责 | 提示词模板 |
|-------|------|-----------|
| DBA Agent | 数据库管理员交互 | `dba_prompt.py` |
| Reporter Agent | 诊断报告生成 | `reporter_prompt.py` |
| Repairer Agent | 故障修复建议 | `repairer_prompt.py` |

**核心文件**:
- `agents/base_agent.py` - Agent基类
- `agents/dba.py` - DBA交互Agent
- `agents/prompt/` - 提示词工程

### 4. 知识库系统 (Knowledge Base)

**模块位置**: `GaussMaster/knowledge_base/`

**知识库文件**:
- `gauss_zh.db` - 中文知识库
- `gauss_en.db` - 英文知识库

**功能**:
- 向量化存储
- 相似度检索
- 知识片段重排序

### 5. 向量检索系统

**模块位置**: `GaussMaster/common/embedding/`

**支持的Embedding模型**:
- BGE (BAAI) - 默认
- 支持自定义模型

**向量检索流程**:

```
用户问题 → Embedding模型 → 向量化 → 向量数据库检索 → Top-K结果 → Reranker重排 → 返回
```

### 6. 元数据库系统

**模块位置**: `GaussMaster/common/metadatabase/`

**存储内容**:
- 集群配置信息
- 诊断报告历史
- 对话交互记忆
- 动态配置参数

**数据库表**:
- `clusters` - 集群信息
- `diagnostic_report` - 诊断报告
- `interaction_memory` - 对话记忆
- `config_dynamic_params` - 动态配置

---

## 技术实现细节

### 1. 会话管理机制

**文件**: `GaussMaster/common/metadatabase/dao/dao_interaction_memory.py`

**特点**:
- 支持多用户、多会话
- 本地内存 + 远程数据库双重存储
- 加密存储敏感信息
- 历史记录可配置长度

**会话结构**:
```python
InteractionMemory:
  - qa_record_id: 记录唯一标识
  - user_id: 用户ID
  - session_id: 会话ID
  - question: 用户问题 (加密)
  - answer: 回答内容 (加密)
  - llm_name: 使用的大模型
  - function_call: 工具调用记录 (加密)
  - created_at: 创建时间戳
```

### 2. 工具调用机制

**文件**: `GaussMaster/llms/executor.py`

**核心流程**:

```
1. 意图推断 (infer_tool_name)
   └─→ 分析用户问题，确定需要调用的工具

2. 参数推断 (infer_arguments)
   └─→ 从用户问题中提取工具参数

3. 参数验证 (verify_arguments)
   └─→ 检查参数完整性

4. 工具执行 (call_tool)
   └─→ 调用DBMind接口执行实际操作
```

### 3. 向量检索实现

**文件**: `GaussMaster/utils/retriever_util.py`

**检索策略**:
- 基于向量相似度（余弦相似度）
- Top-K 结果返回
- Reranker重排序优化

### 4. 安全机制

**模块位置**: `GaussMaster/common/safety/`

**功能**:
- 敏感词检测
- 密码强度检查
- SSL/TLS加密传输
- 敏感信息打码

**敏感词分类**:
```
低俗色情 / 账号违规 / 敏感信息 / 暴力恐怖 / 造谣诽谤 /
侮辱英烈 / 谩骂攻击 / 民族宗教 / 赌博诈骗 / 危害未成年 / 违法违禁品
```

### 5. SSL/TLS安全配置

**文件**: `GaussMaster/common/cert_checker.py`

**支持的加密服务**:
- VECTOR 向量数据库
- DBMIND 服务
- Web Service

**配置检查**:
- 证书有效性验证
- 密钥文件检查
- 密码强度验证

---

## 部署架构

### 单机部署

```
┌────────────────────────────────────────┐
│           GaussMaster Server           │
│  ┌──────────────────────────────────┐  │
│  │        Web Service (Port)        │  │
│  └──────────────────────────────────┘  │
│                   │                     │
│  ┌──────────────────────────────────┐  │
│  │       Business Logic Layer      │  │
│  └──────────────────────────────────┘  │
│          │           │           │      │
│  ┌───────┴───┐ ┌─────┴─────┐ ┌──┴────┐ │
│  │  Vector   │ │   Meta    │ │ LLM   │ │
│  │  DB       │ │   DB      │ │ Service│ │
│  └───────────┘ └───────────┘ └───────┘ │
└────────────────────────────────────────┘
```

### 分布式部署

```
┌────────────────────────────────────────────────────────┐
│                    GaussMaster Cluster                  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Load Balancer                        │  │
│  └──────────────────────────────────────────────────┘  │
│            │                        │                   │
│  ┌─────────┴─────────┐   ┌─────────┴─────────┐        │
│  │  GaussMaster-1    │   │  GaussMaster-N    │        │
│  └───────────────────┘   └───────────────────┘        │
│           │                          │                  │
└───────────┼──────────────────────────┼──────────────────┘
            │                          │
    ┌───────┴───────┐          ┌───────┴───────┐
    │  DBMind-1     │   ...    │  DBMind-N     │
    └───────────────┘          └───────────────┘
            │                          │
    ┌───────┴───────┐          ┌───────┴───────┐
    │ openGauss-1   │   ...    │ openGauss-N  │
    └───────────────┘          └───────────────┘
```

---

## 应用场景

### 场景一：智能问答

**场景描述**: 数据库新手用户遇到问题，直接用自然语言提问

**示例**:
```bash
curl -X POST "http://<gaussmaster>/v1/api/ask_gauss" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "session_id": "sess001",
    "question": "如何查看当前数据库的连接数？",
    "lang": "zh"
  }'
```

**返回**: 流式输出的智能回答

### 场景二：集群注册与监控

**场景描述**: 将openGauss集群注册到GaussMaster进行管理

**步骤**:
1. 通过DBMind纳管openGauss实例
2. 在GaussMaster注册集群
3. 开始智能运维交互

**注册命令**:
```bash
curl -X POST "http://<gaussmaster>/v1/api/clusters/register" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod_db",
    "host": "192.168.1.100",
    "port": 5432,
    "username": "dbadmin",
    "password": "****"
  }'
```

### 场景三：智能故障诊断

**场景描述**: 数据库出现异常，通过对话方式诊断问题

**交互流程**:
```
用户: "帮我查询当前数据库集群状态"
GaussMaster: [调用summary_alarms工具] → 返回告警汇总
用户: "这些告警是什么原因导致的"
GaussMaster: [分析告警类型] → 返回根因分析
用户: "如何解决这个问题"
GaussMaster: [调用repairer Agent] → 返回修复建议
```

---

## API接口

### 核心接口列表

| 接口路径 | 方法 | 功能 |
|---------|------|------|
| `/v1/api/ask_gauss` | POST | 智能问答 |
| `/v1/api/clusters/register` | POST | 集群注册 |
| `/v1/api/clusters/list` | GET | 集群列表 |
| `/v1/api/app/intelligent-interaction` | POST | 智能交互 |
| `/v1/api/diagnosis/report` | GET | 诊断报告 |

### 智能问答接口

**端点**: `POST /v1/api/ask_gauss`

**请求参数**:
```json
{
  "user_id": "string",        // 用户ID
  "session_id": "string",     // 会话ID
  "model_name": "string",     // 大模型名称
  "lang": "zh|en",           // 语言
  "history_len": 3,          // 历史记录长度
  "question": "string"        // 用户问题
}
```

**响应**: Server-Sent Events (SSE) 流式输出

### 智能交互接口

**端点**: `POST /v1/api/app/intelligent-interaction`

**请求参数**:
```json
{
  "query": "string",           // 用户查询
  "mode": "tool_interaction",  // 交互模式
  "user_id": "string",         // 用户ID
  "session_id": "string"       // 会话ID
}
```

---

## 配置说明

### 主配置文件 (gaussmaster.conf)

**路径**: `GaussMaster/misc/gaussmaster.conf`

**配置段**:

```ini
[VECTOR]
host = <向量数据库地址>
port = <端口>
database = <数据库名>
username = <用户名>
password = <密码>

[DBMIND]
api_prefix = https://<dbmind地址>
ssl_certfile = <SSL证书>
ssl_keyfile = <SSL密钥>
ssl_ca_file = <CA证书>

[WEB-SERVICE]
host = 0.0.0.0
port = <服务端口>
ssl = true|false

[LOG]
level = INFO
log_directory = logs
maxbytes = <单个日志大小>
backupcount = <保留日志数量>

[SAFETY]
safety_check = true|false
```

### 大模型配置 (model_config.yaml)

**路径**: `GaussMaster/misc/model_config.yaml`

**配置示例**:

```yaml
# 默认模型
model_name: pangu_sigma_unify_plugin_38b

# Embedding模型
embedding_model:
  api_url: http://<embedding服务>:*/get_embedding_result
  model_path: <模型路径>

# Reranker模型
reranker_model:
  api_url: http://<reranker服务>:*/get_reranker_result

# 大模型列表
online_llm:
  pangu_sigma_unify_plugin_38b:
    enable: True
    api_type: Pangu
    api_url: http://<pangu服务>:*/chat/completions
    recommended_config:
      temperature: 0.7
      top_p: 1.0
```

### 启动流程

**步骤一**: 生成配置目录
```bash
python startup.py service setup -c conf
```

**步骤二**: 初始化（配置检查+知识库导入）
```bash
echo '{"VECTOR_password": "x", "DBMIND_password": "x"}' | \
python startup.py service setup -c conf --initialize --initialize_meta_db
```

**步骤三**: 启动服务
```bash
python startup.py service start -c conf
```

**步骤四**: 停止服务
```bash
python startup.py service stop -c conf
```

---

## 技术栈

### 后端技术

| 组件 | 技术 | 说明 |
|------|------|------|
| **语言** | Python 3.x | 主要开发语言 |
| **框架** | 自主研发 | HTTP服务框架 |
| **数据库** | SQLite + 向量数据库 | 元数据+知识库 |
| **加密** | AES256-CBC | 密码加密存储 |
| **日志** | logging (多进程安全) | 日志管理 |

### AI/ML技术

| 组件 | 技术 | 说明 |
|------|------|------|
| **大模型** | Pangu/ChatGLM/Baichuan/Llama | LLM推理 |
| **Embedding** | BGE | 文本向量化 |
| **Reranker** | BGE-Reranker | 结果重排序 |

### 安全技术

| 组件 | 技术 | 说明 |
|------|------|------|
| **传输加密** | SSL/TLS | HTTPS传输 |
| **密码加密** | AES256-CBC | 静态数据加密 |
| **敏感词检测** | DFA算法 | 内容安全 |
| **密码强度** | 正则校验 | 密码策略 |

### 前端技术

| 组件 | 技术 | 说明 |
|------|------|------|
| **构建工具** | Vite | 开发服务器 |
| **代理配置** | vite.config.ts | API代理 |
| **环境配置** | .env.development | 开发环境变量 |

---

## 项目结构

```
openGauss-GaussMaster/
├── GaussMaster/
│   ├── __init__.py
│   ├── constants.py              # 常量定义
│   ├── global_vars.py             # 全局变量
│   ├── startup.py                 # 启动入口
│   │
│   ├── common/                    # 公共模块
│   │   ├── configs/               # 配置管理
│   │   ├── embedding/             # 向量化
│   │   ├── http/                  # HTTP服务
│   │   ├── metadatabase/          # 元数据库
│   │   ├── platform/              # 平台适配
│   │   ├── plugins/               # 插件系统
│   │   ├── reranker/              # 重排序
│   │   ├── safety/                # 安全模块
│   │   └── utils/                 # 工具函数
│   │
│   ├── controllers/               # 控制器层
│   ├── knowledge_base/            # 知识库文件
│   ├── llms/                      # 大模型模块
│   │   ├── base/                  # LLM基类
│   │   ├── Baichuan.py            # 百川
│   │   ├── Chatglm.py             # ChatGLM
│   │   ├── Llama.py               # Llama
│   │   ├── Pangu.py               # 盘古
│   │   └── executor.py            # 调用执行器
│   │
│   ├── multiagents/               # 多智能体
│   │   ├── agents/                # Agent实现
│   │   ├── config/                # Agent配置
│   │   └── tools/                 # 工具集
│   │
│   ├── server/                    # 服务层
│   │   └── web/                   # Web服务
│   │
│   └── utils/                     # 工具模块
│
├── doc/                           # 文档图片
├── README.md                      # 项目说明
└── LICENSE                        # 许可证
```

---

## 关键特性总结

### 核心优势

1. **AI原生态**: 深度整合大语言模型，实现自然语言运维
2. **工具自动化**: 智能工具匹配与调用，减少人工操作
3. **知识驱动**: 基于知识库的精准问答，覆盖运维全场景
4. **多模型支持**: 兼容主流大模型，灵活切换
5. **安全可靠**: 端到端加密，敏感词检测，密码强度校验
6. **分布式架构**: 支持多集群管理，可扩展部署

### 设计原则

- **模块化**: 各组件解耦，便于维护和扩展
- **可配置**: 多层次配置项，满足不同部署需求
- **安全性**: 密码加密传输，敏感词过滤
- **容错性**: 完善的异常处理与日志记录
- **可观测性**: 详细的日志输出，便于问题排查

---

## 未来演进方向

基于项目的架构设计和发展趋势，GaussMaster可能在以下方向持续演进：

1. **更多LLM支持**: 接入更多国产大模型
2. **智能诊断增强**: 引入更多诊断模型
3. **自动化修复**: 从诊断建议到自动执行
4. **多数据库支持**: 从openGauss扩展到其他数据库
5. **可视化增强**: 更丰富的Web UI
6. **运维生态**: 与更多运维工具集成

---

## 参考资源

- **openGauss官网**: https://www.opengauss.org/
- **DBMind项目**: https://gitcode.com/opengauss/openGauss-DBMind
- **Mulan PSL v2许可证**: http://license.coscl.org.cn/MulanPSL2/
- **社区贡献**: https://opengauss.org/zh/contribution/

---

*本文档基于openGauss-GaussMaster v1.0.0版本编写*
