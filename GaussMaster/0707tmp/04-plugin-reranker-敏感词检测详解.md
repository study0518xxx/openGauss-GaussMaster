# Plugin、Reranker、敏感词检测详解

## 一、Plugin（插件系统）

### 1.1 目录结构

```
common/plugins/
├── __init__.py
├── param.py          # 工具参数定义
└── registry.py       # 工具注册中心
```

### 1.2 registry.py - 工具注册中心

**Registry = 工具的字典 + 角色分类**

```python
class Registry(dict):
    def __init__(self):
        self._dict = {}  # 所有工具 {tool_name: func}
        self._category = {  # 按角色分类
            'sql_expert': {},
            'storage_expert': {},
            'cluster_expert': {},
            'performance_expert': {},
            'source_expert': {},
            'repairer': {}
        }
```

**核心功能**：

#### ① 工具注册装饰器

```python
def register(self, name, description, param_list, roles):
    def decorator(target):
        # 给工具函数添加元数据
        target.__func_name__ = name
        target.__description__ = description
        target.__param_dict_list__ = [item.to_dict for item in param_list]
        target.__detail_with_param_str__ = detail_str(name, description, param_list)
        target.__detail_without_param_str__ = detail_str(name, description, param_list, False)
        
        # 注册到全局字典
        self._dict[name] = target
        
        # 按角色分类
        for role in roles:
            self._category[role][name] = target
        
        return target
    return decorator
```

#### ② 使用示例

```python
# multiagents/tools/dbmind_interface.py
from GaussMaster.multiagents.tools import base_tools
from GaussMaster.multiagents.config.agent_config import AgentRoles

@base_tools(
    name="index_recommendation",
    description="索引推荐工具",
    params=[Param("schema_name", "模式名", "string", required=True)],
    roles=[AgentRoles.Repairer.name]  # 只有 Repairer 角色可用
)
def index_recommendation(...):
    ...
```

### 1.3 param.py - 工具参数定义

```python
class Param:
    def __init__(self, name, description=None, param_type=None, 
                 default_value=None, required: bool = True):
        self.name = name
        self.description = description
        self.type = param_type
        self.default_value = default_value
        self.required = required
```

**作用**：描述工具的参数信息，用于：
- LLM 理解参数含义
- 参数校验
- 生成工具描述文档

---

## 二、Reranker（重排序）

### 2.1 目录结构

```
common/reranker/
└── base.py
```

### 2.2 BaseReranker 抽象类

```python
class BaseReranker:
    @abstractmethod
    def compute_score(self, pairs: List[List[str]]) -> List[float]:
        """
        计算 query-document 的相关性分数
        
        Args:
            pairs: [[query, doc1], [query, doc2], ...]
        
        Returns:
            [score1, score2, ...]  分数越高越相关
        """
```

### 2.3 重排序在 RAG 中的作用

```
用户提问: "什么是WAL日志？"
    │
    ▼
┌─────────────────────────────────────────┐
│ 多路召回                                │
│ • 向量检索 Top5: [docA, docB, docC]     │
│ • 文本检索 Top5: [docB, docD, docE]     │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 去重合并                                │
│ [docA, docB, docC, docD, docE]          │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 重排序 (Cross-Encoder)                  │
│ pairs = [                                │
│   ["什么是WAL日志？", docA],             │
│   ["什么是WAL日志？", docB],             │
│   ["什么是WAL日志？", docC],             │
│   ...                                    │
│ ]                                        │
│                                          │
│ scores = [0.92, 0.85, 0.78, 0.71, 0.65] │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 按分数排序，取 TopK                       │
│ [docA, docB, docC]                      │
└─────────────────────────────────────────┘
```

### 2.4 为什么需要重排序？

| 检索方式 | 特点 | 局限 |
|---------|------|------|
| 向量检索（Bi-Encoder） | 速度快，独立编码 | 精度有限，query和doc分开编码 |
| 文本检索（BM25） | 精确匹配关键词 | 不理解语义 |
| **重排序（Cross-Encoder）** | **精度高，联合编码** | **速度慢，只能处理少量文档** |

