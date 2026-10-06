#!/usr/bin/env python
"""Regenerate the entire synthetic dataset deterministically.

    python scripts/generate_data.py

Writes data/ (knowledge base + RFQ/COA inputs) and evals/datasets/ (ground truth).
All data is fictional. Nothing here comes from any real company.
"""
from __future__ import annotations

import csv
import json
import random
import shutil
import statistics
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from datagen import catalog, coa, consistency, docs, retrieval, rfq  # noqa: E402
from datagen.catalog import (P_HISTORY_DEVIATES, P_WITH_HISTORY, RFQ_REFERENCE_DATE, World)  # noqa: E402
from datagen.reference import reference_quote  # noqa: E402

SEED = 42


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (str(v) if isinstance(v, Decimal) else v) for k, v in r.items()})


def write_margin_xlsx(path: Path, rows: list[dict]) -> None:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    import datetime as _dt

    wb = Workbook()
    wb.properties.created = wb.properties.modified = _dt.datetime(2026, 1, 1)  # reproducible bytes
    ws = wb.active
    ws.title = "margins"
    ws.append(list(rows[0].keys()))
    for r in rows:
        ws.append([float(v) if isinstance(v, Decimal) else v for v in r.values()])
    wb.save(path)
    _normalize_zip(path)


def _normalize_zip(path: Path) -> None:
    """openpyxl stamps 'modified' with the current time; pin zip + XML timestamps for reproducibility."""
    import re
    import zipfile

    with zipfile.ZipFile(path) as zin:
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, blob in items:
            if name == "docProps/core.xml":
                blob = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", blob)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, blob)


def build_history(rng: random.Random, world: World) -> list[dict]:
    rows, rid = [], 1
    for code in P_WITH_HISTORY:
        typ = reference_quote(world, code, 5000.0, None, "Houston", None, RFQ_REFERENCE_DATE, "CIF")
        base = float(typ["price_per_kg"]) if typ["price_per_kg"] is not None else 10.0
        for _ in range(3):
            factor = rng.uniform(0.95, 1.05) * (1.40 if code == P_HISTORY_DEVIATES else 1.0)
            rows.append({"id": rid, "product_code": code, "qty_kg": rng.choice([2000, 5000, 8000, 10000]),
                         "dest_port": rng.choice(["Houston", "Los Angeles", "Savannah", "Rotterdam"]),
                         "quoted_price_per_kg": Decimal(str(round(base * factor, 4))),
                         "outcome": rng.choice(["won", "lost"]),
                         "quoted_at": f"2026-0{rng.randint(3, 8)}-{rng.randint(10, 28)}"})
            rid += 1
    # extra rows for products without enough history are intentionally omitted
    while len(rows) < 30:
        rows.append(rows[len(rows) % len(rows)])  # pragma: no cover (30 reached above)
    return rows


def main() -> None:
    rng = random.Random(SEED)
    data = ROOT / "data"
    for sub in ("products", "specifications", "suppliers", "pricing", "shipping", "regulatory",
                "historical_quotes", "rfqs", "coas"):
        shutil.rmtree(data / sub, ignore_errors=True)

    w = World()
    w.products, base = catalog.build_products(rng)
    w.specs = catalog.build_specs(rng, w.products)
    w.suppliers = catalog.build_suppliers(rng)
    w.prices = catalog.build_prices(rng, w.products, w.specs, w.suppliers, base)
    w.plants = catalog.build_plants(rng, w.products, w.specs, base)
    w.shipping = catalog.build_shipping(rng)
    w.margins = catalog.build_margins()
    w.history = []  # history is generated from reference prices, then added
    w.history = build_history(rng, w)

    write_csv(data / "products" / "products.csv", w.products)
    write_csv(data / "specifications" / "specs.csv", w.specs)
    write_csv(data / "suppliers" / "suppliers.csv", w.suppliers)
    write_csv(data / "pricing" / "supplier_prices.csv", w.prices)
    write_csv(data / "pricing" / "manufacturing_costs.csv", w.plants)
    write_margin_xlsx(data / "pricing" / "margin_rules.xlsx", w.margins)
    write_csv(data / "shipping" / "shipping_rates.csv", w.shipping)
    write_csv(data / "historical_quotes" / "historical_quotes.csv", w.history)

    docs.spec_sheets(rng, w, data)
    docs.supplier_profiles(rng, w, data)
    docs.regulatory_docs(data)
    docs.shipping_notes(data)

    ds = ROOT / "evals" / "datasets"
    ds.mkdir(parents=True, exist_ok=True)
    rfq_cases = rfq.build_rfqs(w, data / "rfqs")
    coa_cases = coa.build_coas(rng, w, data / "coas")
    doc_cases = consistency.build_cases(w)
    ret_cases = retrieval.build_cases(w)
    for name, payload in (("rfq_cases", rfq_cases), ("coa_cases", coa_cases),
                          ("consistency_cases", doc_cases), ("retrieval_cases", ret_cases)):
        (ds / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    (data / "README.md").write_text(
        "# Synthetic data\n\nEverything in this folder is **fictional**, generated by "
        "`python scripts/generate_data.py` (seed 42). It does not contain any real company's data, "
        "prices, specifications or documents. Product names are coined words.\n", encoding="utf-8")

    n_status = {}
    for c in rfq_cases:
        n_status[c["expected"]["status"]] = n_status.get(c["expected"]["status"], 0) + 1
    print(json.dumps({
        "products": len(w.products), "spec_rows": len(w.specs), "suppliers": len(w.suppliers),
        "supplier_price_rows": len(w.prices), "plant_rows": len(w.plants), "shipping_rules": len(w.shipping),
        "margin_rules": len(w.margins), "historical_quotes": len(w.history),
        "rfq_cases": len(rfq_cases), "rfq_expected_status": n_status, "coa_cases": len(coa_cases),
        "consistency_cases": len(doc_cases), "retrieval_cases": len(ret_cases)}, indent=2))


if __name__ == "__main__":
    main()
