from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import get_current_user
from ..docproc.validate import UploadError
from ..models import Quote, User, WorkflowRun
from ..services import approval_service, rfq_service, runs
from .deps import upload_limit

router = APIRouter(prefix="/api/rfq", tags=["rfq"])


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=rfq_service.MAX_TEXT_CHARS)


class DecisionIn(BaseModel):
    decision: str
    reason: str | None = Field(default=None, max_length=2000)


async def _read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {get_settings().max_upload_mb} MB limit")
    return data


@router.post("", status_code=202)
async def upload_rfq(background: BackgroundTasks, file: UploadFile = File(...), user: User = Depends(upload_limit),
                     db: Session = Depends(get_db)):
    content = await _read_limited(file)
    try:
        run = rfq_service.create_run_from_upload(db, user, file.filename, content)
    except UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    background.add_task(rfq_service.process_run, run.id)
    return {"run_id": run.id, "status": run.status}


@router.post("/text", status_code=202)
def submit_text(body: TextIn, background: BackgroundTasks, user: User = Depends(upload_limit),
                db: Session = Depends(get_db)):
    try:
        run = rfq_service.create_run_from_text(db, user, body.text)
    except UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    background.add_task(rfq_service.process_run, run.id)
    return {"run_id": run.id, "status": run.status}


@router.get("")
def list_rfqs(status: str | None = None, limit: int = 50, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    stmt = select(WorkflowRun).where(WorkflowRun.type == "rfq").order_by(WorkflowRun.created_at.desc()).limit(min(max(limit, 1), 200))
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    rows = db.scalars(stmt).all()
    quotes = {q.run_id: q for q in db.scalars(select(Quote).where(Quote.run_id.in_([r.id for r in rows])))} if rows else {}
    out = []
    for r in rows:
        d = runs.run_summary(r)
        q = quotes.get(r.id)
        d["quote"] = None if q is None else {"price_per_kg": str(q.price_per_kg), "total": str(q.total), "currency": q.currency,
                                              "warnings": [w["code"] for w in q.warnings]}
        out.append(d)
    return out


@router.get("/{run_id}")
def get_rfq(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = runs.run_detail(db, run_id)
    if d is None or d["run"]["type"] != "rfq":
        raise HTTPException(404, "RFQ run not found")
    return d


@router.post("/{run_id}/decision")
def decide(run_id: str, body: DecisionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return approval_service.decide(db, user, run_id, body.decision, body.reason)


@router.get("/{run_id}/quote.pdf")
def quote_pdf(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return Response(approval_service.quote_pdf_bytes(db, run_id), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}-quote.pdf"'})
