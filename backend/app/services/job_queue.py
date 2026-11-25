"""Transactional operations for the durable workflow queue."""
from __future__ import annotations

import datetime as dt
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..models import WorkflowJob
from ..models.kb import utcnow


def enqueue(db: Session, run_id: str, job_type: str, max_attempts: int = 3) -> WorkflowJob:
    existing = db.scalar(select(WorkflowJob).where(WorkflowJob.run_id == run_id))
    if existing:
        return existing
    job = WorkflowJob(run_id=run_id, job_type=job_type, status="queued", max_attempts=max_attempts)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next(db: Session, worker_id: str, lease_seconds: int = 1800) -> WorkflowJob | None:
    now = utcnow()
    stale_before = now - dt.timedelta(seconds=lease_seconds)
    # A crashed worker that already used every allowed claim must not leave a
    # permanently-running row behind.
    db.execute(
        update(WorkflowJob)
        .where(
            WorkflowJob.status == "running",
            WorkflowJob.locked_at < stale_before,
            WorkflowJob.attempts >= WorkflowJob.max_attempts,
        )
        .values(status="failed", locked_at=None, worker_id=None, finished_at=now,
                updated_at=now, last_error="Worker lease expired after maximum attempts")
    )
    db.commit()
    candidate = db.scalar(
        select(WorkflowJob)
        .where(
            WorkflowJob.attempts < WorkflowJob.max_attempts,
            WorkflowJob.available_at <= now,
            or_(
                WorkflowJob.status == "queued",
                (WorkflowJob.status == "running") & (WorkflowJob.locked_at < stale_before),
            ),
        )
        .order_by(WorkflowJob.created_at, WorkflowJob.id)
        .limit(1)
    )
    if candidate is None:
        return None
    result = db.execute(
        update(WorkflowJob)
        .where(
            WorkflowJob.id == candidate.id,
            or_(
                WorkflowJob.status == "queued",
                (WorkflowJob.status == "running") & (WorkflowJob.locked_at < stale_before),
            ),
        )
        .values(status="running", attempts=WorkflowJob.attempts + 1, locked_at=now,
                worker_id=worker_id, updated_at=now, last_error=None)
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    db.expire_all()
    return db.get(WorkflowJob, candidate.id)


def complete(db: Session, job_id: int) -> None:
    now = utcnow()
    db.execute(update(WorkflowJob).where(WorkflowJob.id == job_id)
               .values(status="completed", locked_at=None, worker_id=None, finished_at=now, updated_at=now))
    db.commit()


def fail(db: Session, job_id: int, error: str, retry: bool = True) -> None:
    job = db.get(WorkflowJob, job_id)
    if job is None:
        return
    now = utcnow()
    can_retry = retry and job.attempts < job.max_attempts
    delay = min(300, 2 ** max(job.attempts - 1, 0))
    job.status = "queued" if can_retry else "failed"
    job.available_at = now + dt.timedelta(seconds=delay if can_retry else 0)
    job.locked_at = None
    job.worker_id = None
    job.last_error = error[:1000]
    job.finished_at = None if can_retry else now
    job.updated_at = now
    db.commit()


def snapshot(job: WorkflowJob) -> dict:
    return {
        "id": job.id, "run_id": job.run_id, "type": job.job_type, "status": job.status,
        "attempts": job.attempts, "max_attempts": job.max_attempts,
        "available_at": job.available_at.isoformat() if job.available_at else None,
        "last_error": job.last_error, "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
