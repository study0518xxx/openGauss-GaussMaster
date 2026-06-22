"""
数据库诊断工具 —— 对标 GaussMaster 的 dbmind_interface.py
所有工具返回 Mock 数据，无需真实数据库即可运行
"""

from core.registry import ToolRegistry

# 全局工具注册中心
tools = ToolRegistry()


@tools.register(
    name="get_instance_status",
    description="查询当前数据库实例的运行状态，包括节点角色、运行时长、连接数等",
)
def get_instance_status() -> dict:
    """获取实例状态"""
    return {
        "status": "running",
        "role": "primary",
        "host": "192.168.1.100",
        "port": 5432,
        "uptime": "72h30m",
        "active_connections": 23,
        "max_connections": 200,
        "db_version": "openGauss 5.0.0",
    }


@tools.register(
    name="get_slow_sqls",
    description="查询最近一段时间的慢 SQL 列表，返回耗时最长的 SQL 语句和耗时",
    params=[
        {"name": "minutes", "description": "查询最近多少分钟的慢 SQL，默认30分钟"},
    ],
)
def get_slow_sqls(minutes: int = 30) -> list[dict]:
    """获取慢 SQL"""
    mock_data = [
        {"query": "SELECT * FROM orders o JOIN order_items oi ON o.id = oi.order_id WHERE o.status = 'PENDING' ORDER BY o.created_at DESC LIMIT 100", "duration_ms": 12500, "db": "order_db", "occurred_at": "2024-06-13 10:15:23"},
        {"query": "UPDATE inventory SET quantity = quantity - 1 WHERE product_id IN (SELECT product_id FROM order_items WHERE order_id = ?)", "duration_ms": 8700, "db": "order_db", "occurred_at": "2024-06-13 10:14:55"},
        {"query": "SELECT * FROM audit_log WHERE created_at BETWEEN ? AND ? ORDER BY created_at", "duration_ms": 5600, "db": "audit_db", "occurred_at": "2024-06-13 10:10:00"},
    ]
    # 模拟按分钟过滤
    if minutes <= 15:
        mock_data = mock_data[:1]
    return mock_data


@tools.register(
    name="get_active_locks",
    description="查询当前数据库中的锁等待情况，包括被阻塞的会话和阻塞源",
)
def get_active_locks() -> list[dict]:
    """获取活跃锁"""
    return [
        {"blocked_pid": 12345, "blocked_query": "UPDATE accounts SET balance = balance - 100 WHERE id = 1", "blocked_at": "2024-06-13 10:20:00", "blocking_pid": 12340, "blocking_query": "UPDATE accounts SET balance = balance + 200 WHERE id = 1", "wait_seconds": 45},
        {"blocked_pid": 12346, "blocked_query": "DELETE FROM orders WHERE id = 500", "blocked_at": "2024-06-13 10:21:30", "blocking_pid": 12341, "blocking_query": "SELECT * FROM orders FOR UPDATE", "wait_seconds": 30},
    ]


@tools.register(
    name="get_disk_usage",
    description="查询数据库实例的磁盘使用情况，包括总大小、已用空间、使用率",
)
def get_disk_usage() -> dict:
    """获取磁盘使用"""
    return {
        "total_gb": 500,
        "used_gb": 372,
        "usage_percent": 74.4,
        "data_directory": "/data/gaussdata",
        "mount_point": "/data",
        "growth_rate_gb_per_day": 2.3,
        "estimated_days_until_full": 55,
    }


@tools.register(
    name="get_running_queries",
    description="查询当前正在执行的所有查询语句及其运行时间",
)
def get_running_queries() -> list[dict]:
    """获取正在运行的查询"""
    return [
        {"pid": 12345, "query": "SELECT * FROM large_table WHERE status = 'ACTIVE' ORDER BY created_at", "duration_seconds": 120, "state": "active", "user": "app_user"},
        {"pid": 12346, "query": "VACUUM ANALYZE orders", "duration_seconds": 65, "state": "active", "user": "maintenance"},
        {"pid": 12347, "query": "CREATE INDEX idx_orders_status ON orders(status)", "duration_seconds": 30, "state": "active", "user": "admin"},
    ]


@tools.register(
    name="get_table_size_top",
    description="查询数据库中占用空间最大的前 N 张表",
    params=[
        {"name": "limit", "description": "返回前多少张表，默认10"},
    ],
)
def get_table_size_top(limit: int = 10) -> list[dict]:
    """获取最大的表"""
    return [
        {"table": "audit_log", "schema": "public", "size_mb": 25600, "estimated_rows": 50000000},
        {"table": "orders", "schema": "public", "size_mb": 12800, "estimated_rows": 25000000},
        {"table": "order_items", "schema": "public", "size_mb": 9600, "estimated_rows": 80000000},
        {"table": "inventory_snapshots", "schema": "public", "size_mb": 6400, "estimated_rows": 10000000},
        {"table": "user_sessions", "schema": "public", "size_mb": 3200, "estimated_rows": 60000000},
    ][:limit]


@tools.register(
    name="get_connection_summary",
    description="查询数据库当前的连接数汇总，包括活跃连接、空闲连接、等待连接等",
)
def get_connection_summary() -> dict:
    """获取连接汇总"""
    return {
        "total": 187,
        "active": 23,
        "idle": 142,
        "idle_in_transaction": 12,
        "waiting": 5,
        "max_connections": 300,
        "connection_usage_pct": 62.3,
    }
