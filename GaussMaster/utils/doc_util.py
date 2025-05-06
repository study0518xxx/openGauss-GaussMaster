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

import hashlib
import logging
import os
import uuid

import docx

from GaussMaster.utils.split_util_docx import split_text_docx
from GaussMaster.utils.split_util_md import split_text_md, split_text_md_adjacent

SOURCE_LIST = ['idp', 'community', 'huawei_cloud']
VERSION_LIST = ['24.7.30.10']
CLUSTER_LIST = ['centralized', 'distributed', 'miniaturize']


def text_split_pdf(file):
    """Function split pdf file."""
    return []


def text_split_html(file):
    """Function split html file."""
    return []


def text_split_doc(file):
    """Function split doc file."""
    doc = docx.Document(file)
    content_list = split_text_docx(doc)
    return content_list


def text_split_md(file):
    """Function split markdown file."""
    with open(file, 'r', encoding='utf-8') as md_file:
        md_content = md_file.read()
    content_list = split_text_md(md_content)
    return content_list


def text_split_md_adjacent(file):
    """Function split markdown file adjacent."""
    with open(file, 'r', encoding='utf-8') as md_file:
        md_content = md_file.read()
    content_list = split_text_md_adjacent(md_content)
    return content_list


def get_extra_info(root, srcfile):
    """Function set field for knowledge."""
    info_dict = {}

    info_dict['field'] = 'GaussDB'
    info_dict['sub_field'] = 'kernel'
    info_dict['doc_location'] = srcfile
    # need change to pargraph title
    info_dict['title'] = srcfile
    info_dict['visualize'] = ""
    info_dict['link'] = ""
    info_dict['keyword'] = []
    info_dict['ds_id'] = 0
    dir_info = root.split(os.sep)[-3:]
    if len(dir_info) != 3:
        info_dict['source'] = 'unknown'
        info_dict['version'] = 'unknown'
        info_dict['product_format'] = 'unknown'
        info_dict['confidence'] = 'unknown'
        return info_dict
    if dir_info[0] not in SOURCE_LIST:
        info_dict['source'] = 'unknown'
        info_dict['confidence'] = 'unknown'
    else:
        info_dict['source'] = dir_info[0]
        if dir_info[0] == 'idp':
            info_dict['confidence'] = '1'
        elif dir_info[0] == 'community':
            info_dict['confidence'] = '2'
        else:
            info_dict['confidence'] = 'unknown'
    if dir_info[1] not in VERSION_LIST:
        info_dict['version'] = 'unknown'
    else:
        info_dict['version'] = dir_info[1]
    if dir_info[2] not in CLUSTER_LIST:
        info_dict['product_format'] = 'unknown'
    else:
        info_dict['product_format'] = dir_info[2]
    return info_dict


def generate_chunks(root, srcfile, contents):
    """Function generate chunk fields."""
    data_list = []
    info_dict = get_extra_info(root, srcfile)
    prev_uuid = ""
    prev_dup_uuid = ""
    for content in contents:
        dup_uuid = hashlib.md5(content.encode("utf-8")).hexdigest()
        cur_uuid = str(uuid.uuid4())
        data_dict = {}
        data_dict.update(info_dict)
        data_dict['text'] = content
        data_dict['uuid'] = cur_uuid
        data_dict['dup_uuid'] = dup_uuid
        data_dict['prev_uuid'] = prev_uuid
        data_dict['prev_dup_uuid'] = prev_dup_uuid
        data_dict['next_uuid'] = ""
        data_dict['next_dup_uuid'] = ""
        data_dict['context'] = [prev_uuid, cur_uuid, ""]
        if data_list:
            data_list[-1]['next_uuid'] = cur_uuid
            data_list[-1]['next_dup_uuid'] = dup_uuid
            data_list[-1]['context'][-1] = cur_uuid
        data_list.append(data_dict)
        prev_uuid = cur_uuid
        prev_dup_uuid = dup_uuid
    return data_list


