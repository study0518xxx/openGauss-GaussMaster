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

__all__ = ['HttpService', 'Response', 'JSONResponse',
           'request_mapping', 'standardized_api_output', 'Request', 'create_requests_session']

from ._service_impl import HttpService
from ._service_impl import Request
from ._service_impl import Response, JSONResponse
from ._service_impl import request_mapping
from ._service_impl import standardized_api_output
from .requests_utils import create_requests_session
