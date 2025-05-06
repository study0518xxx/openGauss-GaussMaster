# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
#
# openGauss is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.

"""DBMind configuration"""

DBMIND_DETECTIONS = {
    "disk_usage": {
        "name": "磁盘使用率",
        "anomaly_name": "磁盘使用率过高",
        "related_metrics": ["gaussdb_mount_usage", "os_disk_usage"]
    },
    "os_disk_io_exception": {
        "name": "磁盘IO延迟等待",
        "anomaly_name": "磁盘IO延迟过高",
        "related_metrics": ["os_disk_await", "os_disk_io_read_delay"]
    },
    "os_cpu_user_usage": {
        "name": "CPU使用率",
        "anomaly_name": "CPU使用率过高",
        "related_metrics": ["os_cpu_user_usage", "gaussdb_process_cpu_usage"]
    },
    "os_mem_usage": {
        "name": "内存使用率",
        "anomaly_name": "内存使用率过高",
        "related_metrics": ["os_mem_usage", "gaussdb_process_mem_usage"]
    },
    "self_security_exception": {
        "name": "用户高危操作",
        "anomaly_name": "存在用户高危操作",
        "related_metrics": ["scanning_attack", "brute_force_login_attack",
                            "user_violation_attack"]
    },
    "P80_P95": {
        "name": "P80P95异常",
        "anomaly_name": "数据库查询执行耗时整体增加",
        "related_metrics": ["statement_responsetime_percentile_p80",
                            "statement_responsetime_percentile_p95"]
    },
    "pg_long_transaction_count": {
        "name": "长事务",
        "anomaly_name": "数据库存在超长事务",
        "related_metrics": ["pg_long_transaction_count"]
    },
    "gaussdb_ping_lag": {
        "name": "节点网络状态",
        "anomaly_name": "数据库节点间网络异常",
        "related_metrics": ["gaussdb_ping_lag", "gaussdb_ping_packet_rate"]
    },
    "gaussdb_cluster_state": {
        "name": "集群状态",
        "anomaly_name": "数据库节点状态异常",
        "related_metrics": ["gaussdb_cluster_state"]
    },
    "core_dump": {
        "name": "数据库内核异常",
        "anomaly_name": "数据库内核异常",
        "related_metrics": ["gaussdb_log_ffic"]
    },
    "slow_sql": {
        "name": "慢sql",
        "anomaly_name": "存在慢sql",
        "related_metrics": ["slow_sql"]
    },
}

# 根据告警的指标名映射到巡检项（多个指标名对应一个巡检项）
METRIC_2_INSPECTION_MAP = {}
for inspection_key, inspection_detail in DBMIND_DETECTIONS.items():
    for metric in inspection_detail['related_metrics']:
        METRIC_2_INSPECTION_MAP[metric] = inspection_key

# 自安全场景：场景名->相关指标
SCENARIO_MAP = {
    'scanning_attack': ['gaussdb_log_errors_rate', 'gaussdb_user_violation_rate'],
    'brute_force_login_attack': ['gaussdb_invalid_logins_rate', 'gaussdb_user_locked_rate'],
    'user_violation_attack': ['gaussdb_user_violation_rate']
}

NODE_LEVEL_METRIC = {
    "load_average1",
    "gaussdb_cpu_usage",
    "non_db_mem_usage",
    "xlog_setting_margin",
}

