# GaussMaster search\_vector 函数详解

## 函数概述

**位置**: `common/metadatabase/dao/gaussdb_vector.py` 第 177-198 行

**作用**: 执行**向量相似度搜索**，找到与查询语义最相似的文档

**核心原理**:

1. 将查询文本转为向量（Embedding）
2. 在向量数据库中计算相似度
3. 返回最相似的 Top-K 个文档

***

## 完整代码

```python
async def search_vector(self, query: str, topk: int, version="", embedding_key=None, distance=2):
    """Function vector search."""
    # 1. 确定使用哪个向量字段
    if not embedding_key:
        embedding_key = self.embedding_keys[0]
    
    # 2. 将查询文本转为向量
    embedding = await self.embedding_function.query_embedding(query)
    embedding_str = [str(num) for num in embedding]
    query_sql = '\'[' + ','.join(embedding_str) + ']\''
    
    # 3. 构建 SQL 查询
    sql = f'SELECT * FROM "{escape_double_quote(self.db_index)}" '
    if version:
        sql += f'WHERE version=\'{escape_single_quote(version)}\' '
    sql += f'ORDER BY "{escape_double_quote(embedding_key + "_vector")}" <-> {query_sql} LIMIT {topk}'
    
    # 4. 如果指定了距离阈值，使用范围查询
    if distance != 2:
        cur_fields = [f'"{escape_double_quote(field)}"' for field in self.fields]
        sql = f'SELECT "{escape_double_quote(embedding_key + "_vector")}" <-> {query_sql} as dist, ' \
              f'{(",".join(cur_fields))} FROM "{escape_double_quote(self.db_index)}" ' \
              f'where dist<={distance} ORDER BY dist LIMIT {topk}'
    
    # 5. 执行 SQL
    check_sql_valid(sql)
    self._connect()
    self.cur.execute(sql)
    result = self.cur.fetchall()
    self._close()
    
    return result
```

***

## 逐行解析

### 参数说明

| 参数              | 类型  | 默认值  | 说明             |
| --------------- | --- | ---- | -------------- |
| `query`         | str | 必填   | 用户查询文本         |
| `topk`          | int | 必填   | 返回最相似的 K 个结果   |
| `version`       | str | ""   | 文档版本过滤（可选）     |
| `embedding_key` | str | None | 使用哪个向量字段       |
| `distance`      | int | 2    | 距离阈值（默认2表示不限制） |

***

### 执行流程图解

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         search_vector 执行流程                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  输入: query="数据库性能优化方法", topk=3                                │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  1. 确定向量字段                      │                                │
│  │  embedding_key = self.embedding_keys[0]│
│  │  例如: "text_vector"                  │                                │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  2. 文本向量化                        │                                │
│  │  embedding = await embedding_function │                                │
│  │              .query_embedding(query)  │                                │
│  │  返回: [0.023, -0.156, 0.789, ...]   │  1024维向量                    │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  3. 构建 SQL                         │                                │
│  │  SELECT * FROM knowledge_base        │                                │
│  │  ORDER BY text_vector <-> '[0.023,   │                                │
│  │           -0.156, 0.789, ...]'       │                                │
│  │  LIMIT 3                             │                                │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  ┌─────────────────────────────────────┐                                │
│  │  4. 执行 SQL                         │                                │
│  │  self.cur.execute(sql)               │                                │
│  │  result = self.cur.fetchall()        │                                │
│  └─────────────────────────────────────┘                                │
│       ↓                                                                 │
│  输出: [(doc1), (doc2), (doc3)]  ← 最相似的3个文档                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

***

## 核心步骤详解

### 步骤1: 文本向量化

```python
embedding = await self.embedding_function.query_embedding(query)
```

**发生了什么**:

```
用户查询: "数据库性能优化方法"
    ↓
Embedding 模型（如 BGE-large）
    ↓
输出: [0.023, -0.156, 0.789, ..., 0.342]  ← 1024维向量
```

**向量的意义**:

- 每个数字代表文本在某个语义维度上的特征
- 相似的文本，向量距离近
- 不相似的文本，向量距离远

***

### 步骤2: 构建 SQL

#### 标准查询（按相似度排序）

```python
sql = f'SELECT * FROM "{self.db_index}" '
if version:
    sql += f'WHERE version=\'{version}\' '
sql += f'ORDER BY "{embedding_key}_vector" <-> {query_sql} LIMIT {topk}'
```

**生成的 SQL 示例**:

