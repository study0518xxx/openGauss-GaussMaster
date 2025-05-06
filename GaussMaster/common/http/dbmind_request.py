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

"""dbmind request adapter"""
import json
import logging
from urllib.parse import urljoin

import requests

from GaussMaster import global_vars
from GaussMaster.common.http import create_requests_session
from GaussMaster.common.http.ssl import get_ssl_context
from GaussMaster.common.metadatabase.dao.clusters import select_managed_cluster
from GaussMaster.common.security import Encryption
from GaussMaster.common.utils.checking import split_ip_port
from GaussMaster.constants import DBMIND
from GaussMaster.server.web.context_manager import current_instance


class AutoSession(requests.Session):
    instance_session_pairs = dict()

    def __init__(self, login_url, credentials):
        super().__init__()
        self.login_url = login_url
        self.credentials = credentials
        self.token = None

    def login(self):
        # 登录并获取Token
        ssl = True if self.login_url.startswith('https://') else False
        ca_params = get_ca_params() if ssl else {}
        with create_requests_session(ssl_context=get_ssl_context()) as session:
            response = session.request('POST', self.login_url, data=json.dumps(self.credentials),
                                       **ca_params)
        token = response.json().get('access_token')
        if token:
            self.token = token
            self.headers.update({'Authorization': f'Bearer {self.token}'})
        else:
            raise ValueError("Login failed, no token received.")

    def request(self, method, url, **kwargs):
        # 如果没有Token，先登录
        if not self.token:
            self.login()

        # 尝试请求，如果返回401则重新登录
        with create_requests_session(ssl_context=get_ssl_context()) as session:
            session.headers.update({'Authorization': f'Bearer {self.token}'})
            response = session.request(method, url, **kwargs)
        if response.status_code == 401:
            self.login()
            with create_requests_session(ssl_context=get_ssl_context()) as session:
                session.headers.update({'Authorization': f'Bearer {self.token}'})
                response = session.request(method, url, **kwargs)
        return response


def update_session(instance, session_instance):
    """update session"""
    if instance in AutoSession.instance_session_pairs:
        logging.info('The session of instance %s has been updated.', instance)
    else:
        logging.info('The session of instance %s has been created.', instance)
    AutoSession.instance_session_pairs[instance] = session_instance


def dbmind_request(method: str, url: str, **kwargs):
    """send request to DBMind"""
    if url.startswith('https://'):
        use_ssl = True
    elif url.startswith('http://'):
        use_ssl = False
    else:
        raise ValueError('Please configure the api_prefix parameter of DBMind section ')

    request_params = {
        'method': method,
        'url': url,
        **kwargs
    }
    ca_params = get_ca_params() if use_ssl else dict()
    request_params.update(ca_params)
    instance = current_instance.get()
    username, password = get_user_password(instance)
    session = get_dbmind_session(instance, username, password)

    return session.request(**request_params)


def get_user_password(instance):
    host, port = split_ip_port(instance)
    result = select_managed_cluster(host=host, port=port)
    if not result:
        raise ValueError(f"No DBMind cluster found with {host}:{port}")
    return result.get('username'), Encryption.decrypt(result.get('password'))


def create_new_session(instance, username, password):
    """create new session"""
    login_params = {
        "username": username,
        "grant_type": "",
        "password": password,
        "scope": instance,
        "client_id": "",
        "client_secret": "",
    }
    login_url = urljoin(global_vars.configs.get(DBMIND, 'api_prefix'), 'token')
    return AutoSession(login_url, login_params)


def get_dbmind_session(instance, username, password):
    if instance not in AutoSession.instance_session_pairs or not AutoSession.instance_session_pairs[instance]:
        login_params = {
            "username": username,
            "grant_type": "",
            "password": password,
            "scope": instance,
            "client_id": "",
            "client_secret": "",
        }
        login_url = urljoin(global_vars.configs.get(DBMIND, 'api_prefix'), 'token')
        AutoSession.instance_session_pairs[instance] = AutoSession(login_url, login_params)
    return AutoSession.instance_session_pairs[instance]


def get_ca_params():
    ssl_certfile = global_vars.configs.get(DBMIND, 'ssl_certfile')
    ssl_keyfile = global_vars.configs.get(DBMIND, 'ssl_keyfile')
    ssl_ca_file = global_vars.configs.get(DBMIND, 'ssl_ca_file')
    ca_params = {
        'cert': (ssl_certfile, ssl_keyfile),
        'verify': ssl_ca_file
    }
    return ca_params
