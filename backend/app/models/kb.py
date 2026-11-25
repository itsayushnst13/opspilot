"""Knowledge-base tables for RAG. PostgreSQL uses native pgvector; SQLite keeps JSON for tests."""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.config import get_settings
from ..core.db import Base

# Must match the configured embedder dimension for new and migrated vectors.
EMBEDDING_DIM = get_settings().embed_dim


class EmbeddingVector(TypeDecorator):
    """Use pgvector on PostgreSQL and JSON arrays on SQLite.

    The fallback keeps unit tests and lightweight local SQLite runs independent
    of the PostgreSQL vector extension.
    """
    impl = JSON
    cache_ok = True
    comparator_factory = Vector.comparator_factory

    def __init__(self, dimensions: int = EMBEDDING_DIM, **kwargs):
        self.dimensions = dimensions
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(JSON())


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
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingVector(), nullable=True)

    document: Mapped[KBDocument] = relationship(back_populates="chunks")
