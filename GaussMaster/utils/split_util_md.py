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

import logging
import re
from typing import List

TITLE_PATTERN = r'^#{1,6}\s(.+)'  # 标题
LIST_PATTERN = r'^[-*+](\s+)'  # 列表
ORDER_LIST_PATTERN = r'^\d+\.(\s+)'  # 有序列表
QUOTE_PATTERN = r'^>{1,3}'  # 引用
CODE_PATTERN = r'```[\s\S]*?```'  # 代码块
TABLE_PATTERN = r'<table[^>]*>[\s\S]*?</table>'  # 表格
TABLE_ROW_PATTERN = r'<tr[^>]*>[\s\S]*?</tr>'  # 表行
TABLE_COL_HEADER_PATTERN = r'<th[^>]*>[\s\S]*?</th>'  # 表头
TABLE_COL_DATA_PATTERN = r'<td[^>]*>[\s\S]*?</td>'  # 表数据
VERTICAL_TABLE_PATTERN = r'(\|-{1,2})+\|'
CLEAN_PATTERN = r'<.*?>'  # 标签
LINK_PATTERN = r'!*\[([^\]]*)\]\([^\)]*\)'  # 链接
ITALIC_PATTERN = r'\*([\S]+.*?[\S]+|\S)\*'  # 斜体
BOLD_PATTERN = r'\*{2}([\S]+.*?)\*{2}'  # 粗体
BOLD_ITALIC_PATTERN = r'\*{3}([\S]+.*?)\*{3}'  # 粗斜体
STRIKEOVER_PATTERN = r'~{2}([\S]+.*?[\S]+|\S)~{2}'  # 删除线

TABLE_IDENTIFIER = "￥￥￥￥￥TABLE￥￥￥￥￥"
TITLE_IDENTIFIER = "￥￥￥￥￥TITLE￥￥￥￥￥"
LIST_IDENTIFIER = "￥￥￥￥￥LIST￥￥￥￥￥"
QUOTE_IDENTIFIER = "￥￥￥￥￥QUOTE￥￥￥￥￥"
CODE_IDENTIFIER = "￥￥￥￥￥CODE￥￥￥￥￥"
PARAM_IDENTIFIER = "￥￥￥￥￥PARAM￥￥￥￥￥"

MIN_BLOCK_LENGTH = 200
PROPER_BLOCK_LENGTH = 500
MAX_BLOCK_LENGTH = 1000


# 根据正则表达式，清除/获取匹配上的内容
def match_content(content, pattern, match_type='get'):
    res_content = ""
    lp_matches = re.finditer(pattern, content)
    l_index = 0
    for lp_match in lp_matches:
        res_content += content[l_index:lp_match.span()[0]]
        if match_type == 'get':
            res_content += lp_match.groups()[0]
        elif match_type == 'delete':
            pass
        l_index = lp_match.span()[1]
    res_content += content[l_index:]
    return res_content


# 清除链接
def clean_link(content):
    return match_content(content, LINK_PATTERN, match_type='get')


# 清除所有的html标签
def clean_html_tag(content):
    return re.sub(CLEAN_PATTERN, '', content)


# 清楚所有的转义字符，但不能除去代码中的
def clean_escape(content):
    return re.sub(r'\\', '', content)


# 清除字体格式：粗斜体、粗体、斜体、删除线，按顺序执行
def clean_text_font(content):
    bold_italic_content = match_content(content, BOLD_ITALIC_PATTERN, match_type='get')
    bold_content = match_content(bold_italic_content, BOLD_PATTERN, match_type='get')
    italic_content = match_content(bold_content, ITALIC_PATTERN, match_type='get')
    res_content = match_content(italic_content, STRIKEOVER_PATTERN, match_type='delete')
    return res_content


# 列表结束的标志：空，为列表标志，不为列表标志且缩进一致
def get_list_end_tag(line, list_ident):
    if not line:
        return False
    list_match = re.search(LIST_PATTERN, line)
    if list_match:
        return False
    ident_str = " " * list_ident
    if line.startswith(ident_str):
        return False
    return True


