# GaussMaster 类与函数速查手册

## 快速导航

| 模块 | 核心类 | 行数 |
|------|--------|------|
| [1. startup.py](#1-startuppy---启动入口) | `Main` | 1 |
| [2. executor.py](#2-executorpypy---工具调用执行器) | 多个函数 | 2 |
| [3. dba.py](#3-dba-py---对话入口) | `DBA` | 3 |
| [4. base_agent.py](#4-base_agentpy---agent基类) | `BaseAgent` | 4 |
| [5. dbmind_interface.py](#5-dbmind_interfacepy---工具实现) | 多个装饰器函数 | 5 |
| [6. _service_impl.py](#6-_service_implpy---http服务) | `HttpService` | 6 |
| [7. core.py](#7-corepy---控制器) | 多个路由函数 | 7 |
| [8. BaseLLM.py](#8-basellmpy---llm基类) | `BaseLLM` | 8 |
| [9. 安全与加密](#9-安全与加密) | `Encryption` | 9 |

---

## 1. startup.py - 启动入口

**路径**: `GaussMaster/startup.py`

### Main 类

```python
class Main:
    """服务启动主类"""

    def run(self):
        """入口：根据 subcommand 执行对应操作"""
        if self.args.subcommand == 'service':
            if self.args.action == 'setup':
                # 创建配置目录 或 初始化
            elif self.args.action == 'start':
                self.start()  # 启动服务
            elif self.args.action == 'stop':
                self.stop()   # 停止服务

    def start(self):
        """启动Web服务"""
        # 1. 写PID文件
        # 2. init_global_configs() - 加载配置
        # 3. init_logger() - 初始化日志
        # 4. initialize_embedding_model() - 加载Embedding
        # 5. update_llm() - 加载LLM
        # 6. initialize_agent_components() - 初始化Agent
        # 7. init_cluster_info() - 连接DBMind
        # 8. get_detector() - 敏感词检测
        # 9. _http_service.start_listen() - 启动Web服务
```

| 函数 | 功能 |
|------|------|
| `build_parser()` | 构建命令行参数解析器 |
| `Main.run()` | 根据参数执行 setup/start/stop |
| `Main.start()` | 启动Web服务的完整流程 |

---

## 2. executor.py - 工具调用执行器

**路径**: `GaussMaster/llms/executor.py`

### 核心函数（按调用顺序）

```python
async def infer_tool_name(question, user_id, session_id, llm):
    """
    【步骤1】意图识别
    作用：根据用户问题推断应该使用哪个工具
    返回：工具名称字符串
    """
    # 检查 SESSION_TOOL_HISTORY 是否有未完成的意图
    # 构建 TOOL_DES_ZH prompt
    # 调用 LLM 推断工具名

async def infer_arguments(question, intention_tool, qa_record_history, llm):
    """
    【步骤4】参数提取
    作用：从用户问题中提取工具参数
    返回：(content_resp, function_call)
    """
    # 获取工具的详细描述（带参数）
    # 构建 TOOL_INTERACT_ZH prompt（含时间上下文）
    # 调用 LLM 提取参数

def check_has_valid_tool(tool_name):
    """
    【步骤2】工具校验
    作用：检查工具是否在支持列表中
    返回：True/False
    """

def check_is_no_param_tool(tool_name):
    """
    【步骤3】参数校验
    作用：检查工具是否需要参数
    返回：True（无参）/ False（需要参数）
    """

def verify_arguments(function_call):
    """
    【步骤5前】参数验证
    作用：检查参数是否完整
    返回：(is_complete, correct_params, need_params)
    """

def call_tool(tool_name, params=None):
    """
    【步骤5】工具执行
    作用：调用具体工具函数
    返回：工具执行结果
    """
```

### 关键变量

| 变量 | 类型 | 作用 |
|------|------|------|
| `SESSION_TOOL_HISTORY` | dict | 存储用户会话的意图状态 |
| `global_vars.tools_registry` | dict | 所有注册的工具函数 |

### 完整调用流程

```
interact_with_tool()
   │
   ├── infer_tool_name()          → 获取工具名
   │
   ├── check_has_valid_tool()      → 验证工具存在
   │
   ├── check_is_no_param_tool()   → 检查是否需要参数
   │      │
   │      ├── 无参 → 直接 call_tool()
   │      │
   │      └── 有参 → infer_arguments()
   │                    │
   │                    └── verify_arguments()
   │                          │
   │                          └── call_tool()
```

---

## 3. dba.py - 对话入口

**路径**: `GaussMaster/multiagents/agents/dba.py`

### DBA 类

```python
class DBA(BaseAgent):
    def __init__(self, question, user_id, session_id, mode, llm_name, history_len, lang):
        self.question = question       # 用户问题
        self.mode = mode              # 交互模式
        self.llm = instantiate_llm(llm_name)  # LLM实例
        self.memory = global_vars.MEMORY  # 内存存储
        self.history_len = history_len  # 历史记录长度
        self.lang = lang              # 语言

    async def interaction(self):
        """
        【主入口】对话交互
        生成器模式，支持流式输出
        """
        async for step_output in self.interact_with_tool():
            yield step_output
        yield [DONE_FLAG]

    async def interact_with_tool(self):
        """
        【核心】工具交互流程
        """
        # 1. 检查意图状态
        intention_tool = SESSION_TOOL_HISTORY.get(self.user_id, {}).get(self.session_id)

        if intention_tool is None:
            # 新对话：匹配工具
            matched_tool = await infer_tool_name(self.question, self.user_id, self.session_id, self.llm)
            # 校验工具
            # 检查是否需要参数
            # ...

        # 2. 提取参数
        qa_record_history = await self.get_qa_history()
        content_resp, function_call = await infer_arguments(...)

        # 3. 调用工具
        if is_complete_params:
            tool_result = call_tool(intention_tool, correct_params)
            yield tool_result

    async def get_qa_history(self):
        """
        【记忆】获取对话历史
        两层存储：内存 → SQLite
        """
        # 1. 先从 SESSION_QA_HISTORY（内存）获取
        # 2. 没有则从 SQLite 查询
        # 3. 解密并返回

    async def generate_record_and_save(self, answer, function_call):
        """
        【记忆】保存对话记录
        两层存储：内存 + SQLite（加密）
        """
```

| 函数 | 功能 |
|------|------|
| `DBA.interaction()` | 对话主入口，流式输出 |
| `DBA.interact_with_tool()` | 工具交互核心流程 |
| `DBA.get_qa_history()` | 获取对话历史（双层存储） |
| `DBA.generate_record_and_save()` | 保存对话记录（加密） |

### 快捷场景判断

```python
# 直接调工具的场景（不需要LLM推断）
if self.question in ['当前数据库运行状况', '当前有哪些告警']:
    # 默认查询最近1小时
    tz = adjust_timezone(configs.get('TIMEZONE', 'tz'))
    end_time = datetime.now(tz)
    start_time = end_time - timedelta(minutes=60)
    res = call_tool('summary_alarms', params={...})
    yield res
```

---

## 4. base_agent.py - Agent基类

**路径**: `GaussMaster/multiagents/agents/base_agent.py`

### BaseAgent 类

```python
class BaseAgent(metaclass=ABCMeta):
    """所有Agent的基类"""

    def __init__(self, output_parser=None):
        self.output_parser = output_parser or CustomOutputParser()

    @abstractmethod
    async def interaction(self):
        """抽象方法：子类必须实现"""
        pass
```

| 函数 | 功能 |
|------|------|
| `BaseAgent.interaction()` | 抽象方法，子类必须实现 |
| `output_parser` | 输出解析器 |

### Agent 类型

```python
# 在 prompt/ 目录下有三种Agent
dba_prompt.py      # DBA Agent - 对话交互
reporter_prompt.py # Reporter Agent - 诊断报告
repairer_prompt.py # Repairer Agent - 故障修复
```

---

## 5. dbmind_interface.py - 工具实现

**路径**: `GaussMaster/multiagents/tools/dbmind_interface.py`

### 装饰器注册工具

```python
@base_tools(
    name="summary_alarms",
    description="获取指定时间范围内的告警信息",
    params=[
        Param(name="start_time", description="开始时间", param_type="str"),
        Param(name="end_time", description="结束时间", param_type="str")
    ]
)
@validate_return_format
def summary_alarms(start_time, end_time):
    """工具实现"""
    # 1. 获取集群列表
    # 2. 批量获取告警
    # 3. 格式化输出
    return target

@base_tools(name="cluster_diagnosis", ...)
def cluster_diagnosis(...):
    ...

@base_tools(name="slow_sql_rca", ...)
def slow_sql_rca(query, db_name):
    ...
```

### 可用工具清单

| 工具名 | 功能 | 必要参数 |
|--------|------|---------|
| `summary_alarms` | 告警汇总 | start_time, end_time |
| `cluster_diagnosis` | 集群诊断 | start_time(可选) |
| `slow_sql_rca` | 慢SQL根因分析 | query, db_name |
| `index_recommendation` | 索引推荐 | sql, db_name |
| `risk_analysis` | 风险预测 | metric, warning_hours |
| `metric_diagnosis` | 指标诊断 | metric_name, alarm_cause, start_time, end_time |
| `get_top_sqls` | Top SQL | 无 |
| `get_locking_sql` | 锁等待SQL | 无 |
| `get_instance_status` | 实例状态 | 无 |
| `get_database_info` | 数据库列表 | 无 |
| `get_guc_parameter` | GUC参数 | name |
| `collect_stat_activity_workloads` | 活跃SQL | database |
| `collect_history_statement` | 历史SQL | start_time, end_time |
| `knob_recommendation_details` | 参数推荐 | 无 |
| `memory_check` | 内存检查 | latest_hours(可选) |
| `status_overview` | 状态总览 | 无 |

### 参数装饰器

```python
class Param:
    def __init__(self, name, description, param_type, required=True):
        self.name = name
        self.description = description
        self.param_type = param_type
        self.required = required
```

### 输出格式化函数

```python
from GaussMaster.utils.ui_output_util import (
    formatter_str,       # 字符串
    formatter_table,     # 表格
    formatter_graph,     # 图形（时序数据）
    formatter_alarm,     # 告警
    formatter_list,      # 列表
    formatter_title,     # 标题
)
```

---

## 6. _service_impl.py - HTTP服务

**路径**: `GaussMaster/common/http/_service_impl.py`

### HttpService 类

```python
class HttpService:
    """Web服务封装层"""

    def __init__(self, name=__name__):
        self.app = FastAPI(title=name, ...)
        self._server = None

    def attach(self, func, rule, method, **options):
        """注册路由到FastAPI"""
        self.app.add_api_route(rule, func, method=method, **options)

    def start_listen(self, host, port, ssl_keyfile=None, ...):
        """启动监听"""
        config = uvicorn.Config(self.app, host=host, port=port, ssl=ssl_config)
        self._server = uvicorn.Server(config)
        await self._server.serve()

    def stop_listen(self):
        """停止监听"""
        self._server.shutdown()
```

### 装饰器函数

```python
@decorator
def standardized_api_output(f):
    """统一JSON响应格式 {success: true/false, data/msg: xxx}"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            data = f(*args, **kwargs)
            return JSONResponse(content={'success': True, 'data': data})
        except Exception as e:
            return JSONResponse(content={'success': False, 'msg': 'Internal server error.'})
    return wrapper

@decorator
def standardized_event_stream_output(f):
    """统一SSE流式响应格式"""
    async def wrapper(*args, **kwargs):
        async def standardize_generator():
            async for item in generator:
                yield f"data:{json.dumps({'success': True, 'data': item})}\n\n"
        return StreamingResponse(standardize_generator(), media_type="text/event-stream")
    return wrapper

def request_mapping(rule, method, **kwargs):
    """路由注册装饰器"""
    def decorator(f):
        _RequestMappingTable[(rule, method)] = (f, kwargs)
        return f
    return decorator
```

| 函数 | 功能 |
|------|------|
| `HttpService.start_listen()` | 启动Web服务 |
| `HttpService.stop_listen()` | 停止Web服务 |
| `standardized_api_output` | 统一JSON响应 |
| `standardized_event_stream_output` | 统一SSE流式响应 |
| `request_mapping` | 路由注册 |

---

## 7. core.py - 控制器

**路径**: `GaussMaster/controllers/core.py`

### 路由函数

```python
api_prefix = "/v1/api"

@request_mapping(api_prefix + "/ask_gauss", method='POST', api=True)
@standardized_event_stream_output
def ask_gauss(search_params: SearchParams):
    """智能问答"""
    return data_transformer.ask_gauss(search_params)

@request_mapping(api_prefix + "/clusters/register", method='POST', api=True)
def register_cluster(cluster: Cluster):
    """注册集群"""
    return data_transformer.register_cluster(cluster)

@request_mapping(api_prefix + "/clusters/list", method='GET', api=True)
def list_clusters():
    """列出集群"""
    return data_transformer.list_clusters()

@request_mapping(api_prefix + "/app/intelligent-interaction", method='POST', api=True)
@standardized_event_stream_output
def intelligent_interaction(query_params: QueryParams):
    """智能交互"""
    return data_transformer.intelligent_interaction(query_params)
```

| 路由 | 方法 | 功能 |
|------|------|------|
| `/v1/api/ask_gauss` | POST | 智能问答 |
| `/v1/api/clusters/register` | POST | 注册集群 |
| `/v1/api/clusters/list` | GET | 集群列表 |
| `/v1/api/app/intelligent-interaction` | POST | 智能交互 |

---

## 8. BaseLLM.py - LLM基类

**路径**: `GaussMaster/llms/base/BaseLLM.py`

### BaseLLM 类

```python
class BaseLLM(metaclass=ABCMeta):
    """所有LLM的基类"""

    def __init__(self, model_name, api_key=None):
        self.model_name = model_name
        self.api_key = api_key
        self.llm_type = None

    @abstractmethod
    async def invoke(self, messages):
        """
        抽象方法：调用LLM
        messages: [{role: "system"/"user"/"assistant", content: "..."}]
        返回: (response_text, function_call)
        """
        pass

    async def batch_invoke(self, messages_list):
        """批量调用"""
        tasks = [self.invoke(messages) for messages in messages_list]
        return await asyncio.gather(*tasks)
```

### LLM子类

| 类 | 模型 | 文件 |
|---|------|------|
| `Pangu` | 盘古 | `llms/Pangu.py` |
| `PanguCloud` | 盘古云 | `llms/pangu_cloud.py` |
| `Chatglm` | ChatGLM | `llms/Chatglm.py` |
| `Llama` | Llama | `llms/Llama.py` |
| `Baichuan` | 百川 | `llms/Baichuan.py` |

---

## 9. 安全与加密

### Encryption 类

**路径**: `GaussMaster/common/security.py`

```python
class Encryption:
    @staticmethod
    def encrypt(plain_text: str) -> str:
        """AES256-CBC 加密"""
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return base64.b64encode(ciphertext).decode()

    @staticmethod
    def decrypt(cipher_text: str) -> str:
        """AES256-CBC 解密"""
        ...
```

| 函数 | 功能 |
|------|------|
| `Encryption.encrypt()` | AES256-CBC 加密 |
| `Encryption.decrypt()` | AES256-CBC 解密 |

### 加密存储位置

```python
# dba.py - 对话记录加密
question=Encryption.encrypt(qa_record.question)
answer=Encryption.encrypt(qa_record.answer)
function_call=Encryption.encrypt(qa_record.function_call)

# startup.py - 密码加密存储
save_config_password(config, section, option, password)
```

---

## 10. 全局变量

**路径**: `GaussMaster/global_vars.py`

```python
# 全局变量定义
MEMORY = {}                      # 对话历史（内存）
SESSION_TOOL_HISTORY = {}        # 意图状态
tools_registry = {}               # 工具注册表
embedding_model = None           # Embedding模型
llm_config = {}                   # LLM配置
llm_instance = None               # LLM实例
DFA_DETECTOR = None              # 敏感词检测器
configs = None                    # 系统配置
```

---

## 11. Prompt模板

**路径**: `GaussMaster/llms/prompt.py`

```python
# 工具匹配Prompt
TOOL_DES_ZH = """你是一名丰富经验的内容匹配专家...
{functions}...
"""

# 工具交互Prompt（含参数提取）
TOOL_INTERACT_ZH = """你是一个极有帮助的数据库智能运维助手...
时间设定：今年{year}年，今天{date}，当前时间{current}，{weekday}...
{functions}...
"""

# 输出格式
FORMAT_INSTRUCTIONS = """**Option 1:** Use this if you want the human to use a tool...
**Option #2:** Use this if you want to respond directly...
"""
```

---

## 12. 元数据库操作

### DAO 层

**路径**: `GaussMaster/common/metadatabase/dao/`

| 文件 | 函数 | 功能 |
|------|------|------|
| `dao_interaction_memory.py` | `insert_interaction_memory()` | 插入对话记录 |
| `dao_interaction_memory.py` | `select_interaction_memory()` | 查询对话记录 |
| `clusters.py` | `insert_cluster()` | 插入集群 |
| `clusters.py` | `select_clusters()` | 查询集群 |
| `clusters.py` | `delete_cluster()` | 删除集群 |

### Schema 定义

**路径**: `GaussMaster/common/metadatabase/schema/`

```python
class InteractionMemory(ResultDbBase):
    qa_record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(64), nullable=False)
    question = Column(TEXT, nullable=False)
    answer = Column(TEXT, nullable=True)
    llm_name = Column(String(64), nullable=True)
    function_call = Column(TEXT, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class ManagedCluster(ResultDbBase):
    cluster_id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_name = Column(String(120), nullable=False)
    host = Column(String(64), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(TEXT, nullable=False)
    password = Column(TEXT, nullable=False)
```

---

## 13. 快速调用链路

### 智能问答完整链路

```
用户请求 → ask_gauss() [core.py]
    ↓
data_transformer.ask_gauss() [data_transformer.py]
    ↓
DBA.interaction() [dba.py]
    ↓
DBA.interact_with_tool()
    ↓
├── infer_tool_name() [executor.py]  ← 意图识别
├── check_has_valid_tool()           ← 工具校验
├── check_is_no_param_tool()         ← 参数校验
├── infer_arguments() [executor.py]  ← 参数提取
├── verify_arguments()               ← 参数验证
└── call_tool() [executor.py]       ← 工具执行
    ↓
工具函数（summary_alarms等）[dbmind_interface.py]
    ↓
格式化输出（formatter_xxx）[ui_output_util.py]
    ↓
流式返回给用户
```

### 启动完整链路

```
python startup.py
    ↓
Main.run() [startup.py]
    ↓
Main.start()
    ↓
init_global_configs()      → 加载配置
init_logger()             → 初始化日志
initialize_embedding_model() → 加载Embedding
update_llm()              → 加载LLM
initialize_agent_components() → 注册工具
init_cluster_info()       → 连接DBMind
get_detector()            → 敏感词检测
_http_service.start_listen() → 启动Web
    ↓
HttpService.start_listen() [_service_impl.py]
    ↓
uvicorn Server 监听端口
```

---

## 14. 关键配置

### gaussmaster.conf

```ini
[VECTOR]
host = <向量数据库地址>
port = <端口>
database = <数据库名>

[DBMIND]
api_prefix = https://<dbmind地址>

[WEB-SERVICE]
host = 0.0.0.0
port = <端口>
ssl = true

[LOG]
level = INFO
```

### model_config.yaml

```yaml
model_name: pangu_sigma_unify_plugin_38b

embedding_model:
  api_url: http://<embedding服务>
  model_path: <模型路径>

online_llm:
  pangu_sigma_unify_plugin_38b:
    enable: True
    api_type: Pangu
    api_url: http://<pangu服务>
```

---

## 15. 一页纸总结

```
┌─────────────────────────────────────────────────────────────┐
│                      快速学习路径                            │
├─────────────────────────────────────────────────────────────┤
│ 1. startup.py          → 启动入口，了解启动流程              │
│ 2. executor.py          → 工具调用5步，核心逻辑              │
│ 3. dba.py               → 对话入口，多轮记忆                 │
│ 4. dbmind_interface.py  → 工具实现，会用装饰器              │
│ 5. _service_impl.py     → HTTP封装，会用装饰器              │
│ 6. core.py              → 路由定义，API入口                 │
│ 7. BaseLLM.py           → LLM基类，了解多态                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      核心概念                                │
├─────────────────────────────────────────────────────────────┤
│ 工具调用：装饰器注册 → 意图识别 → 参数提取 → 工具执行          │
│ 多轮记忆：内存SESSION_QA_HISTORY + SQLite                   │
│ 流式输出：SSE + generator yield                              │
│ 加密：AES256-CBC，敏感信息加密存储                           │
└─────────────────────────────────────────────────────────────┘
```

---

*本文档用于快速学习 GaussMaster 项目，基于 v1.0.0*
