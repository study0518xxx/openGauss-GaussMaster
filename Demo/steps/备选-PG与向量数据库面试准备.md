# 备选：PostgreSQL + 向量数据库 面试准备

> 围绕 GaussMaster 用 openGauss（PostgreSQL 兼容）做向量数据库这个技术选型，面试官最可能追问的方向。

---

## 一、为什么用 PostgreSQL 做向量数据库

### 核心论点

**不做加法，做减法。** 大部分 RAG 项目是 "PostgreSQL + Milvus + Elasticsearch" 三个系统。GaussMaster 只有一个——openGauss 自身。

### 一张表搞定全部

```sql
CREATE TABLE gauss_kb (
    uuid        TEXT,
    title       TEXT,
    text        TEXT,                        -- 原文
    text_vector floatvector(1024),           -- 1024 维向量列
    version     TEXT,
    prev_uuid   TEXT,                        -- 前一块 ID
    next_uuid   TEXT                         -- 后一块 ID
);

-- 同一个字段建两种索引
CREATE INDEX ON gauss_kb USING gsdiskann(text_vector l2);  -- 向量索引
CREATE INDEX ON gauss_kb USING bm25(text);                  -- 全文索引
```

### 对比

| 方案 | 组件数 | 数据同步 | 运维复杂度 |
|------|--------|---------|-----------|
| 典型方案: PG + Milvus + ES | 3 | 向量写 PG 和 Milvus 两份，BM25 写 PG 和 ES 两份 | 三个系统的备份、扩容、监控 |
| GaussMaster: 纯 openGauss | 1 | 一次写入 | 运维团队已熟悉 PG |

---

## 二、pgvector vs openGauss floatvector

### pgvector（标准 PostgreSQL 扩展）

```sql
CREATE EXTENSION vector;

CREATE TABLE items (
    id    BIGSERIAL PRIMARY KEY,
    embedding vector(1024)    -- pgvector 类型
);

-- 索引
CREATE INDEX ON items USING hnsw (embedding vector_l2_ops);
CREATE INDEX ON items USING ivfflat (embedding vector_l2_ops);

-- 检索
SELECT * FROM items ORDER BY embedding <-> '[0.1, ...]' LIMIT 10;
```

| 索引 | 原理 | 适合 |
|------|------|------|
| IVFFlat | 聚类后只搜最近的几个簇 | 百万级，精度可调 |
| HNSW | 分层图搜索 | 百万级，精度高但内存大 |

### openGauss floatvector（GaussMaster 用的）

```sql
CREATE TABLE gauss_kb (text_vector floatvector(1024));

CREATE INDEX ON gauss_kb USING gsdiskann(text_vector l2) WITH (
    pq_nseg=1024, pq_nclus=16, enable_pq=true
);

SELECT * FROM gauss_kb ORDER BY text_vector <-> '[0.1, ...]' LIMIT 10;
```

| 特性 | pgvector HNSW | openGauss GSDiskANN |
|------|--------------|-------------------|
| 索引位置 | 内存 | 磁盘 + 内存缓存 |
| 压缩 | 无 | PQ 压缩（8:1~16:1） |
| 数据量 | 百万级 | 百万到十亿 |
| 操作符 | `<->` | `<->`（PG 兼容） |
| 部署 | `CREATE EXTENSION vector` | 内核自带 |

**GaussMaster 为什么用 GSDiskANN 不用 pgvector HNSW**：银行百万级文档，HNSW 全内存扛不住。PQ 压缩后内存从 10GB 降到 500MB。

---

## 三、距离度量：L2 vs 余弦 vs 内积

| 距离 | 操作符 | 公式 | 特点 |
|------|--------|------|------|
| L2 | `<->` | √Σ(ai-bi)² | 看绝对差异 |
| 余弦 | `<=>` | 1 - cos(a,b) | 只看方向 |
| 内积 | `<#>` | -a·b | 归一化后 = 余弦 |

### 怎么选

```
文本 embedding（已归一化）→ L2 和余弦等价，选哪个都一样
图片 embedding（未归一化）→ L2 能感知亮度差异，余弦只看形状
推荐/搜索排序            → 内积，分数越大越相关
```

GaussMaster 用 L2 原因：BGE embedding 做了归一化，L2 = 余弦；openGauss GSDiskANN 默认支持 L2。

### 面试时说

> embedding 做了 L2 归一化后，向量长度 = 1。此时余弦相似度退化成点积，L2 距离和余弦排序等价。用 L2 纯粹因为 GSDiskANN 索引就是按 L2 建的。

---

## 四、向量检索 + 传统 SQL 混合查询

