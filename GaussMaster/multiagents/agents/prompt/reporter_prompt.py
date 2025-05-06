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

alarm_desc_prompt = {
    "zh": """
请重新描述下面的告警信息：
{alarm_info}

请注意不要遗漏告警中的任何重要信息。描述模板为如下json格式：
{{
    "AlarmTitle": string, \\\\ 输出告警信息的精简摘要
    "AlarmDate": string, \\\\ 输出告警信息中的开始时间，时间格式为%Y-%m-%d %H:%M:%S，若未检测到时间则默认输出当前时间{time}
    "AlarmDescription": \\\\ 重新输出对告警信息的描述
}}
    """,
    "en": """
Please redescribe the following alarm message:
{alarm_info}

Be careful not to miss any important information in the alarms. The description template is in the following json format:
{{
"AlarmTitle": string, \\\\ Outputs a condensed summary of the alarm information
"AlarmDate" : string, \\\\ output the start time in the alarm message, time format for %Y-%m-%d %H:%M:%S, If no time is detected, the current time {time} is output by default.
"AlarmDescription": \\\\ reprints the description of the alarm message
}}
    """
}

SYSTEM_PROMPT_ROOT_CAUSE = """你是一个极有用的故障根因总结助手，你的任务是根据故障的诊断过程给出该故障最终的根因总结"""
SYSTEM_PROMPT_SOLUTION = """你是一个极有用的数据库运维助手，你的任务是根据故障诊断过程中出现的异常给出对应的解决方案"""
reporter_desc_prompt = {
    "zh": """## 故障信息
{question}

## 诊断过程上下文
{process_str}
注意：上述分析步骤中涉及图展示的内容略过

## 回复规则
{instruction}

## {output_name}
""",
    "en": """
You are a very useful fault root cause summary assistant, can give a short one-sentence summary according to the fault diagnosis process, the summary can clearly describe the cause of the fault.
Now there is a failure {question}, and the analysis is as follows:
{process_str}
Note: The parts of the above analysis steps that involve graphical presentation have been omitted
Please give a one-sentence summary of the above fault and diagnosis process.
    """
}

AUTO_PROMPT = """
## 用户问题
{question}

## 可用的prompt模板类型
{prompt_type}

## 回复样例提示
如模板类型为：
john: 程序员
tony：理发师
other：其他
用户给出的问题为：需要写代码的程序员
则直接输出：john

请跟据用户问题选择合适的prompt类型，直接输出类型名称即可。
"""

LONG_TRANSACTION = {
    'root_cause': """1. 重点分析诊断过程中的异常信息。
2. 输出内容必须展示query、sessionid、wait_status三个关键字段对应值的信息！！
3. 不同事务间可能有直接相互作用，如block_sessionid的值一般对应idle in transaction事务中的某个sessionid，证明该会话对应的query阻塞了该active事务，请你务必记住此相互关系，实现推理！！""",
    'solution': """1. 要求建议尽可能具备实操性，包含真实业务信息。
2. 上下中涉及的查杀select命令你要直接展示，不能忽略。
3. 最后务必附加这一条文字：请注意，这些步骤是基于报告中的信息提出的解决方案建议，实际操作时可能需要考虑用户业务实际情况等深入分析。""",
}

