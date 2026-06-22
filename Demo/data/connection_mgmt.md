# 数据库连接管理

## 连接数配置

GaussDB 通过 `max_connections` 参数控制最大连接数。建议设置为：
- 小型实例：100-200
- 中型实例：200-500
- 大型实例：500-1000

## 连接数过高的问题

1. **内存消耗**：每个连接大约消耗 2-10MB 内存
2. **CPU 上下文切换**：大量连接导致频繁的上下文切换
3. **锁竞争**：更多连接意味着更多并发事务，锁竞争加剧

## 监控连接数

```sql
-- 查看当前连接数和使用率
SELECT count(*) AS current_connections,
       (SELECT setting::int FROM pg_settings WHERE name='max_connections') AS max_connections,
       round(count(*) * 100.0 / (SELECT setting::int FROM pg_settings WHERE name='max_connections'), 2) AS usage_percent
FROM pg_stat_activity;

-- 按状态分组查看连接
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- 查找空闲时间过长的连接
SELECT pid, usename, application_name, state, query_start
FROM pg_stat_activity
WHERE state = 'idle' AND query_start < now() - interval '10 minutes';
```

## 连接池方案

推荐使用连接池中间件（如 PgBouncer）来管理连接：
- 事务模式：每个事务获取和释放连接
- 会话模式：保持连接直到客户端断开
- 语句模式：每个语句获取和释放连接

## 常见问题处理

| 问题 | 处理方式 |
|------|---------|
| 连接数达到上限 | 杀掉空闲连接 `SELECT pg_terminate_backend(pid)` |
| 连接泄漏 | 检查应用是否正确关闭连接 |
| 突然大量连接涌入 | 检查是否有异常流量或攻击 |
