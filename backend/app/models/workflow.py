"""Workflow, approval, audit and evaluation tables."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric,
                        String, Text, event)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .kb import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))  # analyst | approver | admin


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    type: Mapped[str] = mapped_column(String(20), index=True)  # rfq | coa | export_docs
    status: Mapped[str] = mapped_column(String(24), index=True)
    mode: Mapped[str] = mapped_column(String(10), default="rules")  # rules | llm
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_run_id: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(80))
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    method: Mapped[str] = mapped_column(String(20))  # rules | llm
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing: Mapped[list[Any]] = mapped_column(JSON, default=list)
    issues: Mapped[list[Any]] = mapped_column(JSON, default=list)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(60))
    args: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24))  # pending_approval | approved | rejected
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    pdf_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    approver: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(10))  # approved | rejected
    reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class COACheck(Base):
    __tablename__ = "coa_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), unique=True, index=True)
    product_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    batch_no: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    verdict: Mapped[str] = mapped_column(String(20))  # PASS | FAIL | REVIEW REQUIRED
    results: Mapped[list[Any]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    extracted: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ExportDocument(Base):
    __tablename__ = "export_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    file_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConsistencyFinding(Base):
    __tablename__ = "consistency_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    field: Mapped[str] = mapped_column(String(60))
    doc_a: Mapped[str] = mapped_column(String(40))
    doc_b: Mapped[str] = mapped_column(String(40))
    value_a: Mapped[str] = mapped_column(String(200))
    value_b: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    """Append-only, hash-chained audit trail."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    run_id: Mapped[Optional[str]] = mapped_column(String(24), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(mapper, connection, target):  # pragma: no cover - exercised in tests
    raise RuntimeError("audit_log is append-only: updates are not allowed")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(mapper, connection, target):  # pragma: no cover - exercised in tests
    raise RuntimeError("audit_log is append-only: deletes are not allowed")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
