# -*- coding: utf-8 -*-
"""[v1.1] RAG Vector Database Builder - 电力拓扑知识库"""
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions

# 配置
DB_DIR = "output/rag_vector_db"
KB_ROOT = Path(r"E:\项目大全\电力拓扑图修正\权威本地数据库")
CHUNK_SIZE = 512

print("[1/5] Initializing ChromaDB...", flush=True)
ef = embedding_functions.ONNXMiniLM_L6_V2()
client = chromadb.PersistentClient(path=DB_DIR)

try:
    client.delete_collection("power_topology_kb")
except:
    pass

collection = client.create_collection(
    name="power_topology_kb",
    metadata={"description": "电力拓扑异常检测知识库", "version": "v1.1"},
    embedding_function=ef
)
print(f"    Collection: {collection.name}", flush=True)


def load_text_file(path: Path) -> str:
    """加载文本文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except:
            continue
    return ""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> List[str]:
    """文本分块"""
    if len(text) < 100:
        return []
    
    # 按段落分割
    paragraphs = text.replace('\r\n', '\n').split('\n\n')
    chunks = []
    current = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) < chunk_size * 2:
            current += " " + para if current else para
        else:
            if current.strip() and len(current.strip()) > 50:
                chunks.append(current.strip())
            current = para
    
    if current.strip() and len(current.strip()) > 50:
        chunks.append(current.strip())
    
    return chunks


def process_directory(dir_path: Path) -> List[Dict[str, Any]]:
    """处理目录"""
    documents = []
    patterns = ['*.txt', '*.md', '*.json', '*.csv']
    seen_ids = set()
    
    for pattern in patterns:
        for file in dir_path.rglob(pattern):
            if any(x in str(file) for x in ['node_modules', '__pycache__', '.git']):
                continue
            content = load_text_file(file)
            if not content or len(content) < 100:
                continue
            
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                # 生成唯一ID
                uid = f"{file.stem}_{i}_{uuid.uuid4().hex[:8]}"
                while uid in seen_ids:
                    uid = f"{file.stem}_{i}_{uuid.uuid4().hex[:8]}"
                seen_ids.add(uid)
                
                documents.append({
                    "id": uid,
                    "text": chunk[:2000],  # 限制长度
                    "metadata": {
                        "source": str(file.relative_to(KB_ROOT.parent)),
                        "category": file.parent.name,
                        "file": file.name[:100]
                    }
                })
    
    return documents


print("[2/5] Scanning knowledge base...", flush=True)
all_docs = []
kb_roots = [KB_ROOT]

for kb_root in kb_roots:
    if kb_root.exists():
        docs = process_directory(kb_root)
        all_docs.extend(docs)
        print(f"    {kb_root.name}: {len(docs)} chunks", flush=True)

print(f"    Total: {len(all_docs)} chunks", flush=True)

if not all_docs:
    print("[ERROR] No documents found!", flush=True)
    exit(1)

print("[3/5] Generating embeddings...", flush=True)
ids = [d["id"] for d in all_docs]
texts = [d["text"] for d in all_docs]
metadatas = [d["metadata"] for d in all_docs]

batch_size = 50
for i in range(0, len(ids), batch_size):
    batch_ids = ids[i:i+batch_size]
    batch_texts = texts[i:i+batch_size]
    batch_metas = metadatas[i:i+batch_size]
    collection.add(ids=batch_ids, documents=batch_texts, metadatas=batch_metas)
    print(f"    {min(i+batch_size, len(ids))}/{len(ids)}", flush=True)

print("[4/5] Testing query...", flush=True)
results = collection.query(
    query_texts=["配电网拓扑异常检测方法"],
    n_results=3
)
for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
    print(f"  [{i+1}] {meta.get('category', '?')} - {meta.get('file', '?')[:40]}", flush=True)

print("[5/5] Saving stats...", flush=True)
categories = list(set(d["metadata"]["category"] for d in all_docs))
stats = {
    "total_chunks": len(all_docs),
    "categories": categories,
    "db_path": DB_DIR,
    "embedding_model": "ONNXMiniLM_L6_V2",
    "embedding_dim": 384
}
with open(Path(DB_DIR) / "stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"\n[OK] RAG Vector DB built: {DB_DIR}", flush=True)
print(f"    Chunks: {len(all_docs)}, Categories: {len(categories)}", flush=True)
