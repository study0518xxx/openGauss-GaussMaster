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

from enum import Enum

from pydantic import BaseModel

from GaussMaster.multiagents.agents.prompt.reporter_prompt import LONG_TRANSACTION, GENERAL_PROMPT, \
    DISK_USAGE_GUIDANCE, MEM_USAGE_GUIDANCE, RESPONSE_TIME_GUIDANCE, RISK_OPERATION_GUIDANCE, HIGH_IO_GUIDANCE, \
    ABNORMAL_NETWORK_GUIDANCE, CLUSTER_EXCEPTION_GUIDANCE, CPU_USAGE_GUIDANCE


class ReasonTypeDef(BaseModel):
    name: str
    desc: str = ""
    guidance: dict = {}


class ReasonType(Enum):
    """By identifying specific types of tasks, the prompt template is intelligently selected to help solve the task"""

    LONG_TRANSACTION = ReasonTypeDef(
        name="pg_long_transaction_count",
        desc="长事务",
        guidance=LONG_TRANSACTION,
    )
    HIGH_CPU_USAGE = ReasonTypeDef(
        name="high_cpu_usage",
        desc="CPU使用率高",
        guidance=CPU_USAGE_GUIDANCE,
    )
    HIGH_DISK_USAGE = ReasonTypeDef(
        name="high_disk_usage",
        desc="磁盘使用率高",
        guidance=DISK_USAGE_GUIDANCE,
    )
    HIGH_MEM_USAGE = ReasonTypeDef(
        name="high_mem_usage",
        desc="内存使用率高",
        guidance=MEM_USAGE_GUIDANCE,
    )
    ABNORMAL_RESPONSE_TIME = ReasonTypeDef(
        name="abnormal_response_time",
        desc="内P80P95异常",
        guidance=RESPONSE_TIME_GUIDANCE,
    )
    HIGH_RISKY_OPERATION = ReasonTypeDef(
        name="high_risky_operation",
        desc="用户高危操作",
        guidance=RISK_OPERATION_GUIDANCE,
    )
    HIGH_IO_USAGE = ReasonTypeDef(
        name="high_io_usage",
        desc="IO使用率高",
        guidance=HIGH_IO_GUIDANCE,
    )
    ABNORMAL_NETWORK_STATUS = ReasonTypeDef(
        name="abnormal_network_status",
        desc="网络异常",
        guidance=ABNORMAL_NETWORK_GUIDANCE,
    )
    CLUSTER_EXCEPTION = ReasonTypeDef(
        name="gaussdb_cluster_state",
        desc="集群异常",
        guidance=CLUSTER_EXCEPTION_GUIDANCE,
    )
    GENERAL_TASK = ReasonTypeDef(
        name="other",
        desc="其他类型",
        guidance=GENERAL_PROMPT,
    )

    @property
    def reason_name(self):
        """Getting the template name"""
        return self.value.name

    @classmethod
    def get_reason_type(cls, reason_name):
        """Getting the template object by name"""
        for reason in cls:
            if reason.reason_name == reason_name:
                return reason.value
        return None