# 列表结束的标志：空，为列表标志且按照顺序，不为列表标志且缩进一致
def get_order_list_end_tag(line, order_list_ident, order_num):
    if not line:
        return False, order_num
    order_list_match = re.search(ORDER_LIST_PATTERN, line)
    if order_list_match:
        cur_order_num = int(order_list_match.group().split('.')[0])
        if cur_order_num != order_num + 1:
            return True, 0
        return False, order_num + 1
    ident_str = " " * order_list_ident
    if line.startswith(ident_str):
        return False, order_num
    return True, 0


# 标记列表和引用区域
def tag_list_quote(content):
    res_contents = []
    lines = content.splitlines()
    list_status = False
    order_list_status = False
    quote_status = False
    list_ident = 0
    order_list_ident = 0
    order_num = 0
    for line in lines:
        # not in list
        if not list_status:
            list_match = re.search(LIST_PATTERN, line)
            # list start
            if list_match:
                list_status = True
                list_ident = list_match.span()[1] - list_match.span()[0]
                res_contents.append(LIST_IDENTIFIER)
                res_contents.append(line)
                continue
        # in list
        else:
            # list end
            if get_list_end_tag(line, list_ident):
                list_status = False
                res_contents.append(LIST_IDENTIFIER)
            else:
                res_contents.append(line)
                continue
        # not in order list
        if not order_list_status:
            order_list_match = re.search(ORDER_LIST_PATTERN, line)
            # order list start
            if order_list_match:
                order_list_status = True
                order_list_ident = order_list_match.span()[1] - order_list_match.span()[0]
                res_contents.append(LIST_IDENTIFIER)
                res_contents.append(line)
                order_num = int(order_list_match.group().split('.')[0])
                continue
        # in order list
        else:
            # order list end
            order_status, order_num = get_order_list_end_tag(line, order_list_ident, order_num)
            if order_status:
                order_list_status = False
                res_contents.append(LIST_IDENTIFIER)
            else:
                res_contents.append(line)
                continue
        # not in quote
        if not quote_status:
            quote_match = re.search(QUOTE_PATTERN, line)
            # quote start
            if quote_match:
                quote_status = True
                res_contents.append(QUOTE_IDENTIFIER)
                res_contents.append(line)
                continue
        # in quote
        else:
            quote_match = re.search(QUOTE_PATTERN, line)
            # quote end
            if not quote_match:
                quote_status = False
                res_contents.append(QUOTE_IDENTIFIER)
        res_contents.append(line)
    if list_status:
        res_contents.append(LIST_IDENTIFIER + '\n')
    if quote_status:
        res_contents.append(QUOTE_IDENTIFIER + '\n')

    return '\n'.join(res_contents)


# 获取列表范围，空、为列表标志，不为列表标志时缩进一致
def get_list_range(lines, index, list_ident):
    end_index = index + 1
    while end_index < len(lines):
        line = lines[end_index]
        if not line:
            end_index += 1
            continue
        list_match = re.search(LIST_PATTERN, line)
        if list_match:
            end_index += 1
            continue
        ident_str = " " * list_ident
        if line.startswith(ident_str):
            ident_line = line[list_ident:]
            loop_list_match = re.search(LIST_PATTERN, ident_line)
            # 存在嵌套列表
            if loop_list_match:
                loop_list_ident = loop_list_match.span()[1] - loop_list_match.span()[0]
                end_index = get_list_range(lines, end_index, list_ident + loop_list_ident)
            else:
                end_index += 1
                continue
        else:
            return end_index
    return end_index


# 获取有序列表，空，空，为列表标志且按照顺序，不为列表标志且缩进一致
def get_order_list_range(lines, index, list_ident, order_num):
    end_index = index + 1
    while end_index < len(lines):
        line = lines[end_index]
        if not line:
            end_index += 1
            continue
        list_match = re.search(ORDER_LIST_PATTERN, line)
        if list_match:
            cur_order_num = int(list_match.group().split('.')[0])
            if cur_order_num != order_num + 1:
                return end_index
            end_index += 1
            order_num = cur_order_num
            continue
        ident_str = " " * list_ident
        if line.startswith(ident_str):
            ident_line = line[list_ident:]
            loop_list_match = re.search(ORDER_LIST_PATTERN, ident_line)
            # 存在嵌套列表
            if loop_list_match:
                loop_order_num = int(loop_list_match.group().split('.')[0])
                loop_list_ident = loop_list_match.span()[1] - loop_list_match.span()[0]
                end_index = get_order_list_range(lines, end_index, list_ident + loop_list_ident, loop_order_num)
            else:
                end_index += 1
                continue
        else:
            return end_index
    return end_index


