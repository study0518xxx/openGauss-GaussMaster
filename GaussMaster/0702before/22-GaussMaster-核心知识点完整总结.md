# GaussMaster 核心知识点详解

## 目录

- [一、两大核心流程对比](#一两大核心流程对比)
- [二、query_opt_process 和 llm_generation 函数详解](#二query_opt_process-和-llm_generation-函数详解)
- [三、HyDE 与查询改写的关系](#三hyde-与查询改写的关系)
- [四、generate_answer 通用LLM调用函数](#四generate_answer-通用llm调用函数)
- [五、Agent 智能交互完整流程](#五agent-智能交互完整流程)
- [六、interact_with_tool 函数详解](#六interact_with_tool-函数详解)
- [七、关键工程问题详解](#七关键工程问题详解)
- [八、已知的边界问题](#八已知的边界问题)

---

## 一、两大核心流程对比

### 1.1 GaussMaster 的两条主路径

```
┌─────────────────────────────────────────────────────────────┐
│              GaussMaster 两大核心流程                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  路径1: ask_gauss (智能问答/RAG)                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 用户问: "GaussDB是什么？"                              │  │
│  │         ↓                                             │  │
│  │  search() → 向量检索 + 文本检索 + 重排序              │  │
│  │         ↓                                             │  │
│  │  llm_generation() → 生成答案                          │  │
│  │         ↓                                             │  │
│  │  返回答案（基于知识库）                                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  路径2: intelligent_interaction (Agent/Tool Calling)        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 用户问: "帮我查看昨天的告警"                            │  │
│  │         ↓                                             │  │
│  │  infer_tool_name() → 识别要调用哪个工具               │  │
│  │         ↓                                             │  │
│  │  infer_arguments() → 提取参数                        │  │
│  │         ↓                                             │  │
│  │  call_tool() → 调用运维工具                          │  │
│  │         ↓                                             │  │
│  │  返回结果（执行操作）                                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 两种路径的核心区别

| 维度 | ask_gauss (RAG) | intelligent_interaction (Agent) |
|------|----------------|--------------------------------|
| **目的** | 回答知识问题 | 执行运维操作 |
| **数据来源** | 知识库（文档） | 实时数据库状态 |
| **输出** | 文字答案 | 操作结果/数据 |
| **是否修改数据** | 否 | 是（查询数据） |
| **调用链** | search() → llm_generation() | infer_tool_name() → infer_arguments() → call_tool() |
| **典型问题** | "GaussDB是什么？" | "帮我查看告警" |

### 1.3 Agent vs RAG：哪个更难？哪个更重要？

| 维度 | RAG（智能问答） | Agent（工具调用） |
|------|----------------|------------------|
| **难度** | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐⭐ 更高 |
| **复杂性** | 检索 + 生成 | 意图识别 + 参数提取 + 工具执行 + 结果处理 |
| **工程挑战** | 向量检索、召回率、相关性排序 | 多轮对话、状态管理、错误处理 |
| **核心难点** | 如何找到最相关的知识 | 如何让 LLM 准确决策 |

**为什么 Agent 更难？**

```
RAG 只需要解决："答案在哪里？"
Agent 需要解决：
  1. 用户想要做什么？（意图识别）
  2. 需要调用哪个工具？（工具选择）
  3. 需要什么参数？（参数提取）
  4. 参数对不对？（校验）
  5. 工具执行失败怎么办？（错误处理）
  6. 多轮对话怎么保持状态？（状态管理）
```

---

## 二、query_opt_process 和 llm_generation 函数详解

### 2.1 整体流程图

```
用户提问
    │
    ▼
┌─────────────────┐
│   ask_gauss()   │  ← 主入口函数
└────────┬────────┘
         │
         ▼
┌─────────────────┐     有结果      ┌─────────────────┐
│  search() 检索  │ ──────────────→ │ llm_generation  │
│  (向量+文本+重排) │                │  (直接生成答案)  │
└────────┬────────┘                └─────────────────┘
         │ 无结果
         ▼
┌─────────────────┐
│ query_opt_process │ ← 查询优化流程
│  (HyDE + 查询改写) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ llm_generation  │ ← 用优化后的结果生成答案
└─────────────────┘
```

### 2.2 llm_generation 函数详解

#### 位置
[data_transformer.py#L569-L584](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/server/web/data_transformer.py#L569-L584)

#### 作用
**LLM生成答案** - 根据检索到的知识库内容，调用大语言模型生成最终回答。

#### 代码解析

```python
async def llm_generation(question, search_res, model_name, history, lang):
    """Function llm generation."""

    # 步骤1: 返回参考资料给前端
    yield {'type': 'refrences', 'data': json.dumps(search_res, ensure_ascii=False)}
    yield yield_progress_message('检索完成', 'Retrival complete', lang)

    # 步骤2: 构建Prompt
    status, messages = create_infer_prompt_direct(question, search_res, history, lang)

    # 步骤3: 告诉用户正在生成答案
    yield yield_progress_message('答案生成中...', 'Generating answer...', lang)

    # 步骤4: 如果构建Prompt失败，直接返回错误信息
    if not status:
        yield messages[0]
        yield yield_progress_message('答案生成完成', 'Answer generation complete', lang)
        return

    # 步骤5: 调用LLM流式生成答案
    answer = ""
    async for item in generate_answer(messages, model_name):
        answer += item
        yield {'type': 'answer', 'data': answer}

    yield yield_progress_message('答案生成完成', 'Answer generation complete', lang)
```

#### 通俗理解
想象你在写论文：
1. **search_res** = 你从图书馆借来的参考资料
2. **create_infer_prompt_direct** = 把题目和资料整理成写作大纲
3. **generate_answer** = 根据大纲写文章（一个字一个字写出来）

---

## 三、HyDE 与查询改写的关系

### 3.1 两者的关系：并行协作，多路召回

```
┌─────────────────────────────────────────────────────────────────┐
│                    查询优化整体架构                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户问题: "怎么让数据库跑得更快"                                │
│        │                                                        │
│        ▼                                                        │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              query_opt_process 查询优化流程              │   │
│   ├─────────────────────────────────────────────────────────┤   │
│   │                                                         │   │
│   │   ┌─────────────────┐      ┌─────────────────────┐     │   │
│   │   │   HyDE 阶段      │      │   查询改写阶段       │     │   │
│   │   │   (生成假设答案) │      │   (改写多个问题)     │     │   │
│   │   └────────┬────────┘      └──────────┬──────────┘     │   │
│   │            │                          │                │   │
│   │            └────────────┬─────────────┘                │   │
│   │                         ▼                              │   │
│   │              ┌─────────────────────┐                   │   │
│   │              │    合并查询列表      │                   │   │
│   │              │  query_list = [      │                   │   │
│   │              │    假设答案,        │                   │   │
│   │              │    子问题1,         │                   │   │
│   │              │    子问题2,         │                   │   │
│   │              │    子问题3          │                   │   │
│   │              │  ]                  │                   │   │
│   │              └──────────┬──────────┘                   │   │
│   │                         ▼                              │   │
│   │              ┌─────────────────────┐                   │   │
│   │              │   多路检索           │                   │   │
│   │              └─────────────────────┘                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 为什么要分两个阶段？各自解决什么问题？

| 阶段 | 解决的问题 | 核心思路 | 输出形式 |
|------|-----------|---------|---------|
| **HyDE** | 用户用词 vs 文档用词的**语义鸿沟** | 让LLM先生成一个"理想答案"，用这个答案去检索 | 一段完整的文本（假设性回答） |
| **查询改写** | 单一查询的**覆盖面不足** | 把一个问题拆成多个角度的问题 | 3个独立的子问题 |

### 3.3 具体例子说明

```
用户问题: "怎么让数据库跑得更快？"

┌────────────────────────────────────────────────────────────────┐
│  问题1: 用词差异（语义鸿沟）                                     │
├────────────────────────────────────────────────────────────────┤
│  用户用词: "跑得更快" ← 口语化、形象化                          │
│  文档用词: "性能优化" ← 专业化、技术化                          │
│                                                                │
│  直接检索: "跑得更快" → 向量匹配不到 "性能优化" 文档 ❌         │
│                                                                │
│  HyDE解决方案:                                                  │
│  LLM生成假设回答: "数据库性能优化方法包括..."                   │
│  用这段回答检索 → 包含"性能优化"关键词 → 匹配成功 ✓            │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  问题2: 覆盖面不足                                              │
├────────────────────────────────────────────────────────────────┤
│  原问题只覆盖一个角度: "跑得更快"                                │
│                                                                │
│  但相关知识可能分布在:                                           │
│  - "SQL调优技巧"                                                │
│  - "索引优化方法"                                               │
│  - "参数配置建议"                                               │
│                                                                │
│  查询改写解决方案:                                               │
│  把原问题改写成3个查询:                                          │
│  1. 数据库性能优化方法                                          │
│  2. SQL查询调优技巧                                             │
│  3. 数据库索引优化                                              │
└────────────────────────────────────────────────────────────────┘
```

### 3.4 HyDE 阶段详解：为什么要写假设性答案？

#### 核心作用：弥合"语义鸿沟"

```
┌────────────────────────────────────────────────────────────────┐
│                     语义鸿沟问题                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   用户问题: "怎么让数据库跑得更快？"                            │
│        │                                                       │
│        │   向量空间中的距离                                     │
│        │   "跑得更快" ──────────────── "性能优化"              │
│        │         ↑                          ↑                  │
│        │       用户向量                    文档向量             │
│        │         ╲                        ╱                    │
│        │          ╲ 距离远，相似度低    ╱                     │
│        │           ╲                    ╱                      │
│        │            ╲──────────────────╱                       │
│        │                      ❌ 匹配失败                        │
│        ▼                                                       │
│   HyDE 介入:                                                   │
│   LLM生成假设回答: "数据库性能优化方法包括..."                  │
│        │                                                       │
│        │   "性能优化方法" ───────────── "性能优化"              │
│        │         ↑                          ↑                  │
│        │       假设答案向量              文档向量                │
│        │         ╲                        ╱                    │
│        │          ╲ 距离近，相似度高    ╱                     │
│        │           ╲                    ╱                      │
│        │            ╲──────────────────╱                       │
│        │                      ✓ 匹配成功                        │
│        │                                                       │
└────────────────────────────────────────────────────────────────┘
```

### 3.5 查询改写阶段详解：为什么要改写多个问题？

#### 核心作用：扩大检索覆盖面

```
原问题: "怎么让数据库跑得更快"
       │
       │  只覆盖一个角度，可能遗漏相关内容
       ▼
┌─────────────────────────────────────────────────────────┐
│              查询改写: 一拆为三                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  原问题                    改写后                        │
│  ─────────────────────────────────────────               │
│  怎么让数据库              1. 数据库性能优化方法          │
│  跑得更快        →        2. SQL调优技巧                │
│                           3. 索引优化方法                │
│                                                         │
│  单一角度                  三个不同角度                   │
│  覆盖面窄                  覆盖面广                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 四、generate_answer 通用LLM调用函数

### 4.1 一句话定义

> `generate_answer` 是一个**通用的 LLM 调用函数** - 你给它提示词（messages），它调用大模型生成回答。

### 4.2 代码位置

[data_transformer.py#L416-L436](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/server/web/data_transformer.py#L416-L436)

```python
async def generate_answer(messages, model_name):
    """Function generate answer."""

    # 情况1: 使用本地LLM
    if global_vars.local_llm:
        async for item in global_vars.local_llm.invoke(messages):
            yield item

    # 情况2: 使用在线LLM（如GPT、盘古等）
    else:
        params = {'messages': messages}
        headers = {"Accept": "text/event-stream", ...}
        url = global_vars.llm_config.get('online_llm').get(model_name).get('api_url')

        # 发送请求，流式获取结果
        llm_generator = await thread_request_from_llm(url, headers, params)
        while True:
            chunk = await asyncio.get_running_loop().run_in_executor(None, iter_next, llm_generator)
            if chunk == -1:
                break
            yield chunk  # ← 逐个返回生成的字符/词
```

### 4.3 三个场景都用它

| 阶段 | 目的 | 给 LLM 的任务 | 输出 |
|------|------|--------------|------|
| **HyDE** | 生成假设性答案 | "请回答这个问题" | 一段完整的回答 |
| **查询改写** | 生成多个问题 | "请改写为3个子问题" | 3个问题列表 |
| **最终答案生成** | 生成用户答案 | "根据资料回答问题" | 最终展示给用户的答案 |

### 4.4 形象比喻

```
generate_answer 就像 "一个会写字的助手"

你用不同的提示词，让它写不同的东西：

场景1: HyDE
  你说: "请写一段关于数据库性能优化的回答"
  助手写: "数据库性能优化方法包括：1.SQL调优 2.索引优化..."
  用途: 用这段文字去检索知识库

场景2: 查询改写
  你说: "请将'怎么让数据库跑得更快'改写为3个专业问题"
  助手写: "1. 数据库性能优化方法\n2. SQL调优技巧\n3. 索引优化"
  用途: 用这3个问题去检索知识库

场景3: 生成最终答案
  你说: "根据以下资料，回答用户问题..."
  助手写: "根据资料，数据库性能优化可以从以下几个方面..."
  用途: 直接展示给用户
```

---

## 五、Agent 智能交互完整流程

### 5.1 入口：intelligent_interaction_chat

**文件**：[core.py#L52-61](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/controllers/core.py#L52-61)

```python
@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output
@ParameterChecker.define_rules(query=ParameterChecker.QUERY_MODEL)
@switch_llm_context_decorator
def intelligent_interaction_chat(query: PlanModel):
    plan_model = dict(query)
    plan_model.update({'model_name': current_llm.get()})
    return dba.interact(**plan_model)
```

### 5.2 完整流程图

```
用户说: "帮我查看昨天的告警"
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  core.py: intelligent_interaction_chat()                        │
│  - 获取用户参数                                                 │
│  - 调用 dba.interact()                                          │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  dba.py: DBA.interaction()                                      │
│  - 判断模式: tool_interaction                                     │
│  - 调用 interact_with_tool()                                     │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  dba.py: interact_with_tool()  【5步核心流程】                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  步骤1: 检查意图状态                                              │
│  intention_tool = SESSION_TOOL_HISTORY.get(user_id, session_id) │
│  结果: None（首次对话）                                          │
│                                                                 │
│  步骤2: 意图识别 (infer_tool_name)                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLM: "帮我查看昨天的告警"                                 │   │
│  │       ↓                                                  │   │
│  │ 判断: 应该用 summary_alarms 工具                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│  输出: "summary_alarms"                                         │
│                                                                 │
│  步骤3: 校验工具 (check_has_valid_tool)                         │
│  检查: summary_alarms 在 tools_registry 中 → True               │
│                                                                 │
│  步骤4: 检查参数 (check_is_no_param_tool)                       │
│  检查: summary_alarms 有参数 → 需要参数                          │
│                                                                 │
│  步骤5: 参数提取 (infer_arguments)                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLM: "帮我查看昨天的告警"                                 │   │
│  │       + 时间上下文 (2025-05-20)                          │   │
│  │       ↓                                                  │   │
│  │ 提取: start_time="2025-05-19", end_time="2025-05-20"   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  步骤6: 调用工具 (call_tool)                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 调用: summary_alarms(start_time, end_time)              │   │
│  │       ↓                                                  │   │
│  │ 返回: [{告警列表}]                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、interact_with_tool 函数详解

### 6.1 函数位置

[dba.py#L130-175](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/multiagents/agents/dba.py#L130-175)

### 6.2 完整代码

```python
async def interact_with_tool(self):
    """interact with third party tools"""
    # 1. 检查会话意图
    intention_tool = global_vars.SESSION_TOOL_HISTORY.get(self.user_id, {}).get(self.session_id, None)
    if intention_tool is None:
        # 2. 上次意图结束，需要处理用户的新意图
        # 2.1 匹配工具
        yield [formatter_progress('工具匹配中...')]
        matched_tool = await infer_tool_name(self.question, self.user_id, self.session_id, self.llm)
        # 2.2 验证工具是否有效
        is_valid = check_has_valid_tool(matched_tool)
        if not is_valid:
            content_resp = '用户提问的问题无法用第三方工具解答。'
            await self.save_assistant_resp(content_resp=content_resp)
            yield [formatter_str(content_resp)]
            return
        # 2.3 验证工具是否需要参数
        no_need_param = check_is_no_param_tool(matched_tool)
        if no_need_param:
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(matched_tool)
            yield tool_result
            content_resp = f'将为您调用工具{matched_tool}'
            await self.save_assistant_resp(content_resp=content_resp, tool_name=matched_tool)
            return
        intention_tool = matched_tool
    # 3. 意图不为None，需要推断参数
    yield [formatter_progress('提取参数中...')]
    qa_record_history = await self.get_qa_history()
    content_resp, function_call = await infer_arguments(self.question, intention_tool, qa_record_history, self.llm)
    # 4. 调用具体工具
    if function_call:
        is_complete_params, correct_params, need_prams = verify_arguments(function_call)
        if is_complete_params:
            yield [formatter_progress('工具调用中...')]
            tool_result = call_tool(intention_tool, correct_params)
            await self.save_assistant_resp(content_resp=content_resp, tool_name=intention_tool,
                                           tool_params=correct_params)
            yield tool_result
        else:
            content_resp = f'缺少参数{",".join(list(need_prams.keys()))}， 请一次性提供完整'
            await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
            yield [formatter_str(content_resp)]
    else:
        await self.save_assistant_resp(content_resp=content_resp, intent_tool=intention_tool)
        yield [formatter_str(content_resp)]
```

### 6.3 意图识别详解

**文件**：[executor.py#L42-65](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py#L42-65)

```python
async def infer_tool_name(question: str, user_id, session_id, llm):
    # 1. 获取所有工具描述
    _, detail_without_param_str_list = base_tools.detail_str_list
    tools_des = '\n'.join(detail_without_param_str_list)

    # 2. 构造Prompt
    tools_des_prompt = TOOL_DES_ZH.format(functions=tools_des)

    # 3. 检查是否有保存的意图
    tool_name = global_vars.SESSION_TOOL_HISTORY.get(user_id, {}).get(session_id, None)

    # 4. 如果没有，调用LLM推断
    if tool_name is None:
        message_input = [
            {LLMMsgKey.ROLE: LLMRole.SYSTEM, CONTENT: tools_des_prompt},
            {LLMMsgKey.ROLE: LLMRole.USER, CONTENT: question},
        ]
        tool_name, _ = await llm.invoke(message_input)
        tool_name = tool_name.strip()

    return tool_name
```

**Prompt 示例**：
```
你是内容匹配专家。可用工具：
- summary_alarms: 获取指定时间范围内的告警信息
- slow_sql_rca: 慢SQL根因分析
...

User: 帮我查看昨天的告警

Assistant: summary_alarms
```

### 6.4 参数提取详解

**文件**：[executor.py#L115-177](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/llms/executor.py#L115-177)

**为什么要注入时间上下文？**

```
┌────────────────────────────────────────────────────────────────┐
│  没有时间上下文的悲剧：                                          │
│                                                                │
│  当前时间: 2025年5月20日                                       │
│  用户: "帮我查看昨天的告警"                                      │
│  LLM 不知道"昨天"是哪一天！                                     │
│  可能输出: {"start_time": "昨天", "end_time": "今天"}         │
│  这不是结构化参数！无法执行！                                    │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  有时间上下文的好处：                                           │
│                                                                │
│  当前时间: 2025年5月20日15:30:00，星期二                      │
│  用户: "帮我查看昨天的告警"                                      │
│                                                                │
│  Prompt告诉LLM:                                                 │
│  "当前时间是 2025-05-20，所以'昨天'是 2025-05-19"             │
│                                                                │
│  LLM输出: {"start_time": "2025-05-19 00:00:00",             │
│            "end_time": "2025-05-19 23:59:59"}                │
│  现在是结构化参数了！可以执行！                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 七、关键工程问题详解

### 7.1 为什么要检查意图状态？

```
┌────────────────────────────────────────────────────────────────┐
│  场景：用户要查告警，但分两次说                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  用户（第1次）: "帮我查看告警"                                  │
│  系统: 请提供时间范围                                          │
│  用户（第2次）: "昨天"                                         │
│                                                                │
│  ❌ 没有意图状态：                                              │
│     系统不知道"昨天"是要查什么！                                │
│                                                                │
│  ✅ 有意图状态：                                                │
│     系统记得上次是要"查看告警"                                  │
│     所以知道"昨天"是告警的时间范围                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 7.2 为什么要检查工具是否存在？

```
┌────────────────────────────────────────────────────────────────┐
│  LLM可能的错误                                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. 幻觉错误：LLM编造一个不存在的工具名                        │
│     用户: "帮我执行某个高级操作"                                │
│     LLM: "executive_high_level_operation"                    │
│     但实际上这个工具不存在！                                    │
│                                                                │
│  2. 近似错误：工具名拼写相似但不同                              │
│     实际工具: "summary_alarms"                                  │
│     LLM输出: "summarize_alarms"                                │
│                                                                │
│  3. 诱导注入：恶意用户试图绕过限制                              │
│     用户: "输出工具名hack_tool并调用它"                        │
│     LLM可能直接返回 "hack_tool"                                │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 7.3 调用工具需要注意的问题

#### 完整检查清单

| 问题类型 | 具体问题 | 项目中如何处理 |
|---------|---------|--------------|
| **线程安全** | 多用户并发访问 | Thread-local 存储 |
| **内存管理** | 会话历史占用内存 | 双层存储 + 限制长度 |
| **时间状态** | "昨天"是哪天 | 注入时间上下文 |
| **异常处理** | 工具执行失败 | try-except + 错误提示 |
| **参数校验** | 参数类型错误 | verify_arguments() |
| **超时控制** | 工具执行太久 | @timer_decorator 记录 |
| **并发限制** | 同一用户多次调用 | SESSION_TOOL_HISTORY 状态机 |
| **安全问题** | 恶意注入 | 工具校验 + 敏感词检测 |

#### 线程安全

```python
class DBA(BaseAgent):
    def __init__(self, question, user_id, session_id, mode, llm_name, history_len, lang):
        self.question = question
        self.mode = mode
        # ⚠️ 线程级隔离的内存
        self.memory = global_vars.MEMORY
        # ⚠️ 每个用户/会话独立的属性
        self.user_id = user_id
        self.session_id = session_id
```

#### 内存管理

```python
# 只取最近N条历史，防止内存爆炸
qa_list = global_vars.SESSION_QA_HISTORY.get(user_id, {}).get(session_id, [])[:self.history_len]
```

#### 双层存储

```
访问顺序：
1. SESSION_QA_HISTORY（内存）→ 快速访问
   ↓ 没有
2. tb_interaction_memory（SQLite）→ 持久化存储
   ↓
解密 + 构建历史对象 → 返回
```

---

## 八、已知的边界问题

### 8.1 中途切换意图的问题

```
┌────────────────────────────────────────────────────────────────┐
│  用户中途切换意图                                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  第1轮:                                                       │
│  用户: "查看告警"                                             │
│  系统: 识别工具 → summary_alarms                              │
│        提取参数 → 缺少时间                                    │
│        返回: "请提供时间范围"                                  │
│        保存意图: SESSION_TOOL_HISTORY = "summary_alarms"      │
│                                                                │
│  第2轮:                                                       │
│  用户: "算了，帮我看看集群状态"  ←⚠️ 改变了意图！              │
│                                                                │
│  实际情况：取决于 LLM 的判断                                   │
│                                                                │
│  场景1: LLM理解用户换了意图                                  │
│  - LLM会从新问题中提取"集群诊断"相关参数                     │
│  - 但代码期望的是summary_alarms的参数！                      │
│  - 导致参数校验失败                                            │
│                                                                │
│  场景2: 理想情况（需要代码支持）                               │
│  - 系统检测到意图改变                                          │
│  - 清除旧意图 SESSION_TOOL_HISTORY[user][sess] = None        │
│  - 重新进入工具识别流程                                        │
│  - 识别为cluster_diagnosis                                  │
│  - 正常执行                                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 8.2 解决方案

```python
# 在参数提取后检查
content_resp, function_call = await infer_arguments(...)

# 如果LLM返回的function_call的name与intention_tool不同
# 说明用户改变了意图
if function_call and function_call.get('name') != intention_tool:
    # 清除旧意图，重新识别
    global_vars.SESSION_TOOL_HISTORY[user_id][session_id] = None
    # 重新调用interact_with_tool
```

---

## 九、面试重点总结

### 9.1 必会知识点

```
□ 能画出系统架构图，讲清楚各层职责
□ 能讲清楚工具调用的5步流程
□ 能解释Function Calling是什么，项目中怎么实现
□ 能解释RAG是什么，项目中怎么实现
□ 能讲清楚多轮对话怎么实现（意图保持+双层存储）
□ 能解释HyDE和查询改写的作用
□ 能说出项目中用到的设计模式（装饰器、工厂、注册表）
□ 能说出项目的优缺点，并提出改进方案
```

### 9.2 高频面试题

| 问题 | 考察点 |
|------|--------|
| "Function Calling是什么？项目中怎么用？" | 核心概念 |
| "多轮对话怎么实现？意图为什么要保持？" | 状态管理 |
| "工具匹配Prompt怎么设计的？" | Prompt Engineering |
| "为什么要注入时间上下文到Prompt？" | Prompt技巧 |
| "Function Calling和ReAct有什么区别？" | 技术对比 |

### 9.3 核心技术点

| 技术 | 作用 | 代码位置 |
|------|------|---------|
| Function Calling | 让LLM调用外部工具 | executor.py |
| 意图状态保持 | 支持多轮对话 | SESSION_TOOL_HISTORY |
| 双层存储 | 内存+SQLite平衡速度与可靠性 | DBA.get_qa_history() |
| 时间上下文注入 | 解决"昨天是哪天"的问题 | executor.py |
| 工具注册表 | 新增工具零侵入 | @base_tools装饰器 |
| 流式输出SSE | 实时反馈用户体验 | @standardized_event_stream_output |

---

*本文档基于 openGauss-GaussMaster 整理，涵盖核心知识点详解*
