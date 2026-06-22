# 备选：PostgreSQL + 向量数据库 通用面试题

---

## 一、PostgreSQL 高频面试题

### 1. PostgreSQL 和 MySQL 的区别

| | PostgreSQL | MySQL |
|---|---|---|
| 开源协议 | PostgreSQL License（自由） | GPL（Oracle 控制） |
| ACID | 完整支持，DDL 也支持事务 | InnoDB 支持，MyISAM 不支持 |
| 并发控制 | MVCC（多版本并发控制），无读写锁 | MVCC + 间隙锁 |
| JSON | JSONB 支持索引 | JSON 支持但索引不如 PG |
| 扩展 | 丰富（PostGIS、pgvector、TimescaleDB） | 较少 |
| 复杂查询 | CTE、窗口函数、递归查询、LATERAL | 较弱 |
| 复制 | 流复制、逻辑复制 | 主从复制、Group Replication |
| 适用 | 复杂查询、地理数据、时序、分析 | 简单 OLTP、互联网 CRUD |

**面试一句话**："MySQL 更适合简单读写，PG 更适合需要复杂查询、扩展能力的场景。我们选 PG 做向量数据库就是因为它的扩展机制。"

---

### 2. MVCC 是什么？PG 怎么实现的

```
MVCC = 不直接修改数据，而是写入新版本，保留旧版本。

PG 做法: 每行数据有 xmin（插入事务 ID）和 xmax（删除事务 ID）
  INSERT → 新行，xmin = 当前事务 ID
  UPDATE → 旧行 xmax = 当前事务 ID，插入新行 xmin = 当前事务 ID
  DELETE → 该行 xmax = 当前事务 ID

读取时: 只读 xmin < 当前事务 ID 且 xmax 为空或 > 当前事务 ID 的行
```

**优点**：读不阻塞写，写不阻塞读。

**缺点**：旧版本需要 VACUUM 清理，不然膨胀。

---

### 3. 索引类型

| 索引 | 适用 | 举例 |
|------|------|------|
| B-Tree | 等值、范围查询 | `WHERE id = 123` |
| Hash | 等值查询 | `WHERE email = 'a@b.com'` |
| GIN | 全文搜索、数组、JSONB | `WHERE tags @> ARRAY['cpu']` |
| GiST | 地理空间、全文搜索 | `WHERE geo && ST_MakeEnvelope(...)` |
| BRIN | 大表顺序数据 | `WHERE created_at BETWEEN ...` |
| 部分索引 | 只索引部分行 | `WHERE status = 'active'` |
| 覆盖索引 | 索引包含查询列，不回表 | `INCLUDE (title)` |

---

### 4. EXPLAIN 怎么看

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@test.com';
```

关注三个点：

```
Seq Scan → 全表扫描，大概率需要建索引
Index Scan → 用索引找到行，然后回表读完整行
Index Only Scan → 索引里就有所有需要的列，不回表（最快）

还要看:
  cost=0.00..1.00  → 预估代价
  rows=1           → 预估行数
  actual time=0.01 → 实际执行时间
  buffers=4        → 读了多少个数据页
```

---

### 5. 连接池为什么需要

PG 每个连接 fork 一个进程，占 5-10MB 内存。1000 个连接 = 5-10GB 内存没了。

| 方案 | 做法 |
|------|------|
| PgBouncer | 轻量级连接池，事务模式最常用 |
| Pgpool-II | 连接池 + 读写分离 + 负载均衡 |
| 应用层 | SQLAlchemy pool_size + max_overflow |

**为什么不用 MySQL 那样直接 1000 连接**：MySQL 是线程模型，一个连接只占几百 KB。PG 是进程模型，贵得多。

---

### 6. VACUUM 干什么

```
DELETE 不会真正删除行，只是标记 xmax = 事务 ID
旧版本一直堆着 → 表膨胀、查询变慢、事务 ID 回卷风险

VACUUM: 标记旧版本的空间为"可复用"，不归还磁盘
VACUUM FULL: 重写整张表，归还磁盘（会锁表）
AUTOVACUUM: 自动执行，默认开启
```

---

### 7. 主从复制

| 方式 | 做法 |
|------|------|
| 流复制 | WAL 日志从主库实时传到备库，备库只读 |
| 逻辑复制 | 按表级别复制，可以部分表复制，跨版本 |
| 同步复制 | 备库确认收到 WAL 才返回客户端，不丢数据但慢 |

---

### 8. JSONB 怎么用

```sql
-- 存
INSERT INTO logs (data) VALUES ('{"cpu": 80, "instance": "db_001"}');

-- 查
SELECT * FROM logs WHERE data->>'cpu' = '80';
SELECT * FROM logs WHERE data @> '{"instance": "db_001"}';

-- 索引
CREATE INDEX ON logs USING GIN (data);
```

**和 MongoDB 的区别**：JSONB 能做 JOIN 和事务，MongoDB 的分片和水平扩展更强。

---

## 二、向量数据库高频面试题

### 1. 向量数据库和传统数据库的区别

```
传统数据库: 精确匹配
  WHERE name = 'CPU'