# 标记列表区域
def tag_list_block(content):
    res_contents = []
    lines = content.splitlines()
    list_status = False
    order_list_status = False
    list_ident = 0
    order_list_ident = 0
    order_num = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        list_match = re.search(LIST_PATTERN, line)
        # list start
        if list_match:
            list_ident = list_match.span()[1] - list_match.span()[0]
            end_index = get_list_range(lines, index, list_ident)
            res_contents.append(LIST_IDENTIFIER)
            for i in range(index, end_index):
                res_contents.append(lines[i])
            res_contents.append(LIST_IDENTIFIER)
            index = end_index
            continue
        order_list_match = re.search(ORDER_LIST_PATTERN, line)
        # order list start
        if order_list_match:
            order_list_ident = order_list_match.span()[1] - order_list_match.span()[0]
            order_num = int(order_list_match.group().split('.')[0])
            end_index = get_order_list_range(lines, index, order_list_ident, order_num)
            res_contents.append(LIST_IDENTIFIER)
            for i in range(index, end_index):
                res_contents.append(lines[i])
            res_contents.append(LIST_IDENTIFIER)
            index = end_index
            continue
        res_contents.append(line)
        index += 1
    return '\n'.join(res_contents)


# 标记引用区域
def tag_quote_block(content):
    res_contents = []
    lines = content.splitlines()
    quote_status = False
    for line in lines:
        # not in quote
        if not quote_status:
            quote_match = re.search(QUOTE_PATTERN, line)
            # quote start
            if quote_match:
                quote_status = True
                res_contents.append(QUOTE_IDENTIFIER)
                res_contents.append(line)
                continue
        # in quote
        else:
            quote_match = re.search(QUOTE_PATTERN, line)
            # quote end
            if not quote_match:
                quote_status = False
                res_contents.append(QUOTE_IDENTIFIER)
        res_contents.append(line)
    if quote_status:
        res_contents.append(QUOTE_IDENTIFIER + '\n')
    return '\n'.join(res_contents)


# 匹配出所有的代码块，记录代码块位置
def find_code_partion(content):
    code_partion = []
    code_matches = re.finditer(CODE_PATTERN, content)
    for code_match in code_matches:
        code_partion.append((code_match.span()[0], code_match.span()[1]))
    return code_partion


# 处理表格中单行信息，获取各列内容
def deal_table_row(row_content):
    row_eles = []
    tc_matches = list(re.finditer(TABLE_COL_HEADER_PATTERN, row_content))
    if len(tc_matches) == 0:
        tc_matches = list(re.finditer(TABLE_COL_DATA_PATTERN, row_content))
    for tc_match in tc_matches:
        tc_content = row_content[tc_match.span()[0]:tc_match.span()[1]]
        tc_content = clean_html_tag(tc_content)
        row_eles.append(tc_content.replace('\n', ''))
    return '\t'.join(row_eles)


# 处理表格中信息，获取所有表格内容
def deal_table(table_content):
    table_eles = []
    tr_matches = re.finditer(TABLE_ROW_PATTERN, table_content)
    for tr_match in tr_matches:
        row_content = deal_table_row(table_content[tr_match.span()[0]:tr_match.span()[1]])
        table_eles.append(row_content)
    # 表格前后添加标识符，后续处理可以识别为表格
    if table_eles:
        table_eles.insert(0, TABLE_IDENTIFIER)
        table_eles.append(TABLE_IDENTIFIER)
    return '\n'.join(table_eles)


# 匹配所有的标签表格，获取表格中的内容，仅保留文本信息
def extract_table_tag(content):
    res_content = ""
    table_matches = re.finditer(TABLE_PATTERN, content)
    l_index = 0
    for table_match in table_matches:
        res_content += content[l_index:table_match.span()[0]]
        res_content += deal_table(content[table_match.span()[0]:table_match.span()[1]])
        l_index = table_match.span()[1]
    res_content += content[l_index:]
    return res_content


