# GaussMaster 两大主流程详解

## 概述

GaussMaster 有两个核心主流程：

| 流程 | 入口 | 特点 | 适用场景 |
|------|------|------|---------|
| **流程一：Agent工具调用** | `dba.interact()` | 工具交互、多轮对话 | 数据库运维操作 |
| **流程二：RAG知识问答** | `data_transformer.ask_gauss()` | 向量检索+LLM生成 | 知识库问答 |

---

## 流程一：Agent工具调用（dba.interact）

### 完整调用链

```
用户HTTP请求
    ↓
core.py: intelligent_interaction_chat()
    ↓
dba.interact()              ← 入口
    ↓
DBA.__init__()              ← 创建Agent实例
    ↓
DBA.interaction()           ← 主生成器
    ↓
DBA.interact_with_tool()    ← 工具交互核心
    ↓
    ├── infer_tool_name()   ← 意图识别（LLM）
    ├── check_has_valid_tool()
    ├── check_is_no_param_tool()
    ├── infer_arguments()   ← 参数提取（LLM）
    ├── verify_arguments()
    └── call_tool()         ← 执行工具
        ↓
    dbmind_interface.py: summary_alarms等
        ↓
    返回结果给用户
```

### 代码走读

#### 第1步：core.py 入口

```python
# core.py 第52-61行
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output  # 流式输出
def intelligent_interaction_chat(query: PlanModel):
    """
    智能交互入口
    请求体: {
        "query": "帮我查看数据库状态",
        "user_id": "user1",
        "session_id": "sess1",
        "mode": "tool_interaction",
        "history_len": 1
    }
    """
    plan_model = dict(query)
    plan_model.update({'model_name': current_llm.get()})
    return dba.interact(**plan_model)  # ← 调用Agent
```

#### 第2步：dba.py - interact() 入口

```python
# dba.py 第38-48行
async def interact(user_id, session_id, query, mode, model_name, history_len=1, lang='zh'):
    """
    对话交互入口（生成器）
    """
    # 创建DBA Agent实例
    dba = DBA(
        user_id=user_id,
        session_id=session_id,
        question=query,
        mode=mode,
        llm_name=model_name,
        history_len=history_len,
        lang=lang
    )

    # 流式输出每个步骤
    async for step_output in dba.interaction():
        yield step_output

    yield [DONE_FLAG]  # 结束标记
```

#### 第3步：DBA.interaction() 主生成器

```python
# dba.py 第75-87行
async def interaction(self):
    """主交互流程"""
    # 快捷场景：直接调用工具（不需要LLM推断）
    if self.question in ['当前数据库运行状况', '当前有哪些告警']:
        # 默认查询最近1小时
        tz = adjust_timezone(configs.get('TIMEZONE', 'tz'))
        end_time = datetime.now(tz)
        start_time = end_time - timedelta(minutes=60)
        res = call_tool('summary_alarms', params={
            'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S')
        })
        yield res

    # 标准工具交互流程
    elif self.mode == InteractionType.TOOL_INTERACTION:
        async for step in self.interact_with_tool():
            yield step
```

#### 第4步：DBA.interact_with_tool() 核心

```python
# dba.py 第89-156行
async def interact_with_tool(self):
    """与第三方工具交互"""

    # ====== 1. 检查意图状态 ======
    intention_tool = SESSION_TOOL_HISTORY.get(
        self.user_id, {}
    ).get(self.session_id, None)

    # ====== 2. 如果没有意图，需要推断 ======
    if intention_tool is None:
        # 2.1 匹配工具
        yield [formatter_progress('工具匹配中...')]
        matched_tool = await infer_tool_name(
            self.question,
            self.user_id,
            self.session_id,
            self.llm
        )

        # 2.2 校验工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            yield [formatter_str('用户提问的问题无法用第三方工具解答。')]
            return

        # 2.3 检查是否需要参数
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            # 无参工具，直接调用
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(matched_tool)
            yield tool_result
            return

        intention_tool = matched_tool

    # ====== 3. 提取参数 ======
    yield [formatter_progress('提取参数中...')]
    qa_record_history = await self.get_qa_history()
    content_resp, function_call = await infer_arguments(
        self.question,
        intention_tool,
        qa_record_history,
        self.llm
    )

    # ====== 4. 调用工具 ======
    if function_call:
        is_complete_params, correct_params, need_prams = verify_arguments(function_call)
        if is_complete_params:
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(intention_tool, correct_params)
            yield tool_result
        else:
            # 参数不完整，要求用户提供
            yield [formatter_str(f'缺少参数{",".join(list(need_prams.keys()))}，请一次性提供完整')]
    else:
        yield [formatter_str(content_resp)]
```

