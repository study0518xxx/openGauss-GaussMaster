# 慢 SQL 诊断与优化

## 什么是慢 SQL

慢 SQL 是指执行时间超过阈值的 SQL 语句。GaussDB 中可通过 `log_min_duration_statement` 参数设置慢 SQL 阈值（单位毫秒），默认值为 1000ms。

## 慢 SQL 的常见根因

### 1. 缺少索引

当查询条件中的列没有索引时，数据库需要全表扫描。可以使用以下 SQL 查找缺失的索引：

```sql
SELECT schemaname, tablename, seq_scan, seq_tup_read,
       idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE seq_scan > 0
ORDER BY seq_tup_read DESC;
```

### 2. 索引失效

即使有索引，以下情况也会导致索引失效：
- 查询条件中对索引列使用了函数，如 `WHERE lower(name) = 'abc'`
- 使用了 `LIKE '%keyword'`（前缀模糊匹配）
- 数据类型隐式转换

### 3. 统计信息不准确

统计信息不准确会导致优化器估算错误。执行计划中 `rows` 估算值和实际值偏差过大时，说明统计信息需要更新：

```sql
ANALYZE table_name;
```

### 4. 锁等待

慢 SQL 可能是因为等待锁。查看锁等待情况：

```sql
SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query,
       blocking.pid AS blocking_pid, blocking.query AS blocking_query
FROM pg_locks blocked
JOIN pg_locks blocking ON blocked.locktype = blocking.locktype
WHERE NOT blocked.granted AND blocking.granted;
```

## 优化方法

1. **创建合适的索引**：为 WHERE、JOIN、ORDER BY 中使用的列创建索引
2. **改写 SQL**：避免 `SELECT *`，使用覆盖索引
3. **更新统计信息**：定期执行 `ANALYZE`
4. **分区表**：对大表进行分区，减少扫描范围
5. **调整参数**：增大 `work_mem` 允许更多内存排序
