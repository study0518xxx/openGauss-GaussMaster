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
import logging
import os
from configparser import ConfigParser

from GaussMaster.common.configs.base_configurator import BaseConfig
from GaussMaster.common.configs.config_constants import (
    SKIP_LIST, NULL_TYPE, GAUSSMASTER_CONF_HEADER,
    check_config_validity, ENCRYPTED_SIGNAL)
from GaussMaster.common.exceptions import (ConfigSettingError, InvalidCredentialException)
from GaussMaster.common.security import Encryption
from GaussMaster.common.utils import ExceptionCatcher


class ReadonlyConfig(BaseConfig):
    def set(self, section, option, value, *args, **kwargs):
        raise AssertionError('Should not call this method!')

    def __init__(self, filepath):
        """This is a readonly config and bing
        used in the running mode.
        Other apps will get config value by using this class.

        :param filepath: config filepath.
        """
        # Note: To facilitate the user to modify
        # the configuration items through the
        # configuration file easily, we add
        # inline comments to the file, but we need
        # to remove the inline comments while parsing.
        # Otherwise, it will cause the read configuration
        # items to be wrong.
        self._configs = ConfigParser(inline_comment_prefixes='#')
        with open(file=filepath, mode='r', encoding='utf-8') as fp:
            self._configs.read_file(fp)

    def check_config_validity(self):
        for section in self._configs.sections():
            for option in self._configs.options(section):
                valid, reason = check_config_validity(section, option, self._configs.get(section, option), silent=True)
                if not valid:
                    raise ConfigSettingError('%s.' % reason)

    def __getattribute__(self, name):
        try:
            return object.__getattribute__(self, name)
        except (AttributeError, KeyError):
            return self._configs.__getattribute__(name)

    # Self-defined converters:
    def get(self, section, option, *args, **kwargs):
        """Faked get() for ConfigParser class."""
        kwargs.setdefault('fallback', None)
        try:
            value = self._configs.get(section, option, *args, **kwargs)
        except configparser.InterpolationSyntaxError as e:
            raise configparser.InterpolationSyntaxError(
                e.section, e.option, 'Found bad configuration: %s-%s.' % (e.section, e.option)
            ) from None
        if value is None and not option.startswith('ssl') and option != 'api_prefix':
            logging.warning('Not set %s-%s.', section, option)
            return value

        if value == NULL_TYPE:
            value = ''
        if 'password' in option and value != '' and value:
            if value.startswith(ENCRYPTED_SIGNAL):
                real_value = value[len(ENCRYPTED_SIGNAL):]
            else:
                raise ExceptionCatcher.DontIgnoreThisError(configparser.InterpolationSyntaxError(
                    section, option, 'Gauss_master only supports encrypted password. '
                                     'Please try to set %s-%s and initialize the configuration file.'
                                     % (section, option),
                ))
            try:
                value = Encryption.decrypt(real_value)
            except Exception as e:
                raise InvalidCredentialException(
                    'An exception %s raised while decrypting.' % type(e)
                ) from None
        return value

    def getint(self, section, option, *args, **kwargs):
        """Faked getint() for ConfigParser class."""
        value = self._configs.get(section, option, *args, **kwargs)

        return int(value)

    def getfloat(self, section, option, *args, **kwargs):
        """Faked getfloat() for ConfigParser class."""
        value = self._configs.get(section, option, *args, **kwargs)

        return float(value)


class UpdateConfig(BaseConfig):
    def __init__(self, filepath):
        self.config = ConfigParser(inline_comment_prefixes=None)
        self.filepath = os.path.realpath(filepath)
        self.fp = None
        self.readonly = True

    def get(self, section, option):
        value = self.config.get(section, option)
        try:
            default_value, inline_comment = map(str.strip, value.rsplit('#', 1))
        except ValueError:
            default_value, inline_comment = value.strip(), ''
        if default_value == '':
            default_value = NULL_TYPE
        return default_value, inline_comment

    def set(self, section, option, value, inline_comment=''):
        self.readonly = False
        self.config.set(section, option, '%s  # %s' % (value, inline_comment))

    def sections(self):
        for section in self.config.sections():
            if section not in SKIP_LIST:
                comment = self.config.get('COMMENT', section, fallback='')
                yield section, comment

    def items(self, section):
        for option in self.config.options(section):
            default_value, inline_comment = self.get(section, option)
            yield option, default_value, inline_comment

    def __enter__(self):
        self.fp = open(file=self.filepath, mode='r+', errors='ignore')
        self.config.read_file(self.fp)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.readonly:
            # output configurations
            self.fp.truncate(0)
            self.fp.seek(0)
            self.fp.write(GAUSSMASTER_CONF_HEADER)
            self.config.write(self.fp)
            self.fp.flush()
        self.fp.close()