#### 第5步：executor.py - 工具调用5步

```python
# executor.py - 步骤1: 意图识别
async def infer_tool_name(question, user_id, session_id, llm):
    """根据用户问题推断应该使用哪个工具"""
    # 1. 获取所有工具描述
    tools_des = '\n'.join([json.dumps(tool) for tool in base_tools.detail_str_list])

    # 2. 构建意图识别Prompt
    tools_des_prompt = TOOL_DES_ZH.format(functions=tools_des)

    # 3. 检查会话历史（意图状态保持）
    tool_name = SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id)

    # 4. 调用LLM推断工具名
    if tool_name is None:
        message_input = [
            {ROLE: SYSTEM, CONTENT: tools_des_prompt},
            {ROLE: USER, CONTENT: question},
        ]
        tool_name, _ = await llm.invoke(message_input)

    return tool_name.strip()

# executor.py - 步骤4: 参数提取
async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """从用户问题中提取工具参数"""
    # 1. 获取目标工具的详细描述（带参数定义）
    target_tool_des = base_tools.get(intention_tool).__detail_with_param_str__

    # 2. 构建时间参数
    tz = adjust_timezone(configs.get('TIMEZONE', 'tz'))
    propose_prompt_dict = {
        "year": str(datetime.now(tz).year),
        "date": str(datetime.now(tz).date()),
        "current": str(datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')),
    }

    # 3. 构建Prompt并调用LLM
    propose_prompt = TOOL_INTERACT_ZH.format(**propose_prompt_dict)
    message_inputs = [{ROLE: SYSTEM, CONTENT: propose_prompt}]
    # ... 添加历史记录
    message_inputs.append({ROLE: USER, CONTENT: question})

    content_resp, function_call = await llm.invoke(message_inputs)
    return content_resp, function_call

# executor.py - 步骤5: 工具执行
def call_tool(tool_name: str, params=None):
    """执行工具"""
    if params is None:
        params = {}
    function_result = global_vars.tools_registry.get(tool_name)(**params)
    return function_result
```

#### 第6步：dbmind_interface.py - 具体工具

```python
# dbmind_interface.py
@base_tools(
    name="summary_alarms",
    description="获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
def summary_alarms(start_time, end_time):
    """获取所有告警"""
    # 1. 时间转换
    start_at, end_at = transfer_date_2_timestamp(start_time, end_time)

    # 2. 获取集群列表
    instance_list = get_cluster_list().get(current_instance.get())

    # 3. 批量获取告警
    final_alarms = fetch_all_alarms(start_at, end_at, ip_list)

    # 4. 格式化输出
    target = generate_alarm_output(final_alarms, ip_list)
    return target
```

### 流程一特点总结

```
┌─────────────────────────────────────────┐
│           Agent工具调用流程              │
├─────────────────────────────────────────┤
│ 1. 意图识别（infer_tool_name）           │
│    └─ LLM判断该用哪个工具               │
│                                         │
│ 2. 工具校验（check_has_valid_tool）      │
│    └─ 检查工具是否存在                  │
│                                         │
│ 3. 参数校验（check_is_no_param_tool）    │
│    └─ 检查是否需要参数                  │
│                                         │
│ 4. 参数提取（infer_arguments）           │
│    └─ LLM从问题中提取参数               │
│                                         │
│ 5. 参数验证（verify_arguments）          │
│    └─ 检查参数完整性                    │
│                                         │
│ 6. 工具执行（call_tool）                 │
│    └─ 调用具体工具函数                  │
│                                         │
│ 特点：                                   │
│ - 支持多轮对话（意图状态保持）           │
│ - 流式输出（generator yield）            │
│ - 工具调用失败可追问补充参数             │
└─────────────────────────────────────────┘
```

