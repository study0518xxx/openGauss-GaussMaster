# common/configs/ 配置文件详解

## 目录结构

```
common/configs/
├── __init__.py
├── base_configurator.py      # 配置基类
├── config_constants.py       # 配置常量
├── configurators.py          # 配置读写实现
├── config_utils.py           # 配置工具函数
└── kb_config.py              # 知识库配置
```

---

## 1. base_configurator.py - 配置基类

定义了配置的抽象接口：

```python
class BaseConfig:
    def get(self, section, option):
        raise NotImplementedError()

    def set(self, section, option, value):
        raise NotImplementedError()
```

**设计意图**：统一配置读写接口，支持不同的配置实现（只读、可更新）。

---

## 2. configurators.py - 配置读写实现

### ReadonlyConfig（运行时只读配置）

```python
class ReadonlyConfig(BaseConfig):
    def __init__(self, filepath):
        # 解析 gaussmaster.conf，移除行内注释
        self._configs = ConfigParser(inline_comment_prefixes='#')
        with open(file=filepath, mode='r', encoding='utf-8') as fp:
            self._configs.read_file(fp)
```

**核心功能**：
- 读取 `gaussmaster.conf` 配置文件
- 自动移除行内注释（`#` 后面的内容）
- 密码自动解密（`Encrypted->` 前缀的密文）

**密码解密逻辑**：
```python
def get(self, section, option, *args, **kwargs):
    value = self._configs.get(section, option, *args, **kwargs)
    
    if 'password' in option and value != '':
        if value.startswith('Encrypted->'):
            real_value = value[len('Encrypted->'):]
            value = Encryption.decrypt(real_value)  # AES256解密
        else:
            raise Exception('密码必须是加密存储的！')
    
    return value
```

### UpdateConfig（初始化时更新配置）

```python
class UpdateConfig(BaseConfig):
    def set(self, section, option, value, inline_comment=''):
        self.config.set(section, option, '%s  # %s' % (value, inline_comment))
```

**使用场景**：`--initialize` 初始化时，将明文密码加密后写回配置文件。

---

## 3. config_constants.py - 配置常量

```python
NULL_TYPE = '(null)'           # 配置中的空值标记
ENCRYPTED_SIGNAL = 'Encrypted->'  # 加密密码前缀

# 配置校验规则
CONFIG_OPTIONS = {
    'LOG-level': ['DEBUG', 'INFO', 'WARNING', 'ERROR']
}
POSITIVE_INTEGER_CONFIG = ['LOG-maxbytes', 'LOG-backupcount']
```

**配置校验函数**：
```python
def check_config_validity(section, option, value, silent=False):
    # 校验端口号范围 (1024-65535)
    # 校验IP地址格式
    # 校验数据库名非空
    # 校验正整数
    # 校验布尔值
    # 校验SSL证书路径
```

---

## 4. config_utils.py - 配置工具函数

```python
def load_sys_configs(confile):
    """加载系统配置"""
    config = ReadonlyConfig(confile)
    config.check_config_validity()
    return config

def save_config_password(config, section, option, password):
    """安全保存密码（加密后存储）"""
    config.set(section, option, 'Encrypted->' + Encryption.encrypt(password))

def has_config_password(config, section, option):
    """检查配置中是否存在密码"""
    # 如果密码未加密，抛出异常（禁止明文存储）
```

---

## 5. kb_config.py - 知识库配置

定义知识库表结构：

```python
KT_TABLE_NAME = "gauss_kb"        # 知识库表
KB_TABLE_NAME = "knowledge_base"   # 通用知识库
DS_TABLE_NAME = "data_source"      # 数据源表
QA_TABLE_NAME = "qa_record"        # QA记录表

# 表字段配置
KT_TABLE_CONFIG = {
    "vector_field": ["text"],           # 向量字段
    "bm25_field": ["text"],             # 全文检索字段
    "text_field": ['uuid', 'title', 'text', 'version', ...]  # 文本字段
}
```

---

## 配置加载流程

```
启动时
    │
    ▼
┌─────────────────────────────┐
│ startup.py                  │
│ load_sys_configs(confile)   │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ ReadonlyConfig              │
│ 1. 读取 gaussmaster.conf    │
│ 2. 移除行内注释             │
│ 3. 校验配置合法性           │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ global_vars.configs         │
│ 全局配置对象                │
│ 各处通过 configs.get() 读取 │
└─────────────────────────────┘
```

---

## 面试要点

1. **为什么密码要加密存储？**
   - 配置文件可能被多人查看，明文密码泄露风险高
   - 使用 AES256-CBC 加密，密钥分存（part_a在数据库，part_b在文件）

2. **ReadonlyConfig 的设计意图？**
   - 运行时不允许修改配置，防止运行时配置漂移
   - 配置修改必须通过初始化流程（`--initialize`）

3. **配置校验有哪些维度？**
   - 端口范围、IP格式、数据库名非空、正整数、布尔值、SSL证书路径
