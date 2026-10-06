"""Export-document workflow: one structured order -> four documents -> consistency gate -> PDFs.

Documents are never rendered while the set is inconsistent: the run is 'blocked' and the findings are shown.
"""
from __future__ import annotations

import copy
import datetime as dt
import time
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (ConsistencyFinding, ExportDocument, Extraction, Quote, ToolCall, User, WorkflowRun)
from ..tools.doc_validation import DOC_ORDER, check_documents
from ..tools.export_docs import ExportOrder, generate_all
from ..tools.pricing_engine import ToolError
from . import audit, pdf_render, runs

EDITABLE = {"net_quantity_kg", "gross_weight_kg", "packages_count", "total_value", "unit_price_per_kg", "incoterm",
            "origin_country", "destination_port", "consignee.name", "product.hs_code", "product.code",
            "net_weight_per_package_kg"}


def order_from_quote(db: Session, quote_run_id: str) -> ExportOrder:
    q = db.scalar(select(Quote).where(Quote.run_id == quote_run_id))
    if q is None or q.status != "approved":
        raise HTTPException(409, "Export documents can only be generated from an approved quote")
    ex = db.scalar(select(Extraction).where(Extraction.run_id == quote_run_id))
    fields = (ex.fields if ex else {}) or {}
    calc = db.scalars(select(ToolCall).where(ToolCall.run_id == quote_run_id, ToolCall.tool == "calculate_quote")
                      .order_by(ToolCall.seq.desc())).first()
    sel = ((calc.result or {}).get("selected_option") if calc else None) or {}
    b = q.breakdown
    if not sel.get("country") or not b.get("destination_port"):
        raise HTTPException(422, "The quote has no destination port or origin country; use manual order entry")
    return ExportOrder(order_ref=quote_run_id.replace("rfq-", "").upper(), date=dt.date.today(),
                       customer_name=fields.get("customer_name") or "Customer (name missing in RFQ)",
                       product_code=b["product_code"], qty_kg=b["qty_kg"], unit_price_per_kg=Decimal(str(q.price_per_kg)),
                       total_value=Decimal(str(q.total)), currency=q.currency, incoterm=b["incoterm"],
                       origin_country=sel["country"], destination_port=b["destination_port"])


def _store_findings(db: Session, run_id: str, result: dict) -> None:
    db.execute(delete(ConsistencyFinding).where(ConsistencyFinding.run_id == run_id))
    for f in result["findings"]:
        db.add(ConsistencyFinding(run_id=run_id, **f))


def generate(db: Session, user: User, order: ExportOrder, parent: str | None = None) -> dict:
    started = time.perf_counter()
    run = runs.new_run(db, "export_docs", user.email, "rules", parent=parent)
    try:
        docs = generate_all(db, order)
    except ToolError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None
    for t in DOC_ORDER:
        db.add(ExportDocument(run_id=run.id, doc_type=t, payload=docs[t], file_name=f"{t}-{order.order_ref}.pdf"))
    audit.append(db, run.id, user.email, "documents_generated",
                 {"order": order.model_dump(mode="json"), "doc_types": DOC_ORDER, "parent_run_id": parent})
    return _evaluate(db, run, docs, started, actor="system")


def _evaluate(db: Session, run: WorkflowRun, docs: dict, started: float, actor: str) -> dict:
    result = check_documents(docs)
    _store_findings(db, run.id, result)
    status = "completed" if result["consistent"] else "blocked"
    audit.append(db, run.id, "system", "consistency_checked",
                 {"consistent": result["consistent"], "findings": [f"{f['field']}: {f['value_a']} vs {f['value_b']}" for f in result["findings"]]})
    if status == "blocked":
        audit.append(db, run.id, "system", "documents_blocked",
                     {"reason": "cross-document inconsistency; PDFs are not generated until fixed"})
    runs.finish(db, run, status, started, metrics={"findings": len(result["findings"])})
    return {"run_id": run.id, "status": status, "findings": result["findings"]}


def _set_path(doc: dict, path: str, value) -> None:
    cur = doc
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur[p]
    old = cur.get(parts[-1])
    if old is None:
        raise HTTPException(422, f"Field '{path}' does not exist on this document")
    if isinstance(old, (int, float)) and not isinstance(old, bool):
        try:
            value = float(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            raise HTTPException(422, f"'{path}' must be a number") from None
        if value <= 0:
            raise HTTPException(422, f"'{path}' must be positive")
        if path == "packages_count":
            value = int(value)
    else:
        value = str(value).strip()
        if not value or len(value) > 200:
            raise HTTPException(422, f"'{path}' must be 1-200 characters")
    cur[parts[-1]] = value


def apply_edit(db: Session, user: User, run_id: str, doc_type: str, field: str, value) -> dict:
    run = db.get(WorkflowRun, run_id)
    if run is None or run.type != "export_docs":
        raise HTTPException(404, "Export run not found")
    if field not in EDITABLE:
        raise HTTPException(422, f"Field '{field}' is not editable. Editable: {', '.join(sorted(EDITABLE))}")
    rows = {d.doc_type: d for d in db.scalars(select(ExportDocument).where(ExportDocument.run_id == run_id))}
    if doc_type not in rows:
        raise HTTPException(404, f"No {doc_type} in this run")
    payload = copy.deepcopy(rows[doc_type].payload)
    old_val = _peek(payload, field)
    _set_path(payload, field, value)
    rows[doc_type].payload = payload
    audit.append(db, run_id, user.email, "document_edited",
                 {"doc_type": doc_type, "field": field, "from": old_val, "to": _peek(payload, field)})
    docs = {t: r.payload for t, r in rows.items()}
    return _evaluate(db, run, docs, time.perf_counter(), actor=user.email)


def _peek(doc: dict, path: str):
    cur = doc
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def render(db: Session, run_id: str, doc_type: str) -> tuple[bytes, str]:
    run = db.get(WorkflowRun, run_id)
    row = db.scalar(select(ExportDocument).where(ExportDocument.run_id == run_id, ExportDocument.doc_type == doc_type))
    if run is None or row is None:
        raise HTTPException(404, "Document not found")
    if run.status != "completed":
        raise HTTPException(409, "Documents are blocked until the cross-document inconsistencies are resolved")
    return pdf_render.export_pdf(row.payload), row.file_name or f"{doc_type}.pdf"
