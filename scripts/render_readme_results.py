"""Fill the results table in README.md from evals/results/latest.json (no hand-typed numbers)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "evals/results/latest.json").read_text())
s, m = d["suites"], d["meta"]
r = lambda x: f"{x['passed']}/{x['total']} ({x['rate'] * 100:.1f}%)"  # noqa: E731
lat = s["latency"]
rows = [
    ("RFQ field extraction (all 8 fields exact)", f"{m['datasets']['rfq']} RFQ PDFs", r(s["rfq_extraction"]["all_fields_exact"]), "Rules extractor was tuned on this set: optimistic"),
    ("Pricing: price/kg exact vs reference engine", "23 priceable RFQs", r(s["pricing"]["price_per_kg_exact"]), "Reference engine written for this project"),
    ("Pricing: selected source matches", "23", r(s["pricing"]["selected_option_match"]), ""),
    ("Warning set exact / critical precision & recall", "30", f"{r(s['pricing']['warning_set_exact'])} / {s['pricing']['critical_warning_precision']} & {s['pricing']['critical_warning_recall']}", ""),
    ("Tool calls: calculate_quote last, args match validated fields", "30", f"{r(s['tool_calls']['calculate_quote_last'])}; {r(s['tool_calls']['calc_args_match_validated_fields'])}", "Rules-mode fixed plan"),
    ("Agent guardrails vs a scripted misbehaving model", "7 scenarios", r(s["guardrails_scripted_agent"]), "Fake LLM, not Gemini"),
    ("COA verdict accuracy", f"{m['datasets']['coa']} COA PDFs", r(s["coa"]["verdict_accuracy"]), f"Unsafe passes: {s['coa']['unsafe_passes (non-PASS COA judged PASS)']}; false alarms: {s['coa']['false_alarms (PASS COA flagged)']}"),
    ("COA parameters extracted exactly", "15", r(s["coa"]["parameters_extraction_exact"]), "Template-generated PDFs"),
    ("Document-set consistency: exact finding match", f"{m['datasets']['consistency']} sets", r(s["consistency"]["exact_finding_set_match"]), "7 inconsistent, 3 clean"),
    ("Blocked-render gate after a bad edit", "4", r(s["consistency"]["gate_blocks_rendering_after_inconsistent_edit"]), ""),
    ("Retrieval hit@1 / hit@3 / MRR", f"{m['datasets']['retrieval']} queries", f"{r(s['retrieval']['hit@1'])} / {r(s['retrieval']['hit@3'])} / {s['retrieval']['mrr']}", f"Embedder: {m['embedder']} (lexical hashing). Misses listed in the report"),
    ("Quote total equals deterministic tool result", "23", r(s["grounding"]["quote_total_equals_deterministic_tool_result"]), ""),
    ("KB citations point to indexed documents", "94 citations", r(s["grounding"]["kb_citations_point_to_ingested_documents"]), "Checks the document exists, not that it supports the claim"),
    ("No price produced for incomplete RFQs", "7", r(s["grounding"]["no_price_invented_for_incomplete_rfqs"]), ""),
    ("Prompt-injection RFQ flagged, price unaffected", "1", r(s["grounding"]["prompt_injection_flagged_and_price_unaffected"]), "One case"),
    ("RFQ end-to-end latency p50 / p95 (ms)", "30 runs", f"{lat['rfq_end_to_end_ms']['p50']} / {lat['rfq_end_to_end_ms']['p95']}", "Rules mode, SQLite, sandbox CPU. No LLM latency measured"),
]
table = "| Check | Cases | Result | Caveat |\n|---|---|---|---|\n" + "\n".join(f"| {a} | {b} | {c} | {e} |" for a, b, c, e in rows)
stamp = f"Mode: **{m['mode']}**, generated {m['generated_at']}, embedder `{m['embedder']}`. Full report: [`evals/results/REPORT.md`](evals/results/REPORT.md)."
p = ROOT / "README.md"
txt = p.read_text()
txt = re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->", lambda _: f"<!-- RESULTS:START -->\n{stamp}\n\n{table}\n<!-- RESULTS:END -->", txt, flags=re.S)
p.write_text(txt)
print("README results updated")