```sql
SELECT * FROM "knowledge_base" 
ORDER BY "text_vector" <-> '[0.023, -0.156, 0.789, ...]' 
LIMIT 3
```

**关键运算符** **`<->`**:

- PostgreSQL/openGauss 的向量距离运算符
- 计算两个向量的欧氏距离（L2距离）
- 距离越小，相似度越高

#### 带版本过滤的查询

```python
if version:
    sql += f'WHERE version=\'{version}\' '
```

**生成的 SQL 示例**:

```sql
SELECT * FROM "knowledge_base" 
WHERE version='v1.0' 
ORDER BY "text_vector" <-> '[0.023, -0.156, 0.789, ...]' 
LIMIT 3
```

#### 带距离阈值的查询

```python
if distance != 2:
    sql = f'SELECT "{embedding_key}_vector" <-> {query_sql} as dist, ' \
          f'... FROM "{self.db_index}" ' \
          f'where dist<={distance} ORDER BY dist LIMIT {topk}'
```

**生成的 SQL 示例**:

```sql
SELECT "text_vector" <-> '[0.023, ...]' as dist, uuid, title, text 
FROM "knowledge_base" 
WHERE dist <= 0.5 
ORDER BY dist 
LIMIT 3
```

**用途**: 只返回相似度足够高的结果，过滤低质量匹配

***

### 步骤3: 执行查询

```python
check_sql_valid(sql)      # SQL 安全检查
self._connect()           # 建立数据库连接
self.cur.execute(sql)     # 执行 SQL
result = self.cur.fetchall()  # 获取所有结果
self._close()             # 关闭连接
```

**返回结果格式**:

```python
[
    ('uuid_1', 'title_1', 'content_1', 'source_1', ..., [0.023, ...]),  # 文档1
    ('uuid_2', 'title_2', 'content_2', 'source_2', ..., [0.015, ...]),  # 文档2
    ('uuid_3', 'title_3', 'content_3', 'source_3', ..., [0.031, ...]),  # 文档3
]
```

***

## 向量相似度计算原理

### 欧氏距离 (L2 Distance)

```
向量 A: [a1, a2, a3, ..., an]
向量 B: [b1, b2, b3, ..., bn]

距离 = √((a1-b1)² + (a2-b2)² + ... + (an-bn)²)
```

**示例**:

```
查询向量: [1.0, 2.0, 3.0]
文档1向量: [1.1, 2.1, 3.1]  → 距离 = 0.17  ← 最相似
文档2向量: [2.0, 3.0, 4.0]  → 距离 = 1.73
文档3向量: [5.0, 6.0, 7.0]  → 距离 = 6.93
```

**SQL 中的** **`<->`** **运算符**:

- 就是计算这个欧氏距离
- `ORDER BY vector <-> query_vector` = 按距离从小到大排序
- 距离最小的 = 最相似的

***

## 完整调用链

```
用户提问: "数据库性能优化方法"
    ↓
search_vector("数据库性能优化方法", topk=3)
    ↓
┌─────────────────────────────────────┐
│  1. embedding_function.query_embedding │
│     "数据库性能优化方法" → [0.023, ...] │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  2. 构建 SQL                        │
│     SELECT * FROM knowledge_base    │
│     ORDER BY text_vector <-> [...]  │
│     LIMIT 3                         │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  3. 执行 SQL → 返回 Top-3 文档       │
└─────────────────────────────────────┘
    ↓
返回: [doc1, doc2, doc3]
```

***

## 对比 search\_text

| 函数              | 原理         | 优点    | 缺点              |
| --------------- | ---------- | ----- | --------------- |
| `search_vector` | 向量相似度      | 语义理解好 | 需要 Embedding 服务 |
| `search_text`   | BM25 关键词匹配 | 精确匹配  | 不理解语义           |

**search\_text 实现**:

```python
def search_text(self, query: str, topk: int, version=""):
    bm25_fields = ','.join(self.bm25_field)
    sql = f'SELECT * FROM "{self.db_index}" '
    if version:
        sql += f'WHERE version=\'{version}\' '
    sql += f'ORDER BY "{bm25_fields}" ### \'{query}\' desc LIMIT {topk}'
    # ### 是 openGauss 的全文检索运算符
    ...
```

***

## 一句话总结

> `search_vector` 是 RAG 的核心：将查询文本转为向量 → 在向量数据库中计算相似度 → 返回最相似的文档。使用 `<->` 运算符计算欧氏距离，距离越小相似度越高！

