import datetime as dt

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import WorkflowJob, WorkflowRun
from app.models.kb import utcnow
from app.services import job_queue


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def _run(db):
    run = WorkflowRun(id="rfq-test-001", type="rfq", status="processing", mode="rules",
                      created_by="analyst@opspilot.demo", metrics={})
    db.add(run)
    db.commit()
    return run


def test_enqueue_is_idempotent():
    engine = _db()
    with Session(engine) as db:
        run = _run(db)
        first = job_queue.enqueue(db, run.id, "rfq")
        second = job_queue.enqueue(db, run.id, "rfq")
        assert first.id == second.id
        assert db.scalar(select(WorkflowJob).where(WorkflowJob.run_id == run.id)).status == "queued"
    engine.dispose()


def test_job_can_only_be_claimed_once():
    engine = _db()
    with Session(engine) as db:
        run = _run(db)
        job = job_queue.enqueue(db, run.id, "rfq")
        claimed = job_queue.claim_next(db, "worker-a")
        assert claimed.id == job.id
        assert claimed.status == "running"
        assert claimed.attempts == 1
        assert job_queue.claim_next(db, "worker-b") is None
    engine.dispose()


def test_expired_worker_lease_can_be_recovered():
    engine = _db()
    with Session(engine) as db:
        run = _run(db)
        job = job_queue.enqueue(db, run.id, "rfq")
        claimed = job_queue.claim_next(db, "worker-crashed")
        claimed.locked_at = utcnow() - dt.timedelta(hours=1)
        db.commit()

        recovered = job_queue.claim_next(db, "worker-recovery")
        assert recovered.id == job.id
        assert recovered.status == "running"
        assert recovered.attempts == 2
        assert recovered.worker_id == "worker-recovery"
    engine.dispose()


def test_completed_job_is_not_claimed_again():
    engine = _db()
    with Session(engine) as db:
        run = _run(db)
        job = job_queue.enqueue(db, run.id, "rfq")
        claimed = job_queue.claim_next(db, "worker-a")
        job_queue.complete(db, claimed.id)
        assert job_queue.claim_next(db, "worker-b") is None
        assert db.get(WorkflowJob, job.id).status == "completed"
    engine.dispose()
