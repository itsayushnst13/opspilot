"""In-process exact cosine search over embeddings persisted in the database.

For a knowledge base of a few hundred chunks, exact search in NumPy is faster and simpler than an ANN
index. The class boundary is deliberately narrow so it can be swapped for pgvector later.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.kb import KBChunk, KBDocument

_lock = threading.Lock()
_cache: dict[str, "_Index"] = {}


@dataclass
class _Index:
    signature: tuple
    matrix: np.ndarray
    meta: list[dict]


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _signature(db: Session, embedder_name: str) -> tuple:
    row = db.execute(
        select(func.count(KBChunk.id), func.max(KBChunk.id), func.max(KBDocument.ingested_at))
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBDocument.embedder == embedder_name, KBChunk.embedding.is_not(None))
    ).one()
    return (str(db.get_bind().url), embedder_name, row[0], row[1], str(row[2]))


def _load(db: Session, embedder_name: str) -> _Index:
    sig = _signature(db, embedder_name)
    with _lock:
        cached = _cache.get(embedder_name)
        if cached and cached.signature == sig:
            return cached
    rows = db.execute(
        select(KBChunk, KBDocument)
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBDocument.embedder == embedder_name, KBChunk.embedding.is_not(None))
        .order_by(KBChunk.id)
    ).all()
    meta = [{"chunk_id": c.id, "doc_id": d.id, "path": d.source_path, "doc_type": d.doc_type,
             "title": d.title, "locator": c.locator, "content": c.content,
             "product_codes": set(c.product_codes or [])} for c, d in rows]
    matrix = np.asarray([c.embedding for c, _ in rows], dtype=np.float64) if rows else np.zeros((0, 1))
    idx = _Index(sig, matrix, meta)
    with _lock:
        _cache[embedder_name] = idx
    return idx


def search(db: Session, query_vec: list[float], embedder_name: str, k: int = 5,
           doc_types: set[str] | None = None, boost_codes: set[str] | None = None,
           boost: float = 0.2) -> list[tuple[float, dict]]:
    idx = _load(db, embedder_name)
    if len(idx.meta) == 0:
        return []
    scores = idx.matrix @ np.asarray(query_vec, dtype=np.float64)
    for i, m in enumerate(idx.meta):
        if doc_types and m["doc_type"] not in doc_types:
            scores[i] = -1e9
        elif boost_codes and (m["product_codes"] & boost_codes):
            scores[i] += boost
    order = np.argsort(-scores)[:k]
    return [(float(scores[i]), idx.meta[i]) for i in order if scores[i] > -1e8]
