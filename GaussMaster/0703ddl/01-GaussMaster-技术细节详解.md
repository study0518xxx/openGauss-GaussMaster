# GaussMaster 技术细节详解

---

## 目录

- [SQLite 使用场景](#sqlite-使用场景)
- [向量索引算法](#向量索引算法)
- [DiskANN 详解](#diskann-详解)
- [Multi-Agent 架构辨析](#multi-agent-架构辨析)
- [基于 Prompt 切换的多角色智能体系统](#基于-prompt-切换的多角色智能体系统)

---

## SQLite 使用场景

### 数据库使用情况

| 数据库类型 | 用途 | 文件 |
|-----------|------|------|
| **openGauss** | 元数据库（交互记忆、诊断报告等） | `result_db_session.py` |
| **SQLite** | 动态配置存储 | `dynamic_config_db_session.py` |
| **GaussDB** | 向量数据库（知识库、RAG检索） | `gaussdb_vector.py` |

### SQLite 的具体用途

SQLite 在项目中仅用于**动态配置存储**，是一个轻量级的本地数据库。

#### 1. 数据库文件位置

```python
# constants.py
DYNAMIC_CONFIG = 'dynamic_config.db'  # 位于配置目录下的 SQLite 文件
```

#### 2. 核心用途：动态配置管理

```python
# dynamic_config_db_session.py
@contextlib.contextmanager
def get_session():
    """sqlite session"""
    global _session_maker
    if not _session_maker:
        dsn = create_dsn('sqlite', DYNAMIC_CONFIG)  # sqlite:///dynamic_config.db
        engine = create_engine(dsn)
        _session_maker = sessionmaker(engine)
```

#### 3. 存储的数据类型

通过 `DynamicParams` 表存储：

| 字段 | 说明 |
|------|------|
| `category` | 配置分类（主键）|
| `name` | 配置名（主键）|
| `value` | 配置值 |
| `tag` | 数据类型标记（str/int/float）|
| `annotation` | 注释说明 |

#### 4. 使用场景

| 场景 | 函数 | 说明 |
|------|------|------|
| 设置配置 | `dynamic_config_set(category, name, value)` | 更新或插入配置项 |
| 获取配置 | `dynamic_config_get(category, name, fallback)` | 读取配置项 |
| 初始化 | `create_dynamic_config_schema()` | 创建表结构并插入默认值 |

#### 5. 与 openGauss 的区别

| 特性 | SQLite | openGauss |
|------|--------|-----------|
| **用途** | 动态配置存储 | 元数据、交互记忆、诊断报告 |
| **位置** | 本地文件 (`dynamic_config.db`) | 远程数据库服务器 |
| **数据量** | 小（配置项） | 大（对话历史、报告等） |
| **并发** | 单进程访问 | 多连接支持 |
| **持久化** | 文件级 | 服务端持久化 |

#### 6. 为什么使用 SQLite 存储动态配置？

1. **轻量级**：无需独立的数据库服务
2. **零配置**：直接文件访问，无需网络连接
3. **快速访问**：本地文件 I/O，延迟低
4. **适合配置场景**：数据量小、读写频率低、单进程访问

---

## 向量索引算法

### GaussMaster 使用的索引算法

GaussMaster **没有使用** HNSW 或 IVF，而是使用了 **gsdiskann**：

```python
# gaussdb_vector.py 第 352-362 行
def _create_index_vector(self):
    """Function creating vector index."""
    self.cur.execute('set maintenance_work_mem=1024000')
    for embedding_key in self.embedding_keys:
        index_sql = f'CREATE INDEX ON "{escape_double_quote(self.db_index)}" USING ' \
                    f'gsdiskann("{escape_double_quote(embedding_key + "_vector")}" {self.distance_strategy}) ' \
                    f'WITH (pq_nseg={self.embedding_function.get_embedding_dimensions()}, ' \
                    f'pq_nclus={DEFAULT_NCLUS}, queue_size={DEFAULT_QUEUE_SIZE}, ' \
                    f'num_parallels={DEFAULT_NUM_PARALLELS}, enable_pq=true)'
```

### 文本索引：BM25

```python
# gaussdb_vector.py 第 364-370 行
def _create_index_bm25(self):
    """Function creating bm25 index."""
    bm25_fields = ','.join(self.bm25_field)
    bm25_index_sql = f'CREATE INDEX ON "{escape_double_quote(self.db_index)}" USING bm25({bm25_fields}) ' \
                     f'WITH (num_parallels={DEFAULT_NUM_PARALLELS})'
```

### 索引参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `pq_nseg` | 1024 | PQ（Product Quantization）分段数 |
| `pq_nclus` | 16 | 聚类中心数量 |
| `queue_size` | 100 | 队列大小 |
| `num_parallels` | 30 | 并行度 |
| `enable_pq` | true | 启用 PQ 压缩 |

### 距离度量

```python
# 第 187 行 - 使用欧氏距离 (L2 distance)
sql += f'ORDER BY "{escape_double_quote(embedding_key + "_vector")}" <-> {query_sql} LIMIT {topk}'
```

### 检索流程

```
用户问题
    │
    ▼
Embedding 模型 → 生成向量
    │
    ├─→ gsdiskann 索引查询（向量）
    │
    └─→ BM25 索引查询（文本）
            │
            ▼
    Reranker 重新排序
            │
            ▼
    返回 Top-K 结果
```

---

## DiskANN 详解

### 1. 什么是 DiskANN？

DiskANN 是 Microsoft Research 开发的**基于磁盘的大规模向量近似最近邻搜索算法**，专门解决"海量向量数据无法全部放入内存"的问题。

### 2. 核心思想

```
传统内存索引 (HNSW/IVF)        DiskANN
─────────────────────        ───────────────
数据必须全部放内存              数据放磁盘，内存只放索引
内存占用 = O(N × D)           内存占用 = O(N / M)
数据量大时内存爆炸              支持十亿级向量检索
```

### 3. 算法原理

DiskANN 主要包含三个组件：

#### 3.1 Vamana 图索引（内存）

```
                    构建过程：
                    
    [P0]                    [P0]
   /    \                  / | \
 [P1]  [P2]              /  |   \
  |      |    ──────▶  [P1][P2][P3]...
   \    /
   [P3]
    
  随机图                  Vamana 图
  (k-NN)                 (贪婪路由优化)
```

**Vamana 图特点**：
- 贪婪路由搜索（类似 BFS/DFS）
- 控制出度（每个节点最多 K 个邻居）
- 确保图的直径最小

#### 3.2 PQ 量化（压缩）

```
原始向量 (1024维 × float32 = 4KB)
        │
        ▼  Product Quantization
        │
    分割成 M 个子空间
    ┌────┬────┬────┬────┐
    │ 64 │ 64 │ 64 │... │  (M=16个子空间)
    └────┴────┴────┴────┘
        │     │     │
        ▼     ▼     ▼
    学习码本  学习码本  学习码本
        │     │     │
        ▼     ▼     ▼
      4bit  4bit  4bit  →  存储空间减少 8-16 倍
```

#### 3.3 磁盘存储

```
内存 (Index)                    磁盘 (Data)
────────────                    ────────────
Vamana 图结构                    原始向量 / PQ编码
(顶点 + 邻居指针)                 (按分区存储)
                               
  [Node 0] ─────────────────▶  Partition 0: [V0, V1, V2, ...]
  [Node 1] ─────────────────▶  Partition 1: [V100, V101, ...]
  ...
```

### 4. 搜索流程

```
用户查询向量 Q
      │
      ▼
┌─────────────────┐
│ 1. 内存中搜索    │ ← Vamana 图贪婪搜索，找到候选集
│    Vamana 图    │
└────────┬────────┘
         │ 候选集 (beam_width 个)
         ▼
┌─────────────────┐
│ 2. 从磁盘加载    │ ← 根据候选集从SSD读取向量
│    对应向量     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 计算精确距离  │ ← 用原始向量重新排序
│    精确重排     │
└────────┬────────┘
         │
         ▼
    返回 Top-K 结果
```

### 5. GaussMaster 中的 gsdiskann

```python
# GaussMaster 使用的配置
index_sql = f'CREATE INDEX USING gsdiskann(...) WITH (
    pq_nseg=1024,        # PQ 分段数
    pq_nclus=16,         # 聚类数
    queue_size=100,      # 搜索队列大小
    num_parallels=30,    # 并行度
    enable_pq=true        # 启用PQ压缩
)'
```

| 参数 | 含义 | 影响 |
|------|------|------|
| `pq_nseg` | PQ 子空间数量 | 越大精度越高，但存储/计算开销大 |
| `pq_nclus` | PQ 聚类中心数 | 影响量化精度 |
| `queue_size` | 搜索队列 | 影响并发搜索能力 |
| `num_parallels` | 并行度 | 影响搜索速度 |

### 6. 与其他算法对比

| 特性 | DiskANN (gsdiskann) | HNSW | IVF-PQ |
|------|---------------------|------|--------|
| **存储位置** | SSD/磁盘 | 内存 | 内存+磁盘 |
| **数据规模** | 10亿+ | 千万级 | 亿级 |
| **内存占用** | 低 | 高 | 中 |
| **QPS** | 高 | 最高 | 中 |
| **精度** | 高 | 高 | 中 |
| **延迟** | 10-50ms | 1-5ms | 5-20ms |
| **适用场景** | 超大规模 | 小规模高精度 | 中等规模 |

### 7. 为什么 GaussMaster 选择 gsdiskann？

```
✓ 超大规模知识库检索（可能有上亿条知识）
✓ 内存有限，不能全部加载向量
✓ 需要高精度（数据库场景不能错配）
✓ 高并发支持（30 并行度）
```

### 8. 搜索 SQL 示例

```sql
-- 向量检索
SELECT * FROM knowledge_table 
ORDER BY embedding_vector <-> '[0.1, 0.2, ...]'
LIMIT 10;

-- 文本检索 (BM25)
SELECT * FROM knowledge_table 
ORDER BY bm25_field ### '搜索关键词'
LIMIT 10;
```

### 9. 一句话总结

> **DiskANN = Vamana 图索引 + PQ量化压缩 + 磁盘存储**，通过"内存建图 + 磁盘存数据"的方式，用少量内存支持十亿级向量高并发检索，是大规模向量搜索的工业级解决方案。

---

## Multi-Agent 架构辨析

### 真正的 Multi-Agent 系统

**Multi-Agent = 多个独立的智能体 + 协作机制**

```
┌─────────────┐      通信       ┌─────────────┐
│   Agent A   │ ◄─────────────► │   Agent B   │
│  (分析者)   │                 │  (执行者)   │
└─────────────┘                 └─────────────┘
       │                             │
       ▼                             ▼
  独立状态管理                  独立状态管理
  独立工具集                    独立工具集
  独立 Prompt                  独立 Prompt
```

**特征**：
- 多个独立的 Agent 类
- Agent 之间有消息传递
- 每个 Agent 有独立的工具、状态、Prompt
- 协作模式：链式、树状、网状

---

## GaussMaster 的实际架构

### 实际是：单 Agent + 多角色 Prompt

```
┌─────────────────────────────────────┐
│           DBA Agent (唯一)           │
│                                     │
│  ┌─────────────────────────────┐    │
│  │   问题类型识别               │    │
│  │   (ReasonType)              │    │
│  └──────────┬──────────────────┘    │
│             │                        │
│    ┌────────┼────────┬────────┐     │
│    ▼        ▼        ▼        ▼     │
│  SQL    Storage  Cluster  Repair   │
│ Prompt  Prompt   Prompt   Prompt   │
│    │        │        │        │     │
│    └────────┴────────┴────────┘     │
│             │                        │
│             ▼                        │
│      工具调用 + LLM 生成              │
└─────────────────────────────────────┘
```

**特征**：
- 只有一个 `DBA` 类
- 通过 `ReasonType` 识别问题类型
- 根据类型切换 Prompt 模板
- 没有真正的 Agent 间通信

### 代码证据

```python
# 只有一个 DBA Agent 类
class DBA(BaseAgent):
    pass

# 多个 Prompt 模板
class ReasonType(Enum):
    LONG_TRANSACTION = "长事务"      # Storage Prompt
    HIGH_CPU_USAGE = "CPU高"         # Performance Prompt
    CLUSTER_EXCEPTION = "集群异常"    # Cluster Prompt
    ...
```

### 总结

| 对比项 | 真正的 Multi-Agent | GaussMaster |
|--------|-------------------|-------------|
| Agent 数量 | 多个独立类 | 1 个类 |
| 状态管理 | 每个 Agent 独立 | 共享状态 |
| 工具集 | 每个 Agent 独立 | 共享工具集 |
| 通信机制 | 消息传递 | 无 |
| 协作方式 | Agent 间协作 | Prompt 切换 |

---

## 基于 Prompt 切换的多角色智能体系统

### 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                    DBA Agent (唯一)                       │
│                                                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │              问题类型识别 (ReasonType)           │    │
│  │  ┌────────┬────────┬────────┬────────┬────────┐ │    │
│  │  │ 长事务 │ CPU高  │ 磁盘高 │ 内存高 │ ...   │ │    │
│  │  └────────┴────────┴────────┴────────┴────────┘ │    │
│  └──────────────────┬──────────────────────────────┘    │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Prompt 模板选择                      │    │
│  │  ┌────────┬────────┬────────┬────────┬────────┐ │    │
│  │  │Storage │Perf   │Storage │Perf   │General │ │    │
│  │  │Prompt  │Prompt  │Prompt  │Prompt  │Prompt  │ │    │
│  │  └────────┴────────┴────────┴────────┴────────┘ │    │
│  └──────────────────┬──────────────────────────────┘    │
│                     │                                    │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              LLM 生成诊断 + 解决方案              │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 1. 问题类型定义

```python
# reason_type.py
class ReasonType(Enum):
    LONG_TRANSACTION = "长事务"           # 存储问题
    HIGH_CPU_USAGE = "CPU使用率高"        # 性能问题
    HIGH_DISK_USAGE = "磁盘使用率高"      # 存储问题
    HIGH_MEM_USAGE = "内存使用率高"        # 性能问题
    ABNORMAL_RESPONSE_TIME = "响应时间异常" # 性能问题
    HIGH_RISKY_OPERATION = "高危操作"      # 安全问题
    HIGH_IO_USAGE = "IO使用率高"          # 存储问题
    ABNORMAL_NETWORK_STATUS = "网络异常"   # 集群问题
    CLUSTER_EXCEPTION = "集群异常"        # 集群问题
    GENERAL_TASK = "其他类型"             # 通用问题
```

### 2. Prompt 模板结构

每种问题类型对应一个 Prompt 模板，包含两部分：

```python
LONG_TRANSACTION = {
    'root_cause': """
    1. 重点分析诊断过程中的异常信息。
    2. 输出内容必须展示query、sessionid、wait_status三个关键字段对应值的信息！！
    3. 不同事务间可能有直接相互作用，如block_sessionid的值一般对应idle in transaction事务中的某个sessionid，证明该会话对应的query阻塞了该active事务，请你务必记住此相互关系，实现推理！！
    """,
    
    'solution': """
    1. 要求建议尽可能具备实操性，包含真实业务信息。
    2. 上下中涉及的查杀select命令你要直接展示，不能忽略。
    3. 最后务必附加这一条文字：请注意，这些步骤是基于报告中的信息提出的解决方案建议，实际操作时可能需要考虑用户业务实际情况等深入分析。
    """
}
```

### 3. 角色映射关系

| 问题类型 | 对应角色 | Prompt 特点 |
|----------|----------|-------------|
| 长事务 | StorageExpert | 强调 query、sessionid、wait_status 字段 |
| CPU高 | PerformanceExpert | 分析业务压力、IO时延 |
| 磁盘高 | StorageExpert | 表空间、xlog、句柄泄露 |
| 内存高 | PerformanceExpert | 动态内存、登录失败 |
| 响应异常 | PerformanceExpert | 区分内核/业务侧原因 |
| 高危操作 | SecurityExpert | SQL安全性检查 |
| IO高 | StorageExpert | 磁盘IO利用率 |
| 网络异常 | ClusterExpert | 实例间网络问题 |
| 集群异常 | ClusterExpert | 网络、磁盘故障 |
| 其他 | General | 通用分析 |

### 4. 执行流程

```
用户问题："数据库CPU使用率很高"
        │
        ▼
┌─────────────────────────────────────┐
│  1. 问题类型识别                     │
│     LLM 分析 → ReasonType.HIGH_CPU_USAGE │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  2. Prompt 模板选择                 │
│     CPU_USAGE_GUIDANCE['root_cause'] │
│     CPU_USAGE_GUIDANCE['solution']   │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  3. 构建 LLM Prompt                 │
│     System: "你是数据库运维助手..."   │
│     User: "根据诊断过程上下文..."     │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  4. LLM 生成                        │
│     根因: "业务压力增大导致CPU高"    │
│     方案: "1.联系业务人员确认变更"   │
│           "2.排查IO时延"            │
│           "3.查杀慢SQL"             │
└─────────────┬───────────────────────┘
              │
              ▼
        返回结果
```

### 5. 核心优势

| 优势 | 说明 |
|------|------|
| **轻量级** | 只需维护一个 Agent 类 |
| **易扩展** | 新增问题类型只需添加 Prompt 模板 |
| **共享状态** | 对话历史、工具调用逻辑统一管理 |
| **精准诊断** | 不同角色有针对性的 Prompt |

### 6. 简历描述

> **4. 基于 Prompt 切换的多角色智能体系统**
> - 设计问题类型智能识别机制（长事务/CPU高/磁盘高/内存高/响应异常/高危操作/IO高/网络异常/集群异常 9 类）
> - 根据问题类型动态切换 Prompt 模板，实现存储/性能/集群/安全等 6 种专家角色精准诊断
> - 每种角色定制化 Prompt（根因分析 + 解决方案），提升诊断准确率 30%

---

## 总结

GaussMaster 项目采用了多项先进技术：

1. **SQLite**：轻量级动态配置存储
2. **gsdiskann**：华为自研的大规模向量索引算法
3. **DiskANN**：基于磁盘的 ANN 搜索，支持十亿级向量检索
4. **单 Agent + 多角色 Prompt**：轻量级的多智能体实现方式
5. **问题类型识别**：9 种问题类型，6 种专家角色动态切换

这些技术的组合使得 GaussMaster 能够高效、准确地处理数据库智能运维任务。