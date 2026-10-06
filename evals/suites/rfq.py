"""RFQ extraction, pricing and tool-call evals, all computed from the same 30 real pipeline runs."""
from __future__ import annotations

import re

from evals.harness import load, rate, run_rfq_file

FIELDS = ["product_code", "quantity_kg", "purity_min", "destination_port", "required_date", "incoterm", "customer_name", "rfq_date"]
REQUIRED_WHEN_READY = {"search_product", "get_product_spec", "search_knowledge_base", "recommend_source", "calculate_quote"}


def _norm(v):
    return re.sub(r"\s+", " ", v.strip().lower()) if isinstance(v, str) else v


def run_all(cases: list[dict]) -> dict[str, dict]:
    return {c["id"]: run_rfq_file(c["file"]) for c in cases}


def _calc(detail):
    ok = [t for t in detail["tool_calls"] if t["tool"] == "calculate_quote" and t["ok"]]
    return ok[-1] if ok else None


def evaluate(cases: list[dict], runs: dict[str, dict]) -> dict:
    per_field = {f: [0, 0] for f in FIELDS}
    all_exact, ext_cases = 0, []
    st = [0, 0]
    price, total, option, warns, missing = [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]
    crit_tp = crit_fp = crit_fn = 0
    tools = {k: [0, 0] for k in ("no_failed_tool_calls", "calculate_quote_last", "calc_args_match_validated_fields",
                                 "only_whitelisted_tools", "required_tools_called", "citations_present")}
    pricing_cases = []
    from app.tools.warnings import EVAL_CODES, SEVERITY
    from app.tools.registry import RFQ_AGENT_TOOLS

    for c in cases:
        d, exp = runs[c["id"]], c["expected"]
        got_f = (d["extraction"] or {}).get("fields") or {}
        bad = []
        for f in FIELDS:
            ok = _norm(got_f.get(f)) == _norm(exp["fields"].get(f))
            per_field[f][0] += ok
            per_field[f][1] += 1
            if not ok:
                bad.append({"field": f, "expected": exp["fields"].get(f), "got": got_f.get(f)})
        all_exact += not bad
        ext_cases.append({"id": c["id"], "ok": not bad, "mismatches": bad})

        status = {"pending_approval": "ready_for_review", "needs_info": "needs_info"}.get(d["run"]["status"], d["run"]["status"])
        st[0] += status == exp["status"]
        st[1] += 1
        q = d["quote"]
        got_codes = {w["code"] for w in (q["warnings"] if q else _needs_info_warnings(d))} & EVAL_CODES
        want_codes = set(exp["warnings"]) & EVAL_CODES
        warns[0] += got_codes == want_codes
        warns[1] += 1
        gc = {x for x in got_codes if SEVERITY[x] == "critical"}
        wc = {x for x in want_codes if SEVERITY[x] == "critical"}
        crit_tp += len(gc & wc)
        crit_fp += len(gc - wc)
        crit_fn += len(wc - gc)
        got_missing = sorted((d["run"]["metrics"].get("needs_info") or {}).get("missing", [])) if not q else []
        missing[0] += got_missing == sorted(exp["missing"])
        missing[1] += 1
        row = {"id": c["id"], "status_ok": status == exp["status"], "warnings_got": sorted(got_codes), "warnings_expected": sorted(want_codes)}
        if exp["status"] == "ready_for_review":
            calc = _calc(d)
            sel = ((calc or {}).get("result") or {}).get("selected_option") or {}
            pp = q["price_per_kg"] if q else None
            tt = q["total"] if q else None
            price[0] += pp == exp["price_per_kg"]
            price[1] += 1
            total[0] += tt == exp["total"]
            total[1] += 1
            option[0] += sel.get("option_id") == exp["option"]
            option[1] += 1
            row.update(price=pp, price_expected=exp["price_per_kg"], total=tt, total_expected=exp["total"],
                       option=sel.get("option_id"), option_expected=exp["option"])
        pricing_cases.append(row)

        # tool-call checks
        calls = d["tool_calls"]
        tools["no_failed_tool_calls"][1] += 1
        tools["no_failed_tool_calls"][0] += all(t["ok"] for t in calls)
        tools["calculate_quote_last"][1] += 1
        tools["calculate_quote_last"][0] += bool(calls) and calls[-1]["tool"] == "calculate_quote" and calls[-1]["ok"]
        tools["only_whitelisted_tools"][1] += 1
        tools["only_whitelisted_tools"][0] += all(t["tool"] in RFQ_AGENT_TOOLS for t in calls)
        calc = _calc(d)
        if exp["fields"]["product_code"] and exp["fields"]["quantity_kg"] and exp["status"] != "needs_info" or calc:
            tools["calc_args_match_validated_fields"][1] += 1
            a = (calc or {}).get("args", {})
            tools["calc_args_match_validated_fields"][0] += (a.get("product_code") == got_f.get("product_code")
                                                             and a.get("qty_kg") == got_f.get("quantity_kg"))
        if exp["status"] == "ready_for_review":
            tools["required_tools_called"][1] += 1
            tools["required_tools_called"][0] += REQUIRED_WHEN_READY <= {t["tool"] for t in calls}
            tools["citations_present"][1] += 1
            tools["citations_present"][0] += bool(q and any(s["kind"] == "kb" for s in q["sources"]))
    prec = crit_tp / (crit_tp + crit_fp) if crit_tp + crit_fp else 1.0
    rec = crit_tp / (crit_tp + crit_fn) if crit_tp + crit_fn else 1.0
    return {
        "extraction": {"cases": len(cases), "all_fields_exact": rate(all_exact, len(cases)),
                       "per_field": {f: rate(*v) for f, v in per_field.items()}, "failures": [x for x in ext_cases if not x["ok"]]},
        "pricing": {"status_accuracy": rate(*st), "price_per_kg_exact": rate(*price), "total_exact": rate(*total),
                    "selected_option_match": rate(*option), "warning_set_exact": rate(*warns), "missing_fields_exact": rate(*missing),
                    "critical_warning_precision": round(prec, 4), "critical_warning_recall": round(rec, 4),
                    "failures": [r for r in pricing_cases if not r["status_ok"] or r.get("price") != r.get("price_expected")
                                 or r["warnings_got"] != r["warnings_expected"] or r.get("option") != r.get("option_expected")]},
        "tool_calls": {k: rate(*v) for k, v in tools.items()},
    }


def _needs_info_warnings(d):
    return (d["run"]["metrics"].get("needs_info") or {}).get("warnings", [])
