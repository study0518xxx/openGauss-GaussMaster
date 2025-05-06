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

import time

from GaussMaster.global_vars import LANGUAGE

DONE_FLAG = {
    'type': 'progress',
    'content': 'DONE'
}


def get_content_by_language(default_content):
    """get content by language"""
    if isinstance(default_content, str):
        content = default_content
    elif isinstance(default_content, dict):
        if LANGUAGE in default_content:
            content = default_content.get(LANGUAGE)
        else:
            content = default_content.get("en")
    else:
        content = default_content.get("en", "")
    return content


def formatter_filter(name, default_content, candidate):
    """ Filter box """
    return {'type': 'filter', 'name': name, 'content': get_content_by_language(default_content), 'candidate': candidate}


def formatter_list(name, content_list):
    """ Packaging the unordered list """
    return {'type': 'sort', 'name': name, 'content': content_list}


def formatter_alarm(metric, status, content, event, instance):
    """alarm button formatter"""
    return {
        'type': 'status',
        'ip': instance,
        'content': {
            'name': metric,
            'status': status,
            'button': {
                'name': f'一键诊断',
                'show': content,
                'event': event,
                'question': 1
            }
        }
    }


def formatter_empty_alarm(name, status):
    """empty alarm button formatter"""
    return {
        'type': 'status',
        'content': {
            'name': name,
            'status': status,
            'button': {}
        }
    }


def down_sampling(source_timestamps, source_values, k=50):
    """down sampling"""
    step = len(source_timestamps) / k
    if len(source_timestamps) <= k or step <= 1:
        return source_timestamps, source_values

    target_timestamps = []
    target_values = []
    cur = 0
    while cur < len(source_timestamps):
        target_timestamps.append(source_timestamps[int(cur)])
        target_values.append(source_values[int(cur)])
        cur += step

    return target_timestamps, target_values


def formatter_graph(timestamps, values, x='', y='', title='', color: str = 'black'):
    """graph formatter"""
    if timestamps and isinstance(timestamps[0], int):
        timestamps = [time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(item / 1000)))
                      for item in timestamps]

    if values and isinstance(values[0], float):
        values = [round(item, 4) for item in values]

    timestamps_down_sampled, values_down_sampled = down_sampling(timestamps, values)

    return {
        'type': 'graph',
        'content': {
            'timestamps': timestamps_down_sampled,
            'values': values_down_sampled,
            'x': x,
            'y': y,
            'title': get_content_by_language(title),
            'color': color
        }
    }


def formatter_table(headers, rows):
    """table formatter"""
    return {
        'type': 'table',
        'content': {
            'headers': headers,
            'rows': rows
        }
    }


def formatter_str(content, color: str = 'black'):
    """string output formatter"""
    if isinstance(content, str):
        return {'type': 'str', 'content': content, 'color': color}
    elif isinstance(content, dict):
        if LANGUAGE in content:
            return {'type': 'str', 'content': content.get(LANGUAGE), 'color': color}
        elif "en" in content:
            return {'type': 'str', 'content': content.get("en"), 'color': color}

    return {'type': 'str', 'content': ""}


def formatter_button(name, question, show='', event='', text=None):
    """
    :param name: the button's name
    :param question: 0|1, if question == 1, clicking the button will send new question as human, or will open a drawer
    :param show: only used when question = 1, clicking the button will send new question as human
    :param event: only used when question = 1, clicking the button will send the event to backend
    :param text: the text to be shown in the drawer, only used when question == 0
    :return:
    """
    if text is None:
        text = dict()

    template = {
        'type': 'button',
        'content': {
            'name': name,
            'show': show,
            'event': event,
            'question': question,
            'text': text
        }
    }
    return template


def formatter_progress(default_content):
    """progress type"""
    content = get_content_by_language(default_content)
    return {'type': 'progress', 'content': content}


def formatter_multi_option(candidate: dict):
    """
    formatter_multi_option
    :param candidate: {"father_name":["child1", "child2"]}
    :return: [{"value":1, "label": "xx", "children": []}]
    """

    def formatter_child_option(value):
        """child option formatter"""
        return {'value': value, 'label': value}

    output = []
    for father_label, children in candidate.items():
        father_options = {
            'value': father_label,
            'label': father_label,
            'children': [formatter_child_option(child) for child in children]
        }
        output.append(father_options)
    return output


def formatter_inspection_button(tip, option, select, button):
    """
    formatter_inspection_button
    :param tip: 'Please select inspection items'
    :param option: the dictionary of inspection items
    :param select: instance list
    :param button: the text in the button
    :return:
    """
    return {
        'type': 'inspection',
        'tip': get_content_by_language(tip),
        'option': option,
        'select': select,
        'button': get_content_by_language(button)
    }


def formatter_title(content, level, color: str = 'black'):
    """
    formatter title
    :param color: color
    :param content: title str
    :param level: [1,2,3,4], h1, h2, h3, h4
    """
    return {
        'type': 'title',
        'level': level,
        'content': get_content_by_language(content),
        'color': color
    }


def formatter_inspection_result(data):
    """
    the type of data is as follows:
    {
        "class A": [
            {'type': 'title', 'level': 3, 'content': 'test_db'},
            {'type': 'str', 'content': 'xxx, error_count: 4'}
        ],
        "class B": []
    }
    """
    return {
        'type': 'inspection_result',
        'content': data
    }


def formatter_divider(divider_type: str, titles: list = None, content: str = None):
    """
    cutting line
    """
    if divider_type == 'vertical':
        return {
            'type': 'vertical_divider',
            'content': titles
        }
    return {
        'type': 'horizontal_divider',
        'content': content if content else ''
    }