---

## 流程二：RAG知识问答（data_transformer.ask_gauss）

### 完整调用链

```
用户HTTP请求
    ↓
core.py: ask_gauss()
    ↓
data_transformer.ask_gauss()      ← 入口
    ↓
    ├── 敏感词检测
    ├── search()                  ← RAG检索
    │       ↓
    │   BaseRetriever.search_vector_result_gaussdb()  ← 向量检索
    │   BaseRetriever.search_text_result_gaussdb()    ← 文本检索
    │   BaseRetriever.reranker_search_result()        ← 重排序
    │
    ├── llm_generation()          ← LLM生成答案
    │       ↓
    │   create_infer_prompt()     ← 构建Prompt
    │   generate_answer()         ← 调用LLM
    │
    └── 保存到数据库
        ↓
    返回结果给用户
```

### 代码走读

#### 第1步：core.py 入口

```python
# core.py 第201-213行
@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output  # 流式输出
def ask_gauss(search_params: SearchParams):
    """
    智能问答入口（带RAG检索）
    请求体: {
        "question": "如何优化慢SQL？",
        "user_id": "user1",
        "session_id": "sess1",
        "vector_topk": 6,      # 向量检索Top-K
        "text_topk": 6,        # 文本检索Top-K
        "rerank_topk": 3,      # 重排序Top-K
        "kb_id": 0,            # 知识库ID
        "model_name": "pangu_cloud...",
        "lang": "zh",
        "history_len": 1
    }
    """
    return data_transformer.ask_gauss(
        search_params.question,
        search_params.user_id,
        search_params.session_id,
        search_params.switch,
        search_params.vector_topk,
        search_params.text_topk,
        search_params.rerank_topk,
        search_params.kb_id,
        search_params.version,
        search_params.model_name,
        search_params.lang,
        search_params.history_len,
        search_params.model_config
    )
```

#### 第2步：data_transformer.ask_gauss() 主流程

```python
# data_transformer.py 第448-566行
async def ask_gauss(question, user_id, session_id, switch, vector_topk, text_topk,
                    rerank_topk, kb_id, version, model_name, lang, history_len, model_config):
    """端到端问答流程"""

    # ====== 1. 参数校验 ======
    if not question:
        raise ValueError('question can not be empty.')
    # ... 各种参数校验

    # ====== 2. 敏感词检测 ======
    if (global_vars.configs.get(SECTION_SAFETY, 'safety_check').strip().upper() == 'TRUE'
            and global_vars.DFA_DETECTOR.is_unsafe_text(question)):
        # 返回安全警告
        yield {'type': 'answer', 'data': '无法回答安全敏感话题！'}
        return

    # ====== 3. 初始化QA记录 ======
    start_time = time.time()
    answer_id = str(uuid.uuid4())
    qa_dict = {
        'question': question,
        'answer_id': answer_id,
        'user_id': user_id,
        'session_id': session_id,
        'model_name': model_name,
        'lang': lang,
        'task_type': 'QA',
        'like': 0,
        'hate': 0,
    }

    # ====== 4. RAG检索 ======
    yield {'type': 'progress', 'data': '问题检索中...'}
    res_dict = await search(
        question, user_id, session_id,
        vector_topk, text_topk, rerank_topk,
        kb_id, version, lang, history_len
    )
    question_id = res_dict['question_id']
    search_res = res_dict['search_res']

    # ====== 5. 生成答案 ======
    try:
        history = get_history_chat(user_id, session_id, history_len)

        if not search_res:
            # 无检索结果，进入查询优化流程
            async for item in query_opt_process(...):
                yield item
        else:
            # 有检索结果，直接LLM生成
            async for item in llm_generation(question, search_res, model_name, history, lang):
                yield item

        # 返回完成标记
        yield {'type': 'complete', 'data': {'time': ..., 'question_id': question_id, 'answer_id': answer_id}}

    finally:
        # 保存到数据库
        gaussdb_vector.insert_qa_record(qa_dict)
```

