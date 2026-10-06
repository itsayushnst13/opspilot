"""Retrieval with citations."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from . import store
from .chunk import extract_product_codes
from .embed import Embedder


@dataclass
class Hit:
    chunk_id: int
    path: str
    doc_type: str
    title: str
    locator: str
    score: float
    content: str

    @property
    def citation(self) -> str:
        return f"{self.path} ({self.locator})"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["citation"] = self.citation
        return d


def retrieve(db: Session, query: str, embedder: Embedder, k: int = 5, product_code: str | None = None,
             doc_types: set[str] | None = None) -> list[Hit]:
    codes = set(extract_product_codes(query))
    if product_code:
        codes.add(product_code.upper())
    qvec = embedder.embed_query(query)
    results = store.search(db, qvec, embedder.name, k=k, doc_types=doc_types, boost_codes=codes or None)
    return [Hit(chunk_id=m["chunk_id"], path=m["path"], doc_type=m["doc_type"], title=m["title"],
                locator=m["locator"], score=round(s, 4), content=m["content"]) for s, m in results]