# 匹配竖线表格，同样保留文本信息，格式一致，后续同意修改
def extract_table_vertical(content):
    res_contents = []
    lines = content.split('\n')
    insert_list = []
    table_status = False
    vertical_count = 0
    for index, line in enumerate(lines):
        cur_vertical_count = line.count('|')
        # in table
        if table_status:
            # table end
            if cur_vertical_count <= 0:
                table_status = False
                insert_list.append(index)
            res_contents.append(line)
            continue
        # not in table
        else:
            matches = re.search(VERTICAL_TABLE_PATTERN, line)
            if not matches:
                res_contents.append(line)
                continue
            # table start
            insert_list.append(index - 1)
            table_status = True
            vertical_count = cur_vertical_count
            res_contents.append(line)
    for index in insert_list[::-1]:
        res_contents.insert(index, TABLE_IDENTIFIER)
    return '\n'.join(res_contents)


def extract_table(content):
    content = extract_table_tag(content)
    content = extract_table_vertical(content)
    return content


# 标记标题，必须要先分割开代码，避免代码中出现# 字样的内容和标题类型重复
def tag_title(content):
    res_contents = []
    lines = content.split('\n')
    for line in lines:
        matches = re.findall(TITLE_PATTERN, line)
        if not matches:
            res_contents.append(line)
            continue
        res_contents.append(TITLE_IDENTIFIER)
        res_contents.append(line)  # 不删掉#标签
    return '\n'.join(res_contents)


def tag_param_config(content):
    """Function tag param config"""
    res_contents = []
    lines = content.split('\n')
    index = len(lines)
    first_tag = True
    last_index = -1
    while index > 0:
        index -= 1
        res_contents.insert(0, lines[index])
        if lines[index].startswith('**参数说明'):
            while index > 0:
                if not lines[index - 1]:
                    index -= 1
                    res_contents.insert(0, lines[index])
                    continue
                if lines[index - 1].endswith('**'):
                    index -= 1
                    res_contents.insert(0, lines[index])
                    res_contents.insert(0, PARAM_IDENTIFIER)
                    if not first_tag:
                        res_contents.insert(0, PARAM_IDENTIFIER)
                        last_index = index
                    first_tag = False
                break
    if last_index != -1:
        res_contents.pop(last_index)
    return '\n'.join(res_contents)


def text_split_without_code(content):
    res_content = ""
    table_content = extract_table(content)
    link_content = clean_link(table_content)
    flag_content = clean_html_tag(link_content)
    flag_content = clean_escape(flag_content)
    title_content = tag_title(flag_content)
    return title_content


# 预处理
def preprocess_md_content(md_content):
    '''
    首先，获取不可分块的区域，并做上标记，list、quote
    其次，把代码块分割出来，仅对其余内容处理文本信息，代码块内内容不变
    之后，对表格进行标记
    随后，提取链接信息中的内容
    然后，处理字体格式
    再次，去掉所有标签信息
    最后，标记标题信息
    '''
    res_content = ""
    md_content = tag_list_block(md_content)
    md_content = tag_quote_block(md_content)
    code_partion = find_code_partion(md_content)
    c_index = 0
    for l, r in code_partion:
        if c_index < l:
            link_content = text_split_without_code(md_content[c_index:l])

            res_content += link_content
            c_index = l
        res_content += CODE_IDENTIFIER + '\n'
        res_content += md_content[l:r]
        res_content += '\n' + CODE_IDENTIFIER
        c_index = r
    link_content = text_split_without_code(md_content[c_index:])
    res_content += link_content
    return res_content


def clean_tag_info(content):
    content = content.replace(LIST_IDENTIFIER + '\n', '')
    content = content.replace(QUOTE_IDENTIFIER + '\n', '')
    content = content.replace(TABLE_IDENTIFIER + '\n', '')
    content = content.replace(CODE_IDENTIFIER + '\n', '')
    content = content.replace(PARAM_IDENTIFIER + '\n', '')
    content = content.replace(LIST_IDENTIFIER, '')
    content = content.replace(QUOTE_IDENTIFIER, '')
    content = content.replace(TABLE_IDENTIFIER, '')
    content = content.replace(CODE_IDENTIFIER, '')
    content = content.replace(PARAM_IDENTIFIER, '')

    return content


