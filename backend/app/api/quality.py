from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..docproc.validate import UploadError
from ..models import COACheck, User, WorkflowRun
from ..services import coa_service, runs
from .deps import upload_limit
from .rfq import _read_limited

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.post("/coa", status_code=202)
async def upload_coa(background: BackgroundTasks, file: UploadFile = File(...), user: User = Depends(upload_limit),
                     db: Session = Depends(get_db)):
    content = await _read_limited(file)
    try:
        run = coa_service.create_run(db, user, file.filename, content)
    except UploadError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    background.add_task(coa_service.process_run, run.id)
    return {"run_id": run.id, "status": run.status}


@router.get("")
def list_checks(limit: int = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(WorkflowRun).where(WorkflowRun.type == "coa").order_by(WorkflowRun.created_at.desc())
                      .limit(min(max(limit, 1), 200))).all()
    checks = {c.run_id: c for c in db.scalars(select(COACheck).where(COACheck.run_id.in_([r.id for r in rows])))} if rows else {}
    out = []
    for r in rows:
        d = runs.run_summary(r)
        c = checks.get(r.id)
        d["coa"] = None if c is None else {"product_code": c.product_code, "batch_no": c.batch_no, "verdict": c.verdict}
        out.append(d)
    return out


@router.get("/{run_id}")
def get_check(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = runs.run_detail(db, run_id)
    if d is None or d["run"]["type"] != "coa":
        raise HTTPException(404, "COA run not found")
    return d
