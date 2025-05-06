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

import functools

import psycopg2
from GaussMaster import global_vars
from GaussMaster.constants import DBMIND, SECTION_VECTOR


class SSLContext:
    def __init__(self, cert, key, ca=None, key_pwd=None):
        self.ssl_certfile = cert
        self.ssl_keyfile = key
        self.ssl_keyfile_password = key_pwd
        self.ssl_ca_file = ca

    def __bool__(self):
        return bool(self.ssl_certfile) and bool(self.ssl_keyfile)


def get_ssl_context():
    """
    The GaussMaster service only uses one set of ssl_context as client.
    """
    ssl_certfile = global_vars.configs.get(DBMIND, "ssl_certfile", fallback=None)
    ssl_keyfile = global_vars.configs.get(DBMIND, "ssl_keyfile", fallback=None)
    ssl_ca_file = global_vars.configs.get(DBMIND, "ssl_ca_file", fallback=None)
    keyfile_password = global_vars.configs.get(DBMIND, 'ssl_keyfile_password', fallback=None)
    ssl_context = SSLContext(cert=ssl_certfile, key=ssl_keyfile, ca=ssl_ca_file, key_pwd=keyfile_password)
    return ssl_context


def configure_psycopg2_ssl():
    """configure psycopg2 ssl module"""
    if global_vars.configs.get(SECTION_VECTOR, "ssl", fallback='false').upper() == 'TRUE':
        ssl_certfile = global_vars.configs.get(SECTION_VECTOR, 'ssl_certfile')
        ssl_keyfile = global_vars.configs.get(SECTION_VECTOR, 'ssl_keyfile')
        ssl_ca_file = global_vars.configs.get(SECTION_VECTOR, 'ssl_ca_file')
        ssl_mode = global_vars.configs.get(SECTION_VECTOR, 'ssl_mode')
        if ssl_mode not in ['disable', 'prefer', 'verify-ca']:
            raise ValueError(f"ssl_mode only support disable or prefer or verify-ca mode."
                             f" Please make sure the parameters meet the requirements.")
        psycopg2.connect = functools.partial(psycopg2.connect, sslmode=ssl_mode, sslcert=ssl_certfile,
                                             sslkey=ssl_keyfile,
                                             sslrootcert=ssl_ca_file)
