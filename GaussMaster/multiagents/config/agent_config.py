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

"""Agent role definitions"""

from enum import Enum


class AgentRoles(Enum):
    """Agent role Enum"""
    SQLExpert = 'sql_expert'
    StorageExpert = 'storage_expert'
    ClusterExpert = 'cluster_expert'
    PerformanceExpert = 'performance_expert'
    SourceExpert = 'source_expert'
    Repairer = 'repairer'

    @classmethod
    def values(cls):
        """values"""
        return {member.value for member in cls}
