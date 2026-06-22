# 第一步：文档加载 + 分块 + 向量化 + 入库 + 检索

## 做了什么

跑通了 GaussMaster 最核心的 RAG 管道的前半段：**从原始文档到可检索的知识库**。

## 涉及的文件

| 文件 | 作用 | 对应 GaussMaster 源码 |
|------|------|---------------------|
| `data/*.md` | 3 份数据库运维文档（CPU、慢SQL、连接管理） | GaussDB 产品文档 |
| `loader.py` | 加载 .md 文件，用 LangChain 切成 500 字的块 | `utils/split_util_md.py` |
| `embedder.py` | 用 BGE-large-zh 把文本转成 1024 维向量 | `utils/retriever_util.py:OnlineEmbedding` |
| `retriever.py` | 向量存入 Chroma，支持相似度搜索 | `gaussdb_vector.py:GaussDB` |

## 核心逻辑

```
data/cpu_tuning.md  ──┐
data/slow_query.md  ──┤
data/connection_mgmt.md ──┘
        │
        ▼
   loader.py
   load_markdown_files() → 读文件内容
   split_documents()     → 按 ## 标题 + 500字切块
        │
        ▼
   embedder.py
   Embedder.embed() → BGE-large-zh → 1024维向量
        │
        ▼
   retriever.py
   index_documents() → 向量 + 文本 → Chroma 持久化
   search()          → 查询向量化 → Chroma 相似度搜索 → Top-3
```

## 和 GaussMaster 的对应

| Demo | GaussMaster | 简化了什么 |
|------|------------|-----------|
| `RecursiveCharacterTextSplitter(chunk_size=500)` | 自研 776 行 `split_util_md.py` | LangChain 的现成分块器，但参数和思路完全一致 |
| `SentenceTransformer("BAAI/bge-large-zh-v1.5")` | HTTP 嵌入服务 `OnlineEmbedding` | 本地跑模型，省了 HTTP 调用的复杂度 |
| `chromadb.PersistentClient` | `psycopg2` + GSDiskANN | Chroma 开箱即用，不需要装数据库 |
| `collection.query(n_results=3)` | `ORDER BY vector <-> '[...]' LIMIT 3` | Chroma 封装了向量检索 SQL |

**核心流程完全一样，换了更轻量的工具而已。**

## 怎么跑

```powershell
cd C:\2026\0703ddl\openGauss-GaussMaster\Demo

# 先单独看分块效果
python loader.py

# 看向量化效果（首次会下载 BGE 模型，约 1.3GB，等几分钟）
python embedder.py

# 完整链路：加载 → 分块 → 向量化 → 入库 → 检索
python retriever.py
```

## 预期输出

```
=== 测试 loader ===
  [loader] 加载: cpu_tuning.md (xxx 字)
  [loader] 加载: slow_query.md (xxx 字)
  [loader] 加载: connection_mgmt.md (xxx 字)
  [loader] cpu_tuning.md → 切成 4 块
  [loader] slow_query.md → 切成 3 块
  [loader] connection_mgmt.md → 切成 3 块
  [loader] 总计: 3 个文档 → 10 个块

=== 测试 retriever 完整链路 ===
  [embedder] 加载模型: BAAI/bge-large-zh-v1.5 ...
  [embedder] 加载完成，维度: 1024
  [retriever] Chroma 已连接，当前块数: 0
  [retriever] 向量化 10 个块 ...
  [retriever] 入库完成，共 10 块

=== 检索测试 ===
  [retriever] 命中1: 距离=0.2345 | CPU 使用率过高诊断...
  [retriever] 命中2: 距离=0.4567 | 当 GaussDB 数据库...
  
检索到 2 个结果:
[1] CPU 使用率过高诊断...
[2] 当 GaussDB 数据库 CPU...
```

## 面试能讲什么

- "我用了 BGE-large-zh，1024 维，和 GaussMaster 一样"
- "分块用了标题驱动的层次化分块，优先按 ## 切，500 字一块"
- "向量数据库用 Chroma，GaussMaster 用 openGauss+GSDiskANN，但检索流程一样"

