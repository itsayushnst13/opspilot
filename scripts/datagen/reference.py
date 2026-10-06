"""Independent reference implementation of the business rules.

Used only to compute ground truth for evals. It deliberately does NOT import anything from
backend/app so that the evals compare two separate implementations of the same written rules
(see docs/BUSINESS_RULES.md).
"""
from __future__ import annotations

import datetime as dt
import statistics
from decimal import ROUND_HALF_UP, Decimal

from .catalog import World

INSURANCE_RATE = Decimal("0.005")
HANDLING_PER_KG = Decimal("0.04")
QUOTE_VALIDITY_DAYS = 14
DEVIATION_THRESHOLD = 0.15
TIGHT_SLACK_DAYS = 7


def r2(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def r4(x: Decimal) -> Decimal:
    return Decimal(x).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _highest_tier(rows: list[dict], qty: float, key: str) -> dict | None:
    ok = [r for r in rows if float(r[key]) <= qty]
    return max(ok, key=lambda r: float(r[key])) if ok else None


def reference_quote(world: World, product_code: str | None, qty_kg: float | None,
                    purity_min: float | None, dest_port: str | None,
                    required_date: dt.date | None, rfq_date: dt.date,
                    incoterm: str | None, customer_tier: str = "standard") -> dict:
    out: dict = {"status": "needs_info", "warnings": set(), "missing": [], "price_per_kg": None,
                 "total": None, "option": None}
    prod = next((p for p in world.products if p["code"] == product_code), None)
    if product_code is None:
        out["missing"].append("product")
    elif prod is None:
        out["warnings"].add("UNKNOWN_PRODUCT")
    if qty_kg is None:
        out["missing"].append("quantity")
    term = (incoterm or "CIF").upper()
    if term not in ("FOB", "CIF"):
        term = "CIF"
        out["warnings"].add("INCOTERM_ASSUMED")
    if incoterm is None:
        out["warnings"].add("INCOTERM_ASSUMED")
    if term == "CIF" and dest_port is None:
        out["missing"].append("destination")
    if out["missing"]:
        out["warnings"].add("MISSING_FIELD")
    if prod is None or qty_kg is None or (term == "CIF" and dest_port is None):
        return out

    if purity_min is None:
        spec = next(s for s in world.specs if s["product_code"] == product_code and s["parameter"] == "purity")
        purity_min = float(spec["min_value"])
        out["warnings"].add("PURITY_ASSUMED")
    if required_date is None:
        out["warnings"].add("DELIVERY_DATE_MISSING")

    # --- source options
    options = []
    suppliers = {s["code"]: s for s in world.suppliers}
    groups: dict[tuple, list[dict]] = {}
    for row in world.prices:
        if row["product_code"] != product_code:
            continue
        if float(row["purity_grade"]) < purity_min:
            continue
        if dt.date.fromisoformat(row["valid_until"]) < rfq_date:
            continue
        groups.setdefault((row["supplier_code"], float(row["purity_grade"])), []).append(row)
    max_grade = max([float(r["purity_grade"]) for r in world.prices if r["product_code"] == product_code]
                    + [float(r["purity_grade"]) for r in world.plants if r["product_code"] == product_code]
                    or [0.0])
    for (sc, grade), rows in groups.items():
        sup = suppliers[sc]
        if qty_kg < float(sup["moq_kg"]):
            continue
        row = _highest_tier(rows, qty_kg, "tier_min_kg")
        if row is None:
            continue
        options.append({"key": f"SP:{row['id']}", "cost": Decimal(str(row["price_per_kg"])),
                        "lead": int(sup["lead_time_days"]), "origin": sup["country"],
                        "valid_until": dt.date.fromisoformat(row["valid_until"])})
    for row in world.plants:
        if row["product_code"] != product_code or float(row["purity_grade"]) < purity_min:
            continue
        if qty_kg < float(row["min_batch_kg"]) or qty_kg > float(row["capacity_kg_month"]):
            continue
        options.append({"key": f"MF:{row['id']}", "cost": Decimal(str(row["cost_per_kg"])),
                        "lead": int(row["lead_time_days"]), "origin": row["country"], "valid_until": None})

    if max_grade < purity_min:
        out["warnings"].add("PURITY_UNAVAILABLE")
        return out

    rates = {(r["origin_country"], r["dest_port"]): r for r in world.shipping}
    usable = []
    for o in options:
        if term == "CIF":
            rate = rates.get((o["origin"], dest_port))
            if rate is None:
                continue
            o = {**o, "rate": rate, "transit": int(rate["transit_days"])}
        else:
            o = {**o, "rate": None, "transit": 0}
        o["days_needed"] = o["lead"] + o["transit"]
        usable.append(o)
    if not usable:
        out["warnings"].add("NO_SHIPPING_RATE" if options and term == "CIF" else "NO_FEASIBLE_SOURCE")
        return out

    available = (required_date - rfq_date).days if required_date else None
    pool = usable
    if available is not None:
        meets = [o for o in usable if o["days_needed"] <= available]
        if meets:
            pool = meets
        else:
            out["warnings"].add("DEADLINE_INFEASIBLE")
    best = min(pool, key=lambda o: (o["cost"], o["lead"], o["key"]))
    if available is not None and "DEADLINE_INFEASIBLE" not in out["warnings"]:
        if available - best["days_needed"] < TIGHT_SLACK_DAYS:
            out["warnings"].add("DEADLINE_TIGHT")
    if best["valid_until"] and best["valid_until"] < rfq_date + dt.timedelta(days=QUOTE_VALIDITY_DAYS):
        out["warnings"].add("PRICE_VALIDITY_SHORT")

    q = Decimal(str(qty_kg))
    cost_total = r2(best["cost"] * q)
    freight = surcharge = insurance = Decimal("0")
    if term == "CIF":
        rate = best["rate"]
        freight = r2(max(Decimal(str(rate["rate_per_kg"])) * q, Decimal(str(rate["min_charge"]))))
        if prod["hazmat_class"]:
            surcharge = r2(freight * Decimal(str(rate["hazmat_surcharge_pct"])))
        insurance = r2(cost_total * INSURANCE_RATE)
    if prod["hazmat_class"]:
        out["warnings"].add("HAZMAT")
    handling = r2(HANDLING_PER_KG * q)
    landed = cost_total + freight + surcharge + insurance + handling

    rules = [m for m in world.margins if m["category"] == prod["category"]
             and m["customer_tier"] == customer_tier]
    rule = _highest_tier(rules, qty_kg, "qty_tier_min_kg")
    margin = Decimal(str(rule["margin_pct"]))
    total = r2(landed / (Decimal("1") - margin))
    ppk = r4(total / q)

    hist = [Decimal(str(h["quoted_price_per_kg"])) for h in world.history if h["product_code"] == product_code]
    if len(hist) >= 2:
        med = statistics.median(hist)
        if abs(float((ppk - med) / med)) > DEVIATION_THRESHOLD:
            out["warnings"].add("DEVIATION_FROM_HISTORY")

    out.update(status="ready_for_review", price_per_kg=ppk, total=total, option=best["key"],
               landed=landed, margin=margin, days_needed=best["days_needed"])
    return out


def reference_coa(world: World, product_code: str, values: dict[str, float | None]) -> dict:
    """Return per-parameter statuses and overall verdict (PASS | FAIL | REVIEW REQUIRED)."""
    specs = [s for s in world.specs if s["product_code"] == product_code]
    results, overall = [], "PASS"
    rank = {"PASS": 0, "REVIEW REQUIRED": 1, "FAIL": 2}
    for s in specs:
        v = values.get(s["parameter"])
        margin = float(s["review_margin"])
        critical = bool(int(s["critical"]))
        if v is None:
            status = "REVIEW REQUIRED"
        else:
            lo = float(s["min_value"]) if s["min_value"] != "" else None
            hi = float(s["max_value"]) if s["max_value"] != "" else None
            below = lo is not None and v < lo
            above = hi is not None and v > hi
            miss = (lo - v) if below else (v - hi) if above else 0.0
            if not below and not above:
                status = "PASS"
            elif miss <= margin + 1e-9:
                status = "REVIEW REQUIRED"
            else:
                status = "FAIL" if critical else "REVIEW REQUIRED"
        results.append({"parameter": s["parameter"], "status": status})
        if rank[status] > rank[overall]:
            overall = status
    return {"verdict": overall, "results": results}