MEM_USAGE_GUIDANCE = {
    'root_cause': """1. 根据诊断过程上下文的信息中的异常场景，提炼出导致故障现象的最底层根本原因，不要给出推理过程
2. 若上下文中没有过异常提示的字眼，此时输出当前获取到的诊断信息有限无法判断故障根因，不要给出过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。
例1. 检测到动态内存，相关的sql语句为xxx，执行pg_terminate_session命令中止会话
例2. 检测到有大量登录失败或连接数上涨，建议查看审计日志找出异常操作
例3. 检测到非数据库内存上升或其他内存上升，建议排查第三方进程或应用
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

CPU_USAGE_GUIDANCE = {
    'root_cause': """1. 根据诊断过程上下文的信息中的异常场景，提炼出导致故障现象的最底层根本原因，不要给出推理过程
2. 若上下文中没有过异常提示的字眼，此时输出当前获取到的诊断信息有限无法判断故障根因，不要给出过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。
例1. 检测到业务压力增大，建议联系业务人员，确定业务是否有变更
例2. 检测到IO时延增大，需要排查是否有业务变更、升级等
例3. 检测到有长事务或慢SQL，建议查杀
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

DISK_USAGE_GUIDANCE = {
    'root_cause': """1. 根据诊断过程上下文的信息中的异常场景，提炼出导致故障现象的最底层根本原因，不要给出推理过程
2. 若上下文中没有过异常提示的字眼，此时输出当前获取到的诊断信息有限无法判断故障根因，不要给出过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。
例1. 检测到表空间异常或存在临时文件，请给出相关详细信息
例2. 检测到xlog异常，请给出什么原因导致xlog堆积
例3. 检测到存在长事务，建议查杀
例4. 检测到存在句柄泄露情况，建议使用“lsof +L1|grep deleted”命令查询是否有已删除文件但是未释放磁盘空间的文件
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

RESPONSE_TIME_GUIDANCE = {
    'root_cause': """1. 首先给出P80P95异常是数据库内核侧原因，还是业务侧原因
2. 根据诊断过程上下文的信息中的异常场景，提炼出导致故障现象的最底层根本原因，不要给出推理过程
3. 若上下文中没有过异常提示的字眼，此时输出当前获取到的诊断信息有限无法判断故障根因，不要给出过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子
例1. 检测到业务侧有异常，可能是业务压力增大，建议联系业务人员，确定业务是否有变更
例2. 检测到存在慢SQL，需要给出具体的慢SQL语句
例3. 检测到数据库配置不优，明确指出哪些参数不优
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

RISK_OPERATION_GUIDANCE = {
    'root_cause': """根据诊断过程上下文中的异常场景进行总结，说明什么指标出现了异常，不要给出推理过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。
例1. 检测到SQL执行错误率异常，建议对SQL命令进行安全性检查，确保没有恶意构造
例2. 检测到用户锁定率和登录频繁出错，建议排查审计日志，找出具体用户。
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

HIGH_IO_GUIDANCE = {
    'root_cause': """根据诊断过程上下文的信息中的异常场景，提炼出哪个磁盘的IO出现了异常，不要给出推理过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。
1. 使用iostat -xm 1 100查看有问题磁盘的IO利用率
2. 查询视图GS_WLM_SESSION_STATISTICS找到top10的线程，使用select pg_terminate_backend(pid);终止会话
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条，如果某检查项正常，请不要进行总结。"""
}

ABNORMAL_NETWORK_GUIDANCE = {
    'root_cause': """根据诊断过程上下文的信息中的异常场景，提炼出从哪个实例到哪个实例的网络出现了什么问题，不要给出推理过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。注意，只对有异常的检查项给出解决方案，不要超过5条，对于没有异常的检查项，不要赘述。
例1. 建议检查IP地址配置是否正确，是否存在管理面IP和业务面IP映射问题
例2. 使用PING x.x.x.x -t命令测试是否存在丢包
例3. 建议排查是否为物理线路故障或设备故障
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

CLUSTER_EXCEPTION_GUIDANCE = {
    'root_cause': """诊断过程上下文中提到的异常即为根因，直接输出即可，不要给出推理过程""",
    'solution': """请结合诊断过程上下文中出现的异常给出解决方案，可以参考如下例子。注意，只对有异常的检查项给出解决方案，不要超过5条，对于没有异常的检查项，不要赘述。
例1. 检测到网络、磁盘等故障，建议先解决物理故障后再重启集群
例2. 检测到dn只读，查看磁盘使用率是否超过80%
例3. 使用cm_ctl stop && cm_ctl start命令重启集群‘
注意，要以诊断过程中出现的异常为准，只对有异常的检查项给出解决方案，不要超过5条。如果某检查项正常，请不要进行总结。"""
}

GENERAL_PROMPT = {
    'root_cause': """1. 根据诊断过程上下文的信息中的异常场景，提炼出导致故障现象的最底层根本原因
2. 软件方面分析到具体哪个SQL导致可算作最底层根本原因
3. 硬件方面分析到具体哪个磁盘、具体网卡可算作根本原因
4. 若上下文中没有过异常提示的字眼，此时输出当前获取到的诊断信息有限无法判断故障根因""",
    'solution': """1. 建议尽可能具备实操性，包含真实业务信息。
2. 当确认根因为SQL导致时可以给出使用SELECT pg_terminate_session(sessionid)命令去查杀特定的会话的建议。
3. 当根因总结没有分析出具体根因，则也不要给出解决方案建议。
3. 最后务必附加这一条文字：请注意，这些步骤是基于报告中的信息提出的解决方案建议，实际操作时可能需要考虑用户业务实际情况等深入分析。"""
}
