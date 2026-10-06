"""COA vs specification comparison. Deterministic; exact Decimal arithmetic."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SpecParameter
from .pricing_engine import ToolError, dec, get_product

RANK = {"PASS": 0, "REVIEW REQUIRED": 1, "FAIL": 2}


class CheckQualityArgs(BaseModel):
    product_code: str
    batch_no: str | None = None
    measurements: dict[str, float | None] = Field(description="Canonical parameter name -> measured value")


def _limit_text(s: SpecParameter) -> str:
    unit = f" {s.unit}" if s.unit else ""
    if s.operator == ">=":
        return f">= {s.min_value:g}{unit}"
    if s.operator == "<=":
        return f"<= {s.max_value:g}{unit}"
    return f"{s.min_value:g} - {s.max_value:g}{unit}"


def check_quality(db: Session, a: CheckQualityArgs) -> dict:
    product = get_product(db, a.product_code)
    if product is None:
        raise ToolError(f"Unknown product code: {a.product_code}")
    specs = db.scalars(select(SpecParameter).where(SpecParameter.product_id == product.id)
                       .order_by(SpecParameter.id)).all()
    results, overall = [], "PASS"
    for s in specs:
        raw = a.measurements.get(s.parameter)
        limit = _limit_text(s)
        row = {"parameter": s.parameter, "spec": limit, "actual": raw, "unit": s.unit, "critical": s.critical,
               "review_margin": s.review_margin, "source_ref": s.source_ref}
        if raw is None:
            row.update(status="REVIEW REQUIRED", reason=f"{s.parameter} is required by the specification ({limit}) but was not reported")
        else:
            v = dec(raw)
            lo = dec(s.min_value) if s.min_value is not None else None
            hi = dec(s.max_value) if s.max_value is not None else None
            miss = Decimal("0")
            if lo is not None and v < lo:
                miss = lo - v
            elif hi is not None and v > hi:
                miss = v - hi
            margin = dec(s.review_margin)
            if miss == 0:
                row.update(status="PASS", reason=f"{s.parameter} {raw:g} meets {limit}")
            elif miss <= margin:
                row.update(status="REVIEW REQUIRED",
                           reason=f"{s.parameter} {raw:g} misses {limit} by {miss:g}, within the review margin {margin:g}")
            elif s.critical:
                row.update(status="FAIL",
                           reason=f"{s.parameter} {raw:g} misses {limit} by {miss:g}, beyond the review margin {margin:g} (critical parameter)")
            else:
                row.update(status="REVIEW REQUIRED",
                           reason=f"{s.parameter} {raw:g} misses {limit} by {miss:g} (non-critical parameter)")
        results.append(row)
        if RANK[row["status"]] > RANK[overall]:
            overall = row["status"]
    notes = []
    extra = sorted(set(a.measurements) - {s.parameter for s in specs})
    if extra:
        notes.append(f"Parameters on the COA without a specification limit were ignored: {', '.join(extra)}")
    if not a.batch_no:
        notes.append("Batch number is missing from the COA")
        if RANK[overall] < RANK["REVIEW REQUIRED"]:
            overall = "REVIEW REQUIRED"
    failed = [r for r in results if r["status"] != "PASS"]
    if failed:
        explanation = f"{overall}: " + "; ".join(r["reason"] for r in failed)
    else:
        explanation = "PASS: every specified parameter is within limits."
    if notes:
        explanation += " Note: " + "; ".join(notes) + "."
    return {"verdict": overall, "results": results, "explanation": explanation, "notes": notes,
            "product": {"code": product.code, "name": product.name}}
