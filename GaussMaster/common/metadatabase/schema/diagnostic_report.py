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

"""Diagnostic Report meta-Database Structure"""

from sqlalchemy import Column, String, BigInteger, Index, TEXT, DateTime, Boolean

from GaussMaster.common.metadatabase.base import ResultDbBase


class DiagnosticReport(ResultDbBase):
    """Diagnostic Report meta-Database Structure"""

    __tablename__ = "tb_diagnostic_report"

    report_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    alarm_title = Column(TEXT, nullable=False)
    instance = Column(String(64), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=True)
    description = Column(TEXT, nullable=False)
    scenario = Column(String(64), nullable=True)
    root_cause = Column(TEXT, nullable=False)
    solution_advice = Column(TEXT, nullable=False)
    diagnosis = Column(TEXT, nullable=False)
    cleared = Column(Boolean, nullable=False)
    created_at = Column(BigInteger, nullable=False)  # unix timestamp

    idx_history_alarms = Index(
        "idx_diagnostic_report",
        report_id,
        user_id
    )
