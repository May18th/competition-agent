# -*- coding: utf-8 -*-
"""Chroma-backed赛事资料检索 Agent。

首次运行会把 ``backend/data/*.txt`` 写入本地持久化 collection；没有安装
chromadb 或向量库尚未就绪时，明确降级到现有 TF-IDF 检索，不伪装成向量命中。
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


BASE = Path(__file__).resolve().parent
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(BASE / "chroma_db")))
COLLECTION = os.getenv("CHROMA_COLLECTION", "competition-official-docs")
_DOCS_CACHE = None


def _norm_name(value):
    """统一赛事名用于短名/全名匹配，不改变展示名或来源字段。"""
    return "".join(str(value or "").lower().split()).replace("（", "(").replace("）", ")")


def _documents():
    global _DOCS_CACHE
    if _DOCS_CACHE is not None:
        return _DOCS_CACHE
    out = []
    for path in sorted((BASE / "data").glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not text:
            continue
        # 以段落为最小单元，避免整本规则文档超过 embedding 上下文。
        chunks = [x.strip() for x in text.replace("\r", "").split("\n\n") if x.strip()]
        for idx, chunk in enumerate(chunks):
            doc_id = hashlib.sha1(f"{path.name}:{idx}:{chunk}".encode("utf-8")).hexdigest()
            out.append((doc_id, chunk, {"competition": path.stem, "source": path.name, "chunk": idx}))
    _DOCS_CACHE = out
    return out


def _resolve_stem(competition_name, docs):
    """将用户选择的赛事全名映射到资料文件短名，避免 Chroma 精确 where 误过滤。"""
    query = _norm_name(competition_name)
    if not query:
        return ""
    stems = sorted({meta.get("competition", "") for _, _, meta in docs if meta.get("competition")},
                   key=lambda x: len(_norm_name(x)), reverse=True)
    exact = [stem for stem in stems if _norm_name(stem) == query]
    if exact:
        return exact[0]
    # 括号别名优先于品牌名（例如“挑战杯（小挑）”不能误命中挑战杯总库）。
    bracket_aliases = re.findall(r"\(([^)]+)\)", query)
    for alias in bracket_aliases:
        for stem in stems:
            if _norm_name(stem) == _norm_name(alias):
                return stem
    # 文件短名通常出现在赛事全名中（例如 iCAN、挑战杯、互联网+）。
    contained = [stem for stem in stems if _norm_name(stem) in query or query in _norm_name(stem)]
    if contained:
        return contained[0]
    # 少量名称带括号别名，按括号内短名再匹配一次。
    aliases = [x.strip("() ") for x in query.replace("+", " + ").split() if x.strip("() ")]
    for stem in stems:
        nstem = _norm_name(stem)
        if any(alias and alias == nstem for alias in aliases):
            return stem
    return ""


def search(competition_name, query, top_k=5):
    """返回 ``{documents, metadatas, distances, backend}``，不抛出依赖错误。"""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collection = client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})
        docs = _documents()
        if docs:
            existing = collection.count()
            if existing < len(docs):
                collection.upsert(ids=[x[0] for x in docs],
                                  documents=[x[1] for x in docs],
                                  metadatas=[x[2] for x in docs])
        stem = _resolve_stem(competition_name, docs)
        where = {"competition": stem} if stem else None
        result = collection.query(query_texts=[str(query or "")[:1000]],
                                  n_results=max(1, min(int(top_k or 5), 20)),
                                  where=where)
        return {
            "documents": (result.get("documents") or [[]])[0],
            "metadatas": (result.get("metadatas") or [[]])[0],
            "distances": (result.get("distances") or [[]])[0],
            "backend": "chroma",
        }
    except Exception as exc:
        try:
            from competition_agents import retrieve_knowledge
            text = retrieve_knowledge(competition_name, query, top_k=top_k, max_chars=6000)
        except Exception:
            text = ""
        return {"documents": [text] if text else [], "metadatas": [],
                "distances": [], "backend": "tfidf-fallback", "error": str(exc)[:160]}
