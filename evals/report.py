"""Render the eval JSON into a readable Markdown report (all numbers come from the JSON)."""
from __future__ import annotations


def _r(x) -> str:
    if isinstance(x, dict) and "rate" in x and "passed" in x:
        return f"{x['passed']}/{x['total']} ({x['rate'] * 100:.1f}%)" if x["rate"] is not None else "n/a"
    return str(x)


def _table(title: str, d: dict, skip=("failures", "not_top1", "scenarios", "cases", "per_field", "confusion (expected -> got)", "hit@3_by_kind")) -> str:
    rows = [f"| {k} | {_r(v)} |" for k, v in d.items() if k not in skip and not isinstance(v, (list,)) and not (isinstance(v, dict) and "rate" not in v)]
    return f"### {title}\n\n| Metric | Result |\n|---|---|\n" + "\n".join(rows) + "\n"


def write_report(o: dict) -> str:
    m, s = o["meta"], o["suites"]
    out = [f"# OpsPilot evaluation report\n",
           f"Generated {m['generated_at']} · mode **{m['mode']}**{' · model ' + m['model'] if m['model'] else ''} · embedder `{m['embedder']}` "
           f"· reference date {m['reference_date']} · run took {m['duration_s']} s\n",
           "Datasets: " + ", ".join(f"{k}={v}" for k, v in m["datasets"].items()) + ". All data is synthetic.\n",
           "> Every figure below is computed by `evals/run_all.py` against the real pipeline in this run. "
           "See *How to read these numbers* in the README for what they do and do not prove.\n"]
    out.append(_table("RFQ field extraction", {"cases": s["rfq_extraction"]["cases"], "all_fields_exact": s["rfq_extraction"]["all_fields_exact"]}))
    out.append("| Field | Exact match |\n|---|---|\n" + "\n".join(f"| {k} | {_r(v)} |" for k, v in s["rfq_extraction"]["per_field"].items()) + "\n")
    out.append(_table("Pricing vs independent reference engine", s["pricing"]))
    out.append(_table("Tool-call correctness (RFQ runs)", s["tool_calls"]))
    out.append(_table("COA checker", s["coa"]))
    out.append("Confusion (expected → got): " + "; ".join(f"{k}: {v}" for k, v in s["coa"]["confusion (expected -> got)"].items()) + "\n")
    out.append(_table("Export-document consistency", s["consistency"]))
    out.append(_table("Retrieval (RAG)", s["retrieval"]))
    out.append("| Query kind | hit@3 |\n|---|---|\n" + "\n".join(f"| {k} | {_r(v)} |" for k, v in s["retrieval"]["hit@3_by_kind"].items()) + "\n")
    g = s["guardrails_scripted_agent"]
    if "scenarios" in g:
        out.append(f"### Agent guardrails (scripted misbehaving model) — {_r(g)}\n\n| Scenario | Result | Detail |\n|---|---|---|\n"
                   + "\n".join(f"| {x['scenario']} | {'PASS' if x['passed'] else 'FAIL'} | {x['note']} |" for x in g["scenarios"]) + "\n")
    out.append(_table("Grounding / hallucination", s["grounding"]))
    L = s["latency"]
    out.append("### Latency\n\n| Measure | p50 | p95 | max |\n|---|---|---|---|\n"
               f"| RFQ end-to-end ({L['rfq_end_to_end_ms']['n']} runs) ms | {L['rfq_end_to_end_ms']['p50']} | {L['rfq_end_to_end_ms']['p95']} | {L['rfq_end_to_end_ms']['max']} |\n"
               f"| COA end-to-end ({L['coa_end_to_end_ms']['n']} runs) ms | {L['coa_end_to_end_ms']['p50']} | {L['coa_end_to_end_ms']['p95']} | {L['coa_end_to_end_ms']['max']} |\n\n"
               f"Tool time p50 {L['rfq_tool_ms_p50']} ms · LLM time p50 {L['rfq_llm_ms_p50']} ms · tokens {L['tokens_total']}. {L['note']}\n")
    fails = []
    for k in ("rfq_extraction", "pricing", "coa", "consistency", "grounding"):
        for f in s[k].get("failures", []):
            fails.append(f"- **{k}**: `{f}`")
    for f in s["retrieval"]["not_top1"]:
        fails.append(f"- **retrieval** {f['id']}: rank {f['rank']} for “{f['query']}” (top-3: {', '.join(f['top3'])})")
    out.append("### Known failures (not hidden)\n\n" + ("\n".join(fails) if fails else "None in this run.") + "\n")
    return "\n".join(out)
