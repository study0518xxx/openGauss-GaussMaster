# GaussDB 类详解

## 1. 一句话解释

**GaussDB 类不是真正的数据库，而是 openGauss 数据库的 Python 封装（客户端）。**

---

## 2. 类层级关系

```
┌─────────────────────────────────────┐
│         GaussDB 类                   │
│  (对 openGauss 数据库的 Python 封装)  │
└──────────────────┬──────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                      ▼
┌───────────────┐    ┌─────────────────────┐
│  psycopg2     │    │  openGauss 数据库   │
│  (驱动)        │◄──►│  (实际存储)          │
│  连接数据库    │    │  支持向量类型        │
└───────────────┘    └─────────────────────┘
```

---

## 3. 核心代码解析

**位置：** `GaussMaster/common/metadatabase/dao/gaussdb_vector.py` 第 92-116 行

```python
class GaussDB:
    def __init__(self, embedding_function, db_config, vector_config, ...):
        # 数据库连接配置
        self.db_host = db_config['host']      # 数据库地址
        self.db_port = db_config['port']      # 端口
        self.db_name = db_config['dbname']    # 数据库名
        self.db_user = db_config['user']      # 用户名
        self.db_pwd = db_config['password']   # 密码

        # 向量配置
        self.embedding_keys = vector_config["vector_field"]
```

---

## 4. 连接数据库

```python
def _connect(self):
    self.mem_db_conn = psycopg2.connect(
        dbname=self.db_name,
        user=self.db_user,
        password=self.db_pwd,
        host=self.db_host,
        port=self.db_port,
        client_encoding="utf8"
    )
    self.cur = self.mem_db_conn.cursor()
```

---

## 5. 为什么能做向量搜索？

**openGauss 扩展了 PostgreSQL**，支持**向量数据类型和向量索引**：

```sql
-- 创建表时指定向量列
CREATE TABLE knowledge (
    text TEXT,
    text_vector floatvector(1024)  -- 1024维向量列
);

-- 向量相似度查询
SELECT * FROM knowledge
ORDER BY text_vector <-> '[0.1, 0.2, ...]'
LIMIT 5;
```

---

## 6. 完整数据流

```
GaussDB 类（Python 封装）
         │
         │  内部使用 psycopg2 连接 openGauss
         ▼
┌─────────────────────────────────────┐
│         openGauss 数据库              │
│  ┌───────────────────────────────┐  │
│  │  普通列                        │  │
│  │  - uuid (主键)                 │  │
│  │  - title (标题)                │  │
│  │  - text (内容)                 │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  向量列 (floatvector)          │  │
│  │  - text_vector (文本向量)      │  │
│  │  - embedding_vector (嵌入向量) │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

---

## 7. GaussDB 类的职责

| 职责 | 说明 |
|------|------|
| **连接管理** | 连接/断开 openGauss 数据库 |
| **CRUD 操作** | 插入、查询、更新、删除文档 |
| **向量搜索** | 封装向量相似度查询 |
| **全文搜索** | 封装 BM25 搜索 |
| **索引创建** | 创建向量索引和 BM25 索引 |

---

## 8. 类比理解

| 类比 | 实际 |
|------|------|
| **GaussDB** | 就像一个"遥控器" |
| **openGauss** | 实际的"电视机" |
| **pscopg2** | 遥控器的"电池" |

GaussDB 类只是一个**封装层**，真正存储和计算的是 openGauss 数据库。

---

## 9. 总结

- **GaussDB ≠ 数据库**，它是 **openGauss 的 Python 客户端**
- 底层使用 **psycopg2** 驱动连接数据库
- openGauss **扩展了 PostgreSQL**，原生支持**向量类型**
- GaussDB 类只是**方便调用**，把 SQL 操作封装成方法
