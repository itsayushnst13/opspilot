from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import kb_qa
from ..agents.llm import get_llm
from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import get_current_user
from ..docproc.parsers import ParseError
from ..docproc.validate import UploadError, validate_upload
from ..models import KBDocument, User
from ..rag.embed import get_embedder
from ..rag.ingest import ingest_bytes
from ..services import audit
from .deps import upload_limit
from .rfq import _read_limited

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.get("/documents")
def documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = db.scalars(select(KBDocument).order_by(KBDocument.doc_type, KBDocument.source_path)).all()
    return [{"id": d.id, "path": d.source_path, "title": d.title, "doc_type": d.doc_type, "chunks": d.n_chunks,
             "product_codes": d.product_codes, "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None}
            for d in docs]


@router.post("/ask")
def ask(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return kb_qa.answer(db, body.question, get_llm())


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), user: User = Depends(upload_limit), db: Session = Depends(get_db)):
    content = await _read_limited(file)
    s = get_settings()
    try:
        name, ext = validate_upload(file.filename, content, s.max_upload_bytes, allowed={".pdf", ".txt", ".csv", ".xlsx"})
        res = ingest_bytes(db, f"uploads/{name}", content, get_embedder(s), doc_type="uploaded")
    except UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from None
    audit.append(db, None, user.email, "kb_document_uploaded", {"path": res["path"], "chunks": res["chunks"], "status": res["status"]})
    db.commit()
    return res
