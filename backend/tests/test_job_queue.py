import datetime as dt

from sqlalchemy import select

from app.models import WorkflowJob
from app.models.kb import utcnow
from app.services import job_queue, runs


def _run(db, analyst):
    run = runs.new_run(db, "rfq", analyst.email, "rules")
    db.commit()
    return run


def test_enqueue_is_idempotent(db, analyst):
    run = _run(db, analyst)
    first = job_queue.enqueue(db, run.id, "rfq")
    second = job_queue.enqueue(db, run.id, "rfq")
    assert first.id == second.id
    assert db.scalar(select(WorkflowJob).where(WorkflowJob.run_id == run.id)).status == "queued"


def test_job_can_only_be_claimed_once(db, analyst):
    run = _run(db, analyst)
    job = job_queue.enqueue(db, run.id, "rfq")
    claimed = job_queue.claim_next(db, "worker-a")
    assert claimed.id == job.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert job_queue.claim_next(db, "worker-b") is None


def test_expired_worker_lease_can_be_recovered(db, analyst):
    run = _run(db, analyst)
    job = job_queue.enqueue(db, run.id, "rfq")
    claimed = job_queue.claim_next(db, "worker-crashed")
    claimed.locked_at = utcnow() - dt.timedelta(hours=1)
    db.commit()

    recovered = job_queue.claim_next(db, "worker-recovery")
    assert recovered.id == job.id
    assert recovered.status == "running"
    assert recovered.attempts == 2
    assert recovered.worker_id == "worker-recovery"


def test_completed_job_is_not_claimed_again(db, analyst):
    run = _run(db, analyst)
    job = job_queue.enqueue(db, run.id, "rfq")
    claimed = job_queue.claim_next(db, "worker-a")
    job_queue.complete(db, claimed.id)
    assert job_queue.claim_next(db, "worker-b") is None
    assert db.get(WorkflowJob, job.id).status == "completed"
