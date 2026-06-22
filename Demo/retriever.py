"""
retriever.py — 向量检索（Chroma）
对应 GaussMaster: 
  utils/retriever_util.py:BaseRetriever
  common/metadatabase/dao/gaussdb_vector.py:GaussDB

做了什么：
1. 用 Chroma 作为向量数据库（GaussMaster 用 openGauss+GSDiskANN）
2. index_documents(): 把文档块向量化后存入 Chroma
3. search(): 用户问题向量化 → Chroma 相似度检索 → 返回 Top-K 文本
"""
import os
import uuid
import chromadb
from embedder import Embedder

# 固定路径，不管从哪个目录执行都能找到
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Retriever:
    def __init__(self, embedder: Embedder, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(BASE_DIR, "chroma_db")
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="gauss_kb",
            metadata={"hnsw:space": "cosine"}
        )
        print(f"  [retriever] Chroma 已连接，当前块数: {self.collection.count()}")

    def index_documents(self, chunks: list[str]):
        """
        文档块入库：向量化 → 存入 Chroma
        每块生成一个 UUID4 作为 ID，对应 GaussMaster 的 uuid.uuid4()

        如果集合已有数据，先清空再重建（避免重复）
        """
        if self.collection.count() > 0:
            print(f"  [retriever] 清空旧数据 ({self.collection.count()} 块) ...")
            # 删掉旧集合，建新的
            self.client.delete_collection("gauss_kb")
            self.collection = self.client.get_or_create_collection(
                name="gauss_kb",
                metadata={"hnsw:space": "cosine"}
            )

        print(f"  [retriever] 向量化 {len(chunks)} 个块 ...")
        embeddings = self.embedder.embed(chunks)  # 批量向量化
        ids = [str(uuid.uuid4()) for _ in chunks]  # UUID4 唯一 ID

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
        )
        print(f"  [retriever] 入库完成，共 {self.collection.count()} 块")

    def search(self, query: str, topk: int = 3, return_distances: bool = False):
        """
        向量检索：查询向量化 → Chroma 相似度搜索 → 返回 Top-K 文本
        
        参数:
          return_distances=True → 返回 (文本列表, 距离列表)
          return_distances=False→ 只返回文本列表（保持向后兼容）
        """
        query_embedding = self.embedder.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=topk,
        )
        docs = results["documents"][0]
        distances = results.get("distances", [[0]] * len(docs))[0]

        for i, (doc, dist) in enumerate(zip(docs, distances)):
            print(f"  [retriever] 命中{i+1}: 距离={dist:.4f} | {doc[:80]}...")

        if return_distances:
            return docs, distances
        return docs


if __name__ == "__main__":
    # 测试：完整链路 加载→分块→向量化→检索
    from loader import load_markdown_files, split_documents

    print("=== 测试 retriever 完整链路 ===")
    e = Embedder()
    r = Retriever(e)

    docs = load_markdown_files()
    chunks = split_documents(docs)
    r.index_documents(chunks)

    print("\n=== 检索测试 ===")
    result = r.search("CPU 使用率过高怎么办", topk=2)
    print(f"\n检索到 {len(result)} 个结果:")
    for i, doc in enumerate(result):
        print(f"[{i+1}] {doc[:150]}...")
