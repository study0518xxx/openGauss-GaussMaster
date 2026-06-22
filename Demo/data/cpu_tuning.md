# CPU 使用率过高诊断指南

## 问题现象

当 GaussDB 数据库 CPU 使用率持续超过 80% 时，需要立即排查。

## 常见原因

### 1. 慢 SQL 导致 CPU 飙升

大量慢 SQL 同时执行会消耗大量 CPU 资源。可以通过以下 SQL 查询当前正在执行的慢查询：

```sql
SELECT pid, query, state, wait_event, query_start
FROM pg_stat_activity
WHERE state = 'active' AND query_start < now() - interval '5 seconds';
```

### 2. 统计信息过期

统计信息过期会导致查询优化器选择错误的执行计划，比如该用索引却走了全表扫描。建议定期执行 `ANALYZE` 命令更新统计信息。

### 3. 连接数过多

当数据库连接数超过 `max_connections` 的 80% 时，大量连接争抢 CPU 资源。建议：
- 检查是否有空闲连接未释放
- 考虑使用连接池
- 适当调大 `max_connections` 参数

### 4. 参数配置不当

检查以下参数是否合理：
- `shared_buffers`：建议设置为物理内存的 25%
- `work_mem`：过大会导致大量排序操作消耗 CPU
- `max_parallel_workers`：并行度过高会导致 CPU 争抢

## 排查步骤

1. 执行 `SELECT * FROM pg_stat_activity` 查看当前活跃查询
2. 使用 `EXPLAIN ANALYZE` 分析慢 SQL 执行计划
3. 检查 `pg_stat_user_tables` 确认统计信息是否过期
4. 查看 `pg_stat_database` 监控连接数和事务数
5. 对比参数配置和最佳实践建议

## 解决方案

- 终止长时间运行的慢 SQL：`SELECT pg_terminate_backend(pid)`
- 创建或重建索引以优化查询
- 调整配置参数并重启数据库
- 增加物理 CPU 资源
