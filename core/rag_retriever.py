"""
SDTMIG RAG Retriever - 从向量库检索 SDTM 规范条文
"""
import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

try:
    from transformers.utils import logging as _tf_logging
    _tf_logging.set_verbosity_error()
except Exception:
    pass

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def _load_sentence_transformer(model_name: str) -> SentenceTransformer:
    """加载 embedding 模型。

    优先尝试离线（仅使用本地缓存），避免在无网络/代理异常时触发
    huggingface_hub/httpx 的 'client has been closed' 这类错误。
    """
    # 允许用环境变量覆盖（便于在内网/离线环境切换到已缓存模型）
    model_name = os.getenv("SDTM_RAG_EMBED_MODEL", model_name)

    # 1) 优先仅本地缓存
    try:
        return SentenceTransformer(model_name, local_files_only=True)
    except TypeError:
        # 旧版本 sentence-transformers 可能不支持 local_files_only
        pass
    except Exception:
        # 本地没有缓存则继续尝试在线
        pass

    # 2) 在线加载（需要网络）
    return SentenceTransformer(model_name)


@dataclass
class RetrievedChunk:
    score: float
    page: int
    chunk_id: str
    text: str


class SDTMIGRetriever:
    """向量检索 SDTMIG 规范"""

    def __init__(
        self,
        index_dir: str,
        model_name: str = DEFAULT_EMBED_MODEL,
    ):
        self.index_dir = os.path.abspath(index_dir)
        self.model_name = model_name

        # 尝试多个可能的路径
        possible_dirs = [
            self.index_dir,
            os.path.join(self.index_dir, "rag_store"),  # 如果 index_dir 是项目根
            os.path.join(os.path.dirname(self.index_dir), "rag_store"),  # 平级目录
        ]
        
        faiss_path = None
        meta_path = None
        
        for pdir in possible_dirs:
            _faiss = os.path.join(pdir, "sdtmig.faiss")
            _meta = os.path.join(pdir, "sdtmig.meta.jsonl")
            if os.path.exists(_faiss) and os.path.exists(_meta):
                faiss_path = _faiss
                meta_path = _meta
                self.index_dir = pdir
                break
        
        if not faiss_path or not meta_path:
            raise FileNotFoundError(
                f"FAISS index not found in {possible_dirs}. "
                f"Please ensure sdtmig.faiss and sdtmig.meta.jsonl exist."
            )

        print(f"[RAG] Loading FAISS index from {faiss_path}...")
        self.index = faiss.read_index(faiss_path)
        print(f"[RAG] Index loaded. Size: {self.index.ntotal}")
        
        self.meta: List[Dict[str, Any]] = []
        with open(meta_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                self.meta.append(json.loads(line))
        
        print(f"[RAG] Metadata loaded. Count: {len(self.meta)}")
        print(f"[RAG] Loading embedding model: {self.model_name}...")
        try:
            self.model = _load_sentence_transformer(self.model_name)
        except Exception as e:
            raise RuntimeError(
                "Failed to load embedding model for RAG retriever. "
                "If you are offline, please pre-download the model or set SDTM_RAG_EMBED_MODEL to a local path. "
                f"Original error: {e}"
            )
        print(f"[RAG] Model ready.")

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        """向量查询，返回最相关的 K 个块"""
        if not query or not query.strip():
            return []

        q = self.model.encode([query], normalize_embeddings=True)
        q = np.asarray(q, dtype=np.float32)

        scores, idx = self.index.search(q, top_k)
        scores = scores[0].tolist()
        idx = idx[0].tolist()

        out: List[RetrievedChunk] = []
        for s, i in zip(scores, idx):
            if i < 0 or i >= len(self.meta):
                continue
            m = self.meta[i]
            out.append(
                RetrievedChunk(
                    score=float(s),
                    page=int(m.get("page", -1)),
                    chunk_id=str(m.get("chunk_id", "")),
                    text=str(m.get("text", "")),
                )
            )
        return out


def format_retrieved(chunks: List[RetrievedChunk]) -> str:
    """格式化检索结果用于插入 LLM 提示"""
    lines: List[str] = []
    for c in chunks:
        lines.append(f"[page {c.page} | score {c.score:.3f}] {c.text}")
    return "\n".join(lines)


# 进程内缓存
_CACHE: Dict[tuple, "SDTMIGRetriever"] = {}


def get_retriever(index_dir: str, model_name: str = DEFAULT_EMBED_MODEL) -> "SDTMIGRetriever":
    """获取或创建 retriever 单例"""
    key = (os.path.abspath(index_dir), model_name)
    r = _CACHE.get(key)
    if r is None:
        r = SDTMIGRetriever(index_dir=index_dir, model_name=model_name)
        _CACHE[key] = r
    return r
