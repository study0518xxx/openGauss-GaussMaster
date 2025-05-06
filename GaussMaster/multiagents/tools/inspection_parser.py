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

"""intelligent inspection parser"""
import copy
import functools
import logging

from GaussMaster.utils.ui_output_util import formatter_graph, formatter_str, formatter_table, formatter_divider

INSPECTIONS = {
    "database_performance": ["buffer_hit_rate", "user_login_out", "active_session_rate",
                             "log_error_check", "thread_pool", "db_latency", "db_transaction", "db_tmp_file",
                             "db_exec_statement", "db_deadlock", "db_tps", "db_top_query",
                             "long_transaction", "xmin_stuck", "xlog_accumulate"],
    "database_resource": ["data_directory", "log_directory", "db_size"],
    "diagnosis_optimization": ["core_dump", "dynamic_memory", "process_memory", "other_memory",
                               "guc_params", "index_advisor"],
    "instance_status": ["component_error"],
    "system_resource": ["os_cpu_usage", "os_disk_usage", "os_mem_usage", "os_disk_ioutils", "network_packet_loss"]
}
DATA_BY_INSTANCE = "data_by_instance"
DATA_BY_DB = "data_by_db"
DATA_BY_KEY_AND_INSTANCE = "data_by_key_and_instance"
DATA_TOP_QUERY = "db_top_query"
DATA_LOG_ERROR_CHECK = "data_log_error_check"
DATA_LONG_TRANSACTION = "data_long_transaction"
DATA_GUC_PARAMS = "data_guc_params"

DATA_TYPS = {
    DATA_BY_INSTANCE: ["active_session_rate", "thread_pool", "xlog_accumulate", "xmin_stuck", "data_directory",
                       "log_directory", "other_memory", "process_memory", "os_disk_ioutils", "os_disk_usage",
                       "os_mem_usage"],
    DATA_BY_DB: ["buffer_hit_rate", "db_deadlock", "db_tmp_file", "db_size"],
    DATA_BY_KEY_AND_INSTANCE: ["db_exec_statement", "db_latency", "db_tps", "user_login_out", "dynamic_memory",
                               "network_packet_loss", "os_cpu_usage", "data_db_transaction"],
    DATA_TOP_QUERY: ["db_top_query"],
    DATA_LOG_ERROR_CHECK: ["log_error_check"],
    DATA_LONG_TRANSACTION: ["long_transaction"],
    DATA_GUC_PARAMS: ["guc_params"],
}

INSPECTION_TO_DATA_TYPE_MAP = {}
for the_data_type, inspections in DATA_TYPS.items():
    for inspection in inspections:
        INSPECTION_TO_DATA_TYPE_MAP[inspection] = the_data_type


