"""Knowledge-base search tool (RAG) with citations."""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..rag.embed import EmbeddingError, get_embedder
from ..rag.retrieve import retrieve
from .pricing_engine import ToolError


class SearchKBArgs(BaseModel):
    query: str = Field(description="Natural-language question or keywords")
    product_code: str | None = Field(default=None, description="Optional product code to prioritise")
    k: int = Field(default=4, ge=1, le=8)


def search_knowledge_base(db: Session, a: SearchKBArgs) -> dict:
    try:
        hits = retrieve(db, a.query, get_embedder(), k=a.k, product_code=a.product_code)
    except EmbeddingError as exc:
        # A rate-limited or unavailable embedder must not take the whole quote down: the run
        # continues without these passages and the failed tool call is recorded.
        raise ToolError(f"Knowledge base unavailable: {exc}") from None
    return {"passages": [{"citation": h.citation, "doc_type": h.doc_type, "title": h.title,
                          "score": h.score, "text": h.content[:500]} for h in hits]}
