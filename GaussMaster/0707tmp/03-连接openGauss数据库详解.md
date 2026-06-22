# 连接 openGauss 数据库详解

## 一、openGauss 是什么？

**openGauss** 是华为开源的关系型数据库，基于 PostgreSQL 开发，增加了：
- 向量扩展（Vector Extension）
- AI 原生支持
- 高性能优化

GaussMaster 使用 openGauss 存储：
1. **元数据**（对话历史、诊断报告）
2. **向量数据**（知识库文档的 Embedding）

---

## 二、连接配置

### 2.1 配置文件

`misc/gaussmaster.conf`：

```ini
[VECTOR]
host = 10.0.0.1          # openGauss 服务器 IP
port = 5432              # 端口
vector_dbname = vec_db   # 向量数据库名
metadatabase = meta_db   # 元数据库名
user = gaussdb           # 用户名
password = Encrypted->... # 加密后的密码
ssl = true
ssl_mode = prefer        # disable / prefer / verify-ca
```

### 2.2 为什么叫 [VECTOR]？

因为 openGauss 的向量扩展是核心特性，所以用 VECTOR 作为配置节名。

---

## 三、连接实现

### 3.1 数据库类型适配

`common/metadatabase/utils.py`：

```python
class DbType(Enum):
    SQLITE = 'sqlite'
    OPENGAUSS = 'opengauss'
    GAUSSDB = 'gaussdb'
    POSTGRESQL = 'postgresql'

def create_dsn(db_type, database, host, port, username, password):
    if db_type in ['opengauss', 'gaussdb']:
        db_type = 'postgresql'  # SQLAlchemy 只认识 postgresql
        # 欺骗 SQLAlchemy，让它以为连接的是 PostgreSQL 9.2
        from sqlalchemy.dialects.postgresql.base import PGDialect
        PGDialect._get_server_version_info = lambda *args: (9, 2)
    
    dsn = 'postgresql://user:pass@host:port/database'
    return dsn
```

**关键点**：
- openGauss 兼容 PostgreSQL 协议
- SQLAlchemy 不认识 "opengauss"，所以要伪装成 "postgresql"
- 通过 monkey patch 修改版本检测，避免 SQLAlchemy 报错

---

### 3.2 元数据库连接

`common/metadatabase/result_db_session.py`：

```python
@contextlib.contextmanager
def get_session():
    # 从配置读取连接信息
    database = global_vars.configs.get('VECTOR', 'metadatabase')
    host = global_vars.configs.get('VECTOR', 'host')
    port = global_vars.configs.get('VECTOR', 'port')
    username = global_vars.configs.get('VECTOR', 'user')
    password = global_vars.configs.get('VECTOR', 'password')
    ssl_mode = global_vars.configs.get('VECTOR', 'ssl_mode')
    
    # 创建连接池
    dsn = create_dsn('opengauss', database, host, port, username, password)
    engine = create_engine(
        dsn,
        pool_pre_ping=True,      # 连接前 ping，避免使用死连接
        pool_size=10,            # 连接池大小
        max_overflow=10,         # 超出池大小后的额外连接
        pool_recycle=25,         # 连接回收时间（秒）
        connect_args={
            'connect_timeout': 5,
            'application_name': 'DBMind-Service',
            'sslmode': ssl_mode
        }
    )
    
    session = session_maker()
    session.begin()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

**连接池参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| pool_pre_ping | True | 使用前检测连接是否存活 |
| pool_size | 10 | 常驻连接数 |
| max_overflow | 10 | 峰值时额外连接数 |
| pool_recycle | 25 | 连接25秒后强制回收 |
| connect_timeout | 5 | 连接超时5秒 |

---

### 3.3 向量数据库连接

`common/metadatabase/dao/gaussdb_vector.py`：

```python
class GaussDB:
    def __init__(self, embedding_function, gaussdb_config, vector_config):
        self.embedding_function = embedding_function
        self.host = gaussdb_config['host']
        self.port = gaussdb_config['port']
        self.user = gaussdb_config['user']
        self.password = gaussdb_config['password']
        self.dbname = gaussdb_config['dbname']
        self.table_name = vector_config['table_name']
    
    def _connect(self):
        """使用 psycopg2 直连"""
        self.conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.dbname
        )
        self.cur = self.conn.cursor()
