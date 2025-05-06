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

from configparser import ConfigParser

from GaussMaster.common.utils import write_to_terminal
from GaussMaster.common.utils.checking import check_port_valid, check_ip_valid
from GaussMaster.common.utils.checking import warn_ssl_certificate

# header text
GAUSSMASTER_CONF_HEADER = """# Copyright: Copyright (c) Huawei Technologies Co., Ltd. 2024-2024. All rights reserved.

# Notice:
# 1. (null) explicitly represents empty or null. Meanwhile blank represents undefined.
# 2. GaussMaster encrypts password parameters. Hence, there is no plain-text password after initialization.
# 3. Users can only configure the plain-text password in this file before initializing
#    (that is, using the --initialize option),
#    and then if users want to modify the password-related information,
#    users need to use the '--initialize' sub-command to achieve.
# 4. If users use relative path in this file, the current working directory is the directory where this file is located.
"""

# fixed constant flags in the config file
NULL_TYPE = '(null)'  # empty text.
ENCRYPTED_SIGNAL = 'Encrypted->'

# Used by check_config_validity().
CONFIG_OPTIONS = {
    'LOG-level': ['DEBUG', 'INFO', 'WARNING', 'ERROR']
}
POSITIVE_INTEGER_CONFIG = ['LOG-maxbytes', 'LOG-backupcount']
BOOLEAN_CONFIG = []


def check_config_validity(section, option, value, silent=False):
    config_item = '%s-%s' % (section, option)
    # exceptional cases:
    if config_item in ('VECTOR-port', 'VECTOR-host'):
        if value.strip() == '' or value == NULL_TYPE:
            return True, None

    if config_item == 'DBMind-api_prefix' and not silent:
        if value.strip() in ('', NULL_TYPE):
            write_to_terminal(
                'Notice: Without explicitly setting agent configurations, '
                'the automatic detection mechanism is used.',
                color='yellow'
            )

    # normal inspection process:
    if option == 'port':
        if section == 'VECTOR':
            if not check_port_valid(value):
                return False, 'Invalid port for %s: %s(1024-65535)' % (config_item, value)
    if option == 'host':
        if section == 'VECTOR':
            if not check_ip_valid(value):
                return False, 'Invalid IP Address for %s: %s' % (config_item, value)
    if option == ['vector_dbname', 'metadatabase']:
        if value == NULL_TYPE or value.strip() == '':
            return False, 'Unspecified database name %s' % value
    if config_item in POSITIVE_INTEGER_CONFIG:
        if not str.isdigit(value) or int(value) <= 0:
            return False, 'Invalid value for %s: %s' % (config_item, value)
    if config_item in BOOLEAN_CONFIG:
        if value.lower() not in ConfigParser.BOOLEAN_STATES:
            return False, 'Invalid boolean value for %s.' % config_item
    options = CONFIG_OPTIONS.get(config_item)
    if options and value not in options:
        return False, 'Invalid choice for %s: %s' % (config_item, value)
    if value != NULL_TYPE and 'ssl_certfile' in option:
        warn_ssl_certificate(value, None, None)
    if value != NULL_TYPE and 'ssl_keyfile' == option:
        warn_ssl_certificate(None, value, None)
    if value != NULL_TYPE and 'ssl_ca_file' == option:
        warn_ssl_certificate(None, None, value)
    # Add more checks here.
    return True, None


# Ignore the following sections while config iterates
SKIP_LIST = ('COMMENT', 'LOG')
