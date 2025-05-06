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

import copy
import inspect
import json
import re
import time
from urllib.parse import urljoin

from GaussMaster import global_vars
from GaussMaster.common.http.dbmind_request import dbmind_request
from GaussMaster.constants import (
    DBMIND,
    DISTINGUISHING_INSTANCE_LABEL,
    EXPORTER_INSTANCE_LABEL
)


def transfer_timestamp_2_date(timestamp) -> str:
    import time
    if isinstance(timestamp, int):
        timestamp = str(timestamp)
    timestamp = timestamp[0:10]
    if len(timestamp) == 10 and timestamp.isdigit():
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(timestamp)))
        except Exception:
            return timestamp
    return timestamp


def transfer_date_2_timestamp(start_time: str, end_time: str = None):
    time_pattern = r'^\d{4}-\d{2}-\d+:\d{2}:\d{2}$'
    start_time = start_time[:10] + " " + start_time[10:] if re.match(time_pattern, start_time) else start_time
    end_time = end_time[:10] + " " + end_time[10:] if end_time and re.match(time_pattern, end_time) else end_time
    from_timestamp = int(time.mktime(time.strptime(start_time, "%Y-%m-%d %H:%M:%S")) * 1000)
    to_timestamp = int(time.mktime(time.strptime(end_time, "%Y-%m-%d %H:%M:%S")) *
                       1000) if end_time else from_timestamp + 10 * 60 * 1000
    return from_timestamp, to_timestamp


def get_data_source_flag(metric_name):
    """Use this function to determine which
    label can indicate the metric's source.

    For example, the metric `node_dmi_info` comes from
    node exporter and this metric uses the label `instance`
    to indicate where the metric comes from and this label name
    is also Prometheus default. But another
    metric `gaussdb_blks_hit_ratio` uses `from_instance` to
    indicate the same meaning.

    Therefore, this function defines some rules to tell
    a caller what label name is suitable to indicate source.
    """
    instance_flag_prefixes = (
        'node_',  # from node_exporter
        'gaussdb_cluster_',  # from cmd_exporter cmd_module
        'gaussdb_process_',  # from cmd_exporter cmd_module
        'gaussdb_ping_',  # from cmd_exporter cmd_module
        'gaussdb_mount_',  # from cmd_exporter cmd_module
        'gaussdb_xlog_',  # from cmd_exporter cmd_module
        'gaussdb_nic_',  # from cmd_exporter cmd_module
        'gaussdb_log_',  # from cmd_exporter log_module
    )
    if metric_name.strip() == 'gaussdb_log_errors_rate':
        return DISTINGUISHING_INSTANCE_LABEL
    if metric_name.strip().startswith(instance_flag_prefixes):
        return EXPORTER_INSTANCE_LABEL
    return DISTINGUISHING_INSTANCE_LABEL


def get_sequence(metric_name, instance,
                 from_timestamp, to_timestamp,
                 fetch_all, labels=None):
    params = {
        "regex": True,
        "from_timestamp": from_timestamp,
        "to_timestamp": to_timestamp,
        "fetch_all": fetch_all
    }

    source_flag = get_data_source_flag(metric_name)
    if labels:
        label_names = {label.split("=")[0]: label.split("=", 1)[1]
                       for label in labels.split(",")} if isinstance(labels, str) else labels
    else:
        label_names = {}

    if instance:
        params["instance"] = instance
        if source_flag in label_names:
            label_names.pop(source_flag)
    elif source_flag in label_names:
        params["instance"] = label_names.pop(source_flag)

    params["labels"] = ",".join(f"{k}={v}" for k, v in label_names.items()) if label_names else None

    url = urljoin(global_vars.configs.get(DBMIND, "api_prefix"),
                  f"summary/metrics/{metric_name}")
    response = dbmind_request("get", url, params=params)

    if response.status_code == 200 and "data" in response.json():
        return response.json().get("data")
    else:
        return []


def generate_title(name: str, labels: dict):
    need_delete_key = {"job", "from_job", "nodename", "instance", "from_instance"}
    need_delete_key.discard(get_data_source_flag(name))
    for k, v in labels.items():
        if not v or v == "None":
            need_delete_key.add(k)

    labels = {k: v for k, v in labels.items() if k not in need_delete_key}

    return f"{name}{json.dumps(labels)}"


def parse_func_params(func):
    """
    parse the params of function
    :param func:
    :return: arguments which indicate whether is optional, var_optional_name, var_keyword_name
    """
    try:
        # in case that the func is decorated by decorator
        signature = inspect.signature(func.__wrapped__)
    except AttributeError:
        signature = inspect.signature(func)
    arguments = {}  # {param_name: is_optional}
    var_optional_name = None
    var_keyword_name = None
    for name, param in signature.parameters.items():
        if param.kind not in [param.VAR_POSITIONAL, param.VAR_KEYWORD]:
            is_optional = param.default != inspect.Parameter.empty
            arguments[name] = is_optional
        elif param.kind == param.VAR_KEYWORD:
            var_keyword_name = name
        elif param.kind == param.VAR_POSITIONAL:
            var_optional_name = name
    return arguments, var_optional_name, var_keyword_name


def has_correct_params(given_params: dict, func):
    """
    check the arguments output by llm is correct
    :param given_params: the arguments output
    :param func: the tool to be called
    :return: 1. whether is correct, 2. correct_params, 3. need_prams
    """
    arguments, _, var_keyword_name = parse_func_params(func)
    target_params = copy.deepcopy(given_params)
    need_params = dict(filter(lambda item: item[1] is False, arguments.items()))
    for given_key in given_params.keys():
        if given_key not in arguments:
            if var_keyword_name is None:
                # In case of providing redundant param
                target_params.pop(given_key)
        elif given_key in need_params:
            # In case of lacking of param
            need_params.pop(given_key)
    if need_params:
        return False, {}, need_params
    return True, target_params, {}
