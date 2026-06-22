# 备选：PostgreSQL + MySQL + Redis 高频面试题

---

## 一、PostgreSQL

### 1. 事务隔离级别

| 级别 | PG 实现 | 脏读 | 不可重复读 | 幻读 |
|------|---------|------|-----------|------|
| Read Uncommitted | PG 不支持（实现同 Read Committed） | ✅ | ❌ | ❌ |
| Read Committed | **默认**，每次语句看到最新已提交数据 | ❌ | ❌ | ❌ |
| Repeatable Read | 快照隔离，事务开始时拍快照 | ❌ | ✅ | ✅(PG 已防) |
| Serializable | SSI（串行化快照隔离），检测冲突回滚 | ❌ | ✅ | ✅ |

> PG 的 Repeatable Read 已经防了幻读（和 MySQL 不同），Serializable 真正做到了串行化但性能代价大。

### 2. MVCC 怎么实现的

```
每行数据有隐藏字段:
  xmin  → 插入该行的事务 ID
  xmax  → 删除该行的事务 ID（0 = 未删除）

INSERT → 新行，xmin=当前事务ID
UPDATE → 旧行 xmax=当前事务ID + 插入新行 xmin=当前事务ID
DELETE → 该行 xmax=当前事务ID

读取时: 只读 xmin < 快照事务ID 且 (xmax=0 或 xmax > 快照事务ID) 的版本
```

### 3. VACUUM 是什么

```
DELETE/UPDATE 不真正删除数据，只是标记 xmax
旧版本一直堆着 → 表膨胀、事务ID回卷风险

VACUUM:        标记可复用空间，不锁表
VACUUM FULL:   重写整表，归还磁盘，会锁表
AUTOVACUUM:    自动触发，生产必须开
```

### 4. 索引类型

| 索引 | 场景 |
|------|------|
| B-Tree | 等值、范围、排序（默认，90% 场景） |
| Hash | 等值查询，不支持范围，PG 10+ 才可用 |
| GIN | 全文搜索、数组、JSONB（倒排索引） |
| GiST | 地理空间、全文搜索 |
| BRIN | 大表顺序字段（日志时间），索引极小 |
| 部分索引 | `WHERE status = 'active'` |
| 覆盖索引 | `INCLUDE (extra_col)` 不回表 |

### 5. EXPLAIN 怎么看

```sql
EXPLAIN ANALYZE SELECT ...;

Seq Scan          → 全表扫，可能需要建索引
Index Scan        → 用索引找到行，回表读完整行
Index Only Scan   → 索引里已有所有列，不回表（最快）
Bitmap Scan       → 多个索引结果取交集/并集
Nested Loop Join  → 小表驱动大表
Hash Join         → 两张表都较大
Merge Join        → 两表已排序

关注的数字:
  cost=启动代价..总代价  rows=预估行数  width=行宽
  actual time=实际时间  loops=循环次数
  buffers=shared hit=缓存命中
```

### 6. 连接池为什么重要

```
PG 每个连接 fork 一个进程 → ~10MB 内存
1000 连接 = 10GB 内存 → 没干正事就崩了

解决方法:
  PgBouncer    → 连接池，事务/语句/会话模式
  应用端 pool  → SQLAlchemy pool_size + max_overflow
```

### 7. 主从复制

| 方式 | 机制 | 特点 |
|------|------|------|
| 流复制 | WAL 日志实时传输到备库 | 备库只读 |
| 逻辑复制 | 按表/操作类型复制 | 可跨版本，可部分表 |
| 同步复制 | 备库确认才返回 | 不丢数据，延迟高 |

### 8. PostgreSQL vs MySQL

| | PostgreSQL | MySQL |
|---|---|---|
| 并发 | MVCC，无读写锁 | MVCC + 间隙锁 |
| 事务 | DDL 支持事务回滚 | DDL 自动提交 |
| JSON | JSONB + GIN 索引 | JSON，索引不如 PG |
| 扩展 | PostGIS、pgvector、TimescaleDB | 较少 |
| 复制 | 流复制 + 逻辑复制 | 主从 + Group Replication |
| 进程模型 | fork 进程 | 线程池 |
| 复杂查询 | CTE、递归、窗口、LATERAL | 较弱 |

---

## 二、MySQL

### 1. InnoDB 索引结构

```
InnoDB 用 B+Tree:
  - 非叶子节点只存 key 和指针（不存数据）
  - 叶子节点存完整数据行
  - 叶子节点之间用双向链表连接 → 范围查询快

聚簇索引（主键索引）: 叶子节点 = 完整行数据
二级索引（普通索引）:  叶子节点 = 主键值 + 索引列
  → 二级索引查到主键 → 回表查完整行（覆盖索引可避免）
```

