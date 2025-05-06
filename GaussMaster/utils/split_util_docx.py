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

import re
from typing import List

from docx import Document
from docx.table import Table


class MyContent:
    def __init__(self, text: str, level: int):
        self.text = text
        self.level = level


class MyElement:
    def __init__(self, text: str, content: str):
        self.text = text
        self.content = content


class MyParagraph(MyElement):
    def __init__(self, text: str, style: str, content: str = None):
        super().__init__(text, content)
        self.style = style


class MyTable(MyElement):
    def __init__(self, table: Table, content: str = None):
        if len(table.rows) == 0:
            super().__init__('', content)
            return
        headers = [cell.text.strip() for cell in table.rows[0].cells]
        if len(table.rows) == 1:
            super().__init__(",".join(headers), content)
            return
        all_rows_output = ''
        for row in table.rows[1:]:
            row_data = ', '.join(f"{header}: {cell.text.strip()}" for header, cell in zip(headers, row.cells))
            all_rows_output += f"{row_data};\n"
        super().__init__(all_rows_output.strip(), content)


CONTENTS_STYLE = 'Contents'  # docx文档的目录，如toc 1、toc 2
TABLE_OF_CONTENTS_STYLE = r'^toc\s[1-9]$'  # docx文档的目录，如toc 1、toc 2
HEADING_STYLE = r'^Heading\s[1-9]$'  # docx文档的标题，如Heading 1、Heading 2
BLOCK_LABEL_STYLE = 'Block Label'

PROPER_BLOCK_LENGTH = 500

TABLE_OF_CONTENTS_STYLE_COMPILED = re.compile(TABLE_OF_CONTENTS_STYLE, re.IGNORECASE)
HEADING_STYLE_COMPILED = re.compile(HEADING_STYLE, re.IGNORECASE)


def group_elements_by_length(group_list: List[List[MyElement]]):
    """对所有的段落和表格按照Block Label二次分组后,再按照长度三次分组"""
    new_group_list = []
    for old_single_group in group_list:
        new_single_group = []
        new_single_group_length = 0
        for element in old_single_group:
            if new_single_group_length > PROPER_BLOCK_LENGTH:
                if len(new_single_group) > 0:
                    new_group_list.append(new_single_group)
                new_single_group = [element]
                new_single_group_length = 0
            else:
                new_single_group.append(element)
                new_single_group_length += len(element.text)
        if len(new_single_group) > 0:
            new_group_list.append(new_single_group)
    return new_group_list


def group_elements_by_block_label(group_list: List[List[MyElement]]):
    """对所有的段落和表格按照标题一次分组后，再按照Block Label二次分组，此二次分组适用于idp文档"""
    new_group_list = []
    for old_single_group in group_list:
        new_single_group = []
        for element in old_single_group:
            if isinstance(element, MyParagraph):
                if element.style == BLOCK_LABEL_STYLE:
                    if len(new_single_group) > 0:
                        new_group_list.append(new_single_group)
                    new_single_group = [element]
                else:
                    new_single_group.append(element)
            else:
                new_single_group.append(element)
        if len(new_single_group) > 0:
            new_group_list.append(new_single_group)
    return new_group_list


def group_elements_by_heading(element_list: List[MyElement]):
    """对所有的段落和表格按照标题一次分组"""
    group_list = []
    single_group = []
    for element in element_list:
        if isinstance(element, MyParagraph):
            # 不考虑空内容
            if element.text == '':
                continue
            # 不考虑docx的目录
            if TABLE_OF_CONTENTS_STYLE_COMPILED.match(element.style) or element.style == CONTENTS_STYLE:
                continue
            # 使用标题分割
            if HEADING_STYLE_COMPILED.match(element.style):
                if len(single_group) > 0:
                    group_list.append(single_group)
                single_group = []
            else:
                single_group.append(element)
        else:
            single_group.append(element)
    if len(single_group) > 0:
        group_list.append(single_group)
    return group_list


def add_content_to_paragraph(element_list: List[MyElement]):
    """将目录的文字添加到段落中"""
    content_list = []
    for element in element_list:
        if isinstance(element, MyParagraph) and HEADING_STYLE_COMPILED.match(element.style):
            cur_content = MyContent(element.text, int(element.style[-1]))
            if len(content_list) == 0:
                content_list.append(cur_content)
                continue
            while True:
                if len(content_list) == 0 or cur_content.level > content_list[-1].level:
                    content_list.append(cur_content)
                    break
                if cur_content.level <= content_list[-1].level:
                    content_list.pop()
        else:
            element.content = '-'.join(content.text for content in content_list) + '\n' if content_list else ''
    return element_list


def sort_element_list(docx_document: Document):
    """获取段落和表格的顺序，将段落和表格放到一个列表里"""
    paragraph_list = [MyParagraph(para.text, para.style.name) for para in docx_document.paragraphs]
    table_list = [MyTable(table) for table in docx_document.tables]
    element_list = []
    for child in docx_document.element.body.iterchildren():
        if child.tag.endswith('p'):
            element_list.append(paragraph_list.pop(0))
        if child.tag.endswith('tbl'):
            element_list.append(table_list.pop(0))
    return element_list


def split_text_docx(docx_document: Document):
    """分割docx，按段落隔离"""
    content_list = []
    element_list = sort_element_list(docx_document)
    element_list = add_content_to_paragraph(element_list)
    group_list = group_elements_by_heading(element_list)
    group_list = group_elements_by_block_label(group_list)
    group_list = group_elements_by_length(group_list)
    content = ""
    for single_group in group_list:
        cur_content = single_group[0].content + '\n'.join(element.text for element in single_group)
        content += cur_content
        if len(content) < PROPER_BLOCK_LENGTH:
            continue
        content_list.append(content)
        content = ""
    if content:
        content_list.append(content)
    return content_list