REASON_TRANSLATION = {
    # 自安全场景
    "scanning_attack": "扫描攻击",
    "brute_force_login_attack": "暴力登录",
    "user_violation_attack": "用户越权",
    # 根因分析
    "unknown": "未知原因",
    "heavy_transaction": "业务压力增大",
    "cpu_io_delay": "io延时高",
    "thread_pool_io_delay": "磁盘读写时延过高",
    "slow_sql": "慢SQL",
    "heavy_sessions": "会话数上涨",
    "dynamic_memory_rise": "动态内存上涨",
    "shared_memory_rise": "共享内存上涨",
    "heavy_writing": "数据库表空间膨胀",
    "heavy_io": "数据磁盘读写IO使用率超阈值",
    "memory_heavy_writing": "未落盘脏页数过高",
    "disk_io_delay": "io延时高",
    "workload_rise": "负荷持续上升",
    "high_gaussdb_xlog_count": "xlog堆积",
    "other_memory_rise": "其他内存上涨",
    "non_db_memory_rise": "非数据库进程内存泄露",
    "massive_login_denies": "大量登录失败",
    "recycle_lsn": "xlog归档失败",
    "replication_slot": "逻辑复制槽阻塞xlog回收",
    "building": "备机build阻塞xlog回收",
    "dcf": "dcf阻塞xlog回收",
    "dummy_standby": "dummy standby场景阻塞xlog回收",
    "cbm": "增备阻塞xlog回收",
    "standby_backup": "备份槽阻塞xlog回收",
    "extro_read": "极致rto阻塞xlog回收",
    "wrong_xlog_setting": "参数设置不当",
    "recycle_failed": "xlog回收进程失效",
    "lock_conflict": "锁冲突加剧",
    "network_lag": "网络延迟高",
    "process_cpu_usage": "数据库进程cpu占用率高",
    "disk_sub_health": "磁盘读写时延过高",
    "shift_response_time": "SQL执行时间上升",
    "core_dump": "内核错误"
}

METRIC_TRANSLATION = {
    # 自安全场景
    "gaussdb_total_connection": "并发连接数",
    "oldestxmin_increase": "oldestxmin相比于12小时前的增长量",
    "gaussdb_log_errors_rate": "SQL执行错误率",
    "gaussdb_user_violation_rate": "用户越权率",
    "gaussdb_invalid_logins_rate": "无效登录率",
    "gaussdb_user_locked_rate": "用户锁定率",
    "gaussdb_db_size_total_increase": "数据库总大小相比于1h前的增长量",
    # 根因分析
    "gaussdb_qps_by_instance": "数据库事务数",
    "os_network_receive_bytes": "网络下载量",
    "os_network_transmit_bytes": "网络上传量",
    "pg_total_memory_detail_mbytes": "数据库pg_total_memory_detail视图",
    "os_disk_io_read_delay": "磁盘io读延迟",
    "os_disk_io_write_delay": "磁盘io写延迟",
    "gaussdb_active_connection": "数据库活跃连接数",
    "pg_sql_count_insert": "insert语句数量",
    "pg_sql_count_update": "update语句数量",
    "gaussdb_process_cpu_usage": "数据库进程cpu使用率",
    "os_disk_ioutils": "磁盘io使用率",
    "os_disk_await": "平均磁盘读写等待时长",
    "pg_long_transaction_count": "长事务",
    "xlog_margin": "设置的xlog数量与实际xlog数量之差",
    "gaussdb_log_login_denied": "数据库用户登陆失败",
    "gaussdb_log_dead_lock_count": "死锁日志",
    "gaussdb_log_lock_wait_timeout": "等锁超时日志",
    "lsn_margin": "最早的xlog的lsn与xlog回收点之差",
    "replication_lsn_margin": "逻辑复制槽的lsn与最早的xlog的lsn之差",
    "xlog_setting_margin": "xlog所在磁盘容量超出设置的xlog上限的KB数",
    "non_db_mem_usage": "非数据库进程内存使用率",
    "gaussdb_ping_lag": "数据库节点网络延迟",
    "os_cpu_user_usage": "cpu使用率",
    "os_mem_usage": "内存使用率",
    "statement_responsetime_percentile_p80": "语句执行时间的80分位数",
    "statement_responsetime_percentile_p95": "语句执行时间的95分位数",
    "gaussdb_log_recycle_lsn": "xlog日志回收的lsn",
}

