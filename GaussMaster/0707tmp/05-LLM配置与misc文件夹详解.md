# LLM 配置与 misc 文件夹详解

## 一、misc 文件夹

### 1.1 目录结构

```
misc/
├── gaussmaster.conf      # 主配置文件
└── model_config.yaml     # LLM 模型配置
```

**misc = miscellaneous（杂项）**，存放项目的配置文件。

***

## 二、gaussmaster.conf - 主配置文件

### 2.1 配置节说明

```ini
[VECTOR]                    # 数据库连接配置
host =                      # openGauss 服务器 IP
port =                      # 端口
vector_dbname =             # 向量数据库名
metadatabase =              # 元数据库名
user =                      # 用户名
l2_distance_threshold = 0.9 # 向量检索距离阈值
ssl = true                  # 是否启用 SSL
ssl_certfile = (null)       # SSL 证书路径
ssl_keyfile = (null)        # SSL 私钥路径
ssl_ca_file = (null)        # CA 证书路径
ssl_mode = prefer           # SSL 模式

[DBMIND]                    # DBMind 接口配置
api_prefix = http(s)://***/v1/api/  # DBMind API 基础 URL

[WEB-SERVICE]               # Web 服务配置
host =                      # 绑定主机
port =                      # 监听端口

[LOG]                       # 日志配置
maxbytes = 10485760         # 单个日志文件最大 10MB
backupcount = 1             # 备份数量
level = INFO                # 日志级别
log_directory = logs        # 日志目录

[TIMEZONE]                  # 时区配置
tz = UTC+8                  # 默认东八区

[SAFETY]                    # 安全配置
safety_check = false        # 是否启用敏感词检测
```

### 2.2 配置特点

#### ① 密码加密存储

```ini
[VECTOR]
password = Encrypted->U2FsdGVkX1+...  # 加密后的密码
```

- 初始化时 `--initialize` 将明文密码加密
- 运行时 `ReadonlyConfig.get()` 自动解密
- 禁止明文存储密码

#### ② 空值标记

```ini
ssl_certfile = (null)   # 表示空值，不是字符串 "null"
```

- `(null)` 是特殊的空值标记
- 区别于空字符串 `""`
- 区别于未配置（空白）

#### ③ 行内注释

```ini
ssl = true # Using secure protocol by default
```

- `#` 后面是注释
- `ReadonlyConfig` 解析时会自动移除

***

## 三、model\_config.yaml - LLM 模型配置

### 3.1 配置结构

```yaml
# 默认 LLM 模型
model_name: pangu_sigma_unify_plugin_38b

# Embedding 模型（文本向量化）
embedding_model:
  enable: True
  model_name: bge-large-finetune
  api_type: bge-large
  api_url: http://*.*.*.*:*/get_embedding_result

# Reranker 模型（重排序）
reranker_model:
  enable: True
  model_name: bge-reranker-finetune
  api_type: bge-reranker
  api_url: http://*.*.*.*:*/get_reranker_result

# 大语言模型列表
online_llm:
  pangu_sigma_unify_plugin_38b:
    enable: True
    api_type: Pangu
    api_url: http://*.*.*.*:*/chat/completions
    recommended_config:
      temperature: 0.7
      top_p: 1.0
  
  pangu_cloud_sigma_unify_plugin_38b:
    enable: False
    api_type: PanguCloud
    api_url: http://*.*.*.*:*/chat/completions
    recommended_config:
      temperature: 0.7
      top_p: 1.0
  
  Baichuan2-13B-Chat:
    enable: False
    api_type: Baichuan
    api_url: http://*.*.*.*:*/get_qa_baichuan
    recommended_config:
      temperature: 0.7
      top_p: 1.0
  
  chatglm3-6b:
    enable: False
    api_type: Chatglm
    api_url: http://*.*.*.*:*/get_qa_chatglm
    recommended_config:
      temperature: 0.7
      top_p: 1.0
  
  Llama3-8B-Chinese-Chat:
    enable: False
    api_type: Llama3
    api_url: http://*.*.*.*:*/get_llm_result_llama3
    recommended_config:
      temperature: 0.7
      top_p: 1.0
```

### 3.2 模型类型说明

| 模型             | 类型                               | 作用                   |
| -------------- | -------------------------------- | -------------------- |
| **Embedding**  | bge-large-finetune               | 文本向量化（768维）          |
| **Reranker**   | bge-reranker-finetune            | 相关性重排序               |
| **Pangu**      | pangu\_sigma\_unify\_plugin\_38b | 华为盘古大模型（38B参数）       |
| **PanguCloud** | pangu\_cloud\_...                | 华为云盘古服务              |
| **Baichuan**   | Baichuan2-13B-Chat               | 百川大模型（13B参数）         |
| **ChatGLM**    | chatglm3-6b                      | 智谱ChatGLM（6B参数）      |
| **Llama3**     | Llama3-8B-Chinese-Chat           | Meta Llama3中文版（8B参数） |

