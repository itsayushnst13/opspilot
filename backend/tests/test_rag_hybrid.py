import math

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.db import Base
from app.models.kb import KBChunk, KBDocument
from app.rag import store


@pytest.fixture
def kb_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    store.invalidate()
    engine.dispose()


def add_chunk(db, path, content, embedding, doc_type="specifications"):
    doc = KBDocument(source_path=path, doc_type=doc_type, title=path, checksum="0" * 64,
                     product_codes=[], n_chunks=1, embedder="test-embedder")
    db.add(doc)
    db.flush()
    db.add(KBChunk(document_id=doc.id, chunk_index=0, content=content, locator="page 1",
                   product_codes=[], embedding=embedding))
    db.commit()


def test_hybrid_search_ranks_exact_terms_above_vector_only_match(kb_session):
    store.invalidate()
    add_chunk(kb_session, "general.pdf", "general industrial liquid handling", [1.0, 0.0])
    add_chunk(kb_session, "chem-x01.pdf", "CHEM-X01 purity specification 99 percent", [0.8, 0.6])
    hits = store.search(kb_session, [1.0, 0.0], "test-embedder", k=2, query_text="CHEM-X01 purity")
    assert hits[0][1]["path"] == "chem-x01.pdf"
    assert hits[0][0] > hits[1][0]


def test_hybrid_search_respects_document_type_filter(kb_session):
    store.invalidate()
    add_chunk(kb_session, "supplier.txt", "CHEM-X01 supplier price", [1.0, 0.0], "suppliers")
    add_chunk(kb_session, "spec.txt", "CHEM-X01 purity specification", [0.9, 0.1], "specifications")
    hits = store.search(kb_session, [1.0, 0.0], "test-embedder", k=5,
                        doc_types={"specifications"}, query_text="CHEM-X01")
    assert hits
    assert all(item["doc_type"] == "specifications" for _, item in hits)


def test_hybrid_search_rejects_invalid_query_vectors(kb_session):
    store.invalidate()
    add_chunk(kb_session, "spec.txt", "CHEM-X01 specification", [1.0, 0.0])
    with pytest.raises(ValueError, match="dimension"):
        store.search(kb_session, [1.0], "test-embedder")
    with pytest.raises(ValueError, match="non-finite"):
        store.search(kb_session, [math.nan, 0.0], "test-embedder")