# 处理标题文本，独立
def split_title_text(prefix, title_content):
    """Function split title text"""
    content_list = []
    block_list = []
    block_length = 0
    lines = title_content.splitlines()
    lines = [i for i in lines if i]
    table_status = False
    list_status = False
    code_status = False
    quote_status = False
    param_status = False
    for line in lines:
        # 判断现在是否可以结束
        if not (code_status or table_status or list_status or quote_status or param_status) \
                and block_length > PROPER_BLOCK_LENGTH:
            if content_list and prefix:
                content_list.append(prefix + '\n' + clean_tag_info('\n'.join(block_list)))
            else:
                content_list.append(clean_tag_info('\n'.join(block_list)))
            block_list = [line]
            block_length = 0
        else:
            block_list.append(line)
            block_length += len(line)
        if line == LIST_IDENTIFIER:
            list_status = not list_status
        elif line == QUOTE_IDENTIFIER:
            quote_status = not quote_status
        elif TABLE_IDENTIFIER in line:
            table_status = not table_status
        elif CODE_IDENTIFIER in line:
            code_status = not code_status
        elif line == PARAM_IDENTIFIER:
            param_status = not param_status
    if block_list:
        last_block_content = clean_tag_info('\n'.join(block_list))
        if block_length < MIN_BLOCK_LENGTH and content_list:
            content_list[-1] += '\n' + last_block_content
        else:
            if prefix and content_list:
                last_block_content = prefix + '\n' + last_block_content
            content_list.append(last_block_content)
    return content_list


def get_title_info(content):
    """Function get title info"""
    lines = content.splitlines()
    lines = [i for i in lines if i]
    if not lines:
        return 0, ''
    first_row = lines[0]
    stripped_content = first_row.lstrip('#')
    strip_num = len(first_row) - len(stripped_content)
    if strip_num == 0:
        return strip_num, first_row
    if stripped_content.startswith(' '):
        return strip_num, first_row
    return 0, first_row


def get_title_contents(title_contents, title_content, content_titles):
    """Function get title contents"""
    lines = title_content.splitlines()
    lines = [i for i in lines if i]
    title_content = '\n'.join(lines)
    strip_num, title_info = get_title_info(title_content)
    if strip_num == 0:
        prefix_title = '\n'.join(content_titles)
        title_content = prefix_title + title_content
        title_contents += title_content
        return title_contents, content_titles, prefix_title
    if len(content_titles) >= strip_num:
        content_titles = content_titles[:strip_num]
        content_titles[strip_num - 1] = title_info
    elif len(content_titles) < strip_num - 1:
        len_gap = strip_num - 1 - len(content_titles)
        for _ in range(len_gap):
            content_titles.append('')
        content_titles.append(title_info)
    else:
        content_titles.append(title_info)
    prefix_title = ''
    for i in range(strip_num - 1):
        if content_titles[i]:
            prefix_title += content_titles[i] + '\n'
    title_content = prefix_title + title_content
    title_contents += '\n' + title_content
    return title_contents, content_titles, prefix_title + title_info


def get_heading_level(text):
    """Function get heading level"""
    heading_pattern = r'^(#+)\s'
    match = re.match(heading_pattern, text)
    if match:
        heading_level = len(match.group(1))
        return heading_level
    return 0


def delete_duplication_prefix(content_list):
    """Function delete duplication prefix"""
    res_list = []
    for content in content_list:
        lines = content.splitlines()
        dup_index = 0
        title_level = 0
        for index, line in enumerate(lines):
            heading_level = get_heading_level(line)
            if heading_level == 0:
                break
            if heading_level >= title_level + 1:
                title_level = heading_level
            else:
                dup_index = index
                title_level = 0
        cur_content = '\n'.join(lines[dup_index:])
        res_list.append(cur_content)
    return res_list


