from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..models import Quote, ShippingRate, User, WorkflowRun
from ..services import export_service, runs
from ..tools.export_docs import ExportOrder
from .deps import upload_limit

router = APIRouter(prefix="/api/documents", tags=["documents"])


class GenerateIn(BaseModel):
    quote_run_id: str | None = None
    order: ExportOrder | None = None


class EditIn(BaseModel):
    doc_type: str
    field: str
    value: Any


@router.get("/sample-order")
def sample_order(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A ready-made order (5 MT CHEM-X01 to Houston) for trying the document generator without a quote."""
    origin = db.scalar(select(ShippingRate.origin_country).where(ShippingRate.dest_port == "Houston").order_by(ShippingRate.id))
    if origin is None:
        raise HTTPException(404, "No Houston shipping rate in reference data")
    qty, price = 5000.0, Decimal("2.4500")
    return ExportOrder(order_ref="DEMO-001", date=dt.date.today(), customer_name="Gulf Coast Polymers LLC",
                       product_code="CHEM-X01", qty_kg=qty, unit_price_per_kg=price,
                       total_value=(price * Decimal(str(qty))).quantize(Decimal("0.01")), origin_country=origin,
                       destination_port="Houston").model_dump(mode="json")


@router.post("/generate", status_code=201)
def generate(body: GenerateIn, user: User = Depends(upload_limit), db: Session = Depends(get_db)):
    if (body.quote_run_id is None) == (body.order is None):
        raise HTTPException(422, "Provide exactly one of quote_run_id or order")
    order = export_service.order_from_quote(db, body.quote_run_id) if body.quote_run_id else body.order
    result = export_service.generate(db, user, order, parent=body.quote_run_id)
    return result


@router.get("")
def list_runs(limit: int = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(WorkflowRun).where(WorkflowRun.type == "export_docs").order_by(WorkflowRun.created_at.desc())
                      .limit(min(max(limit, 1), 200))).all()
    return [runs.run_summary(r) for r in rows]


@router.get("/{run_id}")
def get_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = runs.run_detail(db, run_id)
    if d is None or d["run"]["type"] != "export_docs":
        raise HTTPException(404, "Export run not found")
    d["editable_fields"] = sorted(export_service.EDITABLE)
    return d


@router.patch("/{run_id}")
def edit(run_id: str, body: EditIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = export_service.apply_edit(db, user, run_id, body.doc_type, body.field, body.value)
    return result


@router.get("/{run_id}/{doc_type}.pdf")
def download(run_id: str, doc_type: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data, name = export_service.render(db, run_id, doc_type)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
