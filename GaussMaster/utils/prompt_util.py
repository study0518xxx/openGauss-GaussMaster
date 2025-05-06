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

import ast

from GaussMaster.constants import MAX_PROMPT_LENGTH

QUESTION = 'question'
ANSWER = 'answer'
ROLE = 'role'
CONTENT = 'content'

QUERY_ROUTER_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是对【问题】进行分类，让我们一步一步的思考，按照下面的步骤来判断问题的【类别】：
##步骤1## 请从【问题】中提取出【线索】，【线索】可以是关键词、短语、上下文信息、语义含义，执行步骤2。
##步骤2## 请根据【问题】和【线索】判断是否包含涉及政治、恐怖事件等敏感信息，如果包含，直接返回【类别0】；反之执行步骤3。
##步骤3## 请根据【问题】和【线索】判断是否与数据库相关，如果不相关，直接返回【类别1】；反之执行步骤4。
##步骤4## 返回【类别2】。返回数据格式如下：
```
{{class：类别}}
```

在```中的内容必须是有效的JSON格式。

----------------------
示例1：
【问题】：特朗普是谁？
##步骤1## 从问题中提取出【线索】：特朗普。
##步骤2## 特朗普是美国总统，与政治相关，返回【类别0】。

----------------------
示例2：
【问题】：第一届奥林匹克运动会在哪里举行？
##步骤1## 从问题中提取出【线索】：第一届、奥林匹克运动会、举行地点。
##步骤2## 【问题】与【线索】不涉及敏感信息；执行步骤3。
##步骤3## 【问题】与【线索】中的信息与数据库无关，返回【类别1】。

----------------------
【问题】：GaussDB是否支持分布式集群？
##步骤1## 从问题中提取出【线索】：GaussDB、分布式、集群。
##步骤2## 【问题】与【线索】不涉及敏感信息；执行步骤3。
##步骤3## 【问题】与【线索】中的信息与数据库有关，执行步骤4。
##步骤4## 返回【类别2】。
"""

QUERY_ROUTER_SYSTEM_TMPL_EN = """You are an expert in Chinese GaussDB database, your task is to classify the [problem], let's think step by step, according to the following steps to judge the [category] of the problem:
## Step 1## Please extract [clue] from [question], [clue] can be keywords, phrases, contextual information, semantic meaning, go to Step 2.
## Step 2## Please judge according to [Question] and [clue] whether it contains sensitive information involving political or terrorist events. If yes, return to [Category 0] directly; Otherwise, go to Step 3.
## Step 3## Please judge whether it is relevant to the database according to [Question] and [clue]. If it is not relevant, directly return to [Category 1]; Otherwise, go to Step 4.
## Step 4## Return to Category 2. The returned data format is as follows:
` ` `
{{class: class}}
` ` `

The content in ' 'must be in valid JSON format.

----------------------
Example 1:
[Question]: Who is Trump?
Step 1## Extract [clue] from the question: Trump.
## Step 2## Trump is the President of the United States, related to politics, return to [category 0].

----------------------
Example 2:
[Question]: Where were the first Olympic Games held?
## Step 1## Extract [clues] from the question: the first Olympic Games, the venue.
## Step 2## [Questions] and [Clues] do not involve sensitive information; Go to Step 3.
## Step 3## # The information in [Question] and [Clue] is not relevant to the database, return to [Category 1].

----------------------
[Question] : Does GaussDB support distributed clusters?
## Step 1## Extract the clue from the question: GaussDB, distributed, cluster.
## Step 2## [Questions] and [Clues] do not involve sensitive information; Go to Step 3.
## Step 3## [Question] is related to the information in [Clue] and the database, go to Step 4.
## Step 4## Return to Category 2.
"""

QUERY_ROUTER_USER_TMPL_ZH = """请判断以下【问题】的【类别】，注意【类别】需要满足指定的JSON格式。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。

----------------------
【问题】：{question}
【类别】：
"""

QUERY_ROUTER_USER_TMPL_EN = """Please determine the [Category] of the following [Question], noting that the [Category] must meet the specified JSON format. This task is very important to me, please finish it carefully, and you can get rewards if you finish it well.

----------------------
[Question] : {question}
[Category] :
"""

QUERY_REWRITE_SYSTEM_TMPL_ZH = """"""

QUERY_REWRITE_SYSTEM_TMPL_EN = """"""

QUERY_REWRITE_USER_TMPL_ZH = """"""

QUERY_REWRITE_USER_TMPL_EN = """"""

QUERY_EXPANSION_SYSTEM_TMPL_ZH = """"""

QUERY_EXPANSION_SYSTEM_TMPL_EN = """"""

QUERY_EXPANSION_USER_TMPL_ZH = """"""

QUERY_EXPANSION_USER_TMPL_EN = """"""

MULTI_QUERY_SYSTEM_TMPL_ZH_ORIGIN = """你是中文GaussDB数据库专家，你精通于根据【原始问题】来生成多个相似的【中文问题】。
"""

MULTI_QUERY_USER_TMPL_ZH_ORIGIN = """请根据【原始问题】来生成多个相似的【中文问题】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。
【原始问题】：{query}
输出(3 中文查询):
"""

MULTI_QUERY_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】来生成3个不同版本的【中文问题】，来从向量数据库中检索相关文档。你的目标是通过生成多个视角下的问题帮助用户克服基于距离的相似性检索的限制。"""

MULTI_QUERY_SYSTEM_TMPL_EN = """You are the Chinese GaussDB database expert, your task is to generate 3 different versions of the Chinese question based on the original question raised by the user to retrieve the relevant documents from the vector database. Your goal is to help users overcome the limitations of distance-based similarity retrieval by generating questions from multiple perspectives."""

MULTI_QUERY_USER_TMPL_ZH = """请根据用户提出的【原始问题】来生成3个不同版本的【中文问题】。通过换行符来分割这些【中文问题】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。【原始问题】：{question}"""

MULTI_QUERY_USER_TMPL_EN = """You are an AI language model assistant. Your task is to generate 3 different versions of the given user question to retrieve relevant documents from a vector database. By generating multiple perspectives on the user question, your goal is to help the user overcome some of the limitations of distance-based similarity search. Provide these alternative questions separated by newlines. Original question: {question}"""

HYDE_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】来生成【中文答案】，请包含尽可能多的关键细节。"""

HYDE_SYSTEM_TMPL_EN = """You are a English GaussDB database expert. Your task is to write a passage to answer the question in English. Try to include as many key details as possible."""

HYDE_USER_TMPL_ZH = """请根据用户提出的【原始问题】来生成【中文答案】。答案的长度不超过100。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。【原始问题】：{question}"""

HYDE_USER_TMPL_EN = """Please write a passage to answer the question. Ensure that the length does not exceed 100 characters. This task is very important to me. Please complete it carefully. You will be rewarded if you complete it well.
> question: {question}
> passage:"""

HYDE_USER_TMPL_EN_EXP = """Please write a chinese passage to answer the question.
Try to include as many key details as possible. Ensure that the length does not exceed 100 characters.
> Question: {question}
> Passage:"""

STEP_BACK_SYSTEM_TMPL_ZH_ORIGIN = """你是中文GaussDB数据库专家，你的任务是后退一步并将【原始问题】解释为更通用的【后退问题】，这样更容易回答。下面是一些示例：

---------------------
【原始问题】: GaussDB是否支持分布式部署？
【后退问题】: GaussDB支持哪些类型的部署方式？

---------------------
【原始问题】: GaussDB是由那个公司推出的产品？
【后退问题】: 请介绍GaussDB产品的起源与演进？"""

STEP_BACK_USER_TMPL_ZH_ORIGIN = """请后退一步将【原始问题】解释为更通用的【后退问题】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。【原始问题】：{question}"""

STEP_BACK_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】提取出更通用的问题，来获取回答【原始问题】所需要的基本原则。下面是一些示例：

---------------------
【原始问题】: GaussDB是否支持分布式部署？
【后退问题】: GaussDB支持哪些类型的部署方式？

---------------------
【原始问题】: GaussDB是由那个公司推出的产品？
【后退问题】: 请介绍GaussDB产品的起源与演进？
"""

STEP_BACK_SYSTEM_TMPL_EN = """You are a Chinese GaussDB database expert, your task is to extract more general questions based on the user's [original question], to obtain the basic principles needed to answer the [original question]. Here are some examples:

---------------------
[Original Question] : Does GaussDB support distributed deployment?
[Backward Question] : What deployment modes does GaussDB support?

---------------------
[Original Question]: Which company launched GaussDB?
[Back Question]: What is the origin and evolution of GaussDB?
"""

STEP_BACK_USER_TMPL_ZH = """请根据用户提出的【原始问题】提取出更通用的问题。如果你不认识一个单词或首字母缩略词，就不要试图重写它。写出简洁的问题。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。【原始问题】：{question}"""

STEP_BACK_USER_TMPL_EN = """You are a English GaussDB database expert. Your task is to step back and paraphrase a question to a more generic step-back question, which is easier to answer. Here are a few examples."""

QUERY_TRANSFORM_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】生成3个相关的【子问题】。目标是将【原始问题】分解成一系列可以独立回答的【子问题】。"""

QUERY_TRANSFORM_SYSTEM_TMPL_EN = """You are a English GaussDB database expert. Your task is to generate three [sub-questions] related to the [original question]. The goal is to break down the [original question] into a series of [sub-questions] that can be answered in isolation."""

QUERY_TRANSFORM_USER_TMPL_ZH = """请根据用户提出的【原始问题】生成3个相关的【子问题】。通过换行符来分割这些【子问题】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。【原始问题】：{question}"""

QUERY_TRANSFORM_USER_TMPL_EN = """Please generate 3 [sub-questions] related to the [original question]. This task is very important to me. Please complete it carefully. You will be rewarded if you complete it well.
[Original question]: {question} 
Output (3 queries):"""

QUERY_TRANSFORM_USER_TMPL_EN_EXP = """You are a helpful assistant that generates multiple sub-questions related to an input question.
The goal is to break down the input into a set of sub-problems / sub-questions that can be answers in isolation.
Generate multiple search queries related to: {question} 
Output (3 queries):"""

DOCUMENT_COMPRESS_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，你的任务是根据用户提出的【原始问题】，从检索到的【上下文】中 *原样* 提取出与【原始问题】相关的【相关上下文】。"""

DOCUMENT_COMPRESS_SYSTEM_TMPL_EN = """You are a Chinese GaussDB database expert, your task is to extract the [relevant context] related to the [original question] from the retrieved [context] according to the [original question] raised by the user."""

DOCUMENT_COMPRESS_USER_TMPL_ZH = """请根据用户提出的【原始问题】，从检索到的【上下文】中 *原样* 提取出与【原始问题】相关的【相关上下文】。如果没有【相关上下文】，请返回空内容。请注意 *不要改动* 【上下文】中提取的内容。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。
> 【原始问题】：{question}
> 【上下文】：{context}
> 【相关上下文】："""

DOCUMENT_COMPRESS_USER_TMPL_EN = """Given the following question and context, extract any part of the context *AS IS* that is relevant to answer the question. If none of the context is relevant return {no_output_str}.

Remember, *DO NOT* edit the extracted parts of the context.

> Question: {{question}}
> Context:
>>>
{{context}}
>>>
Extracted relevant parts:"""

STEP_BACK_INFER_SYSTEM_TMPL_ZH = """你是中文GaussDB数据库专家，给定【原始问题】、检索出来【相关上下文】以及提取出来的【通用上下文】，你的任务是根据【相关上下文】和【通用上下文】来生成全面可靠的【答案】来回答【原始问题】。请注意如果【通用上下文】与【原始问题】无关或者矛盾，请忽略【通用上下文】。"""

STEP_BACK_INFER_SYSTEM_TMPL_EN = """You are a Chinese GaussDB database expert. Given the original question, the retrieved relevant context, and the extracted general context, your task is to generate a comprehensive and reliable answer to the original question based on the relevant context and the general context. Please note that if the general context is irrelevant or contradictory to the original question, please ignore the General context."""

STEP_BACK_INFER_USER_TMPL_ZH = """请根据【原始问题】、【相关上下文】以及【通用上下文】来生成【答案】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。
> 【原始问题】：{question},
> 【原始上下文】：{origin_context},
> 【后退上下文】：{step_back_context}
> 【答案】："""

STEP_BACK_INFER_USER_TMPL_EN = """You are an expert of world knowledge. I am going to ask you a question. Your response should be comprehensive and not contradicted with the following context if they are relevant. Otherwise, ignore them if they are not relevant.
{normal_context}
{step_back_context}

Original Question: {question}
Answer:"""

INFER_SYSTEM_TMPL_ZH = """你是中文 GaussDB 数据库专家，给定【原始问题】和检索出来【相关上下文】，你的任务是根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。
特别地，作为 GaussDB 数据库专家，你的职责是确保返回的【答案】与 GaussDB 数据库的高度相关性、内容的安全性以及合法性。
当用户提出的【原始问题】属于与安全敏感信息相关的问题时，例如但不限于军事政治、个人信息、数据安全、健康记录等，你应该礼貌地拒绝回答。

让我们一步一步的思考，按照下面的步骤完成这个任务。
##步骤1## 判断【相关上下文】是否能够解答【原始问题】，不能则直接返回不相关；反之执行步骤2。
##步骤2## 从【相关上下文】中提取出相关内容，生成全面可靠的【答案】，返回【答案】。
请确保你用中文回答问题。

----------------------
示例1：
【原始问题】：shared_buffer参数应该如何设置？
【相关上下文】：数据库中有很多默认设置，不同的环境下的设置不一样。
##步骤1## 【相关上下文】中主要描述数据库的设置，与【原始问题】中的shared_buffer参数无关，无法解答【原始问题】，因此直接返回不相关

示例2：
【原始问题】：GaussDB是否支持分布式集群？
【相关上下文】：GaussDB支持多种形式的部署，包括集中式与分布式集群。
##步骤1## 【相关上下文】中描述了GaussDB的部署形式，能够解答【原始问题】，执行步骤2
##步骤2## 从【相关上下文】中提取相关信息，生成并返回【答案】：GaussDB支持分布式集群。
"""

INFER_SYSTEM_TMPL_EN = """You are a English GaussDB database expert. Given the [original question] and the retrieved [related context], your task is to generate a comprehensive and reliable [answer] to answer the [original question] based on the [related context]. Let's think step by step and follow the steps below to complete this task.
## Step 1 ## Check whether [related context] can answer [original question]. If no, the system returns [irrelevant]. Otherwise, go to step 2.
## Step 2 ## Extract the relevant content from the [related context], generate a comprehensive and reliable [answer], and return the [answer].
Please make sure you answer in English. 

----------------------
Example 1:
[original question]: How to set the shared_buffer parameter?
[related context]: There are many default settings in the database. The settings vary according to the environment.
## Step 1 ## [related context] describes the database settings, which are irrelevant to the shared_buffer parameter in [original question]. Therefore, [original question] cannot be answered. return [irrelevant]

Example 2:
[original question]: Does GaussDB Support Distributed Clusters?
[related context]: GaussDB supports multiple deployment modes, including centralized and distributed clusters.
## Step 1 ## The GaussDB deployment mode described in [related context] can answer the original question. Go to step 2.
## Step 2 ## Extract related information from [related Context], generate and return [Answer]: GaussDB supports distributed clusters.
"""

INFER_USER_TMPL_ZH = """请根据【相关上下文】来生成全面可靠的【答案】来回答【原始问题】。这个任务对我非常重要，请认真完成，完成的很好可以得到奖励哦。
> 【原始问题】：{question},
> 【相关上下文】：{context}
> 【答案】："""

INFER_USER_TMPL_EN = """Please respond to [original question] by generating a comprehensive and reliable [answer] based on [related context]. This task is very important to me. Please complete it carefully. You will be rewarded if you complete it well.
> [original question]: {question},
> [related context]: {context}
> [answer]:"""

DIRECT_INFER_USER_TMPL_ZH = """{question}"""


def get_history_list(history, prompt_len, lang):
    """Function get history list"""
    history_list = []
    for history_dict in history[::-1]:
        qa_dict = {}
        qa_dict[QUESTION] = history_dict.get(QUESTION)
        answer_list = history_dict.get(ANSWER, "")
        if not answer_list:
            continue
        cur_lang = history_dict.get('lang')
        if cur_lang != lang:
            continue
        try:
            answer_list = ast.literal_eval(answer_list)
        except Exception as e:
            raise Exception(f'can not parse answer from history.') from e
        if not isinstance(answer_list, list):
            raise TypeError("the answer history type is wrong.")
        for answer_dict in answer_list:
            if not isinstance(answer_dict, dict):
                raise TypeError("the answer history type is wrong.")
            if answer_dict['type'] != ANSWER:
                continue
            qa_dict[ANSWER] = answer_dict['data']
            break
        if not qa_dict.get(ANSWER, ""):
            continue
        qa_len = len(history_dict.get(QUESTION)) + len(qa_dict.get(ANSWER))
        if prompt_len + qa_len > MAX_PROMPT_LENGTH:
            break
        prompt_len += qa_len
        history_list.insert(0, qa_dict)
    return history_list


# 构建messages输入
def construct_messages(system_prompt, user_question, history, lang):
    """Function construct messages"""
    messages = []
    prompt_len = 0
    prompt_len += len(system_prompt)
    prompt_len += len(user_question)
    if prompt_len > MAX_PROMPT_LENGTH:
        return messages
    history_list = get_history_list(history, prompt_len, lang)
    if system_prompt:
        init_message = {
            ROLE: "system",
            CONTENT: system_prompt
        }
        messages.append(init_message)
    for qa_dict in history_list:
        user_message_dict = {
            ROLE: "user",
            CONTENT: qa_dict['question']
        }
        messages.append(user_message_dict)
        assistant_message_dict = {
            ROLE: "assistant",
            CONTENT: qa_dict['answer']
        }
        messages.append(assistant_message_dict)
    query_message = {
        ROLE: "user",
        CONTENT: user_question
    }
    messages.append(query_message)
    return messages


def get_hyde_prompt(question, history, lang):
    """Function get hyde prompt"""
    if lang == 'zh':
        system_prompt = HYDE_SYSTEM_TMPL_ZH
        user_question = HYDE_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = HYDE_SYSTEM_TMPL_EN
        user_question = HYDE_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_query_transform_prompt(question, history, lang):
    """Function get query transform prompt"""
    if lang == 'zh':
        system_prompt = QUERY_TRANSFORM_SYSTEM_TMPL_ZH
        user_question = QUERY_TRANSFORM_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = QUERY_TRANSFORM_SYSTEM_TMPL_EN
        user_question = QUERY_TRANSFORM_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_query_router_prompt(question, history, lang):
    """Function get query route prompt"""
    if lang == 'zh':
        system_prompt = QUERY_ROUTER_SYSTEM_TMPL_ZH
        user_question = QUERY_ROUTER_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = QUERY_ROUTER_SYSTEM_TMPL_EN
        user_question = QUERY_ROUTER_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_query_rewrite_prompt(question, history, lang):
    """Function get query rewrite prompt"""
    if lang == 'zh':
        system_prompt = QUERY_REWRITE_SYSTEM_TMPL_ZH
        user_question = QUERY_REWRITE_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = QUERY_REWRITE_SYSTEM_TMPL_EN
        user_question = QUERY_REWRITE_SYSTEM_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_query_expansion_prompt(question, history, lang):
    """Function get query expansion prompt"""
    if lang == 'zh':
        system_prompt = QUERY_EXPANSION_SYSTEM_TMPL_ZH
        user_question = QUERY_EXPANSION_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = QUERY_EXPANSION_SYSTEM_TMPL_EN
        user_question = QUERY_EXPANSION_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


# 多查询生成
def get_multi_query_prompt(question, history, lang):
    """Function get multi query prompt"""
    if lang == 'zh':
        system_prompt = MULTI_QUERY_SYSTEM_TMPL_ZH
        user_question = MULTI_QUERY_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = MULTI_QUERY_SYSTEM_TMPL_EN
        user_question = MULTI_QUERY_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


# step back
def get_step_back_prompt(question, history, lang):
    """Function get step back prompt"""
    if lang == 'zh':
        system_prompt = HYDE_SYSTEM_TMPL_ZH
        user_question = HYDE_USER_TMPL_ZH.format(question=question)
    elif lang == 'en':
        system_prompt = HYDE_SYSTEM_TMPL_EN
        user_question = HYDE_USER_TMPL_EN.format(question=question)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


# 实体抽取
def entity_extractor_prompt(question, history, lang):
    """Function extract entity"""
    return []


# 判断上下文长度是否超出限制
def check_prompt_length(system_tmpl, user_tmpl, question, context_list):
    """Function check prompt length"""
    system_prompt = system_tmpl
    prompt_len = len(system_tmpl) + len(user_tmpl) + len(question)
    if prompt_len > MAX_PROMPT_LENGTH:
        user_question = user_tmpl.format(question=question, context="")
        return system_prompt, user_question
    useful_context_list = []
    for context in context_list:
        if prompt_len + len(context) + 1 > MAX_PROMPT_LENGTH:
            continue
        prompt_len += len(context)
        useful_context_list.append(context)
    user_question = user_tmpl.format(question=question, context='\n'.join(useful_context_list))
    return system_prompt, user_question


# 文档压缩
def get_document_compress_prompt(question, context, history, lang):
    """Function get document compress prompt"""
    if lang == 'zh':
        system_prompt = DOCUMENT_COMPRESS_SYSTEM_TMPL_ZH
        user_question = DOCUMENT_COMPRESS_USER_TMPL_ZH.format(question=question, context=context)
    elif lang == 'en':
        system_prompt = DOCUMENT_COMPRESS_SYSTEM_TMPL_EN
        user_question = DOCUMENT_COMPRESS_USER_TMPL_EN.format(question=question, context=context)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


# step back infer
def get_step_back_infer_prompt(question, origin_context, step_back_context, history, lang):
    """Function get step back infer prompt"""
    if lang == 'zh':
        system_prompt = STEP_BACK_INFER_SYSTEM_TMPL_ZH
        user_question = STEP_BACK_INFER_USER_TMPL_ZH.format(question=question, origin_context=origin_context,
                                                            step_back_context=step_back_context)
    elif lang == 'en':
        system_prompt = STEP_BACK_INFER_SYSTEM_TMPL_EN
        user_question = STEP_BACK_INFER_USER_TMPL_EN.format(question=question, origin_context=origin_context,
                                                            step_back_context=step_back_context)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


# 判断相关性，并回答
def get_infer_prompt(question, context_list, history, lang):
    """Function get infer prompt"""
    if lang == 'zh':
        system_prompt, user_question = check_prompt_length(INFER_SYSTEM_TMPL_ZH, INFER_USER_TMPL_ZH, question,
                                                           context_list)
    elif lang == 'en':
        system_prompt, user_question = check_prompt_length(INFER_SYSTEM_TMPL_EN, INFER_USER_TMPL_EN, question,
                                                           context_list)
    else:
        return []
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_infer_prompt_direct(question, history, lang):
    """Function get infer prompt direct"""
    system_prompt = ""
    user_question = DIRECT_INFER_USER_TMPL_ZH.format(question=question)
    messages = construct_messages(system_prompt, user_question, history, lang)
    return messages


def get_prompt(query, context_list):
    """Function get prompt"""
    if not context_list:
        return "资料库中没有对应知识，请回答如下问题：{}。如果你没有相应的背景知识，请回答不知道，不要尝试编造答案。".format(
            query)
    prompt = '给定以下{}个上下文列表：\n'.format(len(context_list))
    for index, context in enumerate(context_list):
        prompt += '列表{}：{}\n'.format(index, context)
    prompt += '请从上面的列表内容中，提取最相关的知识，回答如下问题：{}。如果没有相关的知识，请回答不知道，不要尝试编造答案'.format(
        query)
    return prompt
