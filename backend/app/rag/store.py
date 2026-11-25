"""Hybrid retrieval backed by pgvector on PostgreSQL and exact NumPy search on SQLite."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from ..models.kb import EMBEDDING_DIM, KBChunk, KBDocument
from .embed import tokenize

_lock = threading.Lock()
_cache: dict[tuple[str, str], "_Index"] = {}


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
        cache_key = (sig[0], embedder_name)
        cached = _cache.get(cache_key)
        if cached and cached.signature == sig:
            return cached
    rows = db.execute(
        select(KBChunk, KBDocument)
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBDocument.embedder == embedder_name, KBChunk.embedding.is_not(None))
        .order_by(KBChunk.id)
    ).all()
    meta = [{
        "chunk_id": c.id, "doc_id": d.id, "path": d.source_path, "doc_type": d.doc_type,
        "title": d.title, "locator": c.locator, "content": c.content,
        "product_codes": set(c.product_codes or []), "terms": set(tokenize(c.content)),
    } for c, d in rows]
    matrix = np.asarray([c.embedding for c, _ in rows], dtype=np.float64) if rows else np.zeros((0, 1))
    idx = _Index(sig, matrix, meta)
    with _lock:
        _cache[cache_key] = idx
    return idx


def _hybrid_score(vector_score: float, meta: dict, terms: set[str],
                  doc_types: set[str] | None, boost_codes: set[str] | None, boost: float) -> float:
    if doc_types and meta["doc_type"] not in doc_types:
        return -1e9
    score = vector_score
    if terms:
        lexical = len(terms & meta["terms"]) / len(terms)
        score = 0.75 * vector_score + 0.25 * lexical
    if boost_codes and (meta["product_codes"] & boost_codes):
        score += boost
    return score


def _search_pgvector(db: Session, query: np.ndarray, embedder_name: str, k: int,
                     doc_types: set[str] | None, boost_codes: set[str] | None,
                     boost: float, query_text: str | None) -> list[tuple[float, dict]]:
    # Import lazily so SQLite-only installations still use the NumPy fallback.
    from pgvector.sqlalchemy import Vector

    distance = cast(KBChunk.embedding, Vector(EMBEDDING_DIM)).cosine_distance(query.tolist())
    stmt = (
        select(KBChunk, KBDocument, (1.0 - distance).label("vector_score"))
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .where(KBDocument.embedder == embedder_name, KBChunk.embedding.is_not(None))
    )
    if doc_types:
        stmt = stmt.where(KBDocument.doc_type.in_(doc_types))
    # Fetch a wider candidate set before applying lexical and product-code boosts.
    candidate_limit = min(max(k * 10, 50), 1000)
    rows = db.execute(stmt.order_by(distance).limit(candidate_limit)).all()
    terms = set(tokenize(query_text or ""))
    ranked: list[tuple[float, dict]] = []
    for chunk, doc, vector_score in rows:
        meta = {
            "chunk_id": chunk.id, "doc_id": doc.id, "path": doc.source_path,
            "doc_type": doc.doc_type, "title": doc.title, "locator": chunk.locator,
            "content": chunk.content, "product_codes": set(chunk.product_codes or []),
            "terms": set(tokenize(chunk.content)),
        }
        score = _hybrid_score(float(vector_score), meta, terms, doc_types, boost_codes, boost)
        ranked.append((score, meta))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:k]


def search(db: Session, query_vec: list[float], embedder_name: str, k: int = 5,
           doc_types: set[str] | None = None, boost_codes: set[str] | None = None,
           boost: float = 0.2, query_text: str | None = None) -> list[tuple[float, dict]]:
    if k <= 0:
        return []
    query = np.asarray(query_vec, dtype=np.float64)
    if query.ndim != 1:
        raise ValueError("Query embedding must be a one-dimensional vector")
    if not np.isfinite(query).all():
        raise ValueError("Query embedding contains non-finite values")

    if db.get_bind().dialect.name == "postgresql":
        if query.shape[0] != EMBEDDING_DIM:
            raise ValueError(f"PostgreSQL pgvector expects {EMBEDDING_DIM}-dimensional embeddings")
        return _search_pgvector(db, query, embedder_name, k, doc_types, boost_codes, boost, query_text)

    idx = _load(db, embedder_name)
    if len(idx.meta) == 0:
        return []
    if query.shape[0] != idx.matrix.shape[1]:
        raise ValueError("Query embedding dimension does not match indexed embeddings")
    vector_scores = idx.matrix @ query
    terms = set(tokenize(query_text or ""))
    ranked = [
        (_hybrid_score(float(vector_scores[i]), meta, terms, doc_types, boost_codes, boost), meta)
        for i, meta in enumerate(idx.meta)
    ]
    ranked = [item for item in ranked if item[0] > -1e8]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:k]
