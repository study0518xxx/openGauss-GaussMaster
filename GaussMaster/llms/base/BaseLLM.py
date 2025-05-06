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

""" LLM abstract class """
from abc import ABC, abstractmethod
from typing import Union


class BaseLLM(ABC):
    """LLM abstract class"""

    def __init__(self, model, url, temperature, stream):
        self.name = model
        self.url = url
        self.temperature = temperature
        self.stream = stream

    @property
    @abstractmethod
    def llm_type(self) -> str:
        """return llm type defined in llm_utils.LLMType"""
        pass

    @abstractmethod
    async def invoke(self, prompt: Union[list, str]) -> tuple:
        """llm invoke"""
        pass
