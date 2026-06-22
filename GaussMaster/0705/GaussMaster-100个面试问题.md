# GaussMaster 项目面试问题100题

> 基于 openGauss-GaussMaster 项目源码整理的面试问题集\
> 覆盖：Agent架构、RAG检索、工具调用、上下文管理、数据库运维、安全机制、性能优化等核心模块

***

## 一、项目整体架构（1-8题）

1. **GaussMaster项目的整体定位是什么？它解决的核心问题是什么？**
2. **项目的技术栈组成是什么？（后端框架、数据库、向量存储、LLM接入等）**
3. **项目的模块划分是怎样的？请描述各模块的职责边界。**
4. **GaussMaster与DBMind的关系是什么？两者如何协作？**
5. **项目的配置管理体系是怎样的？ReadonlyConfig的设计意图是什么？**
6. **6 你**
7. **项目的启动流程是怎样的？startup.py的主要职责是什么？**
8. **项目中的常量定义constants.py包含了哪些关键配置？MAX\_PROMPT\_LENGTH为什么是4096\*2？**

***

## 二、Agent架构与设计（9-22题）

1. **BaseAgent的设计意图是什么？为什么当前实现比较轻量？**
2. **DBA类继承自BaseAgent，它的核心职责是什么？与BaseAgent的分工如何？**
3. **AgentRoles枚举定义了哪些角色？各角色的职责分别是什么？**
4. **为什么index\_recommendation工具要限制roles=\[AgentRoles.Repairer.name]？这种设计的意义是什么？**
5. **DBAgent的交互模式有哪些？TOOL\_INTERACTION和FAULT\_DIAGNOSTIC的区别是什么？**
6. **interact函数为什么是异步生成器（async for）？这种设计有什么好处？**
7. **DBA类的初始化参数有哪些？各参数的作用是什么？**
8. **Agent的output\_parser是如何工作的？CustomOutputParser支持哪些解析模式？**
9. **AgentAction和AgentFinish的区别是什么？什么情况下会返回AgentFinish？**
10. **parse\_action、parse\_tool\_name、parse\_params三个方法分别用于什么场景？**
11. **generate\_json函数的作用是什么？为什么要用栈来处理JSON字符串？**
12. **如果LLM返回的JSON格式不合法，output\_parser会如何处理？**
13. **DBA类中的alarm字段是什么类型？它在什么场景下被使用？**
14. **stream\_exception\_catcher装饰器的作用是什么？与exception\_catcher有什么区别？**

***

## 三、多轮对话与上下文管理（23-36题）

1. **SESSION\_TOOL\_HISTORY的数据结构是什么？为什么要用defaultdict(dict)？**
2. **SESSION\_QA\_HISTORY的数据结构是什么？它与SESSION\_TOOL\_HISTORY的区别是什么？**
3. **用户的多轮对话意图是如何保持的？如果用户中途切换需求，Agent如何感知？**
4. **intention\_tool为None和不为None时，DBA分别执行什么逻辑？**
5. **get\_qa\_history方法为什么采用"本地内存优先、数据库回退"的两级策略？**
6. **history\_len参数的作用是什么？默认值为什么是1？**
7. **InteractionMemory表的结构包含哪些字段？各字段的用途是什么？**
8. **qa\_record\_history在infer\_arguments中是如何被使用的？**
9. **add\_to\_local\_memory函数为什么要维护队列长度？超出长度时如何淘汰？**
10. **用户问题中的时间参数（如"今天"、"现在"）是如何被推断的？**
11. **如果用户连续多轮提供参数，Agent如何累积这些参数？**
12. **save\_assistant\_resp方法保存了哪些信息？为什么function\_call要单独处理？**
13. **上下文管理中的加密机制是怎样的？为什么要加密存储问答记录？**
14. **current\_instance上下文变量是如何在多线程环境下保证隔离性的？**

***

## 四、工具调用链路（37-50题）

1. **工具注册机制是怎样的？base\_tools装饰器做了什么？**
2. **tools\_registry的数据结构是什么？工具是如何被注册和发现的？**
3. **infer\_tool\_name的流程是什么？LLM如何根据用户问题匹配工具？**
4. **TOOL\_DES\_ZH和TOOL\_DES\_EN提示词模板的设计要点是什么？**
5. **check\_has\_valid\_tool和check\_is\_no\_param\_tool的区别是什么？**
6. **无参工具（如get\_top\_sqls）和有参工具的调用流程有什么不同？**
7. **infer\_arguments方法如何提取工具参数？qa\_record\_history在其中起什么作用？**
8. **TOOL\_INTERACT\_ZH提示词中的10条规则分别是什么？为什么要这样设计？**
9. **verify\_arguments函数如何校验参数的正确性？它返回的三个值分别是什么？**
10. **has\_correct\_params函数如何处理多余参数和缺失参数？**
11. **call\_tool函数的实现逻辑是什么？它如何根据工具名找到对应的函数？**
12. **validate\_return\_format装饰器的作用是什么？**
13. **工具调用的防循环机制是什么？为什么不会出现"调用-返回-再调用"的死循环？**
14. **如果LLM匹配了一个不存在的工具名，系统会如何处理？**

***

## 五、RAG检索与智能问答（51-68题）

