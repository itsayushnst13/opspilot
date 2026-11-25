from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..models import WorkflowJob, User
from ..services.job_queue import snapshot

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.scalar(select(WorkflowJob).where(WorkflowJob.id == job_id))
    if job is None:
        raise HTTPException(404, "Workflow job not found")
    return snapshot(job)
