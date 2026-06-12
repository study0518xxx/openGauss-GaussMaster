# GaussMaster 核心知识点补充总结

## 目录

1. [tools_registry 空字典原因](#1-tools_registry-空字典原因)
2. [工具函数实现与开源 openGauss 兼容性](#2-工具函数实现与开源-opengauss-兼容性)
3. [项目开源性分析](#3-项目开源性分析)
4. [意图识别机制详解](#4-意图识别机制详解)

---

## 1. tools_registry 空字典原因

### 1.1 现象描述

在 `global_vars.py` 中，`tools_registry` 初始化为空字典：

```python
tools_registry = {}
```

### 1.2 设计原理

这是一种**延迟注册模式**，工具不会在程序启动时立即加载，而是通过**装饰器**在运行时自动注册。

### 1.3 注册机制

工具注册通过 `@base_tools` 装饰器实现：

```python
@base_tools(
    name="summary_alarms",
    description="获取指定时间范围内的告警信息",
    params=[Param(name="start_time", description="开始时间")]
)
def summary_alarms(start_time, end_time):
    """获取告警摘要"""
    ...
```

### 1.4 注册时机

| 阶段 | 状态 | 说明 |
|------|------|------|
| 程序启动 | `tools_registry = {}` | 空字典初始化 |
| 模块导入 | 装饰器执行 | `@base_tools` 自动注册工具 |
| 运行时 | 工具可用 | `tools_registry['summary_alarms']` 可调用 |

### 1.5 设计优势

| 优势 | 说明 |
|------|------|
| 延迟加载 | 工具可能依赖其他模块，需要等依赖加载完成 |
| 模块化 | 工具定义与注册分离，便于维护 |
| 扩展性 | 新增工具只需添加装饰器，无需修改注册代码 |

---

## 2. 工具函数实现与开源 openGauss 兼容性

### 2.1 当前工具实现方式

当前工具函数通过调用 **DBMind 监控系统的 API** 实现：

```python
@base_tools(name="get_locking_sql")
def get_locking_sql():
    url = "summary/sql/locking"  # DBMind API 端点
    response = dbmind_request("get", url)
    ...
```

### 2.2 开源 openGauss 可行性

**完全可行！** 但需要修改工具函数，使其直接连接 openGauss 数据库。

### 2.3 两种方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **DBMind API** | 开箱即用，监控功能完善 | 需要部署 DBMind | 生产环境、企业级监控 |
| **直连 openGauss** | 轻量级，无需额外服务 | 需要自己实现监控逻辑 | 开发测试、学习研究 |

### 2.4 直连 openGauss 的实现示例

```python
@base_tools(name="get_locking_sql")
def get_locking_sql():
    """直接从 openGauss 查询锁等待信息"""
    sql = """
        SELECT datname, query, pid as sessionid, query_start 
        FROM pg_stat_activity 
        WHERE wait_event_type = 'Lock' 
        ORDER BY query_start;
    """
    result = execute_sql(sql)
    return formatter_table(
        headers=["datname", "query", "sessionid", "query_start"],
        rows=result
    )
```

### 2.5 需要查询的系统视图

| 工具功能 | openGauss 系统视图 |
|----------|-------------------|
| 获取锁等待 | `pg_locks` + `pg_stat_activity` |
| 获取慢 SQL | `pg_stat_statements` |
| 获取数据库列表 | `pg_database` |
| 获取实例状态 | `pg_stat_replication` |
| 获取参数配置 | `pg_settings` |

---

## 3. 项目开源性分析

### 3.1 许可证信息

项目采用 **Mulan PSL v2** 开源许可证：

```python
# openGauss is licensed under Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
# http://license.coscl.org.cn/MulanPSL2
```

Mulan PSL v2 是一个宽松的开源许可证，允许任何人使用、修改和分发代码。

### 3.2 非华为员工运行可行性

**完全可以运行！** 但需要以下修改：

#### 必须修改的配置

```yaml
# model_config.yaml - 当前配置（内部占位符）
api_url: http://*.*.*.*:*/chat/completions  # 需要替换为实际地址
```

#### 需要部署的组件

| 组件 | 当前配置 | 外部用户方案 |
|------|----------|-------------|
| **LLM** | 盘古大模型（内部） | 替换为 Llama/ChatGLM/Qwen 等开源模型 |
| **Embedding** | 内部服务 | 部署 BGE/Sentence-BERT |
| **Reranker** | 内部服务 | 部署 BGE-Reranker |
| **DBMind** | 内部监控系统 | 可选：部署 DBMind 或修改工具函数直连数据库 |

### 3.3 部署步骤

```bash
# 1. 克隆代码
git clone https://github.com/opengauss-mirror/openGauss-GaussMaster

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建配置目录
python startup.py service setup -c /path/to/conf

# 4. 修改配置文件
# - 修改 gaussmaster.conf 中的数据库连接
# - 修改 model_config.yaml 中的 LLM/Embedding/Reranker 地址

# 5. 初始化知识库和元数据库
python startup.py service setup -c /path/to/conf --initialize --initialize_vector_db --initialize_meta_db

# 6. 启动服务
python startup.py service start -c /path/to/conf
```

### 3.4 总结

| 问题 | 答案 |
|------|------|
| **是否开源？** | ✅ 是，Mulan PSL v2 许可证 |
| **外部能否运行？** | ✅ 可以，需要修改配置 |
| **主要障碍？** | 需要部署 LLM/Embedding/Reranker 服务 |
| **是否需要华为内部资源？** | ❌ 不需要，可替换为开源组件 |

---

## 4. 意图识别机制详解

### 4.1 核心概念

意图识别是让**大语言模型根据用户问题选择最合适工具**的过程，支持多轮对话中的意图保持。

### 4.2 会话状态检查

```python
intention_tool = global_vars.SESSION_TOOL_HISTORY.get(self.user_id, {}).get(self.session_id, None)
```

| `intention_tool` 值 | 含义 | 后续流程 |
|---------------------|------|---------|
| `None` | 首次提问或上一意图已完成 | 需要重新匹配工具 |
| 工具名称 | 正在进行中的工具调用 | 跳过匹配，直接参数提取 |

### 4.3 工具匹配流程（infer_tool_name）

```python
async def infer_tool_name(question: str, user_id, session_id, llm):
    # 1. 获取所有工具描述
    _, detail_without_param_str_list = base_tools.detail_str_list
    tools_des = '\n'.join(detail_without_param_str_list)
    
    # 2. 构建意图识别 Prompt
    tools_des_prompt = TOOL_DES_ZH.format(functions=tools_des)
    
    # 3. 调用 LLM 推断工具名
    message_input = [
        {"role": "system", "content": tools_des_prompt},
        {"role": "user", "content": question},
    ]
    tool_name, _ = await llm.invoke(message_input)
    return tool_name.strip()
```

### 4.4 核心 Prompt（TOOL_DES_ZH）

```python
TOOL_DES_ZH = """你是一名丰富经验的内容匹配专家。
可用的第三方工具名称以及描述如下：
{functions}

你的目标是：根据用户的问题，在第三方的工具中找到解决该问题最相关的工具。

你需要严格遵守的规则是：
1. 工具名应该是英文字母和下划线的组合，请你直接输出最相关的工具名
2. 不可输出不存在的工具名
3. 如果用户提问的问题与工具的描述都不相关，输出：'无法解答'
"""
```

### 4.5 意图保持机制

**SESSION_TOOL_HISTORY** 数据结构：

```python
SESSION_TOOL_HISTORY = {
    "user_001": {
        "session_abc": "summary_alarms"  # 当前正在进行的工具调用
    }
}
```

**支持多轮参数补充**：

```
用户1: "帮我查看告警"           → 匹配工具: summary_alarms
系统: "请提供时间范围"
用户2: "昨天"                  → 直接进入参数提取（跳过工具匹配）
系统: 调用工具获取结果
```

### 4.6 完整流程图

```
用户提问："帮我查看昨天的告警"
        │
        ▼
检查 SESSION_TOOL_HISTORY → intention_tool = None?
        │
        ├── YES → 调用 infer_tool_name()
        │           │
        │           ▼
        │       获取工具描述列表
        │           │
        │           ▼
        │       构建 Prompt → 调用 LLM
        │           │
        │           ▼
        │       LLM 返回: "summary_alarms"
        │
        └── NO → 直接进入参数提取
```

---

## 总结

| 知识点 | 核心内容 |
|--------|----------|
| **tools_registry** | 延迟注册模式，通过装饰器自动注册 |
| **工具实现** | 当前依赖 DBMind，可修改为直连 openGauss |
| **开源性** | Mulan PSL v2 许可证，外部用户完全可运行 |
| **意图识别** | 基于 LLM 的工具匹配，支持多轮对话意图保持 |

---

*生成时间：2026年6月12日*