### 单独向量检索

```sql
SELECT * FROM gauss_kb
ORDER BY text_vector <-> query_vec LIMIT 10;
```

### 加过滤条件（生产环境常用）

```sql
-- 只看某个版本文档
SELECT * FROM gauss_kb
WHERE version = 'v2.1'
ORDER BY text_vector <-> query_vec LIMIT 10;

-- 只看某个产品的文档
SELECT * FROM gauss_kb
WHERE product_format = 'GaussDB'
ORDER BY text_vector <-> query_vec LIMIT 10;
```

**这恰恰是 PostgreSQL 做向量数据库的最大优势**——向量搜索和传统 SQL 过滤在一条语句里完成。Milvus 要做过滤需要额外配置 scalar index。

---

## 五、BM25 全文索引 + 向量混合

### 为什么向量不够

```
用户搜: "pg_stat_activity 的用法"

向量检索可能返回:
  ① pg_stat_user_tables 的用法（名字像，向量距离近，但功能不同！）
  ② pg_stat_database 的参数说明（同上）
  ③ pg_stat_activity 官方文档（真正的答案，但向量距离可能排第三）

BM25 关键词检索:
  ① pg_stat_activity 官方文档（精确命中关键词，排第一）
```

向量擅长 "意思像"，BM25 擅长 "关键词准"。两路互补。

### 实战 SQL

```sql
-- 向量: 语义匹配
SELECT *, text_vector <-> query_vec AS distance
FROM gauss_kb ORDER BY distance LIMIT 10;

-- BM25: 关键词匹配
SELECT *, text ### 'pg_stat_activity 用法' AS score
FROM gauss_kb ORDER BY score DESC LIMIT 10;

-- 生产环境: 两路各自检索，应用层合并去重后送 reranker
```

### 面试时说

> 我们不是两条 SQL 拼完就完事。两路各取 Top-10，合并去重得到 15-18 个候选，再用微调的 BGE-reranker 交叉打分。最后取 Top-3 送 LLM，每个命中块还会通过 prev_uuid / next_uuid 拽出相邻块拼接。表面是 3 块，实际 LLM 看到 5-9 块。

---

## 六、向量索引性能调优

### pgvector 常用参数

```sql
-- HNSW
CREATE INDEX ON items USING hnsw (embedding vector_l2_ops)
WITH (m = 16, ef_construction = 200);

-- m: 每个节点的最大连接数（越大精度越高，内存越大）
-- ef_construction: 建索引时的搜索深度（越大精度越高，建索引越慢）
```

### openGauss GSDiskANN 常用参数

```sql
CREATE INDEX ON gauss_kb USING gsdiskann(text_vector l2)
WITH (
    pq_nseg=1024,      -- PQ 段数，= 维度数
    pq_nclus=16,       -- 聚类数，越大精度越高内存越大
    queue_size=100,    -- 搜索队列大小
    num_parallels=30,  -- 并行度
    enable_pq=true     -- 开启乘积量化
);
```

### 面试时说

> pq_nclus=16 是经验值——在 1614 个测试问题上，16 个聚类中心的搜索精度只比原始向量低 3-5%，但内存降低 8 倍。queue_size=100 控制了搜索时的优先队列大小——越大越准但也越慢，100 是延迟和精度的平衡点。

---

## 七、常见追问

### Q: pgvector 和 Milvus 怎么选？

| | pgvector | Milvus |
|---|---|---|
| 部署 | 已有 PG 直接加扩展 | 独立服务 |
| 数据量 | 百万级 | 十亿级 |
| 过滤 | 原生 SQL WHERE | 需配置 scalar index |
| 一致性 | 事务内强一致 | 最终一致 |
| 适用 | 数据量中等、需要和业务表联合查 | 海量向量、纯向量搜索 |

**选型思路**：数据量不大（<1000 万）且需要和业务数据联合查 → pgvector。海量纯向量搜索 → Milvus。GaussMaster 两个因素都占了——百万级 + 需要和 BM25 同表联合查。

### Q: 向量索引建了之后，插入新数据需要重建吗？

HNSW/GSDiskANN 都支持增量插入，不需要全量重建。但频繁插入后索引质量会下降——建议定期 REINDEX。

### Q: 你们怎么避免全表扫描？

向量索引不是 B-Tree——`ORDER BY vector <-> query_vec LIMIT 10` 走的是 GSDiskANN 近似搜索，不是逐行算 L2 距离。但如果加了 `WHERE version = 'v2.1'` 过滤条件，需要额外建版本号的 B-Tree 索引，查询计划才能先过滤再向量搜索。
