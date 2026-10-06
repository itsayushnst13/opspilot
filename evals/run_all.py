"""Run every evaluation against the real pipeline and write evals/results/{latest.json,REPORT.md}.

    python evals/run_all.py            # deterministic rules mode (no API key needed)
    GEMINI_API_KEY=... python evals/run_all.py --llm   # same suites with Gemini function calling

Nothing here is hard-coded: every number in the report is computed from this run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals import harness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use Gemini (needs GEMINI_API_KEY)")
    ap.add_argument("--out", default=str(ROOT / "evals" / "results"))
    args = ap.parse_args()
    started = time.perf_counter()
    harness.setup(use_llm=args.llm)

    from evals.report import write_report
    from evals.suites import coa, consistency, guardrails, retrieval, rfq

    from app.core.config import get_settings

    rfq_cases, coa_cases = harness.load("rfq_cases"), harness.load("coa_cases")
    print(f"running {len(rfq_cases)} RFQs ...", flush=True)
    rfq_runs = rfq.run_all(rfq_cases)
    print(f"running {len(coa_cases)} COAs ...", flush=True)
    coa_runs = coa.run_all(coa_cases)

    rfq_res = rfq.evaluate(rfq_cases, rfq_runs)
    base = rfq_runs["RFQ-001"]["quote"]
    suites = {
        "rfq_extraction": rfq_res["extraction"], "pricing": rfq_res["pricing"], "tool_calls": rfq_res["tool_calls"],
        "coa": coa.evaluate(coa_cases, coa_runs),
        "consistency": consistency.evaluate(),
        "retrieval": retrieval.evaluate(),
        "guardrails_scripted_agent": guardrails.part_a(base["total"], base["price_per_kg"]) if not args.llm else
        {"skipped": "scripted-model scenarios run in rules mode only"},
        "grounding": guardrails.part_b(rfq_cases, rfq_runs),
    }
    lat = [r["run"]["latency_ms"] for r in rfq_runs.values()]
    clat = [r["run"]["latency_ms"] for r in coa_runs.values()]
    tool_ms = [r["run"]["metrics"].get("tool_ms", 0) for r in rfq_runs.values()]
    llm_ms = [r["run"]["metrics"].get("llm_ms", 0) for r in rfq_runs.values()]
    suites["latency"] = {
        "rfq_end_to_end_ms": {"n": len(lat), "p50": harness.pct(lat, .5), "p95": harness.pct(lat, .95), "max": max(lat)},
        "coa_end_to_end_ms": {"n": len(clat), "p50": harness.pct(clat, .5), "p95": harness.pct(clat, .95), "max": max(clat)},
        "rfq_tool_ms_p50": harness.pct(tool_ms, .5), "rfq_llm_ms_p50": harness.pct(llm_ms, .5),
        "tokens_total": sum(r["run"]["metrics"].get("prompt_tokens", 0) + r["run"]["metrics"].get("output_tokens", 0) for r in rfq_runs.values()),
        "note": "SQLite on a shared sandbox CPU; indicative only. In rules mode there are no model calls, so no LLM time or tokens.",
    }
    s = get_settings()
    out = {
        "meta": {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "mode": s.effective_mode,
                 "model": s.gemini_model if s.effective_mode == "llm" else None, "embedder": suites["retrieval"]["embedder"],
                 "python": platform.python_version(), "reference_date": harness.REFERENCE_DATE,
                 "datasets": {"rfq": len(rfq_cases), "coa": len(coa_cases), "consistency": suites["consistency"]["cases"],
                              "retrieval": suites["retrieval"]["queries"]},
                 "duration_s": round(time.perf_counter() - started, 1)},
        "suites": suites,
    }
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / ("latest.json" if not args.llm else "latest_llm.json")).write_text(json.dumps(out, indent=2, default=str))
    (outdir / ("REPORT.md" if not args.llm else "REPORT_llm.md")).write_text(write_report(out))
    print(f"done in {out['meta']['duration_s']}s -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
