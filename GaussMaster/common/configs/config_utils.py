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

import configparser

from GaussMaster.common.configs.config_constants import NULL_TYPE, ENCRYPTED_SIGNAL
from GaussMaster.common.configs.configurators import ReadonlyConfig, UpdateConfig
from GaussMaster.common.exceptions import PlaintextSensitiveDataInConfigError
from GaussMaster.common.security import Encryption


def load_sys_configs(confile):
    config = ReadonlyConfig(confile)
    config.check_config_validity()
    return config


def config_standardize_null_value(value):
    # If not set default value,
    # the default value is null.
    v = value.strip()
    if v == '':
        return NULL_TYPE
    return v


def config_is_null_value(value):
    return value == NULL_TYPE


def config_is_encrypted_value(value):
    """check whether password has been encrypted"""
    return value.startswith(ENCRYPTED_SIGNAL)


def config_set_value_encrypted_flag(cipher_text):
    """Use a signal ENCRYPTED_SIGNAL to mark the password that has been encrypted."""
    return ENCRYPTED_SIGNAL + cipher_text


def save_config_password(config: UpdateConfig, section, option, password):
    """
    Function to save a password securely into the configuration.

    Parameters:
    config (UpdateConfig): The configuration object.
    section (str): The section name in the configuration.
    option (str): The option name in the configuration.
    password (str): The password to be saved.
    """
    config.set(section, option, config_set_value_encrypted_flag(Encryption.encrypt(password)))


def has_config_password(config: UpdateConfig, section, option):
    """
    Function to check if a password exists in the configuration.

    Parameters:
    config (UpdateConfig): The configuration object.
    section (str): The section name in the configuration.
    option (str): The option name in the configuration.

    Returns:
    bool: True if the password exists in the configuration, False otherwise.

    Raises:
    PlaintextSensitiveDataInConfigError: If the sensitive information in the configuration is not encrypted.
    """
    try:
        pwd, _ = config.get(section, option)
    except (KeyError, configparser.NoOptionError):
        pwd = None
    if pwd in (None, '(null)', ''):
        return False
    if not config_is_null_value(pwd):
        if not config_is_encrypted_value(pwd):
            raise PlaintextSensitiveDataInConfigError(
                f"Sensitive information '{option}' of '{section}'should not be "
                f"stored in plaintext in the configuration file."
            )
    return True
