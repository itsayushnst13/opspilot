"""Small database-backed worker. Jobs survive API process restarts."""
from __future__ import annotations

import logging
import threading
import time
import uuid

from sqlalchemy import select

from ..core.db import SessionLocal
from ..models import WorkflowRun
from . import job_queue

logger = logging.getLogger("opspilot.worker")


class WorkflowWorker:
    def __init__(self, poll_seconds: float = 1.0):
        self.poll_seconds = poll_seconds
        self.worker_id = f"worker-{uuid.uuid4().hex[:10]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="opspilot-workflow-worker", daemon=True)
        self._thread.start()
        logger.info("workflow worker started", extra={"ctx": {"worker_id": self.worker_id}})

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job_id = None
            try:
                with SessionLocal() as db:
                    job = job_queue.claim_next(db, self.worker_id)
                    if job:
                        job_id = job.id
                        run_id, job_type = job.run_id, job.job_type
                if job_id is not None:
                    self._execute(job_id, run_id, job_type)
                else:
                    self._stop.wait(self.poll_seconds)
            except Exception:
                logger.exception("workflow worker loop error")
                self._stop.wait(self.poll_seconds)

    def _execute(self, job_id: int, run_id: str, job_type: str) -> None:
        try:
            if job_type == "rfq":
                from .rfq_service import process_run
                process_run(run_id)
            elif job_type == "coa":
                from .coa_service import process_run
                process_run(run_id)
            else:
                raise ValueError(f"Unsupported workflow job type: {job_type}")
            with SessionLocal() as db:
                run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
                if run is None:
                    job_queue.fail(db, job_id, "Workflow run disappeared", retry=False)
                elif run.status == "failed":
                    job_queue.fail(db, job_id, run.error or "Workflow processing failed", retry=False)
                else:
                    job_queue.complete(db, job_id)
        except Exception as exc:
            logger.exception("workflow job crashed", extra={"ctx": {"job_id": job_id, "run_id": run_id}})
            with SessionLocal() as db:
                job_queue.fail(db, job_id, f"{exc.__class__.__name__}: {exc}", retry=True)


def start_worker() -> WorkflowWorker:
    worker = WorkflowWorker()
    worker.start()
    return worker