#### 第3步：search() - RAG检索

```python
# data_transformer.py 第183-256行
async def search(question, user_id, session_id, vector_topk, text_topk, rerank_topk,
                 kb_id, version, lang, history_len):
    """RAG检索：向量检索 + 文本检索 + 重排序"""

    # 1. 确定知识库表名
    if kb_id == 0:
        table_name = kb_config.KT_TABLE_NAME + "_" + lang  # 默认知识库
    else:
        table_name = CUSTOM_KB_PREFIX + str(kb_id)  # 自定义知识库

    # 2. 获取数据库实例
    gaussdb = get_db_instance(table_name, kb_config.KT_TABLE_CONFIG)

    # 3. 创建检索器
    retriever = BaseRetriever(gaussdb, global_vars.reranker_model)

    # 4. 向量检索（语义相似度）
    start_time = time.time()
    vector_result = await retriever.search_vector_result_gaussdb(question, vector_topk, version)
    vector_time = time.time()

    # 5. 文本检索（关键词匹配）
    text_result = retriever.search_text_result_gaussdb(question, text_topk, version)
    text_time = time.time()

    # 6. 重排序（提升精度）
    reranker_scores, reranker_result = await retriever.reranker_search_result(
        question, vector_result, text_result, rerank_topk
    )
    reranker_time = time.time()

    # 7. 组装结果
    search_res = []
    for index, answer in enumerate(reranker_result):
        knowledge_dict = {
            'knowledge_id': answer[column_list.index('uuid')],
            'content': answer[column_list.index('text')],  # 知识内容
            'title': answer[column_list.index('title')],
            'source': answer[column_list.index('source')],
            'score': reranker_scores[index],  # 相似度分数
        }
        search_res.append(knowledge_dict)

    return {
        'search_res': search_res,
        'vector_search_time': round(vector_time - start_time, 6),
        'text_search_time': round(text_time - vector_time, 6),
        'rerank_search_time': round(reranker_time - text_time, 6),
        'question_id': str(uuid.uuid4())
    }
```

#### 第4步：llm_generation() - LLM生成

```python
# data_transformer.py 第569-584行
async def llm_generation(question, search_res, model_name, history, lang):
    """LLM生成答案"""

    # 1. 返回检索到的参考资料
    yield {'type': 'refrences', 'data': json.dumps(search_res, ensure_ascii=False)}
    yield {'type': 'progress', 'data': '检索完成'}

    # 2. 构建推理Prompt
    status, messages = create_infer_prompt_direct(question, search_res, history, lang)

    # 3. 调用LLM生成答案
    yield {'type': 'progress', 'data': '答案生成中...'}
    if not status:
        yield messages[0]  # 返回错误信息
        return

    answer = ""
    async for item in generate_answer(messages, model_name):
        answer += item
        yield {'type': 'answer', 'data': answer}  # 流式输出

    yield {'type': 'progress', 'data': '答案生成完成'}
```

#### 第5步：create_infer_prompt_direct() - 构建Prompt

```python
# data_transformer.py 第322-344行
def create_infer_prompt_direct(question, search_res, history, lang):
    """构建推理Prompt"""

    # 1. 提取检索到的知识内容
    context_list = []
    for search_dict in search_res:
        context_list.append(search_dict['content'])

    # 2. 如果没有检索结果
    if not context_list:
        return False, [{'type': 'answer', 'data': '无法从知识库中检索到相关知识'}]

    # 3. 构建Prompt
    messages = get_infer_prompt(question, context_list, history, lang)
    # messages格式: [
    #   {"role": "system", "content": "你是GaussDB专家..."},
    #   {"role": "user", "content": "问题：xxx\n上下文：xxx"}
    # ]

    return True, messages
```

#### 第6步：generate_answer() - 调用LLM

