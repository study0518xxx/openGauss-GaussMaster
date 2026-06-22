"""
知识库加载器 —— 加载内置运维知识到向量存储
对标 GaussMaster 的 utils/doc_util.py + knowledge_base/*.db
"""

import logging

from .vector_store import kb_store

# 内置示例知识库（数据库运维常见问题）
BUILTIN_KNOWLEDGE = [
    {
        "category": "慢 SQL 优化",
        "qa": [
            {
                "q": "数据库慢 SQL 如何排查",
                "a": "排查慢 SQL 的步骤：1. 通过 pg_stat_activity 查看当前运行中的长时间查询；2. 检查 dbe_perf.statement_history 获取历史慢 SQL；3. 使用 EXPLAIN ANALYZE 分析执行计划；4. 关注全表扫描、索引缺失、数据倾斜等问题。"
            },
            {
                "q": "如何优化慢 SQL 性能",
                "a": "优化建议：1. 添加合适的索引（注意复合索引的列顺序）；2. 避免 SELECT *，只查询需要的列；3. 合理使用 JOIN，避免嵌套循环；4. 对大表做分区；5. 定期 VACUUM ANALYZE 更新统计信息；6. 使用物化视图缓存复杂查询结果。"
            },
        ]
    },
    {
        "category": "锁与并发",
        "qa": [
            {
                "q": "数据库锁等待如何排查",
                "a": "锁等待排查方法：1. 查询 pg_locks 查看锁的持有和等待关系；2. 通过 pg_stat_activity 找到阻塞和被阻塞的会话；3. 设置 lock_timeout 避免长时间等待；4. 优化事务长度，减少锁持有时间。"
            },
            {
                "q": "死锁是怎么产生的",
                "a": "死锁是指两个或多个事务互相等待对方持有的锁，导致所有事务无法继续。例如：事务A锁了行1等待行2，事务B锁了行2等待行1。数据库会自动检测死锁并回滚其中一个事务。避免方法：保持一致的锁顺序、使用 NOWAIT 或 SKIP LOCKED。"
            },
        ]
    },
    {
        "category": "磁盘空间",
        "qa": [
            {
                "q": "磁盘使用率高如何处理",
                "a": "处理步骤：1. 查最大表：SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size(...) DESC；2. 清理过期归档日志；3. 对不再需要的数据做分区裁剪或 truncate；4. 扩展磁盘或迁移数据到新存储。"
            },
            {
                "q": "数据库日志文件过大怎么办",
                "a": "处理方法：1. 调整 log_rotation_size 和 log_rotation_age 控制日志轮转；2. 设置 max_log_files 限制日志文件数量；3. 对不再需要的日志做压缩归档；4. 使用日志采集工具（如 Loki、ELK）集中管理。"
            },
        ]
    },
    {
        "category": "连接管理",
        "qa": [
            {
                "q": "数据库连接数过多怎么处理",
                "a": "处理方案：1. 检查 max_connections 配置是否合理；2. 使用连接池（如 PgBouncer、pgpool）复用连接；3. 排查应用侧连接泄漏，设置合理的连接超时；4. 通过 pg_stat_activity 查看 idle in transaction 的连接并终止。"
            },
            {
                "q": "连接池应该设置多大",
                "a": "经验公式：连接数 = (核心数 * 2 + 有效磁盘数)。通常一个数据库实例 50-200 连接足够。过多连接会导致上下文切换开销。推荐使用 PgBouncer 做事务级连接池，应用只维持少量连接。"
            },
        ]
    },
    {
        "category": "备份恢复",
        "qa": [
            {
                "q": "数据库备份方式有哪些",
                "a": "主要备份方式：1. 逻辑备份（pg_dump/pg_dumpall）适合小库或特定表；2. 物理备份（基础备份 + WAL 归档）适合大库，支持 PITR 时间点恢复；3. 快照备份（存储层快照）速度最快。推荐组合：每日全量 + 每小时 WAL 归档。"
            },
            {
                "q": "如何验证备份是否可用",
                "a": "验证方法：1. 定期在测试环境恢复备份并做数据校验；2. 检查 WAL 归档的完整性和连续性；3. 使用 pg_verifybackup 工具验证物理备份；4. 监控备份日志中是否有错误信息。"
            },
        ]
    },
]


def load_builtin_knowledge(embedding_fn=None):
    """
    加载内置知识库到向量存储
    embedding_fn: 可选，传入文本向量化函数，不传则只存文本不向量化
    """
    count = 0
    for category in BUILTIN_KNOWLEDGE:
        for item in category["qa"]:
            text = f"问题：{item['q']}\n回答：{item['a']}"
            metadata = {
                "category": category["category"],
                "question": item["q"],
            }

            embedding = None
            if embedding_fn:
                embedding = embedding_fn(text)

            kb_store.add_document(
                text=text,
                metadata=metadata,
                embedding=embedding,
            )
            count += 1

    logging.info(f"内置知识库加载完成，共 {count} 条")
    return count