向量数据库: 相似搜索
  ORDER BY embedding <-> query_vector LIMIT 10
  → 返回 "CPU"、"处理器"、"中央处理器" 等意思相近的结果
```

本质区别：传统 DB 的索引是 B-Tree（排序树），向量 DB 的索引是 ANN（近似最近邻图）。

---

### 2. ANN（近似最近邻）和 KNN（精确最近邻）

```
KNN: 查询向量和库里的 N 个向量逐一算距离，选最近的 K 个
  O(N) 复杂度，100 万条 = 100 万次距离计算

ANN: 提前建索引（图/聚类），搜索时只走索引路径
  O(log N) 复杂度，100 万条 = 几十到几百次距离计算
  精度损失 1-5%，但速度快 100-1000 倍
```

**为什么接受近似**：RAG 场景取 Top-3，Top-3 里有一个相关就够了。不需要精确找第 4 名。

---

### 3. 主流向量索引类型

| 索引 | 原理 | 代表 | 适用 |
|------|------|------|------|
| IVFFlat | K-means 聚类，只搜最近的簇 | pgvector IVFFlat | 百万级 |
| HNSW | 多层图，上层跳远下层精细搜 | pgvector HNSW、Chroma、Milvus | 百万到千万 |
| DiskANN | 图上磁盘，PQ 压缩 | GSDiskANN | 千万到十亿 |
| ScaNN | 各向异性量化，Google 出品 | Vertex AI | 十亿级 |

---

### 4. 什么时候不需要向量数据库

```
精确匹配场景 → 不需要
  "查用户 ID=123 的订单" → B-Tree 索引就够了

少量数据 → 不需要
  几千条数据 → numpy 手写 KNN 比部署向量数据库快

只有结构化数据 → 不需要
  纯数字/日期/枚举 → 传统索引
```

---

### 5. Chroma / Milvus / pgvector / Pinecone 对比

| | Chroma | Milvus | pgvector | Pinecone |
|---|---|---|---|---|
| 类型 | 嵌入式 | 独立服务 | PG 扩展 | SaaS |
| 部署 | pip install | Docker/K8s | CREATE EXTENSION | 托管 |
| 索引 | HNSW | HNSW/IVF/DiskANN | HNSW/IVFFlat | 托管 |
| 过滤 | 简单 | 强 | 原生 SQL WHERE | 强 |
| 适用 | 开发/原型 | 生产 | 已有 PG | 不想管运维 |

**GaussMaster 的选型逻辑**：已部署 PG → 不需要新组件 → 选 pgvector/openGauss 方案。

---

### 6. embedding 维度怎么选

| 维度 | 模型 | 效果 | 存储（百万条） |
|------|------|------|-------------|
| 384 | all-MiniLM-L6 | 还行 | ~1.5GB |
| 768 | BGE-base / text2vec | 好 | ~3GB |
| 1024 | BGE-large | 更好 | ~4GB |
| 1536 | OpenAI ada-002 | 最好 | ~6GB |

**选型逻辑**：不只是比效果——要算存储和延迟。1024 维 4GB 加上索引结构 10GB+，512 维减半但可能丢精度。1024 是多数生产场景的平衡点。

---

### 7. 向量检索 + 元数据过滤怎么同时做

```
场景: "在 v2.1 文档中搜 CPU 排查方法"

错误做法（先向量后过滤）:
  SELECT * FROM gauss_kb ORDER BY vec <-> query LIMIT 10;
  → 在应用层筛选 version = 'v2.1'
  → 问题: 可能 10 条里没有一条是 v2.1 的

正确做法（同一条 SQL）:
  SELECT * FROM gauss_kb
  WHERE version = 'v2.1'
  ORDER BY vec <-> query LIMIT 10;
  → 需要 version 也有索引，否则先全表过滤再向量搜

更优做法（生产级）:
  先走 version 的 B-Tree 索引 → 过滤到几百条
  → 再走向量索引精确搜 → 取 Top-10
```

---

### 8. 怎么评估向量检索好不好

| 指标 | 含义 |
|------|------|
| Recall@K | 正确答案在 Top-K 里出现的比例（越高越好） |
| QPS | 每秒查询数 |
| P99 延迟 | 99% 的查询在多少 ms 内完成 |
| 内存 | 索引占多少内存 |
| 建索引时间 | 全量重建要多久 |

**面试时说**："我们在 400 个银行标注 QA 对上跑 Recall@3，目标是 85%+。达不到就调 chunk_size、换 embedding 模型、加 reranker——有闭环。"

---

### 9. 向量数据会不会过期

会。两个场景：

```
① 文档更新了（v2.0 → v2.1）
  → 旧的向量块还在库里，搜出来是过期答案
  → 解决: 按版本过滤 WHERE version = 'v2.1'

② embedding 模型升级了（BGE-large → BGE-M3）
  → 旧向量是旧模型生成的，和新模型生成的查询向量不在同一个语义空间
  → 解决: 全量重新向量化，不能混合用
```
