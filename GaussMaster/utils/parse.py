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

import json
import re
from typing import Union, NamedTuple


class AgentAction(NamedTuple):
    """Agent's action to take."""

    tool: str
    tool_input: dict
    log: str


class AgentFinish(NamedTuple):
    """Agent's return value."""

    return_values: str
    log: str


def generate_json(raw_string):
    """extract json from raw string"""
    stack = []
    result = []
    for c in raw_string:
        result.append(c)
        if c == '{':
            stack.append(c)
        elif c == '}':
            if stack:
                stack.pop()
            else:
                result.pop()
    result.extend('}' * len(stack))
    return ''.join(result)


# 自定义解析类
class CustomOutputParser:
    action_value = ''

    def parse_action(self, output: str) -> Union[AgentAction, AgentFinish]:
        """transfer llm output to AgentAction or AgentFinish"""
        try:
            match = re.search(r"({.*})", output, re.DOTALL)
            if match:
                new_output = re.sub(r'\\n', r'\n', match.group(1).strip('\\n'))
                new_output = re.sub(r'\\"', r'"', new_output)
                new_output = re.sub(r'\\', r'', new_output)
                new_output = generate_json(new_output)
                response = json.loads(new_output)
            else:
                return AgentFinish(output, output)
            action_value = response["action"]
            action_input_value = response["action_input"]
            if action_value == "Final Answer":
                return AgentFinish(action_input_value, output)
            return AgentAction(action_value, action_input_value, output)
        except Exception:
            return AgentFinish(output, output)

    def parse_tool_name(self, output: str) -> Union[AgentAction, AgentFinish]:
        """parse llm output to get tool_name"""
        try:
            match = re.search(r"({.*})", output, re.DOTALL)
            if match:
                new_output = re.sub(r'\\n', r'\n', match.group(1).strip('\\n'))
                new_output = re.sub(r'\\"', r'"', new_output)
                new_output = re.sub(r'\\', r'', new_output)
                new_output = generate_json(new_output)
                response = json.loads(new_output)
            else:
                return AgentFinish('ParseError', output)
            if 'tool_name' in response:
                return AgentAction(response['tool_name'], {}, output)
            if 'answer' in response:
                return AgentFinish(response['answer'], output)
            return AgentFinish('ParseError', output)
        except Exception:
            return AgentFinish('ParseError', output)

    def parse_params(self, output: str):
        """parse llm output to get tool params"""
        try:
            match = re.search(r"({.*})", output, re.DOTALL)
            if match:
                new_output = re.sub(r'\\n', r'\n', match.group(1).strip('\\n'))
                new_output = re.sub(r'\\"', r'"', new_output)
                new_output = re.sub(r'\\', r'', new_output)
                new_output = generate_json(new_output)
                response = json.loads(new_output)
                return response, True
            return {}, False
        except Exception:
            return {}, False


output_parser = CustomOutputParser()
