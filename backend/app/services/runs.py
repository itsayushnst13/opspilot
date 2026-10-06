"""Workflow run helpers: ids, stages, completion, serialisation."""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Approval, AuditLog, COACheck, ConsistencyFinding, ExportDocument, Extraction, Quote,
                      ToolCall, UploadedFile, WorkflowRun)
from ..models.kb import utcnow


def new_run(db: Session, type_: str, user_email: str, mode: str, parent: str | None = None) -> WorkflowRun:
    run = WorkflowRun(id=f"{type_}-{secrets.token_hex(4)}", type=type_, status="processing", mode=mode,
                      created_by=user_email, parent_run_id=parent, metrics={"stage": "queued"})
    db.add(run)
    db.flush()
    return run


def set_stage(db: Session, run: WorkflowRun, stage: str) -> None:
    run.metrics = {**(run.metrics or {}), "stage": stage}
    db.commit()


def finish(db: Session, run: WorkflowRun, status: str, started: float, error: str | None = None,
           metrics: dict | None = None) -> None:
    import time

    run.status = status
    run.finished_at = utcnow()
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.error = error
    run.metrics = {**(run.metrics or {}), **(metrics or {}), "stage": "done" if error is None else "failed"}
    db.commit()


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else v


def run_summary(run: WorkflowRun) -> dict:
    return {"id": run.id, "type": run.type, "status": run.status, "mode": run.mode, "created_by": run.created_by,
            "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at), "latency_ms": run.latency_ms,
            "parent_run_id": run.parent_run_id, "metrics": run.metrics or {}, "error": run.error}


def run_detail(db: Session, run_id: str) -> dict | None:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        return None
    out: dict[str, Any] = {"run": run_summary(run)}
    out["files"] = [{"filename": f.filename, "size": f.size, "sha256": f.sha256, "mime": f.mime}
                    for f in db.scalars(select(UploadedFile).where(UploadedFile.run_id == run_id))]
    ex = db.scalar(select(Extraction).where(Extraction.run_id == run_id))
    out["extraction"] = None if ex is None else {"method": ex.method, "raw": ex.raw, "fields": ex.fields,
                                                  "missing": ex.missing, "issues": ex.issues}
    out["tool_calls"] = [{"seq": t.seq, "tool": t.tool, "args": t.args, "result": t.result, "ok": t.ok,
                          "error": t.error, "duration_ms": t.duration_ms}
                         for t in db.scalars(select(ToolCall).where(ToolCall.run_id == run_id).order_by(ToolCall.seq))]
    q = db.scalar(select(Quote).where(Quote.run_id == run_id))
    out["quote"] = None if q is None else {
        "status": q.status, "breakdown": q.breakdown, "price_per_kg": str(q.price_per_kg), "total": str(q.total),
        "currency": q.currency, "warnings": q.warnings, "sources": q.sources,
        "reasoning_summary": q.reasoning_summary, "has_pdf": bool(q.pdf_path)}
    out["approvals"] = [{"approver": a.approver, "decision": a.decision, "reason": a.reason,
                         "decided_at": _iso(a.decided_at)}
                        for a in db.scalars(select(Approval).where(Approval.run_id == run_id).order_by(Approval.id))]
    c = db.scalar(select(COACheck).where(COACheck.run_id == run_id))
    out["coa"] = None if c is None else {"product_code": c.product_code, "batch_no": c.batch_no,
                                         "verdict": c.verdict, "results": c.results,
                                         "explanation": c.explanation, "extracted": c.extracted}
    out["documents"] = [{"doc_type": d.doc_type, "payload": d.payload, "file_name": d.file_name}
                        for d in db.scalars(select(ExportDocument).where(ExportDocument.run_id == run_id).order_by(ExportDocument.id))]
    out["findings"] = [{"field": f.field, "doc_a": f.doc_a, "doc_b": f.doc_b, "value_a": f.value_a,
                        "value_b": f.value_b, "severity": f.severity, "message": f.message}
                       for f in db.scalars(select(ConsistencyFinding).where(ConsistencyFinding.run_id == run_id))]
    out["audit"] = audit_rows(db, run_id=run_id)
    return out


def audit_rows(db: Session, run_id: str | None = None, limit: int = 500) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if run_id:
        stmt = select(AuditLog).where(AuditLog.run_id == run_id).order_by(AuditLog.id)
    return [{"id": a.id, "ts": _iso(a.ts), "run_id": a.run_id, "actor": a.actor, "action": a.action,
             "payload": a.payload, "hash": a.hash} for a in db.scalars(stmt)]
