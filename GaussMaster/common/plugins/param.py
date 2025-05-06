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

"""Param Object used for agent tool"""


class Param:
    """Param object used for agent tool"""

    def __init__(self, name, description=None, param_type=None, default_value=None, required: bool = True):
        self.name: str = name
        self.description: str = description
        self.default_value: object = default_value
        self.type: str = param_type
        self.required: bool = required

    def __repr__(self):
        param_detail = []
        if self.description:
            param_detail.append(f'{self.description}')
        if self.type:
            param_detail.append(f'{self.type}类型')
        if self.default_value:
            param_detail.append(f'{"默认值为" + str(self.default_value)}')
        if not self.required:
            param_detail.append(f'required: False')
        param_str = f'{self.name + ": "}' + ", ".join(param_detail)
        return f'({param_str})'

    @property
    def to_dict(self):
        """
        transfer param model to dict
        """
        detail = {
            "name": self.name
        }
        if self.type:
            detail["type"] = self.type
        if self.description:
            detail["description"] = self.description
        detail["required"] = self.required
        return detail
