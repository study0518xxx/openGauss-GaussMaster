# 第一步：文档加载 + 分块 + 向量化 + 入库 + 检索

## 环境准备

先装依赖（设计文档规定 pip install ≤ 10 个包，这里共 7 个）：

```bash
pip install fastapi uvicorn chromadb langchain-text-splitters openai sentence-transformers python-dotenv
```

| 包 | 用途 |
|----|------|
| `fastapi` + `uvicorn` | Web 服务（第4步用） |
| `chromadb` | 向量数据库（替代 openGauss+GSDiskANN） |
| `langchain-text-splitters` | 文档分块（替代 GaussMaster 自研 776 行分块代码） |
| `openai` | 调 DeepSeek API（兼容 OpenAI 格式） |
| `sentence-transformers` | 本地跑 BGE-large-zh 嵌入模型 |
| `python-dotenv` | 读取 `.env` 配置 |

> `sentence-transformers` 首次运行会自动下载 BGE-large-zh 模型（约 **1.3GB**），需等几分钟。

配置在 `.env` 中（已预填好）：

| 变量 | 值 |
|------|-----|
| `DEEPSEEK_API_KEY` | 已填（兼容 OpenAI 格式的 key） |
| `DEEPSEEK_BASE_URL` | `https://opencode.ai/zen/go/v1` |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` |

---

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
cd C:\up2026\trae02\openGauss-GaussMaster\Demo

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
  [retriever] 清空旧数据 (0 块) ...
  [retriever] 向量化 10 个块 ...
  [retriever] 入库完成，共 10 块

=== 检索测试 ===
  [retriever] 命中1: 距离=0.3055 | # CPU 使用率过高诊断指...
  [retriever] 命中2: 距离=0.3378 | ### 4. 参数配置不当...
  
检索到 2 个结果:
[1] # CPU 使用率过高诊断指南...
[2] ### 4. 参数配置不当...
```

## 面试能讲什么

| 打开哪个文件 | 可以讲什么 |
|------------|----------|
| `loader.py` | "分块用 `RecursiveCharacterTextSplitter`，`separators=["\n## ","\n### ","\n"," "]` 优先按标题切——这叫**标题驱动的层次化分块**，和 GaussMaster 的 `PROPER_BLOCK_LENGTH=500` 完全对应" |
| `embedder.py` | "BGE-large-zh 的 1024 维是 GaussMaster 的 `OnlineEmbedding.get_embedding_dimensions()` 的返回值。`normalize_embeddings=True` 做 L2 归一化，让余弦距离退化成点积，搜索更快" |
| `retriever.py` | "Chroma 内部用 **HNSW 图索引** + **余弦距离**（`hnsw:space=cosine`），GaussMaster 用 openGauss 的 `<->` L2 距离 + GSDiskANN 索引。思路一样：近似最近邻搜索（ANN），只是托管方不同" |
| `retriever.py` → `index_documents()` | "`uuid.uuid4()` 生成唯一 ID——和 GaussMaster 源码完全一致。先清空旧集合再重建，保证幂等" |
| `engine.py` | "`RELEVANCE_THRESHOLD=0.5` 作为距离防护——查'今天天气'这种无关问题，余弦距离会 > 0.6，直接拒答，不会让 LLM 硬编答案" |

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

**结果**：10~12 个文本块（每块约 500 字，带着完整标题上下文）。

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

**为什么是 1024 维**：BGE-large 的模型结构决定的。数字越大向量越"精细"，但计算量也越大。1024 是平衡点（GaussMaster 的 `OnlineEmbedding.get_embedding_dimensions()` 也返回 1024）。

**关键细节**：`normalize_embeddings=True` 做了 L2 归一化（让向量长度 = 1），这样余弦距离退化成点积，Chroma 里 `hnsw:space=cosine` 底层算的就是点积，搜索效率更高。**归一化和不归一化会影响排序结果，必须保持一致。**

### retriever.py 做了什么

**初始化** → 连 Chroma（一个本地向量数据库）。`PersistentClient` 会把数据存到 `chroma_db/` 目录，重启不丢。

```python
self.collection = self.client.get_or_create_collection(name="gauss_kb")
```

Chroma 里一个 Collection 就相当于 GaussMaster 里的一张表。这里叫 `gauss_kb`。

**入库** → `index_documents(chunks)`：
```
① 把 10~12 个文本块批量向量化 → 10~12 个 1024 维向量
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

```python
# retriever.py 里指定了距离度量
self.collection = self.client.get_or_create_collection(
    name="gauss_kb",
    metadata={"hnsw:space": "cosine"}  # ← 余弦距离
)
```

```
库里每个块都有一个 1024 维向量。
查询向量和每个库向量算余弦距离：
  cos(a,b) = a·b / (|a|×|b|)   ← 归一化后 |a|=|b|=1，所以就是点积

余弦距离（0~2）:
  0.00 = 完全一样（理想情况）
  0.30 = 非常像（命中1）
  0.34 = 也挺像（命中2）
  0.50 = 阈值线（engine.py 的 RELEVANCE_THRESHOLD）
  0.80 = 不太像
  1.00+ = 完全不相关
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

### 距离阈值防护（engine.py 里的关键设计）

Chroma 不管用户问什么都会返回 Top-K——但距离暴露了相关性。`engine.py` 里设了 `RELEVANCE_THRESHOLD = 0.5` 做防护：

| 问题 | 最佳距离 | 结果 |
|------|---------|------|
| "CPU 使用率过高怎么办" | ≈ 0.30（和 CPU 文档高度匹配） | ✅ 正常检索，送 LLM |
| "今天天气怎么样" | > 0.60（和库里所有文档都不搭） | ❌ 拒答："未找到相关知识" |

**这就是第一层防护**：不管 LLM 有多强的编造能力，在检索阶段就把无关问题挡掉。GaussMaster 在生产环境还有第二层（LLM 自己判断）、第三层（DFA 敏感词 + XLNet 安全检测）。
