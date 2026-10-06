"""COA extraction + verdict evals (15 cases, real pipeline)."""
from __future__ import annotations

from evals.harness import rate, run_coa_file


def run_all(cases: list[dict]) -> dict[str, dict]:
    return {c["id"]: run_coa_file(c["file"]) for c in cases}


def evaluate(cases: list[dict], runs: dict[str, dict]) -> dict:
    prod, batch, params, verdict, statuses = [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]
    unsafe_pass = false_alarm = 0
    confusion: dict[str, dict[str, int]] = {}
    fails = []
    for c in cases:
        d, exp = runs[c["id"]], c["expected"]
        coa = d["coa"] or {}
        ex = coa.get("extracted") or {}
        e = exp["extracted"]
        prod[1] += 1; batch[1] += 1; params[1] += 1; verdict[1] += 1
        prod[0] += ex.get("product_code") == e["product_code"]
        batch[0] += ex.get("batch_no") == e["batch_no"]
        params[0] += (ex.get("params") or {}) == e["params"]
        got = coa.get("verdict")
        verdict[0] += got == exp["verdict"]
        confusion.setdefault(exp["verdict"], {}).setdefault(str(got), 0)
        confusion[exp["verdict"]][str(got)] += 1
        if got == "PASS" and exp["verdict"] != "PASS":
            unsafe_pass += 1
        if got != "PASS" and exp["verdict"] == "PASS":
            false_alarm += 1
        by = {r["parameter"]: r["status"] for r in coa.get("results", [])}
        for p, s in exp["statuses"].items():
            statuses[1] += 1
            statuses[0] += by.get(p) == s
        if got != exp["verdict"] or (ex.get("params") or {}) != e["params"]:
            fails.append({"id": c["id"], "expected": exp["verdict"], "got": got, "params_expected": e["params"], "params_got": ex.get("params")})
    return {"cases": len(cases), "verdict_accuracy": rate(*verdict), "product_extraction": rate(*prod),
            "batch_extraction": rate(*batch), "parameters_extraction_exact": rate(*params),
            "parameter_status_accuracy": rate(*statuses),
            "unsafe_passes (non-PASS COA judged PASS)": unsafe_pass, "false_alarms (PASS COA flagged)": false_alarm,
            "confusion (expected -> got)": confusion, "failures": fails}
