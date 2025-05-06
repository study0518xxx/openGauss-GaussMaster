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

"""to manipulate the tb_diagnostic_report table"""
import datetime
import json
from json import JSONDecodeError

from sqlalchemy import desc

from GaussMaster.common.metadatabase.ddl import truncate_table
from GaussMaster.common.metadatabase.result_db_session import get_session
from GaussMaster.common.metadatabase.schema.diagnostic_report import DiagnosticReport
from GaussMaster.common.utils.base import adjust_timezone


async def insert_diagnostic_report(report: DiagnosticReport):
    """to insert new report into tb_diagnostic_report table"""
    with get_session() as session:
        session.add(report)


async def select_diagnostic_report(all_column: bool = True, report_id: str = None, user_id: str = None, **report_args):
    """to select memory record the meet given filter condition"""
    with get_session() as session:
        if all_column:
            result = session.query(DiagnosticReport)
        else:
            result = session.query(DiagnosticReport.report_id, DiagnosticReport.alarm_title, DiagnosticReport.start_at,
                                   DiagnosticReport.cleared, DiagnosticReport.instance)
        if report_id:
            result = result.filter(DiagnosticReport.report_id == report_id)
        if user_id:
            result = result.filter(DiagnosticReport.user_id == user_id)
        scenario = report_args.get('scenario')
        if scenario:
            result = result.filter(DiagnosticReport.scenario == scenario)
        tz = adjust_timezone(report_args.get('tz')) if report_args.get('tz', None) else None
        from_timestamp = report_args.get("from_timestamp")
        to_timestamp = report_args.get("to_timestamp")
        if from_timestamp is not None:
            start_at = datetime.datetime.fromtimestamp(int(from_timestamp) / 1000, tz)
            result = result.filter(DiagnosticReport.start_at >= start_at)
        if to_timestamp is not None:
            end_at = datetime.datetime.fromtimestamp(int(to_timestamp) / 1000, tz)
            result = result.filter(DiagnosticReport.start_at <= end_at)
        instances = report_args.get("instances")
        if instances:
            try:
                instance_list = json.loads(instances)
            except JSONDecodeError:
                instance_list = instances.split(',')
            result = result.filter(DiagnosticReport.instance.in_(instance_list))
        result = result.order_by(desc(DiagnosticReport.created_at))
        offset = report_args.get('offset')
        if offset:
            result = result.offset(offset)
        limit = report_args.get('limit')
        if limit:
            result = result.limit(limit)
        return result


async def count_reports(report_id: str = None, user_id: str = None, **report_args):
    """count reports"""
    result = await select_diagnostic_report(report_id=report_id, user_id=user_id, **report_args)
    return result.count()


async def truncate_diagnostic_report():
    """to truncate the diagnostic_report table"""
    truncate_table(DiagnosticReport.__tablename__)
