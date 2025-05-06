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

"""`dynamic_config_set()` and `dynamic_config_get()` startup after get_session().
And the function get_session() can only load SQLite database in the current working directory.
Hence, if we want to use `dynamic_config_set()` or `dynamic_config_get()`, we should change the
working directory to the confpath (the path of configuration files).

    Examples
    ------------
    >>> import os
    >>> os.chdir(confpath)
    >>> dynamic_config_get('foo', 'bar')

If you want to add more dynamic configurations, you should follow the underlying list:

1. Create a python file named config_xxx.py in the module of ```dbmind.metadatabase.schema```;
2. Define an ORM class for your dynamic configurations. You can refer to class ```DynamicConfigDbBase```.
3. Then, all main processes are finished. You can call ```dynamic_config_set()``` and ```dynamic_config_get()```.
functions to modify and read them.
"""
import logging
import re

from sqlalchemy import update, insert
from sqlalchemy.exc import DBAPIError

from GaussMaster.common.exceptions import ConfigSettingError
# Register dynamic config table here.
from GaussMaster.common.metadatabase.dynamic_config_db_session import get_session
from GaussMaster.common.metadatabase.schema.config_dynamic_params import DynamicParams as Table


def dynamic_config_set(category, name, value):
    """update dynamic config"""
    if Table is None:
        raise ValueError()

    with get_session() as session:
        # If the table has the given name, then update its value.
        # Otherwise, insert a new row into the table.
        if session.query(Table).filter(Table.category == category,
                                       Table.name == name).count() > 0:
            value = None if value == "None" else check_type(category, name, value)
            session.execute(
                update(Table).where(
                    Table.name == name
                ).values(
                    value=value
                ).execution_options(
                    synchronize_session="fetch"
                )
            )
        else:
            check_config_and_name(category, name)
            session.execute(
                insert(Table).values(category=category, name=name, tag='str', value=value)
            )


def check_config_and_name(category, name):
    """check whether config and name is correct"""
    default_config = {}
    for item in Table.default_values():
        if not default_config.get(item.category):
            default_config[item.category] = []
        default_config.get(item.category).append(item.name)
    if not default_config.get(category) and category != 'encryption_components':
        raise ConfigSettingError(f'The config {category} parameter is not correct.')


def check_type(category, name, value):
    """check the type of config value"""
    if 'iv_table' == category:
        return value
    tag = ''
    for item in Table.default_values():
        if item.category == category and item.name == name:
            tag = item.tag
            break
    if not tag:
        raise ConfigSettingError(f'Could not find type of {name}.')
    if tag == 'int':
        if value.isdigit():
            try:
                return int(value)
            except ConfigSettingError:
                raise ConfigSettingError(f'Please check the type of value parameter, '
                                         f'which should be positive int.')
        else:
            raise ConfigSettingError(f'Please check the type of value parameter, '
                                     f'which should be positive int.')
    if tag == 'float':
        if re.match(r'^\d+\.\d+$', value) or 'inf' in value:
            try:
                return float(value)
            except ConfigSettingError:
                raise ConfigSettingError(f'Please check the type of value parameter, '
                                         f'which should be positive float.')
        else:
            raise ConfigSettingError(f'Please check the type of value parameter, '
                                     f'which should be positive float.')
    return value


def dynamic_config_get(category, name, fallback=None):
    """get the value of dynamic config"""
    check_config_and_name(category, name)
    with get_session() as session:
        try:
            result = tuple(session.query(Table).filter(Table.category == category, Table.name == name))
        except DBAPIError as e:
            logging.exception(e)
            # Return a none value instead of raising an
            # error directly because we have a fault-tolerant mechanism
            # later, giving the fault-tolerant mechanism a chance to try.
            return fallback
        if len(result) == 0:
            return fallback
        return result[0].value