```

**为什么用 psycopg2 而不是 SQLAlchemy？**
- 向量操作需要执行原生 SQL（如 `<->` 运算符）
- `COPY FROM` 批量导入需要底层连接
- SQLAlchemy 对向量扩展的支持有限

---

## 四、向量检索 SQL

### 4.1 向量相似度搜索

```sql
-- L2 距离（欧氏距离）
SELECT * FROM "knowledge_base"
WHERE version = '5.0'
ORDER BY "text_vector" <-> '[0.1, -0.2, 0.3, ...]'  -- <-> 是 L2 距离运算符
LIMIT 5;

-- Cosine 距离
SELECT * FROM "knowledge_base"
ORDER BY "text_vector" <=> '[0.1, -0.2, 0.3, ...]'  -- <=> 是 Cosine 距离
LIMIT 5;

-- Inner Product
SELECT * FROM "knowledge_base"
ORDER BY "text_vector" <#> '[0.1, -0.2, 0.3, ...]'  -- <#> 是内积
LIMIT 5;
```

### 4.2 全文检索（BM25）

```sql
SELECT * FROM "knowledge_base"
WHERE "title,text" @@ '查询文本'  -- @@ 是全文匹配运算符
ORDER BY "title,text" @@ '查询文本' DESC
LIMIT 5;
```

### 4.3 向量 + 全文混合

```sql
SELECT /*+ no tablescan("knowledge_base")*/ *
FROM "knowledge_base"
WHERE version = '5.0'
  AND "title,text" @@ '查询文本'
ORDER BY "text_vector" <-> '[0.1, -0.2, ...]'
LIMIT 5;
```

---

## 五、数据导入

### 5.1 COPY FROM 批量导入

```python
def load_local(self, file_name, need_index=False, truncate_table=False):
    self._connect()
    if truncate_table:
        self._drop_table()
    self._create_table()
    
    # 使用 PostgreSQL COPY 命令批量导入
    self._copy_from(file_name)
    
    if need_index:
        self._create_index()  # 创建向量索引和全文索引
```

### 5.2 创建向量索引

```sql
-- 创建 IVF 向量索引
CREATE INDEX idx_vector ON knowledge_base
USING ivfflat (text_vector vector_l2_ops)
WITH (nlists = 16);

-- 创建全文索引
CREATE INDEX idx_bm25 ON knowledge_base
USING gin (to_tsvector('chinese', text));
```

---

## 六、连接流程图

```
GaussMaster 启动
    │
    ▼
┌─────────────────────────────────────────┐
│ 读取 gaussmaster.conf                   │
│ [VECTOR] host/port/user/password/dbname │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ update_session_clz_from_configs()       │
│ • 解析配置                              │
│ • 创建 SQLAlchemy Engine                │
│ • 连接池初始化 (pool_size=10)           │
│ • 测试连接                              │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 运行时                                  │
│                                         │
│ 元数据操作 ──► get_session() ──► SQLAlchemy ORM
│                                         │
│ 向量检索 ──► GaussDB._connect() ──► psycopg2
│                                         │
└─────────────────────────────────────────┘
```

---

## 七、面试要点

1. **为什么 SQLAlchemy 不认识 openGauss？**
   - SQLAlchemy 内置支持 PostgreSQL、MySQL 等
   - openGauss 是兼容 PostgreSQL 协议，但名字不同
   - 通过 monkey patch 伪装成 PostgreSQL 9.2

2. **连接池的作用？**
   - 避免频繁创建/销毁连接的开销
   - 控制并发连接数，防止数据库过载
   - 连接保活和自动回收

3. **向量检索的三种距离？**
   - L2（欧氏距离）：`<->`，适合绝对距离
   - Cosine（余弦距离）：`<=>`，适合方向相似度
   - Inner Product（内积）：`<#>`，适合归一化向量

4. **为什么用 psycopg2 做向量操作？**
   - 需要执行原生 SQL（向量运算符）
   - COPY FROM 批量导入需要底层连接
   - SQLAlchemy ORM 对向量扩展支持不足
