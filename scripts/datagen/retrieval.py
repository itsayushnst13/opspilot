"""30 retrieval test queries with the knowledge-base document(s) that should be found."""
from __future__ import annotations

from .catalog import World
from .docs import REGULATORY


def build_cases(world: World) -> list[dict]:
    cases = []
    spec_products = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 17]
    templates = ["What are the storage conditions and shelf life of {name}?",
                 "What packaging and incompatibilities apply to {name} ({code})?",
                 "Show the specification limits for {code} {name}."]
    for k, i in enumerate(spec_products):
        p = world.products[i]
        ext = "pdf" if i % 2 == 0 else "txt"
        cases.append({"id": f"RET-{len(cases) + 1:03d}", "query": templates[k % 3].format(name=p["name"], code=p["code"]),
                      "expected_paths": [f"specifications/{p['code']}_spec_sheet.{ext}"], "kind": "spec_sheet"})
    for s in world.suppliers[:8]:
        cases.append({"id": f"RET-{len(cases) + 1:03d}",
                      "query": f"Where is {s['name']} located and what certifications does it hold?",
                      "expected_paths": [f"suppliers/supplier_{s['code']}.txt"], "kind": "supplier"})
    reg_queries = [
        ("hazmat_class8_corrosives", "What packaging is required for corrosive Class 8 products?"),
        ("coa_acceptance_policy", "When is a certificate of analysis marked REVIEW REQUIRED instead of FAIL?"),
        ("quote_approval_policy", "How long is a quote valid and when does the approver need to write a reason?"),
        ("incoterms_policy", "What incoterm is assumed when the customer does not state one?"),
        ("export_documentation_requirements", "Which fields must match across invoice, packing list and certificate of origin?"),
    ]
    names = list(REGULATORY)
    for name, q in reg_queries:
        ext = "pdf" if names.index(name) % 3 == 0 else "txt"
        cases.append({"id": f"RET-{len(cases) + 1:03d}", "query": q,
                      "expected_paths": [f"regulatory/{name}.{ext}"], "kind": "regulatory"})
    ship = [
        ("How is the hazmat surcharge calculated and what is the minimum freight charge?", ["shipping/shipping_notes.txt"]),
        ("What is the typical sea transit time from India to Houston?", ["shipping/shipping_notes.txt"]),
        ("What is the freight rate per kg and transit days from India to Rotterdam?", ["shipping/shipping_rates.csv"]),
    ]
    for q, exp in ship:
        cases.append({"id": f"RET-{len(cases) + 1:03d}", "query": q, "expected_paths": exp, "kind": "shipping"})
    return cases
