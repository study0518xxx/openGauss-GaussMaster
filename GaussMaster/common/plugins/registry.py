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

"""Registry for agent tool"""
import logging

from GaussMaster.multiagents.config.agent_config import AgentRoles


class Registry(dict):
    """Registry for agent tool"""

    def __init__(self, *args, **kwargs):
        super(Registry, self).__init__(*args, **kwargs)
        self._dict = {}
        self._category = {member.name: {} for member in AgentRoles}

    def __call__(self, name, description=None, params=None, roles=None):
        if roles is None:
            roles = []
        return self.register(name, description, params, roles)

    def __setitem__(self, key, value):
        self._dict[key] = value

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def __str__(self):
        return str(self._dict)

    @property
    def detail_str_list(self):
        """get function detail in string"""
        detail_with_param_str_list = []
        detail_without_param_str_list = []
        for tool in self._dict.values():
            detail_with_param_str_list.append(tool.__detail_with_param_str__)
            detail_without_param_str_list.append(tool.__detail_without_param_str__)
        return detail_with_param_str_list, detail_without_param_str_list

    @property
    def detail_dict_list(self):
        """get function detail, used for pangu cloud llm's prompt"""
        detail_with_param_dict_list = []
        detail_without_param_dict_list = []
        for tool in self._dict.values():
            detail_with_param_dict_list.append(tool.__detail_with_param_dict__)
            detail_without_param_dict_list.append(tool.__detail_without_param_dict__)
        return detail_with_param_dict_list, detail_without_param_dict_list

    @property
    def all(self):
        """all"""
        return self._dict

    def get(self, key, default_value=None):
        """get"""
        if key in self._dict:
            return self._dict[key]
        return default_value

    def get_role_tools(self, role) -> dict:
        """get_role_tools"""
        return self._category[role]

    def keys(self):
        """keys"""
        return self._dict.keys()

    def values(self):
        """values"""
        return self._dict.values()

    def items(self):
        """items"""
        return self._dict.items()

    def register(self, name, description, param_list, roles: list):
        """register tool"""

        def detail_str(func_name: str, desc: str, params: list, declare_param: bool = True):
            """return tool detail description in string type"""
            tool_desc = func_name + '：'
            if desc:
                tool_desc += desc + '，' if declare_param else desc
            if declare_param:
                tool_desc += "参数列表：" + str(params) if params else "参数列表: 无参"
            return tool_desc

        def detail_dict(func_name: str, desc: str, params: list, declare_param: bool = True):
            """return tool detail description in dict type"""
            detail = {
                "name": func_name,
                "description": desc
            }
            if declare_param:
                detail['arguments'] = [item.to_dict for item in params] if params else []
            return detail

        def decorator(target):
            """add additional attribute for registered tool"""
            target.__func_name__ = name
            target.__description__ = description
            target.__param_dict_list__ = [item.to_dict for item in param_list] if param_list else []
            target.__detail_with_param_str__ = detail_str(name, description, param_list)
            target.__detail_with_param_dict__ = detail_dict(name, description, param_list)
            target.__detail_without_param_str__ = detail_str(name, description, param_list, False)
            target.__detail_without_param_dict__ = detail_dict(name, description, param_list, False)

            def add_item(key, value):
                if key in self._dict:
                    logging.info(f"{value.__name__} already exists and will be overwritten!")
                self[key] = value
                return value

            if callable(target):
                for role in roles:
                    self._category[role].update({target.__func_name__: target})
                return add_item(target.__func_name__, target)
            return lambda x: add_item(target, x)

        return decorator
