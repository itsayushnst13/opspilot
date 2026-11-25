"""SQLAlchemy engine/session setup. Works with SQLite (tests/local) and PostgreSQL (prod)."""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    """Accept common provider URLs (postgres://, postgresql://) and pick the psycopg3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None) -> Engine:
    url = normalize_url(url or get_settings().database_url)
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _prepare_pgvector(bind: Engine) -> None:
    """Enable pgvector and safely upgrade the legacy JSON embedding column."""
    from ..models.kb import EMBEDDING_DIM

    with bind.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        inspector = inspect(conn)
        if inspector.has_table("kb_chunks"):
            columns = {c["name"]: c["type"] for c in inspector.get_columns("kb_chunks")}
            embedding_type = columns.get("embedding")
            # Existing deployments stored float arrays as JSON. PostgreSQL's
            # vector input accepts the JSON array text representation.
            if embedding_type is not None and embedding_type.__class__.__name__.lower() in {"json", "jsonb"}:
                conn.execute(text(
                    "ALTER TABLE kb_chunks "
                    f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) "
                    "USING CASE WHEN embedding IS NULL THEN NULL "
                    "ELSE embedding::text::vector END"
                ))
        if inspector.has_table("kb_chunks"):
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw "
                "ON kb_chunks USING hnsw (embedding vector_cosine_ops)"
            ))


def init_db(bind: Engine | None = None) -> None:
    from .. import models  # noqa: F401  (register tables)

    target = bind or engine
    if target.dialect.name == "postgresql":
        _prepare_pgvector(target)
    Base.metadata.create_all(target)
