# GaussMaster Multi-Agent 改造计划

## 现状分析

### 当前架构（单 Agent + 多工具）
```
用户问题
    │
    ▼
┌─────────────────────────────────────┐
│         DBA Agent (唯一)             │
│  1. 理解问题                        │
│  2. 选择工具                        │
│  3. 调用工具                        │
│  4. 汇总回答                        │
└─────────────────────────────────────┘
    │
    ├──→ 索引推荐工具
    ├──→ 状态查询工具
    └──→ 慢SQL分析工具
```

### 问题
- 只有一个 Agent，无法并行处理
- 各"角色"只是工具标签，不是独立 Agent
- 缺乏 Agent 间协作机制

---

## 目标架构（真正的 Multi-Agent）

```
用户问题
    │
    ▼
┌─────────────────────────────────────────────┐
│           Manager Agent (协调器)              │
│  1. 理解问题                                │
│  2. 分解任务                                │
│  3. 分派给专业 Agent                        │
│  4. 收集结果并汇总                          │
└──────────────────────┬──────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
    ▼                  ▼                  ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ SQL Agent   │  │ 运维 Agent   │  │ 诊断 Agent   │
│ (独立运行)  │  │ (独立运行)   │  │ (独立运行)   │
└─────────────┘  └─────────────┘  └─────────────┘
    │                  │                  │
    └──────────────────┴──────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   Manager 汇总   │
              │   返回最终答案    │
              └─────────────────┘
```

---

## 改造步骤

### Phase 1: 定义多 Agent 基础设施

#### 1.1 创建 Agent 基类
- 文件: `multiagents/agents/base_agent.py`
- 内容:
  - `BaseAgent` 抽象基类
  - `agent_id`: 唯一标识
  - `role`: Agent 角色
  - `capabilities`: Agent 能做什么
  - `chat()`: Agent 对话方法
  - `invoke_tool()`: Agent 调用工具方法

#### 1.2 创建 Agent 通信协议
- 文件: `multiagents/agents/message.py`
- 内容:
  - `Message` 消息类（sender, receiver, content, type）
  - `MessageQueue`: 消息队列
  - `AgentRegistry`: Agent 注册表

#### 1.3 创建 Manager Agent
- 文件: `multiagents/agents/manager.py`
- 内容:
  - 理解用户问题
  - 分解任务
  - 分派给专业 Agent
  - 等待结果
  - 汇总回答

---

### Phase 2: 实现专业 Agent

#### 2.1 SQL Expert Agent
- 文件: `multiagents/agents/sql_expert.py`
- 职责: 处理 SQL 相关问题
- 调用工具: 索引推荐、SQL 优化

#### 2.2 Cluster Expert Agent
- 文件: `multiagents/agents/cluster_expert.py`
- 职责: 处理集群相关问题
- 调用工具: 集群状态、节点信息

#### 2.3 Performance Expert Agent
- 文件: `multiagents/agents/performance_expert.py`
- 职责: 处理性能相关问题
- 调用工具: 慢查询分析、性能指标

---

### Phase 3: 实现 Agent 协作机制

#### 3.1 消息总线
- 文件: `multiagents/bus/message_bus.py`
- 功能:
  - Agent 间消息传递
  - 消息订阅/发布
  - 异步消息处理

#### 3.2 任务分派器
- 文件: `multiagents/scheduler/task_scheduler.py`
- 功能:
  - 接收 Manager 的任务分配
  - 协调多 Agent 并行执行
  - 收集结果返回给 Manager

#### 3.3 结果聚合器
- 文件: `multiagents/aggregator/result_aggregator.py`
- 功能:
  - 收集各 Agent 结果
  - 去重、排序
  - 生成最终回答

---

### Phase 4: 接口改造

#### 4.1 修改智能交互入口
- 文件: `controllers/core.py`
- 改动:
  - `intelligent_interaction_chat()` 改为调用 Manager Agent
  - 不再直接调用 DBA Agent

#### 4.2 添加 Agent 状态管理
- 文件: `global_vars.py`
- 添加:
  - `AGENT_REGISTRY`: Agent 注册表
  - `MESSAGE_BUS`: 消息总线实例

---

### Phase 5: 测试与部署

#### 5.1 单元测试
- 各 Agent 独立测试
- Agent 间通信测试
- Manager 协作测试

#### 5.2 集成测试
- 完整流程测试
- 并行执行测试
- 错误处理测试

---

## 文件清单

### 新增文件
| 文件路径 | 说明 |
|----------|------|
| `multiagents/agents/base_agent.py` | Agent 基类 |
| `multiagents/agents/manager.py` | Manager Agent |
| `multiagents/agents/sql_expert.py` | SQL Expert Agent |
| `multiagents/agents/cluster_expert.py` | Cluster Expert Agent |
| `multiagents/agents/performance_expert.py` | Performance Expert Agent |
| `multiagents/agents/message.py` | 消息类 |
| `multiagents/bus/message_bus.py` | 消息总线 |
| `multiagents/scheduler/task_scheduler.py` | 任务调度器 |
| `multiagents/aggregator/result_aggregator.py` | 结果聚合器 |

### 修改文件
| 文件路径 | 说明 |
|----------|------|
| `controllers/core.py` | 入口改为 Manager |
| `global_vars.py` | 添加 Agent 注册 |
| `multiagents/agents/dba.py` | 保留为 Legacy 或删除 |

---

## 预期效果

| 指标 | 改造前 | 改造后 |
|------|--------|--------|
| Agent 数量 | 1 | 4+ |
| 并行处理 | ❌ 不支持 | ✅ 支持 |
| 角色独立性 | ❌ 工具标签 | ✅ 真正独立 |
| 协作能力 | ❌ 无 | ✅ Agent 间通信 |

---

## 风险与挑战

1. **复杂性增加**: 从单 Agent 变为多 Agent，系统复杂度提升
2. **通信开销**: Agent 间消息传递带来额外延迟
3. **状态管理**: 多 Agent 状态同步困难
4. **调试难度**: 多 Agent 协作问题难以复现

---

## 建议实施顺序

1. **Phase 1 → 2 → 3 → 4 → 5** 顺序实施
2. 每个 Phase 完成后进行测试
3. 保留原有 DBA Agent 作为 Fallback