def inspection_parse_exception_catcher(func):
    """inspection result parse exception catching"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            output = func(*args, **kwargs)
            return output
        except Exception as e:
            logging.error(e)
            return [formatter_str(f'{args[0]}解析出错：{str(e)}')]

    return wrapper


@inspection_parse_exception_catcher
def parse_data_by_instance_or_db(inspection_name, data, title_list=None):
    """
    :param title_list:
    :param inspection_name: inspection name
    :param data: {
        "instance": {
            "data": [],
            "timestamps":[],
            "statistic": {
                "key": "value1",
                "key2": "value1",
            },
            "warnings":{
                "threshold_warning":[
                    {
                        "risk": "lower",
                        "timestamp": 1726106457000,
                        "value": 0.9
                    }
                ]
            }
        }
    }
    """
    if title_list is None:
        title_list = []
    output = []
    for instance_or_db, value in data.items():
        the_titles = copy.deepcopy(title_list)
        the_titles.append(instance_or_db)
        output.append(formatter_divider(divider_type='vertical', titles=the_titles))
        if value.get('data'):
            output.append(
                formatter_graph(timestamps=value.get('timestamps'), values=value.get('data'), title=inspection_name))
        statistic = value.get('statistic')
        if statistic:
            headers = list(statistic.keys())
            rows = [list(statistic.values())]
            output.append(formatter_table(headers, rows))
    return output


@inspection_parse_exception_catcher
def parse_data_by_key_and_instance(inspection_name, data):
    """
    :param inspection_name: inspection name
    :param data: {
        "insert": {
            "instance": {
                "data": [],
                "timestamps":[],
                "statistic": {
                    "key": "value1",
                    "key2": "value1",
                },
                "warnings":{
                    "threshold_warning":[
                        {
                            "risk": "lower",
                            "timestamp": 1726106457000,
                            "value": 0.9
                        }
                    ]
                }
            }
        }
    }
    """
    output = []
    for key, data_by_instance in data.items():
        temp = parse_data_by_instance_or_db(inspection_name, data_by_instance, [key])
        output.extend(temp)
    return output


@inspection_parse_exception_catcher
def parse_db_top_query(data):
    """
    :param data: [
        {
            "key1": "value1",
            "key2": "value1"
        }
    ]
    """
    output = []
    for item in data:
        output.append(formatter_table(list(item.keys()), [list(item.values())]))
    return output


@inspection_parse_exception_catcher
def parse_log_error_check(data):
    """
    :param data: {
        "instance":{
            "error_count": 3,
            "error_types": {
              "cms_heartbeat_timeout": 2,
              "errors_total": 1
            }
        }
    }
    """
    output = []
    for instance, value in data.items():
        output.append(formatter_divider(divider_type='vertical', titles=[instance]))
        output.append(formatter_str('error_count: ' + str(value.get('error_count'))))
        value_types = value.get('types')
        if value_types:
            headers = list(value_types.keys())
            rows = [list(value_types.values())]
            output.append(formatter_table(headers, rows))
    return output


@inspection_parse_exception_catcher
def parse_long_transaction(data):
    """
    :param data: [
        {
            "application_name": "workload",
            "datname": "postgres",
            "duration": 1366958.352435,
            "query": "WLM fetch collect info from data nodes;",
            "query_id": 0,
            "query_start": "2024-08-27 20:11:31.425915+08:00",
            "sessionid": 139928175896320,
            "state": "active",
            "unique_sql_id": 0,
            "usename": "cent2"
        }
    ]
    """
    output = []
    for detail in data:
        output.append(formatter_table(list(detail.keys()), [list(detail.values())]))
    return output


@inspection_parse_exception_catcher
def parse_guc_params(data):
    """
    :param data: {
        "instance": {
            "max_process_memory": {
                "cur_param": 160.0,
                "opt_param": 188.49088096618652,
                "recommend_scope": [
                    169.64179286956787,
                    207.33996906280518
                ],
                "warning": true
            }
        }
    }
    """
    output = []
    for instance, value in data.items():
        output.append(formatter_divider(divider_type='vertical', titles=[instance]))
        for guc, detail in value.items():
            output.append(formatter_str(instance + '_' + guc))
            output.append(formatter_table(list(detail.keys()), [list(detail.values())]))
    return output


def parse_inspection_result(data):
    """
    parse intelligent inspection api result
    :param data: the result of intelligent inspection api
    :return: output list which can be demonstrated in front web
    """
    result = {}
    for inspection_item, case in data.items():
        if inspection_item == 'conclusion':
            continue
        output = []
        for case_name, case_data in case.items():
            output.append(formatter_divider(divider_type='horizontal', content=case_name))
            data_type = INSPECTION_TO_DATA_TYPE_MAP.get(case_name)
            if data_type is None:
                continue
            if data_type in [DATA_BY_INSTANCE, DATA_BY_DB]:
                output.extend(parse_data_by_instance_or_db(case_name, case_data))
            if data_type == DATA_BY_KEY_AND_INSTANCE:
                output.extend(parse_data_by_key_and_instance(case_name, case_data))
            if data_type == DATA_TOP_QUERY:
                output.extend(parse_db_top_query(case_data))
            if data_type == DATA_LONG_TRANSACTION:
                output.extend(parse_long_transaction(case_data))
            if data_type == DATA_LOG_ERROR_CHECK:
                output.extend(parse_log_error_check(case_data))
            if data_type == DATA_GUC_PARAMS:
                output.extend(parse_guc_params(case_data))
        result[inspection_item] = output
    return result