def generate_chunks_custom(filename, contents, ds_id):
    """Function generate custom chunk fields."""
    data_list = []
    prev_uuid = ""
    prev_dup_uuid = ""
    for content in contents:
        dup_uuid = hashlib.md5(content.encode("utf-8")).hexdigest()
        cur_uuid = str(uuid.uuid4())
        data_dict = {}
        data_dict['text'] = content
        data_dict['uuid'] = cur_uuid
        data_dict['dup_uuid'] = dup_uuid
        data_dict['prev_uuid'] = prev_uuid
        data_dict['prev_dup_uuid'] = prev_dup_uuid
        data_dict['next_uuid'] = ""
        data_dict['next_dup_uuid'] = ""
        data_dict['context'] = [prev_uuid, cur_uuid, ""]
        data_dict['field'] = 'custom'
        data_dict['sub_field'] = 'custom'
        data_dict['doc_location'] = filename
        # need change to pargraph title
        data_dict['title'] = filename
        data_dict['visualize'] = ""
        data_dict['link'] = ""
        data_dict['keyword'] = []
        data_dict['source'] = 'unknown'
        data_dict['version'] = 'unknown'
        data_dict['product_format'] = 'unknown'
        data_dict['confidence'] = 'unknown'
        data_dict['ds_id'] = ds_id
        if data_list:
            data_list[-1]['next_uuid'] = cur_uuid
            data_list[-1]['next_dup_uuid'] = dup_uuid
            data_list[-1]['context'][-1] = cur_uuid
        data_list.append(data_dict)
        prev_uuid = cur_uuid
        prev_dup_uuid = dup_uuid
    return data_list


def get_split_content(root, srcfile, split_type='base'):
    """Function split content from file."""
    contents = []
    if srcfile.endswith('pdf'):
        contents = text_split_pdf(os.path.join(root, srcfile))
    elif srcfile.endswith('html'):
        contents = text_split_html(os.path.join(root, srcfile))
    elif srcfile.endswith('md') or srcfile.endswith('markdown'):
        if split_type == 'base':
            contents = text_split_md(os.path.join(root, srcfile))
        elif split_type == 'split':
            contents = text_split_md_adjacent(os.path.join(root, srcfile))
        else:
            contents = []
    elif srcfile.endswith('docx'):
        contents = text_split_doc(os.path.join(root, srcfile))
    return contents


def load_knowledge(source, split_type='base', save_local=False):
    """Function get knowledge fragment from local dir."""
    data_list = []
    count = 0
    for root, dirs, files in os.walk(source):
        for srcfile in files:
            contents = get_split_content(root, srcfile, split_type)
            if not contents:
                continue
            count += 1
            file_data_list = generate_chunks(root, srcfile, contents)
            data_list.extend(file_data_list)
    logging.info('file count: {}, self total content len: {}'.format(count, len(data_list)))
    return data_list


def load_knowledge_from_file(file_path, ds_id):
    """Function get knowledge fragment from file."""
    contents = get_split_content(os.path.dirname(file_path), os.path.basename(file_path))
    file_data_list = generate_chunks_custom(os.path.basename(file_path), contents, ds_id)
    return file_data_list


# 去重
def deduplication(content_list, split_type='base'):
    """Function deduplicate knowledge fragments."""
    unique_content_list = []
    uuid_list = []
    count = 0
    for content in content_list:
        if split_type == 'base':
            if content['dup_uuid'] in uuid_list:
                continue
            uuid_list.append(content['dup_uuid'])
        elif split_type == 'split':
            adjacent_uuids = content['prev_dup_uuid'] + content['dup_uuid'] + content['next_dup_uuid']
            if adjacent_uuids in uuid_list:
                continue
            uuid_list.append(adjacent_uuids)
        unique_content_list.append(content)
        count += 1
    logging.info('content len: {}, unique len: {}.'.format(len(content_list), len(unique_content_list)))
    return unique_content_list


def load_knowledge_base_local(db_file, gaussdb):
    """Function load db file to create basic knowledge table."""
    if not os.path.exists(db_file):
        raise Exception(f"db_file is not found, please check.")
    gaussdb.load_local(db_file, True, True)
