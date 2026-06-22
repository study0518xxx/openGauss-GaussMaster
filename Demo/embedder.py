"""
embedder.py — Embedding 服务封装
对应 GaussMaster: utils/retriever_util.py:OnlineEmbedding

做了什么：
1. 用本地的 sentence-transformers 加载 BGE-large-zh 模型
2. 提供 embed() 批量向量化和 embed_query() 单条向量化
3. 维度 = 1024，和 GaussMaster 完全一致

为什么用本地模型而不是 HTTP 服务：
- GaussMaster 用 HTTP 服务是因为内网多个服务共享
- Demo 只有自己用，本地加载更简单，首次加载慢但后续快
"""
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        """
        加载 BGE-large-zh 模型
        首次运行会下载模型（约 1.3GB），之后缓存到本地
        """
        print(f"  [embedder] 加载模型: {model_name} ...")
        self.model = SentenceTransformer(model_name)
        self.dimension = 1024  # BGE-large 固定 1024 维，和 GaussMaster 一样
        print(f"  [embedder] 加载完成，维度: {self.dimension}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（入库用）"""
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """单条向量化（查询用）"""
        embedding = self.model.encode([query], normalize_embeddings=True)
        return embedding[0].tolist()


if __name__ == "__main__":
    # 测试：向量化一句话看看效果
    print("=== 测试 embedder ===")
    e = Embedder()
    vec = e.embed_query("CPU 使用率过高怎么办")
    print(f"向量维度: {len(vec)}")
    print(f"前5个值: {vec[:5]}")
    print(f"向量长度: {sum(v*v for v in vec)**0.5:.4f} (归一化后应为 1.0)")
