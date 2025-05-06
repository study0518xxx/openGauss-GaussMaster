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

import os

from GaussMaster.common.configs.kb_config import OPS_KB_TABLE_CONFIG, OPS_MEMORY_TABLE_CONFIG
from GaussMaster.constants import GAUSSMASTER_PATH, KNOWLEDGE_BASE_PATH
from GaussMaster.common.metadatabase.utils import get_vector_db


class Document:

    def __init__(self, metadata=None, data=None, data_name=None) -> None:
        self.metadata = metadata
        self.data = data
        self.data_name = data_name


def upload_single_table(table_config, truncate_table):
    """upload db file"""
    vector_db = get_vector_db(vector_config=table_config)
    f_name = table_config.get('table_name') + ".db"
    db_file = os.path.realpath(os.path.join(GAUSSMASTER_PATH, KNOWLEDGE_BASE_PATH, f_name))
    if not os.path.exists(db_file):
        raise Exception(f"db_file is not found, please check.")
    vector_db.load_local(db_file, need_index=False, truncate_table=truncate_table)


def upload_ops_knowledge_base(truncate_table=False):
    """Function load db file to create basic knowledge table."""
    for config in OPS_KB_TABLE_CONFIG.values():
        upload_single_table(config, truncate_table)
    vector_db = get_vector_db(vector_config=OPS_MEMORY_TABLE_CONFIG.get('GM_HISTORY_MEMORY'))
    vector_db.load_table()


def download_single_table_to_db_file(vector_config):
    """download single db file"""
    vector_db = get_vector_db(vector_config)
    db_file = vector_config.get('table_name') + ".db"
    f_name = os.path.realpath(os.path.join(GAUSSMASTER_PATH, KNOWLEDGE_BASE_PATH, db_file))
    vector_db.save_local(f_name)


def download_table_to_db_file():
    """download db file"""
    for config in OPS_KB_TABLE_CONFIG.values():
        download_single_table_to_db_file(config)
