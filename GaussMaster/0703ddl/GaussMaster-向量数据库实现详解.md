# GaussMaster 向量数据库实现详解

## 1. `_create_index_vector` 方法解析

```python
def _create_index_vector(self):
    """Function creating vector index."""
    self.cur.execute('set maintenance_work_mem=1024000')
    for embedding_key in self.embedding_keys:
        index_sql = f'CREATE INDEX ON "{escape_double_quote(self.db_index)}" USING ' \
                    f'gsdiskann("{escape_double_quote(embedding_key + "_vector")}" {self.distance_strategy}) ' \
                    f'WITH (pq_nseg={self.embedding_function.get_embedding_dimensions()}, ' \
                    f'pq_nclus={DEFAULT_NCLUS}, queue_size={DEFAULT_QUEUE_SIZE}, ' \
                    f'num_parallels={DEFAULT_NUM_PARALLELS}, enable_pq=true)'
        check_sql_valid(index_sql)
        self.cur.execute(index_sql)
```

### 执行步骤

1. **设置内存参数**
   ```python
   self.cur.execute('set maintenance_work_mem=1024000')
   ```
   将维护工作内存设置为 1GB（1024000KB），为索引创建提供足够内存。

2. **遍历所有嵌入键**
   ```python
   for embedding_key in self.embedding_keys:
   ```
   对每个需要建立向量索引的字段执行创建操作。

3. **构建索引创建 SQL**
   - **索引类型**：`gsdiskann` - GaussDB 的向量索引类型
   - **索引列**：`embedding_key + "_vector"` 命名的向量列
   - **距离策略**：`self.distance_strategy`（如欧氏距离l2、余弦距离cosine等）
   - **PQ 参数**：使用乘积量化（Product Quantization）进行向量压缩
     - `pq_nseg`：段数（通常等于嵌入维度）
     - `pq_nclus`：聚类数
     - `queue_size`、`num_parallels`：并发控制参数
     - `enable_pq=true`：启用 PQ 压缩

4. **验证并执行**
   ```python
   check_sql_valid(index_sql)
   self.cur.execute(index_sql)
   ```

### 典型输出 SQL 格式

```sql
CREATE INDEX ON "table_name" USING gsdiskann("field_vector" l2) 
WITH (pq_nseg=1536, pq_nclus=16, queue_size=100, num_parallels=30, enable_pq=true)
```

---

## 2. gsdiskann 实现位置

`gsdiskann` **不在这个代码仓库中实现**，它是 GaussDB/openGauss 数据库的**内置功能**。

| 信息 | 说明 |
|------|------|
| **实现位置** | GaussDB 数据库引擎核心，用 C/C++ 编写 |
| **这个项目的作用** | 通过 SQL 语句调用 GaussDB 提供的 `gsdiskann` 接口 |

### 相关文档

- [GaussMaster-技术细节详解.md](../0703ddl/GaussMaster-技术细节详解.md)：提到 "gsdiskann：华为自研的大规模向量索引算法"
- [06-doc-ingestion.md](../GaussMaster-Architecture-Docs/06-doc-ingestion.md)：有详细的 gsdiskann 创建语法

### 查看 GaussDB 的 gsdiskann 实现

需要访问 GaussDB/openGauss 的内核源码仓库：
- GitLab: https://gitee.com/opengauss/openGauss-server
- 涉及的核心代码可能在 `src/gausskernel/optimizer/` 或 `src/gausskernel/storage/vec_index/` 等目录

---

## 3. GaussMaster 使用的向量数据库

**GaussMaster 使用的是 GaussDB（openGauss）** 向量数据库。

### 关键证据

| 证据 | 说明 |
|------|------|
| **类名** | `class GaussDB:` |
| **驱动** | `import psycopg2` - PostgreSQL 兼容驱动 |
| **数据类型** | `floatvector(dimension)` - GaussDB 专有向量类型 |
| **索引** | `gsdiskann` - GaussDB 内置的 DiskANN 向量索引 |

### GaussDB 简介

- **开发厂商**：华为
- **基础**：基于 PostgreSQL 协议
- **向量支持**：
  - `floatvector` 类型存储向量
  - `gsdiskann` 索引加速检索（基于 DiskANN 算法）
  - 支持 L2 距离、余弦距离等
- **适用场景**：超大规模向量检索（十亿级）

---

## 4. GaussDB vs PostgreSQL + pgvector

| 对比项 | **GaussDB/openGauss** | **PostgreSQL + pgvector** |
|--------|----------------------|---------------------------|
| **开发厂商** | 华为 | 开源社区 (pgvector 扩展) |
| **向量类型** | `floatvector(dim)` | `vector(dim)` |
| **索引类型** | `gsdiskann` (DiskANN 算法) | `ivfflat`, `hnsw` |
| **架构** | 原生内置向量支持 | PostgreSQL + 扩展插件 |
| **存储位置** | 磁盘优先 (DiskANN) | 内存优先 |
| **规模** | 十亿级 | 亿级以下效果最佳 |

### 关键区别

