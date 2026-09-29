# -*- coding: utf-8 -*-
"""[v1.0] RAG Query - 知识库检索 v4"""
import os
from pathlib import Path
from typing import List, Optional
import chromadb
from chromadb.utils import embedding_functions

# 使用v4数据库
DB_DIR = "output/rag_vector_db_v4"


class RAGQuerier:
    def __init__(self, db_path: str = DB_DIR):
        self.ef = embedding_functions.ONNXMiniLM_L6_V2()
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_collection("power_topology_kb_v4")
        print(f"[RAG] Loaded v4: {self.collection.count()} chunks", flush=True)
    
    def query(self, question: str, top_k: int = 5) -> List[dict]:
        """检索相关知识"""
        results = self.collection.query(
            query_texts=[question],
            n_results=top_k
        )
        
        docs = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            docs.append({
                "text": doc[:500],
                "source": meta.get("source", ""),
                "category": meta.get("category", ""),
                "file": meta.get("file", ""),
                "type": meta.get("type", ""),
                "relevance": 1.0 - dist
            })
        return docs
    
    def build_context(self, question: str, top_k: int = 3) -> str:
        """构建RAG上下文"""
        docs = self.query(question, top_k)
        if not docs:
            return ""
        
        context = "【参考知识】\n"
        for i, doc in enumerate(docs, 1):
            context += f"[{i}] {doc['category']} - {doc['file']}\n"
            context += f"{doc['text']}\n\n"
        return context


def main():
    querier = RAGQuerier()
    
    test_questions = [
        "配电网拓扑异常检测方法有哪些？",
        "状态估计中如何检测不良数据？",
        "变压器分接头故障有什么表现？",
        "如何处理接地故障？"
    ]
    
    print("\n" + "="*60)
    for q in test_questions:
        print(f"\n[Query] {q}")
        docs = querier.query(q, top_k=2)
        for i, d in enumerate(docs, 1):
            print(f"  [{i}] {d['category']} (relevance={d['relevance']:.2f})")
            print(f"      {d['text'][:150]}...")
        print()


if __name__ == "__main__":
    main()