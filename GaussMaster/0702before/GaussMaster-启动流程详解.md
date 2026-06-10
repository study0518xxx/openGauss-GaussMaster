# GaussMaster 启动流程详解

## 目录

- [入口文件](#入口文件)
- [启动流程图](#启动流程图)
- [三种启动模式](#三种启动模式)
- [命令行参数解析原理](#命令行参数解析原理)
- [完整启动命令序列](#完整启动命令序列)
- [启动后访问的API](#启动后访问的api)
- [关键组件初始化顺序](#关键组件初始化顺序)

---

## 入口文件

**入口点**: `GaussMaster/startup.py` 的最后几行

```python
# startup.py 第484-486行
if __name__ == "__main__":
    main_process = Main(build_parser())
    main_process.run()
```

---

## 启动流程图

```
┌─────────────────────────────────────────────────────────────┐
│                  python startup.py                            │
│                                                              │
│  1. build_parser() → 解析命令行参数                          │
│                                                              │
│  2. Main(parser).run() → 根据参数执行                        │
└─────────────────────────────────────────────────────────────┘
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
     ┌─────────┐ ┌─────────┐ ┌─────────┐
     │ setup   │ │ start   │ │  stop   │
     │ (配置)  │ │ (启动)  │ │ (停止)  │
     └─────────┘ └─────────┘ └─────────┘
```

---

## 三种启动模式

### 1️⃣ setup - 创建配置目录

```bash
python startup.py service setup -c conf
```

**做什么**：
1. 创建配置目录
2. 复制 `GaussMaster/misc/` 下的配置文件到目标目录
3. 提示用户手动修改配置

**代码逻辑**：

```python
def setup_directory(confpath):
    """create customized conf directory and copy config files to the customized conf directory"""
    if os.path.exists(confpath):
        raise SetupError("Given setup directory already exists.")

    print("请修改配置文件:")
    print(f"  - {confpath}/gaussmaster.conf")
    print(f"  - {confpath}/model_config.yaml")

    # 复制配置文件模板
    shutil.copytree(
        src=constants.MISC_PATH,  # GaussMaster/misc/
        dst=confpath
    )
```

---

### 2️⃣ setup --initialize - 初始化

```bash
echo '{"VECTOR_password": "xxx", "DBMIND_password": "xxx"}' | \
python startup.py service setup -c conf --initialize --initialize_vector_db --initialize_meta_db
```

**做什么**：
1. 加载配置 + 检查密码
2. 初始化向量数据库（导入知识库）
3. 初始化元数据库（创建表结构）

**代码逻辑**：

```python
def check_config_and_initialize_kb(self):
    # 1. 初始化全局配置
    init_global_configs(self.confpath, need_check=True)

    # 2. 初始化 Embedding 模型
    initialize_embedding_model()

    # 3. 初始化向量数据库（知识库）
    if self.args.initialize_vector_db:
        # 导入中文知识库
        gaussdb_zh = get_db_instance(...)
        load_knowledge_base_local("gauss_zh.db", gaussdb_zh)
        # 导入英文知识库
        gaussdb_en = get_db_instance(...)
        load_knowledge_base_local("gauss_en.db", gaussdb_en)

    # 4. 初始化元数据库（SQLite表）
    if self.args.initialize_meta_db:
        create_metadatabase_schema()  # 创建 tb_interaction_memory 等表
```

---

### 3️⃣ start - 启动服务

```bash
python startup.py service start -c conf
```

**做什么**：
1. 加载配置（不检查密码）
2. 初始化日志
3. 初始化 Embedding 模型
4. 初始化 LLM
5. 初始化 Agent
6. 初始化集群信息
7. **启动 Web 服务**（监听端口）

**代码逻辑**：

```python
def start(self):
    # 1. 写 PID 文件（进程ID）
    with open(self.pid_file, 'w') as fp:
        fp.write('%d\n' % os.getpid())

    # 2. 初始化全局配置（不检查密码）
    init_global_configs(self.confpath, need_check=False)

    # 3. 初始化日志
    logging_handler = init_logger_with_config()

    # 4. 初始化 Embedding 模型
    initialize_embedding_model()

    # 5. 初始化 LLM（大模型）
    available_llms = get_all_available_online_llms()
    model_name = global_vars.llm_config.get('model_name')
    update_llm(model_name)

    # 6. 初始化 Agent 组件
    initialize_agent_components()

    # 7. 初始化集群信息（连接 DBMind）
    init_cluster_info()

    # 8. 初始化敏感词检测
    global_vars.DFA_DETECTOR = get_detector()

    # 9. 启动 Web 服务（监听端口）
    web_service_host = configs.get(SECTION_WEB_SERVICE, 'host')
    web_service_port = configs.getint(SECTION_WEB_SERVICE, 'port')
    _http_service.start_listen(web_service_host, web_service_port)
```

---

## 命令行参数解析原理

### 核心：argparse 模块

Python 的 `argparse` 模块用于解析命令行参数。

GaussMaster 的参数解析定义在 [`startup.py#L154-174`](file:///c:/up2026/trae02/openGauss-GaussMaster/GaussMaster/startup.py#L154-174)：

```python
def build_parser():
    """构建命令行参数解析器"""
    # 1. 创建主解析器
    actions = ['setup', 'start', 'stop']
    parser = argparse.ArgumentParser(description=__description__)

    # 添加版本参数 -v / --version
    parser.add_argument('-v', '--version', action='version', version=__version__)

    # 2. 添加子命令解析器
    subparsers = parser.add_subparsers(
        title='available subcommands',
        help="type '<subcommand> -h' for help on a specific subcommand",
        dest='subcommand'  # 存储选择的子命令
    )

    # 3. 创建 'service' 子命令
    parser_service = subparsers.add_parser(
        'service',
        help='send a command to GaussMaster to change the status of the service'
    )

    # 4. service 子命令的参数
    parser_service.add_argument(
        'action',
        choices=actions,  # setup / start / stop
        help='perform an action for service'
    )

    parser_service.add_argument(
        '-c', '--conf',
        type=os.path.realpath,
        metavar='DIRECTORY',
        required=True,  # 必须提供
        help='set the directory of configuration files'
    )

    parser_service.add_argument(
        '--initialize',
        action='store_true',  # 不带值，作为标志
        help='initialize config and database'
    )

    parser_service.add_argument(
        '--initialize_vector_db',
        action='store_true',
        help='initialize vector database, must use with --initialize'
    )

    parser_service.add_argument(
        '--initialize_meta_db',
        action='store_true',
        help='initialize meta database, must use with --initialize'
    )

    return parser
```

---

### 参数解析对应关系

```bash
# 命令格式
python startup.py service setup -c conf --initialize --initialize_vector_db --initialize_meta_db
python startup.py service start -c conf
python startup.py service stop -c conf
```

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           参数解析对应关系                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│  python startup.py   →  启动 Python 脚本                                    │
│          │                                                                  │
│          service    →  subcommand = 'service'                               │
│          │               (子命令，用于服务管理)                                   │
│          │                                                                  │
│          start      →  action = 'start'                                     │
│          │               (操作类型: setup/start/stop)                          │
│          │                                                                  │
│          -c conf   →  conf = '/path/to/conf' (绝对路径)                      │
│          │               (配置文件目录，必须提供)                                │
│          │                                                                  │
│          --initialize  →  initialize = True                                 │
│          │               (初始化标志，不带值)                                  │
│          │                                                                  │
│          --initialize_vector_db  →  initialize_vector_db = True              │
│          │                          (初始化向量数据库)                          │
│          │                                                                  │
│          --initialize_meta_db  →  initialize_meta_db = True                 │
│                                  (初始化元数据库)                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### argparse 参数类型说明

| 参数格式 | 说明 | 示例 |
|---------|------|------|
| `action='store_true'` | 布尔标志，不带值 | `--initialize` |
| `type=os.path.realpath` | 类型转换函数 | `-c conf` → 转为绝对路径 |
| `choices=[...]` | 枚举限制 | `action` 只能是 setup/start/stop |
| `required=True` | 必填参数 | `-c` 必须提供 |
| `metavar='DIRECTORY'` | 帮助信息中的名称 | `-c DIRECTORY` |

---

### 执行流程

```python
# 1. 解析参数
parser = build_parser()
args = parser.parse_args()

# 2. 创建 Main 对象
main_process = Main(args)

# 3. 根据 action 执行对应操作
class Main:
    def run(self):
        if self.args.subcommand == 'service':
            if self.args.action == 'setup':
                if self.args.initialize:
                    self.check_config_and_initialize_kb()
                else:
                    setup_directory(self.confpath)
            elif self.args.action == 'start':
                self.start()
            elif self.args.action == 'stop':
                self.stop()
```

---

### 访问帮助信息

```bash
# 查看所有可用命令
python startup.py -h

# 输出:
# usage: startup.py [-h] [-v] {service} ...
#
# optional arguments:
#   -h, --help       show this help message and exit
#   -v, --version    show program's version number and exit
#
# available subcommands:
#   service          send a command to GaussMaster to change the status of the service

# 查看 service 子命令的帮助
python startup.py service -h

# 输出:
# usage: startup.py service [-h] action -c DIRECTORY
#                   [--initialize] [--initialize_vector_db] [--initialize_meta_db]
#
# positional arguments:
#   action            perform an action for service (setup/start/stop)
#
# optional arguments:
#   -h, --help        show this help message and exit
#   -c, --conf        set the directory of configuration files (required)
#   --initialize       initialize config and database
#   --initialize_vector_db  initialize vector database
#   --initialize_meta_db    initialize meta database
```

---

## 完整启动命令序列

```bash
# Step 1: 创建配置目录
python startup.py service setup -c conf

# Step 2: 修改配置文件
# 编辑 conf/gaussmaster.conf
#   - 配置 VECTOR 向量数据库连接
#   - 配置 DBMIND 服务地址
#   - 配置 WEB_SERVICE 端口
#   - 配置 LOG 日志级别
#
# 编辑 conf/model_config.yaml
#   - 配置 LLM 大模型地址
#   - 配置 Embedding 模型地址
#   - 配置 Reranker 模型地址

# Step 3: 初始化（导入知识库 + 创建表）
echo '{"VECTOR_password": "your_password", "DBMIND_password": "your_password"}' | \
python startup.py service setup -c conf --initialize --initialize_vector_db --initialize_meta_db

# Step 4: 启动服务
python startup.py service start -c conf
```

---

## 启动后访问的 API

服务启动后，Web 服务监听在配置的端口，提供以下 API：

| API 路径 | 方法 | 功能 |
|---------|------|------|
| `/v1/api/ask_gauss` | POST | 智能问答 |
| `/v1/api/clusters/register` | POST | 集群注册 |
| `/v1/api/app/intelligent-interaction` | POST | 智能交互 |
| `/v1/api/clusters` | GET | 获取集群状态 |
| `/v1/api/llms` | GET | 获取可用模型 |
| `/v1/api/llms` | PUT | 切换模型 |
| `/v1/api/serve/knowledge_base/add` | POST | 添加知识库 |

---

## 关键组件初始化顺序

```
┌─────────────────────────────────────────────────────────────┐
│  startup.py (入口)                                            │
│    ↓                                                         │
│  Main.run() → Main.start()                                  │
│    ↓                                                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 1. init_global_configs()     → 加载配置                 │  │
│  │    - gaussmaster.conf                               │  │
│  │    - model_config.yaml                              │  │
│  │    - SSL 证书检查                                    │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 2. init_logger()             → 初始化日志              │  │
│  │    - 多进程安全的日志处理器                            │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 3. initialize_embedding_model() → 加载 Embedding 模型   │  │
│  │    - BGE 向量化模型                                  │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 4. update_llm()              → 加载 LLM                │  │
│  │    - 盘古/ChatGLM/Llama 等                          │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 5. initialize_agent_components() → 初始化 Agent       │  │
│  │    - 注册工具到 tools_registry                        │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 6. init_cluster_info()       → 连接 DBMind           │  │
│  │    - 获取托管的集群列表                               │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 7. get_detector()            → 敏感词检测             │  │
│  │    - DFA 算法检测敏感词                              │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ 8. _http_service.start_listen() → 启动 Web 服务     │  │
│  │    - uvicorn + FastAPI                              │  │
│  │    - 监听端口，等待请求                               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 一句话总结

| 命令 | 作用 |
|------|------|
| `python startup.py service setup -c conf` | 创建配置目录模板 |
| `python startup.py service setup -c conf --initialize` | 初始化（知识库 + 数据库表） |
| `python startup.py service start -c conf` | 启动 Web 服务 |

**参数解析原理**：argparse 模块通过 `add_argument()` 定义参数规则，`parse_args()` 解析后存储在 `args` 对象中，通过 `args.参数名` 访问。

---

*本文档基于 openGauss-GaussMaster v1.0.0*