### 3.3 生成参数说明

```yaml
recommended_config:
  temperature: 0.7    # 温度：控制随机性
  top_p: 1.0          # Top-p：控制多样性
```

| 参数              | 范围         | 作用                       |
| --------------- | ---------- | ------------------------ |
| **temperature** | 0.0 \~ 2.0 | 越低越确定，越高越随机              |
| **top\_p**      | 0.0 \~ 1.0 | 核采样，只从概率累积前 p% 的token中采样 |

**运维场景为什么 temperature=0.7？**

- 太低（0.0）：输出死板，缺乏灵活性
- 太高（>1.0）：输出随机，可能给出错误答案
- 0.7 是平衡：有一定创造性，但不会太离谱

***

## 四、LLM 接入实现

### 4.1 模型注册表

`llms/__init__.py`：

```python
llm_registry = {
    'Pangu': Pangu,
    'PanguCloud': PanguCloud,
    'Baichuan': Baichuan,
    'Chatglm': Chatglm,
    'Llama3': Llama3
}
```

### 4.2 模型实例化

```python
def instantiate_llm(model_name: str):
    llm_config = global_vars.llm_config
    model_params = llm_config.get('online_llm').get(model_name)
    
    model_type = model_params.get('api_type')      # 'Pangu'
    api_url = model_params.get('api_url')          # 'http://...'
    
    llm = llm_registry.get(model_type)(model_name, api_url)
    return llm
```

### 4.3 BaseLLM 抽象类

`llms/base/BaseLLM.py`：

```python
class BaseLLM:
    def __init__(self, model_name, api_url):
        self.model_name = model_name
        self.api_url = api_url
        self.llm_type = None
    
    def invoke(self, message_inputs):
        """调用 LLM API"""
        raise NotImplementedError()
```

### 4.4 具体模型实现

每个模型有自己的 `invoke` 实现，处理不同的 API 格式：

```python
# Pangu.py
class Pangu(BaseLLM):
    def invoke(self, message_inputs):
        # 构造盘古 API 请求格式
        payload = {
            "model": self.model_name,
            "messages": message_inputs,
            "temperature": 0.7,
            "top_p": 1.0
        }
        response = requests.post(self.api_url, json=payload)
        return response.json()["choices"][0]["message"]["content"]

# Chatglm.py
class Chatglm(BaseLLM):
    def invoke(self, message_inputs):
        # 构造 ChatGLM API 请求格式
        ...
```

***

## 五、配置加载流程

```
启动时
    │
    ▼
┌─────────────────────────────────────────┐
│ startup.py                              │
│ 1. 加载 gaussmaster.conf                │
│    → ReadonlyConfig                     │
│    → global_vars.configs                │
│                                         │
│ 2. 加载 model_config.yaml               │
│    → yaml.safe_load()                   │
│    → global_vars.llm_config             │
│    → global_vars.embedding_model        │
│    → global_vars.reranker_model         │
└─────────────────────────────────────────┘
    │
    ▼
运行时
    │
    ├──► 需要 LLM ──► instantiate_llm(model_name)
    │                    └──► 读取 llm_config[model_name]
    │
    ├──► 需要 Embedding ──► embedding_model.query_embedding(text)
    │
    └──► 需要 Reranker ──► reranker_model.compute_score(pairs)
```

***

## 六、面试要点

1. **为什么需要 model\_config.yaml 和 gaussmaster.conf 两个配置文件？**
   - `gaussmaster.conf`：系统级配置（数据库、日志、网络）
   - `model_config.yaml`：AI 模型配置（LLM、Embedding、Reranker）
   - 分离关注点，方便不同角色维护
2. **temperature 和 top\_p 的区别？**
   - temperature：整体调整概率分布的"尖锐程度"
   - top\_p：截断低概率token，只从高概率中采样
   - 可以单独用，也可以组合用
3. **支持多模型的意义？**
   - *fallback：主模型故障时切换到备用模型*
   - A/B测试：对比不同模型效果
   - 成本优化：简单任务用小模型，复杂任务用大模型
4. **Embedding 和 Reranker 为什么单独配置？**
   - 它们是独立服务，可能部署在不同机器
   - 可以独立升级和扩缩容
   - 不同业务可能用不同的 Embedding 模型

