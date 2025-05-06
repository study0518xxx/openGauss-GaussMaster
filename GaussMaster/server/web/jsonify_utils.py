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

"""jsonify utils"""
from collections.abc import Iterable


def sqlalchemy_query_jsonify(query, field_names=None):
    """sqlalchemy_query_jsonify"""
    rv = {'header': field_names, 'rows': []}
    if not field_names:
        field_names = query.statement.columns.keys()  # in order keys.
    rv['header'] = field_names
    for result in query:
        if isinstance(result, Iterable):
            row = list(result)
        else:
            row = [getattr(result, field) for field in field_names]
        rv['rows'].append(row)
    return rv
