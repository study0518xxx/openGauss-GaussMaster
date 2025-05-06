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

from sqlalchemy import Column, String, BigInteger, Index, TEXT

from GaussMaster.common.metadatabase.base import ResultDbBase


class InteractionMemory(ResultDbBase):
    """Interaction Memory meta-Database Structure"""

    __tablename__ = "tb_interaction_memory"

    qa_record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False)
    question = Column(TEXT, nullable=False)
    answer = Column(TEXT, nullable=True)
    llm_name = Column(String(64), nullable=True)
    function_call = Column(TEXT, nullable=True)
    created_at = Column(BigInteger, nullable=False)  # unix timestamp

    idx_history_alarms = Index(
        "idx_interaction_memory",
        user_id,
        session_id
    )
