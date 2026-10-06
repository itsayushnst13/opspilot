"""10 synthetic export-document sets for cross-document consistency checks.

Payload layout is the contract described in docs/BUSINESS_RULES.md (section "Export documents").
"""
from __future__ import annotations

import copy

from .catalog import World

BASE_ORDERS = [
    ("CHEM-X01", 5000.0, "Houston", "Brightwater Coatings LLC", "250 kg steel drum", 250.0),
    ("CHEM-X03", 12000.0, "Los Angeles", "Pinecrest Home Care Inc", "200 kg HDPE drum", 200.0),
    ("CHEM-X10", 6000.0, "Savannah", "Orchard Lane Cosmetics Ltd", "1000 kg IBC tote", 1000.0),
    ("CHEM-X04", 2000.0, "Houston", "Lakeshore Adhesives Co", "200 kg steel drum", 200.0),
    ("CHEM-X13", 4000.0, "Rotterdam", "Nordhaven Polymers GmbH", "25 kg multiwall bag", 25.0),
    ("CHEM-X16", 3000.0, "Savannah", "Summit Agro Sciences Inc", "250 kg steel drum", 250.0),
    ("CHEM-X06", 8000.0, "Houston", "Harborline Plastics Ltd", "25 kg multiwall bag", 25.0),
    ("CHEM-X09", 1000.0, "Los Angeles", "Redwood Personal Care LLC", "20 kg pail", 20.0),
    ("CHEM-X05", 5000.0, "Rotterdam", "Westfield Inks Inc", "25 kg multiwall bag", 25.0),
    ("CHEM-X18", 2500.0, "Los Angeles", "Bayview Skin Science Ltd", "25 kg multiwall bag", 25.0),
]
DEST_COUNTRY = {"Houston": "United States", "Los Angeles": "United States", "Savannah": "United States",
                "Rotterdam": "Netherlands"}


def build_docs(world: World, n: int) -> dict:
    code, qty, port, consignee, pkg, unit_w = BASE_ORDERS[n]
    prod = next(p for p in world.products if p["code"] == code)
    price = 3.1234 + n * 0.37
    product = {"code": code, "name": prod["name"], "hs_code": prod["hs_code"]}
    cons = {"name": consignee, "address": f"{100 + n} Example Street, Sample City"}
    packages = int(qty / unit_w)
    gross = qty + packages * 0.0 + 20.0 * (packages // 20 + 1)
    return {
        "commercial_invoice": {"doc_type": "commercial_invoice", "invoice_no": f"INV-2026-{n + 1:04d}",
                               "date": "2026-10-06", "seller": {"name": "Seller Trading Co (synthetic)"},
                               "consignee": cons, "product": product, "net_quantity_kg": qty,
                               "unit_price_per_kg": round(price, 4), "total_value": round(qty * round(price, 4), 2),
                               "currency": "USD", "incoterm": "CIF", "origin_country": "India",
                               "destination_port": port},
        "packing_list": {"doc_type": "packing_list", "packing_list_no": f"PL-2026-{n + 1:04d}",
                         "invoice_no": f"INV-2026-{n + 1:04d}", "consignee": cons, "product": product,
                         "net_quantity_kg": qty, "gross_weight_kg": gross, "package_type": pkg,
                         "packages_count": packages, "net_weight_per_package_kg": unit_w,
                         "origin_country": "India", "destination_port": port},
        "certificate_of_origin": {"doc_type": "certificate_of_origin", "coo_no": f"CO-2026-{n + 1:04d}",
                                  "consignee": cons, "product": product, "net_quantity_kg": qty,
                                  "origin_country": "India", "destination_country": DEST_COUNTRY[port]},
        "shipping_instruction": {"doc_type": "shipping_instruction", "si_no": f"SI-2026-{n + 1:04d}",
                                 "shipper": {"name": "Seller Trading Co (synthetic)"}, "consignee": cons,
                                 "product": product, "net_quantity_kg": qty, "gross_weight_kg": gross,
                                 "packages_count": packages, "port_of_loading": "Nhava Sheva",
                                 "destination_port": port, "incoterm": "CIF",
                                 "hazmat_class": prod["hazmat_class"] or None},
    }


def build_cases(world: World) -> list[dict]:
    cases = []
    for n in range(10):
        docs = build_docs(world, n)
        expected: set[str] = set()
        note = "clean"
        if n == 3:  # quantity mismatch on the packing list (the spec example: 5000 vs 5200)
            docs["packing_list"]["net_quantity_kg"] = docs["packing_list"]["net_quantity_kg"] + 200.0
            docs["packing_list"]["net_weight_per_package_kg"] = docs["packing_list"]["net_weight_per_package_kg"] * 1.1
            docs["packing_list"]["gross_weight_kg"] = docs["packing_list"]["gross_weight_kg"] + 200.0
            expected, note = {"net_quantity_kg", "gross_weight_kg"}, "packing list quantity (and gross weight) differ by 200 kg"
        elif n == 4:
            docs["shipping_instruction"]["consignee"] = {**docs["shipping_instruction"]["consignee"],
                                                         "name": docs["shipping_instruction"]["consignee"]["name"].replace("Polymers", "Polymer")}
            expected, note = {"consignee.name"}, "consignee typo on shipping instruction"
        elif n == 5:
            docs["certificate_of_origin"]["product"] = {**docs["certificate_of_origin"]["product"], "hs_code": "999999"}
            expected, note = {"product.hs_code"}, "HS code differs on certificate of origin"
        elif n == 6:
            docs["commercial_invoice"]["total_value"] = round(docs["commercial_invoice"]["total_value"] * 1.05, 2)
            expected, note = {"invoice_total_arithmetic"}, "invoice total is not quantity x unit price"
        elif n == 7:
            docs["packing_list"]["packages_count"] = docs["packing_list"]["packages_count"] + 1
            expected, note = {"packages_count", "package_weight_arithmetic"}, "package count off by one"
        elif n == 8:
            docs["shipping_instruction"]["destination_port"] = "Los Angeles"
            expected, note = {"destination_port"}, "destination port differs on shipping instruction"
        elif n == 9:
            docs["certificate_of_origin"]["origin_country"] = "Thailand"
            docs["shipping_instruction"]["net_quantity_kg"] = docs["shipping_instruction"]["net_quantity_kg"] - 50.0
            expected, note = {"origin_country", "net_quantity_kg"}, "origin and quantity mismatches"
        cases.append({"id": f"DOC-{n + 1:03d}", "docs": copy.deepcopy(docs),
                      "expected_fields": sorted(expected), "note": note})
    return cases