**组合策略**：
- 先用向量+文本快速召回候选集（百级别）
- 再用 Cross-Encoder 精排（十级别）
- 平衡速度和精度

---

## 三、敏感词检测（word_detect.py）

### 3.1 目录结构

```
common/safety/
├── __init__.py
├── data/
│   └── word_list.txt    # 敏感词列表
└── word_detect.py       # DFA 检测引擎
```

### 3.2 DFA（确定性有限自动机）原理

**DFA = 前缀树（Trie）的查找自动化**

```
构建阶段：
敏感词列表: ["暴力", "恐怖主义", "色情"]

        root
       /    \
      暴     色
     /        \
    力         情
   /end       /end
  恐
 /
主
 \
  义
   /end

检测阶段：
输入文本: "反对恐怖主义"
          ↑
          从root开始，逐字符遍历
          
          反 -> 不在第一层，跳过
          对 -> 不在第一层，跳过
          恐 -> 匹配到 "恐"，继续
          主 -> 匹配到 "主"，继续
          义 -> 匹配到 "义"，is_end=True！
          
          发现敏感词: "恐怖主义"
```

### 3.3 代码实现

```python
class SafeDetectorDFA:
    def __init__(self, word_list):
        self.root = dict()
        self.stop_words = set([" ", "&", "!", "@", ...])
        self._build_trie(word_list)
    
    def _build_trie(self, word_list):
        """构建前缀树"""
        for word in word_list:
            node = self.root
            for char in word:
                if char not in node:
                    node[char] = dict()
                node = node[char]
            node['is_end'] = True  # 标记敏感词结尾
    
    def is_unsafe_text(self, text):
        """检测文本是否包含敏感词"""
        for i, char in enumerate(text):
            if char in self.stop_words:
                continue  # 跳过停用词
            
            node = self.root
            j = i
            while j < len(text) and text[j] in node:
                node = node[text[j]]
                if node.get('is_end'):
                    return True  # 发现敏感词！
                j += 1
        
        return False
```

### 3.4 复杂度分析

| 操作 | 时间复杂度 | 空间复杂度 |
|------|-----------|-----------|
| 构建 Trie | O(N × L) | O(N × L) |
| 检测文本 | O(M) | O(1) |

- N = 敏感词数量
- L = 敏感词平均长度
- M = 待检测文本长度

**为什么用 DFA 而不是简单字符串匹配？**

| 方法 | 时间复杂度 | 缺点 |
|------|-----------|------|
| 暴力匹配 | O(N × M × L) | 慢，需要遍历所有敏感词 |
| KMP | O(N × M) | 实现复杂，每个敏感词一个KMP |
| **DFA/Trie** | **O(M)** | **一次遍历文本，与敏感词数量无关** |

### 3.5 停用词处理

```python
STOP_WORDS = [" ", "&", "!", "！", "@", "#", "$", "￥", "*", "^", "%", "?", "？", "<", ">", "《", "》"]
```

**作用**：
- 用户可能在敏感词中插入空格或符号绕过检测
- "暴 力" → 跳过空格 → 匹配 "暴力"
- 提高检测的鲁棒性

---

## 四、面试要点

1. **Registry 的设计模式？**
   - 装饰器模式：`@base_tools()` 给函数添加元数据
   - 注册表模式：集中管理所有工具
   - 访问控制：按角色分类，实现权限控制

2. **Cross-Encoder 和 Bi-Encoder 的区别？**
   - Bi-Encoder：query和doc分别编码，速度快，精度低
   - Cross-Encoder：query和doc拼接后一起编码，速度慢，精度高
   - 组合：Bi-Encoder召回 + Cross-Encoder精排

3. **DFA 敏感词检测的优势？**
   - 时间复杂度 O(M)，与敏感词数量无关
   - 天然支持前缀匹配和停用词跳过
   - 构建一次，多次复用

4. **如何防止用户绕过敏感词检测？**
   - 停用词跳过（空格、符号）
   - 大小写统一
   - 繁简转换
   - 谐音替换（需要更复杂的策略）
