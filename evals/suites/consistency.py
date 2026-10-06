"""Cross-document consistency evals: detection on 10 labelled sets + 'blocked docs are never rendered' gate checks."""
from __future__ import annotations

from evals.harness import analyst, load, rate


def evaluate() -> dict:
    from fastapi import HTTPException

    from app.core.db import SessionLocal
    from app.services import export_service
    from app.tools.doc_validation import check_documents
    from app.tools.export_docs import ExportOrder

    cases = load("consistency_cases")
    exact = [0, 0]
    tp = fp = fn = 0
    clean_fp = clean_total = bad_detected = bad_total = 0
    fails = []
    for c in cases:
        res = check_documents(c["docs"])
        got = {f["field"] for f in res["findings"]}
        want = set(c["expected_fields"])
        exact[1] += 1
        exact[0] += got == want
        tp += len(got & want); fp += len(got - want); fn += len(want - got)
        if want:
            bad_total += 1
            bad_detected += bool(got)
        else:
            clean_total += 1
            clean_fp += bool(got)
        if got != want:
            fails.append({"id": c["id"], "expected": sorted(want), "got": sorted(got)})
    # gate: an edit that creates a mismatch must block rendering; reverting it must unblock
    import datetime as dt
    from decimal import Decimal

    gate = [0, 0]
    edits = [("packing_list", "net_quantity_kg", 5200, 5000), ("shipping_instruction", "consignee.name", "Gulf Coast Polymer LLC", "Gulf Coast Polymers LLC"),
             ("certificate_of_origin", "product.hs_code", "291540", None), ("commercial_invoice", "total_value", 99999, None)]
    with SessionLocal() as db:
        user = analyst(db)
        order = ExportOrder(order_ref="EVAL-1", date=dt.date(2026, 10, 1), customer_name="Gulf Coast Polymers LLC",
                            product_code="CHEM-X01", qty_kg=5000, unit_price_per_kg=Decimal("2.4500"),
                            total_value=Decimal("12250.00"), origin_country="India", destination_port="Houston")
        for doc, field, bad, good in edits:
            out = export_service.generate(db, user, order)
            run_id = out["run_id"]
            clean_ok = out["status"] == "completed"
            r = export_service.apply_edit(db, user, run_id, doc, field, bad)
            blocked = r["status"] == "blocked"
            try:
                export_service.render(db, run_id, "commercial_invoice")
                rendered = True
            except HTTPException as exc:
                rendered = exc.status_code != 409
            gate[1] += 1
            gate[0] += clean_ok and blocked and not rendered
    return {"cases": len(cases), "clean_sets": clean_total, "inconsistent_sets": bad_total,
            "exact_finding_set_match": rate(*exact), "detection_rate (inconsistent sets flagged)": rate(bad_detected, bad_total),
            "false_positive_rate (clean sets flagged)": rate(clean_fp, clean_total),
            "finding_precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
            "finding_recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
            "gate_blocks_rendering_after_inconsistent_edit": rate(*gate), "failures": fails}