FEATURE_MAP = {
    "cn_status": "cn节点状态",
    "cn_restart": "cn重启",
    "cn_start": "cn启动",
    "cms_heartbeat_restart": "cms仲裁心跳超时重启",
    "cms_phonydead_restart": "cms仲裁僵死超时重启",
    "bind_ip_failed": "cn绑定ip失败",
    "panic": "发生PANIC级别错误",
    "ffic_updated": "ffic日志更新",
    "ping": "网络异常",
    "cn_dn_disconnected": "cn与dn断连",
    "cn_down_to_delete": "cn剔除",
    "cn_restart_time_exceed": "cn重启次数超限",
    "cn_disk_damage": "cn磁盘损坏",
    "cn_port_conflict": "cn端口冲突",
    "cn_NIC_down": "cn网卡故障",
    "cn_manual_stop": "cn手动停止",
    "cn_read_only": "cn只读",
    "dn_status": "dn节点状态",
    "dn_manual_stop": "dn手动停止",
    "dn_disk_damage": "dn磁盘故障",
    "dn_NIC_down": "dn网卡故障",
    "dn_port_conflict": "dn端口冲突",
    "cms_restart_pending": "cms仲裁重启dn",
    "dn_read_only": "dn只读",
    "dn_ping_standby": "日志更新",
    "dn_writable": "dn写入故障",
}

ANSWER_MAP = {
    "cn": {
        "Normal": "正常",
        "Unknown": "未知原因",
        "CN heartbeat timeout": "CN心跳超时",
        "CN phony dead": "CN僵死",
        "Core": "内核错误",
        "CN ip lost": "CN无法绑定ip",
        "CN disk Damage": "CN磁盘损坏",
        "CN port conflict": "CN端口冲突",
        "CN NIC down": "CN网卡故障",
        "CN manual stop": "CN被手动停止",
        "CN down/disconnection": "CN宕机或断网",
        "CN disconnected from dn": "CN与DN断开连接",
        "CN read only": "CN只读",
    },
    "dn": {
        "Normal": "正常",
        "Unknown": "未知原因",
        "DN manual stop": "DN被手动停止",
        "DN disk Damage": "DN磁盘损坏",
        "DN NIC down": "DN网卡故障",
        "DN port conflict": "DN端口冲突",
        "DN restarted by cms": "cm_server仲裁重启DN",
        "DN phony dead": "DN僵死重启",
        "Core": "内核错误",
        "DN read only": "DN只读",
        "DN down/disconnection": "DN宕机或断网",
        "DN Primary disconnected with Standby": "主备DN间网络异常",
        "DN ip lost": "DN无法绑定ip",
    },
}

STATUS_MAP = {
    "cn": {
        "zh": {
            -1: "CM异常",
            0: "正常",
            1: "停机",
            2: "被剔除",
            3: "只读模式",
        },
        "en": {
            -1: "Abnormal output from cm",
            0: "Normal",
            1: "Down",
            2: "Deleted",
            3: "ReadOnly",
        }
    },
    "dn": {
        "zh": {
            -1: "CM异常",
            0: "正常",
            1: "未知",
            2: "需要修复",
            3: "升降级中",
            4: "磁盘损坏",
            5: "端口冲突",
            6: "构建中",
            7: "构建失败",
            8: "内核错误",
            9: "只读模式",
            10: "被手动停止",
        },
        "en": {
            -1: "Abnormal output from cm",
            0: "Normal",
            1: "Unknown",
            2: "Need repair",
            3: "Demoting, Promoting or Wait promoting",
            4: "Disk damaged",
            5: "Port conflicting",
            6: "Building",
            7: "Build failed",
            8: "CoreDump",
            9: "ReadOnly",
            10: "Manually stopped",
        }
    }
}

METRIC_DIAGNOSIS_REASON_MAP = {
    "os_cpu_user_usage": ["high_cpu_usage"],
    "pg_thread_pool_rate": ["high_thread_pool_rate"],
    "gaussdb_mount_usage": ["high_disk_usage"],
    "os_disk_usage": ["high_disk_usage"],
    "os_mem_usage": ["high_dynamic_mem_usage", "high_shared_mem_usage", "mem_leak"],
    "os_disk_await": ["high_io_delay"],
    "xlog_margin": ["high_xlog_count"],
    "pg_long_transaction_count": ["long_transaction"],
    "gaussdb_log_deadlock_count": ["lock_conflict"],
    "gaussdb_log_lock_wait_timeout": ["lock_conflict"],
    "gaussdb_log_ffic": ["core_dump"],
    "statement_responsetime_percentile_p80": ["shift_response_time"],
    "statement_responsetime_percentile_p95": ["shift_response_time"]
}
