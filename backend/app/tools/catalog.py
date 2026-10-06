"""Catalogue / pricing tools exposed to the agent. All results are plain JSON-serialisable dicts."""
from __future__ import annotations

import datetime as dt
import difflib
import re

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ShippingRate, SpecParameter
from .pricing_engine import (ToolError, all_options, attach_shipping, dec, get_product, max_available_grade,
                             pick_option, r2, run_pricing, spec_min_purity, supplier_options, plant_options,
                             _public_option)


class SearchProductArgs(BaseModel):
    query: str = Field(description="Product code (e.g. CHEM-X01) or product name")
    limit: int = Field(default=5, ge=1, le=10)


class ProductSpecArgs(BaseModel):
    product_code: str = Field(description="Product code, e.g. CHEM-X01")


class SourceArgs(BaseModel):
    product_code: str
    qty_kg: float = Field(gt=0, description="Quantity in kilograms")
    purity_min: float | None = Field(default=None, description="Minimum purity in percent; omit to use the spec minimum")
    rfq_date: dt.date = Field(description="RFQ date, YYYY-MM-DD (used for price validity)")


class RecommendArgs(SourceArgs):
    incoterm: str | None = None
    destination_port: str | None = None
    required_date: dt.date | None = Field(default=None, description="Required delivery date, YYYY-MM-DD")


class ShippingArgs(BaseModel):
    origin_country: str
    dest_port: str
    qty_kg: float = Field(gt=0)
    product_code: str | None = None


class CalcQuoteArgs(BaseModel):
    product_code: str | None = None
    qty_kg: float | None = Field(default=None, gt=0, description="Quantity in kilograms")
    purity_min: float | None = Field(default=None, description="Minimum purity in percent")
    rfq_date: dt.date = Field(description="RFQ date, YYYY-MM-DD")
    incoterm: str | None = None
    destination_port: str | None = None
    required_date: dt.date | None = Field(default=None, description="Required delivery date, YYYY-MM-DD")
    option_id: str | None = Field(default=None, description="Source option id from get_supplier_price/get_manufacturing_cost, e.g. SP:12 or MF:3")
    customer_tier: str = "standard"


def _need_product(db: Session, code: str) -> Product:
    p = get_product(db, code)
    if p is None:
        raise ToolError(f"Unknown product code: {code}")
    return p


def search_product(db: Session, a: SearchProductArgs) -> dict:
    q = a.query.strip()
    qn = re.sub(r"[^a-z0-9]+", " ", q.lower()).strip()
    code_like = re.sub(r"[\s_]+", "-", q.upper())
    out = []
    for p in db.scalars(select(Product)):
        name = re.sub(r"[^a-z0-9]+", " ", p.name.lower()).strip()
        if code_like == p.code:
            score = 1.0
        elif qn == name:
            score = 0.98
        else:
            toks_q, toks_n = set(qn.split()), set(name.split())
            overlap = len(toks_q & toks_n) / max(1, len(toks_n))
            score = max(overlap * 0.9, difflib.SequenceMatcher(None, qn, name).ratio() * 0.9)
        if score >= 0.5:
            out.append({"code": p.code, "name": p.name, "category": p.category, "score": round(score, 3),
                        "source_ref": p.source_ref})
    out.sort(key=lambda r: -r["score"])
    return {"matches": out[: a.limit]}


def get_product_spec(db: Session, a: ProductSpecArgs) -> dict:
    p = _need_product(db, a.product_code)
    specs = db.scalars(select(SpecParameter).where(SpecParameter.product_id == p.id).order_by(SpecParameter.id)).all()
    return {"product": {"code": p.code, "name": p.name, "category": p.category, "hazmat_class": p.hazmat_class,
                        "hs_code": p.hs_code, "description": p.description, "source_ref": p.source_ref},
            "specifications": [{"parameter": s.parameter, "operator": s.operator, "min": s.min_value,
                                "max": s.max_value, "unit": s.unit, "critical": s.critical,
                                "review_margin": s.review_margin, "source_ref": s.source_ref} for s in specs],
            "default_purity_min": spec_min_purity(db, p), "max_available_grade": max_available_grade(db, p)}


def get_supplier_price(db: Session, a: SourceArgs) -> dict:
    p = _need_product(db, a.product_code)
    purity = a.purity_min if a.purity_min is not None else spec_min_purity(db, p)
    opts, excl = supplier_options(db, p, a.qty_kg, purity, a.rfq_date)
    return {"purity_min_used": purity, "options": [_public_option(o) for o in sorted(opts, key=lambda o: o["price_per_kg"])],
            "exclusions": excl}


def get_manufacturing_cost(db: Session, a: SourceArgs) -> dict:
    p = _need_product(db, a.product_code)
    purity = a.purity_min if a.purity_min is not None else spec_min_purity(db, p)
    opts, excl = plant_options(db, p, a.qty_kg, purity)
    return {"purity_min_used": purity, "options": [_public_option(o) for o in sorted(opts, key=lambda o: o["price_per_kg"])],
            "exclusions": excl}


def get_shipping_cost(db: Session, a: ShippingArgs) -> dict:
    rate = db.scalar(select(ShippingRate).where(ShippingRate.origin_country == a.origin_country,
                                                ShippingRate.dest_port == a.dest_port))
    if rate is None:
        return {"found": False, "reason": f"No rate for {a.origin_country} -> {a.dest_port}"}
    q = dec(a.qty_kg)
    freight = r2(max(dec(rate.rate_per_kg) * q, dec(rate.min_charge)))
    haz = None
    if a.product_code:
        p = get_product(db, a.product_code)
        if p and p.hazmat_class:
            haz = {"class": p.hazmat_class, "surcharge_pct": str(rate.hazmat_surcharge_pct),
                   "surcharge": str(r2(freight * dec(rate.hazmat_surcharge_pct)))}
    return {"found": True, "rate_id": rate.id, "rate_per_kg": str(rate.rate_per_kg), "min_charge": str(rate.min_charge),
            "transit_days": rate.transit_days, "freight": str(freight), "hazmat": haz, "source_ref": rate.source_ref}


def recommend_source(db: Session, a: RecommendArgs) -> dict:
    p = _need_product(db, a.product_code)
    purity = a.purity_min if a.purity_min is not None else spec_min_purity(db, p)
    term = (a.incoterm or "CIF").upper()
    term = term if term in ("FOB", "CIF") else "CIF"
    options, excl = all_options(db, p, a.qty_kg, purity, a.rfq_date)
    usable = attach_shipping(db, options, term, a.destination_port)
    if not usable:
        return {"recommended_option_id": None, "options": [], "exclusions": excl,
                "reason": "No feasible source (check quantity, purity, price validity or shipping lane)"}
    available = (a.required_date - a.rfq_date).days if a.required_date else None
    best, deadline_ok = pick_option(usable, available)
    return {"recommended_option_id": best["option_id"], "meets_deadline": deadline_ok, "available_days": available,
            "options": [_public_option(o) for o in sorted(usable, key=lambda o: o["price_per_kg"])], "exclusions": excl}


def calculate_quote(db: Session, a: CalcQuoteArgs) -> dict:
    res = run_pricing(db, product_code=a.product_code, qty_kg=a.qty_kg, purity_min=a.purity_min,
                      incoterm=a.incoterm, destination_port=a.destination_port, required_date=a.required_date,
                      rfq_date=a.rfq_date, customer_tier=a.customer_tier, option_id=a.option_id)
    return res
