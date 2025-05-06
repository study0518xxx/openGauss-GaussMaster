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

"""to manipulate the interaction_memory table"""

from sqlalchemy import desc

from GaussMaster.common.metadatabase.result_db_session import get_session
from GaussMaster.common.metadatabase.schema import InteractionMemory


class InteractionMemoryParameter:
    def __init__(self, qa_record_id, user_id, session_id, question, created_at, llm_name=None, answer=None,
                 function_call=None):
        self.qa_record_id = qa_record_id
        self.user_id = user_id
        self.session_id = session_id
        self.question = question
        self.created_at = created_at
        self.llm_name = llm_name
        self.answer = answer
        self.function_call = function_call


async def insert_interaction_memory(
        qa_record_id,
        user_id,
        session_id,
        question,
        created_at,
        llm_name=None,
        answer=None,
        function_call=None
):
    """to insert new memory into interaction_memory table"""
    with get_session() as session:
        session.add(InteractionMemory(
            qa_record_id=qa_record_id,
            user_id=user_id,
            session_id=session_id,
            question=question,
            created_at=created_at,
            llm_name=llm_name,
            answer=answer,
            function_call=function_call
        ))


async def select_interaction_memory(user_id: str, session_id: str, limit: int):
    """to select memory record the meet given filter condition"""
    with get_session() as session:
        result = session.query(InteractionMemory).filter(InteractionMemory.user_id == user_id).filter(
            InteractionMemory.session_id == session_id).order_by(desc(InteractionMemory.created_at)).limit(limit)
        return result


def add_to_local_memory(local_qa: dict, length: int, qa: InteractionMemory):
    """add qa record to local memory"""
    qa_list = local_qa.get(qa.user_id, {}).get(qa.session_id, [])
    qa_list.append(qa)
    while len(qa_list) > length:
        qa_list.pop(0)
