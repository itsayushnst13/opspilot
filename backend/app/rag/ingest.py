"""Knowledge-base ingestion: parse -> chunk -> embed -> store."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..docproc.parsers import ParseError, parse_bytes
from ..models.kb import KBChunk, KBDocument
from . import store
from .chunk import chunk_document, extract_product_codes
from .embed import Embedder

KB_DIRS = ["products", "specifications", "suppliers", "pricing", "shipping", "regulatory", "historical_quotes"]
KB_EXTS = {".pdf", ".txt", ".csv", ".xlsx"}


def ingest_bytes(db: Session, rel_path: str, content: bytes, embedder: Embedder,
                 doc_type: str | None = None, force: bool = False) -> dict:
    """Ingest one document. Returns {'path','status','chunks'} where status is ingested|skipped."""
    settings = get_settings()
    checksum = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(KBDocument).where(KBDocument.source_path == rel_path))
    if existing and existing.checksum == checksum and existing.embedder == embedder.name and not force:
        return {"path": rel_path, "status": "skipped", "chunks": existing.n_chunks}

    parsed = parse_bytes(os.path.basename(rel_path), content, settings.max_pdf_pages, settings.max_sheet_rows)
    chunks = chunk_document(parsed)
    if not chunks:
        raise ParseError("Document produced no chunks")
    vectors = embedder.embed_documents([c.content for c in chunks])

    if existing:
        db.execute(delete(KBChunk).where(KBChunk.document_id == existing.id))
        doc = existing
    else:
        doc = KBDocument(source_path=rel_path, doc_type="", title="", checksum="", product_codes=[],
                         n_chunks=0, embedder="")
        db.add(doc)
    first_line = next((s.text.split("\n", 1)[0] for s in parsed.segments if s.text.strip()), rel_path)
    doc.doc_type = doc_type or (rel_path.split("/", 1)[0] if "/" in rel_path else "uploads")
    doc.title = first_line[:290]
    doc.checksum = checksum
    doc.product_codes = extract_product_codes(parsed.text)
    doc.n_chunks = len(chunks)
    doc.embedder = embedder.name
    db.flush()
    for c, v in zip(chunks, vectors):
        db.add(KBChunk(document_id=doc.id, chunk_index=c.index, content=c.content, locator=c.locator,
                       product_codes=c.product_codes, embedding=v))
    db.commit()
    store.invalidate()
    return {"path": rel_path, "status": "ingested", "chunks": len(chunks)}


def ingest_directory(db: Session, root: Path, embedder: Embedder, force: bool = False) -> dict:
    summary = {"ingested": 0, "skipped": 0, "chunks": 0, "errors": []}
    for sub in KB_DIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in KB_EXTS:
                continue
            rel = f.relative_to(root).as_posix()
            try:
                res = ingest_bytes(db, rel, f.read_bytes(), embedder, force=force)
                summary[res["status"]] += 1
                summary["chunks"] += res["chunks"]
            except Exception as exc:  # keep going; report per-file failures
                db.rollback()
                summary["errors"].append({"path": rel, "error": f"{exc.__class__.__name__}: {exc}"})
    return summary
