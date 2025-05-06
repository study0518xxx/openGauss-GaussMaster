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

"""Interaction Memory meta-Database Structure"""

from sqlalchemy import Column, String, TEXT, UniqueConstraint, Integer

from GaussMaster.common.metadatabase.base import ResultDbBase


class ManagedCluster(ResultDbBase):
    """Managed cluster structure"""

    __tablename__ = "tb_managed_cluster"

    cluster_id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_name = Column(String(120), nullable=False)
    host = Column(String(64), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(TEXT, nullable=False)
    password = Column(TEXT, nullable=False)
    __table_args__ = (
        UniqueConstraint('host', 'port', name='unique_instance_constraint'),
    )
