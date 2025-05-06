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

"""Exception definitions"""

from GaussMaster.global_vars import LANGUAGE


class PlaintextSensitiveDataInConfigError(Exception):
    """Exception raised when sensitive data is found in plaintext in the config file."""
    pass


class ApiClientException(Exception):
    """API client exception, raises when response status code != 200."""
    pass


class CertCheckException(Exception):
    """cert check exception, raises when response status code != 0."""
    pass


class SetupError(Exception):
    def __init__(self, msg, *args, **kwargs):
        self.msg = msg
        super().__init__(msg, *args)


class InvalidCredentialException(Exception):
    """InvalidCredentialException"""
    pass


class SQLExecutionError(Exception):
    """SQLExecutionError"""
    pass


class ConfigSettingError(Exception):
    """ConfigSettingError"""
    pass


class DuplicateTableError(Exception):
    """DuplicateTableError"""
    pass


class InvalidSequenceException(ValueError):
    """InvalidSequenceException raises when tsdb sequence is invalid."""
    pass


class CustomToolException(Exception):
    """CustomToolException raises when agent tool crashes."""

    def __init__(self, msg, *args):
        if isinstance(msg, dict):
            if LANGUAGE in msg:
                message = msg.get(LANGUAGE)
            else:
                message = msg.get("en", "")
        else:
            message = msg

        self.message = message
        super().__init__(message, *args)

    def __str__(self):
        return f"{self.message}"
