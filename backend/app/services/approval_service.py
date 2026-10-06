"""Human approval of suggested quotes. Nothing is 'sent' without a decision from an authorised person."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Approval, Extraction, Quote, User, WorkflowRun
from ..models.kb import utcnow
from . import audit, pdf_render

MIN_REASON = 10


def decide(db: Session, user: User, run_id: str, decision: str, reason: str | None) -> dict:
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")
    if user.role not in ("approver", "admin"):
        raise HTTPException(403, "Only approvers can decide on quotes")
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
    quote = db.scalar(select(Quote).where(Quote.run_id == run_id).with_for_update())
    if run is None or run.type != "rfq" or quote is None:
        raise HTTPException(404, "No quote found for this run")
    if quote.status != "pending_approval":
        raise HTTPException(409, f"Quote is already {quote.status}")
    if user.email == run.created_by and not get_settings().allow_self_approval:
        raise HTTPException(403, "Four-eyes rule: you cannot decide on a quote you created")
    reason = (reason or "").strip()
    criticals = [w["code"] for w in quote.warnings if w["severity"] == "critical"]
    if decision == "approved" and criticals and len(reason) < MIN_REASON:
        raise HTTPException(422, f"Critical warnings ({', '.join(criticals)}) require a written reason of at least {MIN_REASON} characters")
    if decision == "rejected" and len(reason) < 5:
        raise HTTPException(422, "A short reason is required to reject a quote")

    now = utcnow()
    db.add(Approval(run_id=run_id, approver=user.email, decision=decision, reason=reason, decided_at=now))
    quote.status = decision
    run.status = decision
    payload = {"decision": decision, "reason": reason, "critical_warnings_acknowledged": criticals,
               "price_per_kg": str(quote.price_per_kg), "total": str(quote.total)}
    audit.append(db, run_id, user.email, "quote_approved" if decision == "approved" else "quote_rejected", payload)
    if decision == "approved":
        quote.pdf_path = "generated-on-demand"  # rendered from the stored breakdown at download time (no files to lose)
        audit.append(db, run_id, "system", "quote_sent_simulated",
                     {"note": "Prototype: the quote PDF is available for download but nothing was emailed to a customer"})
    db.commit()
    return {"run_id": run_id, "status": decision, "approver": user.email}


def quote_pdf_bytes(db: Session, run_id: str) -> bytes:
    q = db.scalar(select(Quote).where(Quote.run_id == run_id))
    ap = db.scalar(select(Approval).where(Approval.run_id == run_id, Approval.decision == "approved"))
    if q is None or q.status != "approved" or ap is None:
        raise HTTPException(404, "Approved quote PDF not available")
    ex = db.scalar(select(Extraction).where(Extraction.run_id == run_id))
    customer = (ex.fields or {}).get("customer_name") if ex else None
    return pdf_render.quote_pdf(run_id, customer, q.breakdown, ap.approver, ap.decided_at.strftime("%Y-%m-%d %H:%M UTC"))