```python
# data_transformer.py 第416-436行
async def generate_answer(messages, model_name):
    """调用LLM生成答案"""

    if global_vars.local_llm:
        # 本地LLM
        async for item in global_vars.local_llm.invoke(messages):
            yield item
    else:
        # 在线LLM
        params = {'messages': messages}
        headers = {"Accept": "text/event-stream", "Connection": "keep-alive"}
        url = global_vars.llm_config.get('online_llm').get(model_name).get('api_url')

        # 发送请求
        llm_generator = await thread_request_from_llm(url, headers, params)

        # 流式读取响应
        while True:
            chunk = await asyncio.get_running_loop().run_in_executor(None, iter_next, llm_generator)
            if chunk == -1:
                break
            yield chunk
```

### 流程二特点总结

```
┌─────────────────────────────────────────┐
│           RAG知识问答流程                │
├─────────────────────────────────────────┤
│ 1. 敏感词检测                            │
│    └─ DFA算法检测敏感内容                │
│                                         │
│ 2. RAG检索（search）                     │
│    ├─ 向量检索（语义相似度）              │
│    ├─ 文本检索（关键词匹配）              │
│    └─ 重排序（Reranker提升精度）          │
│                                         │
│ 3. Prompt构建                            │
│    └─ 将检索结果作为上下文               │
│                                         │
│ 4. LLM生成（generate_answer）            │
│    └─ 流式输出答案                       │
│                                         │
│ 5. 保存记录                              │
│    └─ 存入向量数据库                     │
│                                         │
│ 特点：                                   │
│ - 基于知识库，减少幻觉                   │
│ - 多路召回（向量+文本）                  │
│ - 重排序提升精度                         │
│ - 流式输出体验好                         │
└─────────────────────────────────────────┘
```

---

## 两大流程对比

| 对比项 | 流程一：Agent工具调用 | 流程二：RAG知识问答 |
|--------|---------------------|-------------------|
| **入口** | `dba.interact()` | `data_transformer.ask_gauss()` |
| **核心能力** | 工具调用、运维操作 | 知识检索、问答生成 |
| **使用场景** | 查看告警、诊断集群 | 查询文档、知识问答 |
| **LLM作用** | 意图识别、参数提取 | 答案生成 |
| **数据来源** | DBMind API | 向量数据库（知识库） |
| **多轮对话** | ✅ 支持（意图状态保持） | ❌ 单次问答 |
| **流式输出** | ✅ 支持 | ✅ 支持 |
| **关键文件** | dba.py, executor.py | data_transformer.py |
| **核心装饰器** | @base_tools | @request_mapping |

---

## 面试要点

### Q1: 两个流程有什么区别？

```
答：
1. Agent工具调用（dba.interact）：
   - 用于数据库运维操作
   - 通过LLM识别意图、提取参数
   - 调用DBMind工具执行
   - 支持多轮对话

2. RAG知识问答（data_transformer.ask_gauss）：
   - 用于知识库问答
   - 通过向量检索+文本检索召回知识
   - LLM基于检索结果生成答案
   - 单次问答，基于知识库减少幻觉
```

### Q2: 为什么需要两个流程？

```
答：
- 不同场景需要不同能力
- 运维操作需要调用外部工具（DBMind）
- 知识问答需要基于文档生成答案
- 分离设计使架构更清晰
```

### Q3: RAG流程中的检索策略是什么？

```
答：
1. 向量检索：基于语义相似度，召回Top-K
2. 文本检索：基于关键词匹配，召回Top-K
3. 重排序：使用Reranker模型对合并结果重排，取Top-K

这种多路召回+重排序的策略可以提高检索精度。
```

---

## 一句话总结

```
┌─────────────────────────────────────────┐
│  流程一：dba.interact()                  │
│  智能运维 → 意图识别 → 工具调用          │
│  适合：数据库操作、故障诊断              │
├─────────────────────────────────────────┤
│  流程二：data_transformer.ask_gauss()    │
│  知识问答 → RAG检索 → LLM生成            │
│  适合：文档查询、知识问答                │
└─────────────────────────────────────────┘
```

---

*本文档基于 openGauss-GaussMaster v1.0.0*