### 2. 事务隔离级别

| 级别 | 脏读 | 不可重复读 | 幻读 | MySQL 默认 |
|------|------|-----------|------|-----------|
| Read Uncommitted | ✅ | ❌ | ❌ | |
| Read Committed | ❌ | ❌ | ❌ | |
| Repeatable Read | ❌ | ✅ | ✅(部分) | ✅ **默认** |
| Serializable | ❌ | ✅ | ✅ | |

> InnoDB 的 RR 通过 MVCC + Next-Key Lock 防了大部分幻读（比标准 SQL 强），但不能防所有——比如 `SELECT ... FOR UPDATE` 会锁间隙。

### 3. 锁机制

```
行锁（Record Lock）:     锁索引记录
间隙锁（Gap Lock）:      锁记录之间的间隙
临键锁（Next-Key Lock）:  行锁 + 间隙锁（RR 级别默认）

表锁:                    LOCK TABLES / MDL 元数据锁
意向锁:                   表级锁，协调行锁和表锁
```

### 4. 慢查询优化思路

```
1. 开慢查询日志: slow_query_log = ON, long_query_time = 1

2. EXPLAIN 看:
   type → ALL（全表扫）= 最差，index/ref/const = 好
   key  → 用了哪个索引
   rows → 扫描行数（越小越好）
   Extra → Using filesort/Using temporary = 需要优化

3. 常见优化:
   - 加索引（WHERE / JOIN / ORDER BY 列）
   - 覆盖索引避免回表
   - 减少 SELECT *，只取需要的列
   - 大分页改游标: WHERE id > last_id LIMIT N
   - JOIN 小表驱动大表
   - 分库分表（水平拆分）
```

### 5. Binlog 三种格式

| 格式 | 记录内容 | 特点 |
|------|---------|------|
| STATEMENT | SQL 语句 | 日志小，但不确定性语句（NOW()）会出错 |
| ROW | 每行变更 | 日志大，但精确（默认推荐） |
| MIXED | 混合 | 大多数用 STATEMENT，不确定的用 ROW |

### 6. JOIN 算法

```
Nested Loop:  外表每行去内表查（小表驱动大表，内表有索引）
Block Nested Loop: 同上但用 Join Buffer 批量读
Hash Join:    内表建哈希表，外表逐行匹配（MySQL 8.0+）
```

### 7. 分库分表策略

```
垂直拆分: 按业务模块分库（用户库、订单库）
水平拆分: 按数据行分（user_id % 16 分到不同表/库）

中间件: ShardingSphere、Vitess、自研路由层

痛点:
  - 跨库 JOIN 不支持
  - 分布式事务（XA / TCC / 最终一致性）
  - 全局唯一 ID（雪花算法 / Leaf）
```

### 8. 缓存策略（和 Redis 配合）

| 策略 | 读 | 写 | 风险 |
|------|----|----|------|
| Cache Aside | 先读缓存，miss 读 DB 回写缓存 | 先写 DB，再删缓存 | 经典方案，会有短暂不一致 |
| Read Through | 缓存层读，miss 自动加载 | — | 代码简单，缓存层复杂 |
| Write Through | — | 同步写缓存+DB | 一致性好，写入慢 |
| Write Behind | — | 先写缓存，异步写 DB | 高性能但可能丢数据 |

---

## 三、Redis

### 1. 为什么 Redis 快

```
1. 纯内存操作（不是磁盘 IO）
2. 单线程（无上下文切换、无锁竞争）
3. IO 多路复用（epoll，一个线程处理多个连接）
4. 高效数据结构（SDS、ZipList、SkipList 定制实现）
```

### 2. 数据结构及应用场景

| 类型 | 底层 | 场景 |
|------|------|------|
| String | SDS 动态字符串 | 缓存、计数器、分布式锁 |
| Hash | ZipList / Hashtable | 对象缓存（用户信息） |
| List | QuickList | 消息队列、最新列表 |
| Set | Hashtable / IntSet | 去重、共同好友、标签 |
| ZSet | SkipList + Hashtable | 排行榜、延时队列 |
| Stream | Rax 树 | 消息队列（持久化、消费者组） |
| Bitmap | String | 签到、在线状态 |
| HyperLogLog | — | UV 统计（有误差） |
| GEO | ZSet | 附近的人 |

### 3. 持久化：RDB vs AOF

