#!/usr/bin/env python
"""
Skill: 从 RAG 检索 SDTM 规范
"""
import sys
import json
import os
from core.rag_retriever import get_retriever, format_retrieved

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: retrieve_rules.py <query> [domain]"}, ensure_ascii=False))
        sys.exit(1)
    
    query = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else "general"
    
    try:
        rag_store = os.path.join(os.path.dirname(__file__), "..", "rag_store")
        if not os.path.exists(rag_store):
            raise FileNotFoundError(f"RAG store not found at: {rag_store}")
        
        # 获取 retriever
        retriever = get_retriever(rag_store)
        
        # 构建增强查询
        enhanced_query = f"[{domain}] {query}" if domain != "general" else query
        
        # 检索
        chunks = retriever.retrieve(enhanced_query, top_k=5)
        
        result = {
            "success": True,
            "query": query,
            "domain": domain,
            "chunks": [
                {
                    "page": c.page,
                    "score": float(c.score),
                    "text": c.text,
                }
                for c in chunks
            ],
            "formatted": format_retrieved(chunks),
        }
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