1. **多路召回具体指哪几路？每路召回的技术原理是什么？**
2. **向量检索和文本检索（BM25）的区别是什么？为什么需要两路召回？**
3. **BaseRetriever类的职责是什么？它包含哪些核心方法？**
4. **reranker\_search\_result方法的实现逻辑是什么？如何对召回结果去重？**
5. **OnlineReranker的compute\_score方法是如何工作的？pairs的数据格式是什么？**
6. **重排序时分数小于0的结果为什么被过滤掉？**
7. **AdjacentRetriever的作用是什么？prev\_uuid和next\_uuid解决了什么问题？**
8. **union\_adjacent\_text函数如何实现相邻文本的合并？**
9. **HyDE（假设性文档嵌入）在项目中是如何实现的？**
10. **查询改写（Query Transform）的流程是什么？生成的子查询如何被使用？**
11. **query\_opt\_process方法在什么情况下被触发？它的完整流程是什么？**
12. **search接口的参数校验逻辑有哪些？vector\_topk、text\_topk、rerank\_topk的取值范围是什么？**
13. **ask\_gauss方法的完整流程是什么？从用户提问到答案生成经历了哪些阶段？**
14. **llm\_generation方法的输出格式是什么？为什么包含type字段？**
15. **create\_infer\_prompt和create\_infer\_prompt\_direct的区别是什么？**
16. **get\_history\_chat方法从哪个表获取历史对话？为什么要做语言过滤？**
17. **prompt\_util.py中定义了多少种提示词模板？各用于什么场景？**
18. **INFER\_SYSTEM\_TMPL\_ZH中的"步骤1"和"步骤2"分别做什么判断？**

***

## 六、DBMind接口与数据库运维（69-80题）

1. **dbmind\_request函数的职责是什么？AutoSession的作用是什么？**
2. **DBMind接口的认证机制是怎样的？Token过期后如何自动刷新？**
3. **get\_cluster\_list函数返回的数据格式是什么？如何解析集群拓扑？**
4. **workload\_collection\_call函数如何处理大量SQL结果？limit参数的作用是什么？**
5. **summary\_alarms工具聚合了哪些告警来源？如何处理重复告警？**
6. **filter\_latest\_alarms函数的实现逻辑是什么？为什么只保留同类告警中时间最晚的？**
7. **integrate\_self\_security\_alarms函数的作用是什么？为什么要合并自安全告警？**
8. **metric\_diagnosis工具的输入参数有哪些？METRIC\_DIAGNOSIS\_REASON\_MAP的作用是什么？**
9. **cluster\_diagnosis工具如何区分CN和DN节点？**
10. **get\_metric\_range\_sequence工具如何查询多实例的指标数据？**
11. **index\_recommendation工具的返回结果包含哪些字段？**
12. **slow\_sql\_rca工具的根因分析结果如何格式化输出？**

***

## 七、诊断报告系统（81-88题）

1. **DiagnosticReport表的结构包含哪些核心字段？**
2. **ReasonType枚举定义了哪些故障场景？每种场景的guidance包含什么？**
3. **reporter\_prompt.py中的LONG\_TRANSACTION指导模板有什么特殊要求？**
4. **GENERAL\_PROMPT和特定场景prompt（如CPU\_USAGE\_GUIDANCE）的区别是什么？**
5. **诊断报告的root\_cause和solution\_advice是如何生成的？**
6. **get\_history\_report和diagnostic\_replay分别用于什么场景？**
7. **诊断报告中的cleared字段表示什么？**
8. **batch\_intelligent\_scheduling的功能是什么？它与单个告警诊断有什么区别？**

***

## 八、安全机制（89-94题）

1. **SafeDetectorDFA的实现原理是什么？为什么要用DFA而不是简单的字符串匹配？**
2. **敏感词检测的stop\_word列表包含哪些字符？它们的作用是什么？**
3. **Encryption类的加密方案是什么？part\_a和part\_b分别存储在哪里？**
4. **为什么要用workkey和root\_key两层密钥结构？**
5. **check\_password\_strength函数的判断逻辑是什么？密码强度如何分级？**
6. **safety\_check配置项的作用是什么？开启后会对用户输入做什么检查？**

***

## 九、性能优化与工程实践（95-100题）

1. **timer\_decorator装饰器的作用是什么？它如何区分同步和异步函数？**
2. **ttl\_cache装饰器的实现原理是什么？\_\_time\_salt参数的作用是什么？**
3. **create\_requests\_session中的重试策略是怎样的？MAX\_REQUEST\_RETRIES为什么是3？**
4. **dbmind\_interface.py中的pagesize限制有什么意义？**
5. **ui\_output\_util.py中的down\_sampling函数用于什么场景？**
6. **项目中使用了哪些Python异步编程技术？asyncio和ThreadPoolExecutor分别在什么场景下使用？**

***

## 附录：参考代码路径速查

| 模块      | 核心文件                                               |
| ------- | -------------------------------------------------- |
| Agent核心 | `multiagents/agents/dba.py`                        |
| Agent基类 | `multiagents/agents/base_agent.py`                 |
| 工具注册    | `multiagents/tools/dbmind_interface.py`            |
| 工具执行器   | `llms/executor.py`                                 |
| RAG检索   | `utils/retriever_util.py`                          |
| 问答流程    | `server/web/data_transformer.py`                   |
| 上下文管理   | `server/web/context_manager.py`                    |
| 提示词模板   | `utils/prompt_util.py`                             |
| 安全配置    | `common/security.py`                               |
| 敏感词检测   | `common/safety/word_detect.py`                     |
| 诊断报告    | `common/metadatabase/schema/diagnostic_report.py`  |
| 交互记忆    | `common/metadatabase/schema/interaction_memory.py` |
| 全局变量    | `global_vars.py`                                   |
| 常量定义    | `constants.py`                                     |

