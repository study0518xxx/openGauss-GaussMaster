"""
tools/db_tools.py — 模拟数据库运维工具
对应 GaussMaster: multiagents/tools/dbmind_interface.py

注册 3 个模拟工具：
1. get_cpu_usage    — 获取指定实例的 CPU 使用率
2. get_slow_queries — 获取当前慢 SQL 列表
3. get_connections  — 获取当前连接数（无参数工具）
"""
from tools.registry import ToolRegistry, Param

# 全局注册表（和 GaussMaster 的 base_tools 一样）
registry = ToolRegistry()


@registry.register(
    name="get_cpu_usage",
    description="获取指定数据库实例当前的 CPU 使用率百分比",
    params=[Param("instance", "数据库实例名称，如 db_001", param_type="str", required=True)]
)
def get_cpu_usage(instance: str) -> dict:
    """
    模拟：返回 CPU 使用率
    生产版 GaussMaster 这里会调 DBMind API
    """
    return {
        "instance": instance,
        "cpu_percent": 78.5,
        "status": "warning",
        "suggestion": "CPU 使用率接近 80% 阈值，建议排查慢 SQL 和连接数",
        "timestamp": "2025-01-15 14:30:00"
    }


@registry.register(
    name="get_slow_queries",
    description="获取当前正在执行的慢 SQL 列表（执行时间超过 1 秒的 SQL）",
    params=[Param("limit", "返回条数上限，默认 5 条", param_type="int", required=False)]
)
def get_slow_queries(limit: int = 5) -> list:
    """
    模拟：返回慢 SQL 列表
    """
    all_queries = [
        {"sql": "SELECT * FROM orders WHERE status='pending' ORDER BY created_at",
         "duration_sec": 12.3, "calls": 150, "rows": 85000,
         "suggestion": "建议在 (status, created_at) 上建复合索引"},
        {"sql": "UPDATE users SET last_login=now() WHERE id IN (SELECT user_id FROM sessions WHERE ...)",
         "duration_sec": 8.7, "calls": 89, "rows": 12000,
         "suggestion": "子查询可改写为 JOIN，避免全表扫描"},
        {"sql": "SELECT COUNT(*) FROM logs WHERE created_at > now()-interval '30 days'",
         "duration_sec": 5.2, "calls": 320, "rows": 2000000,
         "suggestion": "考虑对 logs 表按时间分区"},
        {"sql": "DELETE FROM temp_data WHERE processed=true AND created_at < now()-interval '7 days'",
         "duration_sec": 3.1, "calls": 10, "rows": 50000,
         "suggestion": "可改为分批删除，避免长事务锁表"},
        {"sql": "SELECT DISTINCT user_id, product_id FROM order_items WHERE ...",
         "duration_sec": 2.8, "calls": 45, "rows": 30000,
         "suggestion": "DISTINCT 操作消耗大，检查是否可以去掉或用 GROUP BY 替代"},
    ]
    return all_queries[:limit]


@registry.register(
    name="get_connections",
    description="获取当前数据库的连接数统计信息（总连接数、活跃数、空闲数）",
    params=[]  # ← 无参数工具，对应 GaussMaster 的快捷路径
)
def get_connections() -> dict:
    """
    模拟：返回连接数统计
    无参数工具 — 和 GaussMaster 的 check_is_no_param_tool() 一样，跳过参数提取阶段
    """
    return {
        "total": 120,
        "active": 45,
        "idle": 60,
        "idle_in_transaction": 10,
        "waiting": 5,
        "max_connections": 200,
        "usage_percent": 60.0,
        "status": "normal",
        "suggestion": "连接数使用率 60%，处于正常范围"
    }
