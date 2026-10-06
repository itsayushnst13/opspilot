"""Knowledge-base tables for RAG. Embeddings are stored as JSON float lists."""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    checksum: Mapped[str] = mapped_column(String(64))
    product_codes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    n_chunks: Mapped[int] = mapped_column(Integer, default=0)
    embedder: Mapped[str] = mapped_column(String(80), default="")
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list["KBChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(String(80), default="")
    product_codes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    embedding: Mapped[Optional[list[float]]] = mapped_column(JSON, nullable=True)

    document: Mapped[KBDocument] = relationship(back_populates="chunks")