**1. 向量类型不同**
```sql
-- GaussDB
"text_vector" floatvector(1024)

-- PostgreSQL + pgvector  
"text_vector" vector(1024)
```

**2. 索引算法不同**
```sql
-- GaussDB: DiskANN 算法的 gsdiskann
CREATE INDEX ... USING gsdiskann("text_vector" l2);

-- PostgreSQL: HNSW 或 IVF
CREATE INDEX ... USING hnsw("text_vector" l2距离);
CREATE INDEX ... USING ivfflat("text_vector" l2距离);
```

**3. 设计理念不同**
- **GaussDB/DiskANN**：为超大规模（十亿+）设计，优先用磁盘存储，图结构搜索
- **pgvector/HNSW**：为中等规模设计，内存友好，图的层次结构

> **注意**：GaussDB 的 `gsdiskann` 是华为**自研的 DiskANN 算法实现**，不是 pgvector 的复制品。

---

## 5. GaussMaster 向量处理完整流程

```
文件加载 → 文本切分 → 去重处理 → 向量化 → 批量插入 → 创建索引
```

### 流程详解

#### 1. 文档加载 (`GaussMaster/utils/doc_util.py`)

```python
def get_split_content(root, srcfile, split_type='base'):
    if srcfile.endswith('md'):
        contents = text_split_md(os.path.join(root, srcfile))  # Markdown
    elif srcfile.endswith('docx'):
        contents = text_split_doc(os.path.join(root, srcfile))  # Word
    elif srcfile.endswith('pdf'):
        contents = text_split_pdf(...)
```

#### 2. 文本切分 (`GaussMaster/utils/split_util_md.py`)

```python
def split_text_md(content):
    # 基于 Markdown 标题层级切分，保持语义连贯
    # 按 ## 标题层级递归切分，生成 chunks 列表
```

#### 3. Chunk 生成 (`GaussMaster/utils/doc_util.py`)

```python
def generate_chunks(root, srcfile, contents):
    # 为每个 chunk 生成 UUID、去重指纹、上下文关联
    data_dict['uuid'] = str(uuid.uuid4())
    data_dict['dup_uuid'] = hashlib.md5(content.encode()).hexdigest()  # 去重
    data_dict['prev_uuid'] = prev_uuid  # 前后关联
    data_dict['next_uuid'] = ""
```

#### 4. 向量化 (`GaussMaster/utils/retriever_util.py`)

```python
class OnlineEmbedding:
    async def embed_query(self, query):
        resp = self.session.post(f"{self.url}/embed", json={"texts": [query]})
        return resp.json()["embeddings"][0]
```

#### 5. 批量插入 (`GaussMaster/common/metadatabase/dao/gaussdb_vector.py`)

```python
async def _batch_insert(self, docs: List):
    sql = f'INSERT INTO "{escape_double_quote(self.db_index)}" VALUES'
    for doc in docs:
        cur_value = await self._doc_to_db_string(doc)
        values.append(cur_value)
        if count % 1000 == 0:
            self.cur.execute(sql + ','.join(values))  # 每1000条批量提交
```

#### 6. 创建索引 (`GaussMaster/common/metadatabase/dao/gaussdb_vector.py`)

**向量索引 - gsdiskann**
```python
def _create_index_vector(self):
    self.cur.execute('set maintenance_work_mem=1024000')  # 1GB内存
    for embedding_key in self.embedding_keys:
        CREATE INDEX ... USING gsdiskann("text_vector" l2) 
        WITH (pq_nseg=1024, pq_nclus=16, enable_pq=true)
```

**文本索引 - BM25**
```python
def _create_index_bm25(self):
    CREATE INDEX ... USING bm25(text) WITH (num_parallels=30)
```

#### 7. 向量检索 (`GaussMaster/common/metadatabase/dao/gaussdb_vector.py`)

```python
async def search_vector(self, query, topk, embedding_key=None):
    # 1. 查询向量
    embedding = await self.embedding_function.query_embedding(query)
    # 2. 构造 SQL，用 <-> 操作符计算 L2 距离
    sql = f'SELECT * FROM "table" ORDER BY "text_vector" <-> {embedding} LIMIT {topk}'
```

---

## 核心文件对应关系

| 流程 | 文件 |
|------|------|
| 文档加载/切分 | `GaussMaster/utils/doc_util.py` |
| Markdown 切分 | `GaussMaster/utils/split_util_md.py` |
| 向量化 | `GaussMaster/utils/retriever_util.py` (OnlineEmbedding) |
| 数据库操作 | `GaussMaster/common/metadatabase/dao/gaussdb_vector.py` |
| BM25索引 | `gaussdb_vector.py` (_create_index_bm25) |
| 向量索引 | `gaussdb_vector.py` (_create_index_vector) |

---

## 总结

GaussMaster 是一个基于 GaussDB 的 RAG 知识库系统：

- **向量存储**：使用 GaussDB 的 `floatvector` 类型
- **向量索引**：使用华为自研的 `gsdiskann`（基于 DiskANN 算法）
- **文本索引**：使用 `BM25` 全文检索
- **检索方式**：支持向量检索 + 文本检索双路召回
