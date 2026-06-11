# Embedding 机制详解

## 1. 一句话解释

**Embedding 将文本转换为数字向量（数字列表），让计算机能"理解"文本语义。**

---

## 2. 架构图

```
┌─────────────────┐     HTTP POST      ┌─────────────────────┐
│   GaussMaster   │ ────────────────►  │   Embedding 服务     │
│                 │   {"query": "..."} │   (如 HuggingFace   │
│ query_embedding │                   │    / 硅基流动 /      │
│ ("如何创建索引") │                   │    自建服务)         │
└─────────────────┘                   └─────────────────────┘
        │                                      │
        │  [0.123, -0.456, ...]  ◄────────────┘
        │  (1024 维向量)
        ▼
```

---

## 3. OnlineEmbedding 类

**位置：** `GaussMaster/utils/retriever_util.py` 第 50-84 行

```python
class OnlineEmbedding():
    """Class representing online embedding"""

    def __init__(self, url, ssl_context):
        self.url = url           # embedding 服务的 URL
        self.ssl_context = ssl_context

    async def query_embedding(self, query):
        """将用户问题转为向量"""
        embedding_list = await self.__embedding(query)
        return embedding_list[0]

    async def __embedding(self, queries):
        """调用外部 embedding 服务"""
        data = {"query": queries}
        # 发送 HTTP POST 请求到 embedding 服务
        embedding_response = session.post(url=self.url, data=json.dumps(data))
        response = embedding_response.json()
        return response  # 返回向量列表
```

---

## 4. 两个项目的区别

| 项目 | embedding 方式 | 特点 |
|------|---------------|------|
| **GaussMaster** | 调用外部 HTTP API | 需要联网，模型强大 |
| **ai_agent_rag_project** | 本地加载模型 / TF-IDF | 可离线，灵活降级 |

---

## 5. ai_agent_rag_project 的 fallback 机制

**位置：** `ai_agent_rag_project/vector_store.py` 第 251-262 行

```python
def _load_embedding_function(self):
    """Load embedding function."""
    import os
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'  # 使用镜像站

    try:
        # 尝试加载 sentence-transformers 模型
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(self.embedding_model)
        return model.encode  # ← 返回 model.encode 函数
    except Exception:
        # 如果失败，使用简单的 TF-IDF fallback
        self._use_simple_embed = True
        return self._simple_embed
```

---

## 6. TF-IDF 原理

```
文本: "数据库 创建 索引"
         │
         ▼
┌─────────────────────────────────────┐
│  词汇表 (vocab)                      │
│  数据库→0, 创建→1, 索引→2, 查询→3   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  向量表示                             │
│  [1, 1, 1, 0, 0, ...]               │
│   ↑    ↑   ↑                        │
│  数据库 创建 索引                      │
└─────────────────────────────────────┘
         │
         ▼
    归一化 → [0.58, 0.58, 0.58, 0, ...]
```

---

## 7. embedding 配置

在 `model_config.yaml` 中指定：

```yaml
embedding_model:
  api_url: http://xxx.xxx.xxx:xxx/embedding  # ← Embedding 服务地址
  model_path: xxx
```

---

## 8. 支持的 embedding 服务

| 服务 | 说明 |
|------|------|
| **HuggingFace** | 免费、开源 |
| **硅基流动** | 国内可用、便宜 |
| **阿里云** | 百炼平台 |
| **自建服务** | 自己部署的 embedding 模型 |

---

## 9. 使用流程

```
用户查询: "如何创建索引"
              │
              ▼
┌─────────────────────────────────────┐
│  embed_query()                      │
│  调用 self._embedding_function([query]) │
└─────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  可能用哪个？        │
    ├─────────────────────┤
    │ model.encode()      │  ← sentence-transformers (高质量)
    │   或              │
    │ _simple_embed()    │  ← TF-IDF fallback (离线可用)
    └─────────────────────┘
              │
              ▼
    返回: [0.123, -0.456, 0.789, ...]
              │
              ▼
    用这个向量去向量数据库搜索相似文档
```

---

## 10. 总结

| 方法 | 作用 |
|------|------|
| `_load_embedding_function()` | 加载模型，返回 `model.encode` 或 `_simple_embed` |
| `_simple_embed()` | TF-IDF 离线备选方案，不需要联网 |
| `embed_documents()` | 为文档列表生成 embedding |
| `embed_query()` | 为单个查询生成 embedding |

**一句话：`__embedding` 就是通过 HTTP POST 请求调用外部的 embedding 服务，把文本转成向量数字。**
