"""Deterministic pricing logic. All money math uses Decimal; no LLM is involved.

The rules implemented here are written down in docs/BUSINESS_RULES.md. An independent
implementation lives in scripts/datagen/reference.py and is used only to compute eval ground truth.
"""
from __future__ import annotations

import datetime as dt
import statistics
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (HistoricalQuote, ManufacturingCost, MarginRule, Product, ShippingRate,
                      SpecParameter, Supplier, SupplierPrice)
from .warnings import warn

INSURANCE_RATE = Decimal("0.005")
HANDLING_PER_KG = Decimal("0.04")
QUOTE_VALIDITY_DAYS = 14
DEVIATION_THRESHOLD = 0.15
TIGHT_SLACK_DAYS = 7
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class ToolError(Exception):
    """A tool was called with invalid arguments or something it cannot do."""


def dec(v: Any) -> Decimal:
    return Decimal(str(v))


def r2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def r4(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def get_product(db: Session, code: str | None) -> Product | None:
    if not code:
        return None
    return db.scalar(select(Product).where(Product.code == code.strip().upper()))


def spec_min_purity(db: Session, product: Product) -> float:
    spec = db.scalar(select(SpecParameter).where(SpecParameter.product_id == product.id,
                                                 SpecParameter.parameter == "purity"))
    if spec is None or spec.min_value is None:
        raise ToolError(f"No purity specification for {product.code}")
    return float(spec.min_value)


def max_available_grade(db: Session, product: Product) -> float:
    grades = [g for (g,) in db.execute(select(SupplierPrice.purity_grade).where(SupplierPrice.product_id == product.id))]
    grades += [g for (g,) in db.execute(select(ManufacturingCost.purity_grade).where(ManufacturingCost.product_id == product.id))]
    return max(grades) if grades else 0.0


def supplier_options(db: Session, product: Product, qty_kg: float, purity_min: float,
                     rfq_date: dt.date) -> tuple[list[dict], dict]:
    excl = {"expired_price_rows": 0, "below_supplier_moq": 0}
    rows = db.execute(select(SupplierPrice, Supplier).join(Supplier, Supplier.id == SupplierPrice.supplier_id)
                      .where(SupplierPrice.product_id == product.id,
                             SupplierPrice.purity_grade >= purity_min)).all()
    groups: dict[tuple, list] = {}
    for sp, sup in rows:
        if sp.valid_until < rfq_date:
            excl["expired_price_rows"] += 1
            continue
        groups.setdefault((sup.id, sp.purity_grade), []).append((sp, sup))
    options = []
    for items in groups.values():
        sup = items[0][1]
        if qty_kg < sup.moq_kg:
            excl["below_supplier_moq"] += 1
            continue
        eligible = [sp for sp, _ in items if sp.tier_min_kg <= qty_kg]
        if not eligible:
            continue
        sp = max(eligible, key=lambda r: r.tier_min_kg)
        options.append({"option_id": f"SP:{sp.id}", "source_type": "supplier", "source_name": sup.name,
                        "source_code": sup.code, "country": sup.country, "purity_grade": sp.purity_grade,
                        "price_per_kg": dec(sp.price_per_kg), "tier_min_kg": sp.tier_min_kg,
                        "lead_time_days": sup.lead_time_days, "valid_until": sp.valid_until,
                        "moq_kg": sup.moq_kg, "source_ref": sp.source_ref})
    return options, excl


def plant_options(db: Session, product: Product, qty_kg: float, purity_min: float) -> tuple[list[dict], dict]:
    excl = {"plant_batch_or_capacity": 0}
    options = []
    for mc in db.scalars(select(ManufacturingCost).where(ManufacturingCost.product_id == product.id,
                                                         ManufacturingCost.purity_grade >= purity_min)):
        if qty_kg < mc.min_batch_kg or qty_kg > mc.capacity_kg_month:
            excl["plant_batch_or_capacity"] += 1
            continue
        options.append({"option_id": f"MF:{mc.id}", "source_type": "plant", "source_name": mc.plant_name,
                        "source_code": "PLANT", "country": mc.country, "purity_grade": mc.purity_grade,
                        "price_per_kg": dec(mc.cost_per_kg), "tier_min_kg": 0.0,
                        "lead_time_days": mc.lead_time_days, "valid_until": None,
                        "moq_kg": mc.min_batch_kg, "source_ref": mc.source_ref})
    return options, excl


def all_options(db: Session, product: Product, qty_kg: float, purity_min: float,
                rfq_date: dt.date) -> tuple[list[dict], dict]:
    s_opts, s_ex = supplier_options(db, product, qty_kg, purity_min, rfq_date)
    p_opts, p_ex = plant_options(db, product, qty_kg, purity_min)
    return s_opts + p_opts, {**s_ex, **p_ex}


def attach_shipping(db: Session, options: list[dict], term: str, dest_port: str | None) -> list[dict]:
    rates = {(r.origin_country, r.dest_port): r for r in db.scalars(select(ShippingRate))}
    usable = []
    for o in options:
        rate = None
        transit = 0
        if term == "CIF":
            rate = rates.get((o["country"], dest_port))
            if rate is None:
                continue
            transit = rate.transit_days
        usable.append({**o, "rate": rate, "transit_days": transit, "days_needed": o["lead_time_days"] + transit})
    return usable


def pick_option(usable: list[dict], available_days: int | None) -> tuple[dict, bool]:
    """Cheapest option among those that meet the deadline; if none do, the cheapest overall."""
    pool, ok = usable, True
    if available_days is not None:
        meets = [o for o in usable if o["days_needed"] <= available_days]
        if meets:
            pool = meets
        else:
            ok = False
    best = min(pool, key=lambda o: (o["price_per_kg"], o["lead_time_days"], o["option_id"]))
    return best, ok


def margin_rule(db: Session, category: str, qty_kg: float, tier: str) -> MarginRule:
    rules = [m for m in db.scalars(select(MarginRule).where(MarginRule.category == category,
                                                            MarginRule.customer_tier == tier))
             if m.qty_tier_min_kg <= qty_kg]
    if not rules:
        raise ToolError(f"No margin rule for {category}/{tier}")
    return max(rules, key=lambda m: m.qty_tier_min_kg)


def history_stats(db: Session, product: Product) -> list[Decimal]:
    return [dec(q) for (q,) in db.execute(select(HistoricalQuote.quoted_price_per_kg)
                                          .where(HistoricalQuote.product_id == product.id))]


def _public_option(o: dict) -> dict:
    return {"option_id": o["option_id"], "source_type": o["source_type"], "source_name": o["source_name"],
            "country": o["country"], "purity_grade": o["purity_grade"], "price_per_kg": str(o["price_per_kg"]),
            "lead_time_days": o["lead_time_days"], "transit_days": o.get("transit_days"),
            "days_needed": o.get("days_needed"), "moq_kg": o["moq_kg"],
            "valid_until": o["valid_until"].isoformat() if o["valid_until"] else None,
            "source_ref": o["source_ref"]}


def _sorted_warnings(codes: list[str]) -> list[dict]:
    uniq = sorted(set(codes))
    ws = [warn(c) for c in uniq]
    return sorted(ws, key=lambda w: (SEVERITY_ORDER[w["severity"]], w["code"]))


def run_pricing(db: Session, *, product_code: str | None, qty_kg: float | None, purity_min: float | None,
                incoterm: str | None, destination_port: str | None, required_date: dt.date | None,
                rfq_date: dt.date, customer_tier: str = "standard", option_id: str | None = None) -> dict:
    """Price an RFQ. Returns status ('ready_for_review' | 'needs_info'), warnings, breakdown, sources."""
    codes: list[str] = []
    missing: list[str] = []
    result: dict[str, Any] = {"status": "needs_info", "missing": missing, "breakdown": None, "sources": [],
                              "options": [], "exclusions": {}}

    product = get_product(db, product_code)
    if not product_code:
        missing.append("product")
    elif product is None:
        codes.append("UNKNOWN_PRODUCT")
    if qty_kg is None:
        missing.append("quantity")
    term = (incoterm or "CIF").upper()
    if incoterm is None or term not in ("FOB", "CIF"):
        term = term if term in ("FOB", "CIF") else "CIF"
        codes.append("INCOTERM_ASSUMED")
    if term == "CIF" and not destination_port:
        missing.append("destination")
    if missing:
        codes.append("MISSING_FIELD")
    if product is None or qty_kg is None or (term == "CIF" and not destination_port):
        result["warnings"] = _sorted_warnings(codes)
        return result

    if purity_min is None:
        purity_min = spec_min_purity(db, product)
        codes.append("PURITY_ASSUMED")
    if required_date is None:
        codes.append("DELIVERY_DATE_MISSING")

    options, exclusions = all_options(db, product, qty_kg, purity_min, rfq_date)
    result["exclusions"] = exclusions
    if max_available_grade(db, product) < purity_min:
        codes.append("PURITY_UNAVAILABLE")
        result["warnings"] = _sorted_warnings(codes)
        return result

    usable = attach_shipping(db, options, term, destination_port)
    result["options"] = [_public_option(o) for o in sorted(usable, key=lambda o: o["price_per_kg"])]
    if not usable:
        codes.append("NO_SHIPPING_RATE" if (options and term == "CIF") else "NO_FEASIBLE_SOURCE")
        result["warnings"] = _sorted_warnings(codes)
        return result

    available = (required_date - rfq_date).days if required_date else None
    recommended, _ = pick_option(usable, available)
    if option_id:
        chosen = next((o for o in usable if o["option_id"] == option_id), None)
        if chosen is None:
            raise ToolError(f"option_id {option_id} is not a feasible source for this request")
        if chosen["option_id"] != recommended["option_id"] and \
                (chosen["price_per_kg"], chosen["lead_time_days"]) > (recommended["price_per_kg"],
                                                                        recommended["lead_time_days"]):
            codes.append("OPTION_NOT_CHEAPEST")
    else:
        chosen = recommended

    if available is not None:
        if chosen["days_needed"] > available:
            codes.append("DEADLINE_INFEASIBLE")
        elif available - chosen["days_needed"] < TIGHT_SLACK_DAYS:
            codes.append("DEADLINE_TIGHT")
    if chosen["valid_until"] and chosen["valid_until"] < rfq_date + dt.timedelta(days=QUOTE_VALIDITY_DAYS):
        codes.append("PRICE_VALIDITY_SHORT")

    q = dec(qty_kg)
    cost_total = r2(chosen["price_per_kg"] * q)
    freight = surcharge = insurance = Decimal("0.00")
    rate = chosen["rate"]
    lines = [{"label": "Material cost", "formula": f"{qty_kg:g} kg x {chosen['price_per_kg']} USD/kg",
              "amount": str(cost_total)}]
    if term == "CIF":
        freight = r2(max(dec(rate.rate_per_kg) * q, dec(rate.min_charge)))
        lines.append({"label": "Ocean freight", "formula": f"max({rate.rate_per_kg} x {qty_kg:g} kg, min {rate.min_charge})",
                      "amount": str(freight)})
        if product.hazmat_class:
            surcharge = r2(freight * dec(rate.hazmat_surcharge_pct))
            lines.append({"label": f"Hazmat surcharge (Class {product.hazmat_class})",
                          "formula": f"{freight} x {rate.hazmat_surcharge_pct}", "amount": str(surcharge)})
        insurance = r2(cost_total * INSURANCE_RATE)
        lines.append({"label": "Insurance", "formula": f"{cost_total} x {INSURANCE_RATE}", "amount": str(insurance)})
    if product.hazmat_class:
        codes.append("HAZMAT")
    handling = r2(HANDLING_PER_KG * q)
    lines.append({"label": "Handling", "formula": f"{qty_kg:g} kg x {HANDLING_PER_KG}", "amount": str(handling)})
    landed = cost_total + freight + surcharge + insurance + handling

    rule = margin_rule(db, product.category, qty_kg, customer_tier)
    margin = dec(rule.margin_pct)
    total = r2(landed / (Decimal("1") - margin))
    ppk = r4(total / q)

    hist = history_stats(db, product)
    hist_info: dict[str, Any] = {"n": len(hist), "median": None, "deviation_pct": None}
    if len(hist) >= 2:
        med = statistics.median(hist)
        dev = float((ppk - med) / med)
        hist_info.update(median=str(r4(med)), deviation_pct=round(dev * 100, 1))
        if abs(dev) > DEVIATION_THRESHOLD:
            codes.append("DEVIATION_FROM_HISTORY")

    sources = [{"ref": product.source_ref, "what": f"Product {product.code}"},
               {"ref": chosen["source_ref"], "what": f"{'Supplier price' if chosen['source_type'] == 'supplier' else 'Manufacturing cost'}: {chosen['source_name']}"},
               {"ref": rule.source_ref, "what": f"Margin rule {product.category} / {customer_tier} / tier >= {rule.qty_tier_min_kg:g} kg"}]
    if rate is not None:
        sources.append({"ref": rate.source_ref, "what": f"Shipping rate {rate.origin_country} -> {rate.dest_port}"})

    result.update(
        status="ready_for_review", sources=sources, selected_option=_public_option(chosen),
        breakdown={
            "product_code": product.code, "product_name": product.name, "qty_kg": qty_kg,
            "purity_min": purity_min, "incoterm": term, "destination_port": destination_port,
            "lines": lines, "landed_cost": str(landed), "margin_pct": str(margin),
            "total": str(total), "price_per_kg": str(ppk), "currency": "USD",
            "quote_valid_until": (rfq_date + dt.timedelta(days=QUOTE_VALIDITY_DAYS)).isoformat(),
            "days_needed": chosen["days_needed"], "available_days": available, "history": hist_info,
            "shipping": None if rate is None else {"rate_id": rate.id, "rate_per_kg": str(rate.rate_per_kg),
                                                  "min_charge": str(rate.min_charge),
                                                  "transit_days": rate.transit_days},
        })
    result["warnings"] = _sorted_warnings(codes)
    return result