# 分割文本，标题间分隔
def split_text_md(content):
    """Function split text md"""
    content_list = []
    p_content = preprocess_md_content(content)
    title_list = p_content.split(TITLE_IDENTIFIER)
    title_list = [i for i in title_list if i]
    title_contents = ""
    content_titles = []
    prefix_title = ''
    for title_content in title_list:
        title_content = tag_param_config(title_content)
        title_content = clean_text_font(title_content)
        title_contents, content_titles, prefix_title = get_title_contents(title_contents, title_content, content_titles)
        if len(title_contents) < MIN_BLOCK_LENGTH:
            continue
        cur_content_list = split_title_text(prefix_title, title_contents)
        content_list.extend(cur_content_list)
        title_contents = ""
    cur_content_list = split_title_text(prefix_title, title_contents)
    content_list.extend(cur_content_list)
    # delete duplication prefix
    dedup_content_list = delete_duplication_prefix(content_list)
    return dedup_content_list


def split_text_with_regex(text, separator, keep_separator):
    """Function split text with regex"""
    if separator:
        if keep_separator:
            # The parentheses in the pattern keep the delimiters in the result.
            _splits = re.split(f"({separator})", text)
            splits = [_splits[i] + _splits[i + 1] for i in range(1, len(_splits), 2)]
            if len(_splits) % 2 == 0:
                splits += _splits[-1:]
            splits = [_splits[0]] + splits
        else:
            splits = re.split(separator, text)
    else:
        splits = list(text)
    return [s for s in splits if s != ""]


def join_docs(docs, separator):
    """Function join docs with separator"""
    text = separator.join(docs)
    text = text.strip()
    if text == "":
        return ""
    return text


def merge_splits(splits, separator, chunk_size, chunk_overlap):
    """Function merge splits with chunk_size and chunk_overlap"""
    separator_len = len(separator)

    docs = []
    current_doc: List[str] = []
    total = 0
    for d in splits:
        _len = len(d)
        if (
                total + _len + (separator_len if len(current_doc) > 0 else 0)
                > chunk_size
        ):
            if total > chunk_size:
                logging.info(
                    "Created a chunk of size %s, which is longer than the specified %s", total, chunk_size
                )
            if len(current_doc) > 0:
                doc = join_docs(current_doc, separator)
                if doc is not None:
                    docs.append(doc)
                # Keep on popping if:
                # - we have a larger chunk than in the chunk overlap
                # - or if we still have any chunks and the length is long
                while total > chunk_overlap or (
                        total + _len + (separator_len if len(current_doc) > 0 else 0)
                        > chunk_size
                        and total > 0
                ):
                    total -= len(current_doc[0]) + (
                        separator_len if len(current_doc) > 1 else 0
                    )
                    current_doc = current_doc[1:]
        current_doc.append(d)
        total += _len + (separator_len if len(current_doc) > 1 else 0)
    doc = join_docs(current_doc, separator)
    if doc is not None:
        docs.append(doc)
    return docs


def recursive_split_text(text, separators, chunk_size, chunk_overlap):
    """Function recursive split text"""
    final_chunks = []
    separator = separators[-1]
    new_separators = []
    for i, _s in enumerate(separators):
        _separator = re.escape(_s)
        if _s == "":
            separator = _s
            break
        if re.search(_separator, text):
            separator = _s
            new_separators = separators[i + 1:]
            break
    _separator = re.escape(separator)
    _keep_separator = True
    splits = split_text_with_regex(text, _separator, _keep_separator)

    _good_splits = []
    _separator = ""
    for s in splits:
        if len(s) < chunk_size:
            _good_splits.append(s)
        else:
            if _good_splits:
                merged_text = merge_splits(_good_splits, _separator, chunk_size, chunk_overlap)
                final_chunks.extend(merged_text)
                _good_splits = []
            if not new_separators:
                final_chunks.append(s)
            else:
                other_info = recursive_split_text(s, new_separators, chunk_size, chunk_overlap)
                final_chunks.extend(other_info)
    if _good_splits:
        merged_text = merge_splits(_good_splits, _separator, chunk_size, chunk_overlap)
        final_chunks.extend(merged_text)
    return final_chunks


# split
def split_text_md_adjacent(content):
    """Function split md text adjacent"""
    content_list = []
    p_content = preprocess_md_content(content)
    p_content = clean_tag_info(p_content)
    p_content = p_content.replace(TITLE_IDENTIFIER, '')

    # split 384
    separators = ["\n\n", "\n", " ", ""]
    content_list = recursive_split_text(p_content, separators, 384, 75)
    return content_list