| | RDB | AOF |
|---|---|---|
| 机制 | 定期快照（save 900 1） | 每条写命令追加日志 |
| 文件 | dump.rdb（二进制） | appendonly.aof（文本） |
| 恢复速度 | 快 | 慢（重放命令） |
| 数据安全 | 可能丢最后几分钟 | 可以每条都 fsync（最安全） |
| 生产 | RDB + AOF 混合 | — |

### 4. 过期删除策略

```
惰性删除: 访问 key 时检查过期 → 过期就删
定期删除: 每秒 10 次，随机抽一批 key 检查

为什么不用定时器: 100 万个 key 设过期 = 100 万个定时器，CPU 扛不住
```

### 5. 内存淘汰（缓存满了怎么办）

| 策略 | 行为 |
|------|------|
| noeviction | 不淘汰，写入报错 |
| allkeys-lru | 所有 key 里淘汰最近最少用的 |
| volatile-lru | 有过期时间的 key 里淘汰 |
| allkeys-random | 所有 key 随机淘汰 |
| volatile-ttl | 优先淘汰 ttl 短的 |
| allkeys-lfu | Redis 4.0+，淘汰使用频率最低的 |

**LRU vs LFU**: LRU 看最近有没有被访问，LFU 看历史访问频率。热搜排行榜用 LFU。

### 6. 缓存三大问题

**缓存穿透**：查不存在的数据，每次都打到 DB。

```
解决:
  - 布隆过滤器（先问是否存在，不存在直接返回）
  - 空值缓存（查不到也存个 null，设短过期时间）
```

**缓存击穿**：热点 key 过期瞬间，大量请求打到 DB。

```
解决:
  - 互斥锁（第一个请求去加载，其他等待）
  - 逻辑过期（永不过期，后台异步更新）
```

**缓存雪崩**：大量 key 同时过期，DB 瞬间压力巨大。

```
解决:
  - 过期时间加随机值（避免同时过期）
  - 多级缓存（本地 + Redis）
  - 限流降级
```

### 7. 集群方案

| 方案 | 特点 |
|------|------|
| 主从复制 | 一主多从，读写分离，不能自动故障转移 |
| Sentinel | 哨兵监控，自动故障转移，但数据还是全量 |
| Cluster | 数据分片（16384 槽），每个节点存部分数据 |

```
Cluster 分片: key → CRC16(key) % 16384 → 槽号 → 对应节点
扩容: 迁移部分槽到新节点
限制: 跨槽事务不支持，mget 跨节点需要用 hash tag {key}
```

### 8. 分布式锁怎么实现

```redis
# 加锁（NX = 不存在才设，PX = 过期毫秒）
SET lock_key unique_value NX PX 30000

# 解锁（Lua 脚本保证原子性，先判断再删除）
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
```

| 问题 | 解决 |
|------|------|
| 锁过期了业务没完成 | Watch Dog 自动续期（Redisson） |
| 单点故障 | RedLock：多个独立 Redis 实例，大多数加锁成功才算 |
| 误删别人锁 | value 用 UUID，解锁前校验 |

### 9. 单线程模型

> Redis 6.0 以前，网络 IO 和命令处理都是单线程。6.0+ 引入多线程 IO（只处理网络读写），命令执行仍是单线程。

```
单线程的好处: 无并发竞争、无上下文切换、代码简单
单线程的限制: 一个慢命令（KEYS *）会阻塞所有请求
  → 生产禁用 KEYS，用 SCAN
  → 大 key 拆成小 key
  → 复杂计算放 Lua 脚本
```

### 10. Pipeline 和事务的区别

```
Pipeline:
  客户端打包多个命令一次发送，不保证原子性
  用途: 减少 RTT（往返延迟）

事务（MULTI/EXEC）:
  命令入队，EXEC 时批量执行，保证原子性但不支持回滚
```

---

## 四、快速对照：查什么用什么

| 场景 | 用什么 |
|------|--------|
| OLTP 复杂查询、GIS、分析 | PostgreSQL |
| 简单互联网 CRUD、高并发读写 | MySQL |
| 缓存、计数器、排行榜 | Redis String/ZSet |
| 会话存储、临时数据 | Redis Hash + TTL |
| 消息队列（简单） | Redis List / Stream |
| 消息队列（生产） | RabbitMQ / Kafka |
| 精确匹配搜索 | PostgreSQL / MySQL B-Tree |
| 模糊/语义搜索 | Elasticsearch / 向量数据库 |
| 海量时序数据 | TimescaleDB / InfluxDB |
