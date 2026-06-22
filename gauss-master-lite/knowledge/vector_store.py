"""
内存向量存储 —— 对标 GaussMaster 的 PostgreSQL + pgvector 方案
用 numpy 实现余弦相似度检索，无需外部数据库
"""

import numpy as np
from typing import Optional


class VectorStore:
    """
    简单的内存向量存储
    
    功能:
    - 存储文本及其向量表示
    - 余弦相似度检索 top_k
    - 阈值过滤
    """

    def __init__(self):
        self.documents: list[dict] = []
        self.embeddings: list[np.ndarray] = []

    def add_document(self, text: str, metadata: Optional[dict] = None, embedding: Optional[np.ndarray] = None):
        """添加文档"""
        self.documents.append({
            "text": text,
            "metadata": metadata or {},
        })
        if embedding is not None:
            self.embeddings.append(embedding)
        else:
            self.embeddings.append(np.array([]))

    def add_documents(self, texts: list[str], metadatas: Optional[list[dict]] = None,
                      embeddings: Optional[list[np.ndarray]] = None):
        """批量添加文档"""
        if metadatas is None:
            metadatas = [{}] * len(texts)
        if embeddings is None:
            embeddings = [np.array([])] * len(texts)

        for text, meta, emb in zip(texts, metadatas, embeddings):
            self.add_document(text, meta, emb)

    def search(self, query_embedding: np.ndarray, top_k: int = 5,
               threshold: float = 0.0) -> list[dict]:
        """
        余弦相似度检索
        返回: [{"text": ..., "metadata": ..., "score": ...}, ...]
        """
        if not self.embeddings:
            return []

        query_vec = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)

        scores = []
        for i, emb in enumerate(self.embeddings):
            if emb.size == 0:
                continue
            emb_norm = emb / (np.linalg.norm(emb) + 1e-10)
            score = float(np.dot(query_vec, emb_norm))
            if score >= threshold:
                scores.append((i, score))

        # 按分数降序
        scores.sort(key=lambda x: x[1], reverse=True)
        scores = scores[:top_k]

        results = []
        for idx, score in scores:
            results.append({
                "text": self.documents[idx]["text"],
                "metadata": self.documents[idx]["metadata"],
                "score": round(score, 4),
            })

        return results

    def count(self) -> int:
        return len(self.documents)

    def clear(self):
        self.documents.clear()
        self.embeddings.clear()


# 全局向量存储实例
kb_store = VectorStore()
