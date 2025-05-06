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

"""knowledge base config"""

KT_TABLE_NAME = "gauss_kb"  # base + ft
KB_TABLE_NAME = "knowledge_base"
DS_TABLE_NAME = "data_source"
QA_TABLE_NAME = "qa_record"

KT_TABLE_CONFIG = {
    "vector_field": ["text"],
    "bm25_field": ["text"],
    "text_field": ['uuid', 'field', 'source', 'product_format', 'sub_field', 'doc_location', 'title', 'text',
                   'visualize', 'link', 'version', 'context', 'keyword', 'confidence', 'ds_id', 'prev_uuid',
                   'next_uuid']
}
KB_TABLE_CONFIG = {
    "vector_field": [],
    "bm25_field": [],
    "text_field": ['kb_id', 'name', 'user_id', 'kb_type', 'description', 'context', 'create_time', 'update_time'],
    "serial_field": ['kb_id']
}
DS_TABLE_CONFIG = {
    "vector_field": [],
    "bm25_field": [],
    "text_field": ['ds_id', 'name', 'related_kb_id', 'description', 'file_name', 'create_time', 'update_time'],
    "serial_field": ['ds_id'],
    "int_field": ['related_kb_id']
}
QA_TABLE_CONFIG = {
    "vector_field": [],
    "bm25_field": [],
    "text_field": ['question', 'question_id', 'answer', 'answer_id', 'user_id', 'session_id', 'switch', 'vector_topk',
                   'text_topk', 'rerank_topk', 'kb_id', 'version', 'model_name', 'model_config', 'lang', 'task_type',
                   'like', 'hate', 'feedback_info', 'report_type', 'report_info', 'create_time', 'update_time'],
    "serial_field": []
}

OPS_KB_TABLE_CONFIG = {
    "CASE_OP": {
        "table_name": "case_op_kb",
        "vector_field": ['inspection'],
        "bm25_field": [],
        "text_field": ['inspection', 'procedure_name', 'steps']
    }
}

OPS_MEMORY_TABLE_CONFIG = {
    "GM_HISTORY_MEMORY": {
        "table_name": "gm_tool_history_memory",
        "vector_field": ['question'],
        "bm25_field": [],
        "text_field": ['question', 'tool_name', 'user_id', 'user_name', 'created_at']
    }
}
