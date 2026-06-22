"""
peek_chroma.py — 查看 Chroma 向量库里存了什么
"""
import os
import chromadb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chroma_db")

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_collection(name="gauss_kb")

print(f"=== Chroma 数据库内容 ===")
print(f"路径: {DB_PATH}")
print(f"集合名: gauss_kb")
print(f"总块数: {collection.count()}")
print()

# 查看前5条记录
results = collection.get(limit=5, include=["documents", "metadatas", "embeddings"])
has_embeddings = results.get("embeddings") is not None
print(f"取到 {len(results['ids'])} 条记录:")
print()

for i, (id, doc) in enumerate(zip(results["ids"], results["documents"])):
    print(f"--- 块 {i+1} ---")
    print(f"ID: {id}")
    print(f"文本长度: {len(doc)} 字")
    if has_embeddings:
        emb = results["embeddings"][i]
        print(f"向量维度: {len(emb)}")
        print(f"向量前5个值: {[round(v,4) for v in emb[:5]]}")
    print(f"文本前200字: {doc[:200]}...")
    print()