---

## 详细解释：每个文件到底做了什么

### loader.py 做了什么

**读文件** → `load_markdown_files()` 遍历 `data/` 目录，把每个 `.md` 文件内容读到内存，返回 `[{"source": "cpu_tuning.md", "content": "全文..."}, ...]`。

**切块** → `split_documents()` 用 LangChain 的 `RecursiveCharacterTextSplitter`，按优先级切：

```
separators = ["\n## ", "\n### ", "\n", " ", ""]

切分优先级：
  ① 先找 "## "（二级标题），在这里切
  ② 找不到就找 "### "（三级标题），在这里切
  ③ 找不到就按 "\n"（段落）切
  ④ 最后按 " "（空格）切

切完后每段不超过 500 字（chunk_size=500），相邻段之间重叠 50 字（overlap=50）
```

**结果**：12 个文本块（每块约 500 字，带着完整标题上下文）。

### embedder.py 做了什么

**加载模型** → `SentenceTransformer("BAAI/bge-large-zh-v1.5")`，BAAI 是智源研究院，bge-large-zh 是中文嵌入模型里效果最好的之一。首次运行从 HuggingFace 下载（约 1.3GB），之后缓存本地。

**向量化** → `model.encode(texts, normalize_embeddings=True)`：

```
输入: "CPU 使用率过高诊断指南\n\n## 问题现象\n\n当 GaussDB..."
       ↓ BGE-large-zh 模型
输出: [0.12, -0.34, 0.56, ..., 0.78]  ← 1024 个浮点数

normalize_embeddings=True → 归一化，向量长度变成 1
这样 L2 距离和余弦相似度排序结果一样
```

**为什么是 1024 维**：BGE-large 的模型结构决定的。数字越大向量越"精细"，但计算量也越大。1024 是平衡点。

### retriever.py 做了什么

**初始化** → 连 Chroma（一个本地向量数据库）。`PersistentClient` 会把数据存到 `chroma_db/` 目录，重启不丢。

```python
self.collection = self.client.get_or_create_collection(name="gauss_kb")
```

Chroma 里一个 Collection 就相当于 GaussMaster 里的一张表。这里叫 `gauss_kb`。

**入库** → `index_documents(chunks)`：
```
① 把 12 个文本块批量向量化 → 12 个 1024 维向量
② 每个块生成一个 UUID4 唯一 ID（和 GaussMaster 源码一样用 uuid.uuid4()）
③ collection.add(ids=..., documents=..., embeddings=...)
   文本 + 向量 + ID 一起存进 Chroma
④ Chroma 内部自动建索引（HNSW），加速后续搜索
```

**搜索** → `search(query, topk=3)`：
```
① 用户问题 "CPU 使用率过高怎么办" → embed_query() → 1024 维向量
② collection.query(query_embeddings=[向量], n_results=3)
   Chroma 内部用 HNSW 索引 + 余弦相似度找距离最近的 3 个块
③ 返回 3 个块的文本原文
```

**Chroma 内部怎么算相似度**：
```
库里每个块都有一个 1024 维向量。
查询向量和每个库向量算余弦距离：
  cos(a,b) = a·b / (|a|×|b|)   ← 归一化后 |a|=|b|=1，所以就是点积

余弦越接近 1，距离越近，意思越像。
距离 0.30 = 非常像（命中1）
距离 0.34 = 也挺像（命中2）
距离 0.80 = 不太像
距离 1.00+ = 完全不相关
```

## 你实际跑出来的结果解读

```
[retriever] 命中1: 距离=0.3055 | # CPU 使用率过高诊断指南
  ↑ 最相关！因为问题就是问 CPU，文档标题也正好匹配

[retriever] 命中2: 距离=0.3378 | ### 4. 参数配置不当
  ↑ 也相关！参数配置那段提到了 CPU 相关内容

12 个块 → 搜出 2 个最相关的 → 排序正确
```

**0.30 的距离意味着这两个向量的余弦相似度约为 0.7，属于强相关。**
