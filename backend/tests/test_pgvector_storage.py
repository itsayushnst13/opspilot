from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.types import JSON

from app.models.kb import EmbeddingVector


def test_embedding_column_uses_pgvector_for_postgresql():
    impl = EmbeddingVector().load_dialect_impl(postgresql.dialect())
    assert impl.__class__.__name__ == "Vector"


def test_embedding_column_keeps_json_for_sqlite():
    impl = EmbeddingVector().load_dialect_impl(sqlite.dialect())
    assert isinstance(impl, JSON)
