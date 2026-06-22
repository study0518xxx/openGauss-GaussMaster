"""
loader.py — 文档加载与分块
对应 GaussMaster: utils/split_util_md.py + utils/doc_util.py

做了什么：
1. 从 data/ 目录加载 .md 文件
2. 用 LangChain 的 RecursiveCharacterTextSplitter 分块
   - chunk_size=500 对应 GaussMaster 的 PROPER_BLOCK_LENGTH
   - 优先按 ## 和 ### 标题切，再按段落切
"""
import os

# 固定为脚本所在目录下的 data/，不管从哪个目录执行都能找到
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_markdown_files(data_dir: str = None) -> list[dict]:
    """
    加载 data/ 目录下所有 .md 文件
    返回: [{"source": "cpu_tuning.md", "content": "全文..."}, ...]
    """
    if data_dir is None:
        data_dir = DATA_DIR
    
    documents = []
    for filename in os.listdir(data_dir):
        if filename.endswith(".md"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            documents.append({"source": filename, "content": content})
            print(f"  [loader] 加载: {filename} ({len(content)} 字)")
    return documents


def split_documents(documents: list[dict], chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    把每个文档切分成块
    chunk_size=500 对应 GaussMaster 的 PROPER_BLOCK_LENGTH = 500
    overlap=50 保证相邻块有重叠，不会在关键信息处截断
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n## ", "\n### ", "\n", " ", ""],
    )

    all_chunks = []
    for doc in documents:
        chunks = splitter.split_text(doc["content"])
        all_chunks.extend(chunks)
        print(f"  [loader] {doc['source']} → 切成 {len(chunks)} 块")

    print(f"  [loader] 总计: {len(documents)} 个文档 → {len(all_chunks)} 个块")
    return all_chunks


if __name__ == "__main__":
    print("=== 测试 loader ===")
    docs = load_markdown_files()
    chunks = split_documents(docs)
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n--- 块 {i+1} ({len(chunk)} 字) ---")
        print(chunk[:200] + "...")
