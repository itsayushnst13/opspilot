"""Cross-document consistency checks for the export document set."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

DOC_ORDER = ["commercial_invoice", "packing_list", "certificate_of_origin", "shipping_instruction"]
SHORT = {"commercial_invoice": "Invoice", "packing_list": "Packing List",
         "certificate_of_origin": "Certificate of Origin", "shipping_instruction": "Shipping Instruction"}

# field path, severity, kind
FIELDS = [
    ("product.code", "critical", "str"), ("product.hs_code", "critical", "str"),
    ("net_quantity_kg", "critical", "num"), ("consignee.name", "critical", "str"),
    ("origin_country", "critical", "str"), ("destination_port", "critical", "str"),
    ("gross_weight_kg", "critical", "num"), ("packages_count", "critical", "num"),
    ("incoterm", "warning", "str"),
]


class ValidateDocsArgs(BaseModel):
    documents: dict[str, dict] = Field(description="Document type -> payload")


def _get(doc: dict, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _norm_str(v: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(v).lower())).strip()


def _equal(a: Any, b: Any, kind: str) -> bool:
    if kind == "num":
        return abs(float(a) - float(b)) <= 0.001
    return _norm_str(a) == _norm_str(b)


def _finding(field: str, da: str, db_: str, va: Any, vb: Any, severity: str, msg: str) -> dict:
    return {"field": field, "doc_a": da, "doc_b": db_, "value_a": str(va), "value_b": str(vb),
            "severity": severity, "message": msg}


def validate_documents(db, a: ValidateDocsArgs) -> dict:  # noqa: ARG001 (db unused; keeps tool signature uniform)
    return check_documents(a.documents)


def check_documents(docs: dict[str, dict]) -> dict:
    present = [d for d in DOC_ORDER if d in docs]
    findings: list[dict] = []
    for path, severity, kind in FIELDS:
        values = [(d, _get(docs[d], path)) for d in present if _get(docs[d], path) is not None]
        if len(values) < 2:
            continue
        anchor_doc, anchor_val = values[0]
        for d, v in values[1:]:
            if not _equal(anchor_val, v, kind):
                label = path.split(".")[-1].replace("_", " ")
                findings.append(_finding(path, anchor_doc, d, anchor_val, v, severity,
                                         f"{label.capitalize()} mismatch: {SHORT[anchor_doc]} = {anchor_val}, {SHORT[d]} = {v}"))
    inv = docs.get("commercial_invoice")
    if inv and all(k in inv for k in ("net_quantity_kg", "unit_price_per_kg", "total_value")):
        qty, price, total = float(inv["net_quantity_kg"]), float(inv["unit_price_per_kg"]), float(inv["total_value"])
        tol = max(0.01, qty * 0.00005 + 0.005)  # unit price is shown to 4 decimals
        if abs(qty * price - total) > tol:
            findings.append(_finding("invoice_total_arithmetic", "commercial_invoice", "commercial_invoice",
                                     total, round(qty * price, 2), "critical",
                                     f"Invoice total {total:.2f} is not quantity x unit price ({qty * price:.2f})"))
    pl = docs.get("packing_list")
    if pl and all(k in pl for k in ("packages_count", "net_weight_per_package_kg", "net_quantity_kg")):
        n, unit, net = float(pl["packages_count"]), float(pl["net_weight_per_package_kg"]), float(pl["net_quantity_kg"])
        if abs(n * unit - net) > 0.0005 * n + 0.001:
            findings.append(_finding("package_weight_arithmetic", "packing_list", "packing_list", net, round(n * unit, 3),
                                     "critical", f"Packages x unit weight = {n * unit:g} kg but net quantity is {net:g} kg"))
    for d in present:
        doc = docs[d]
        if "gross_weight_kg" in doc and "net_quantity_kg" in doc and float(doc["gross_weight_kg"]) < float(doc["net_quantity_kg"]):
            findings.append(_finding("gross_weight_arithmetic", d, d, doc["gross_weight_kg"], doc["net_quantity_kg"],
                                     "critical", f"{SHORT[d]}: gross weight is lower than net quantity"))
    return {"consistent": not findings, "findings": findings, "documents_checked": present}
