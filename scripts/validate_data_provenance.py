#!/usr/bin/env python3
"""Validate OpsPilot dataset provenance boundaries and public identity references."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EVALS = ROOT / "evals" / "datasets"


def main() -> int:
    manifest = json.loads((DATA / "provenance_manifest.json").read_text(encoding="utf-8"))
    assert manifest["synthetic_operational_data"]["source_type"] == "synthetic"
    assert manifest["public_reference_data"]["source"] == "PubChem"

    verified = DATA / "verified" / "chemical_identity.csv"
    with verified.open(newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    assert len(records) == manifest["public_reference_data"]["record_count"]
    required = {"preferred_name", "cas_number", "pubchem_cid", "molecular_formula",
                "molecular_weight_g_mol", "source_url", "source_type", "review_status"}
    assert records and required.issubset(records[0])
    for row in records:
        assert row["source_type"] == "public_reference", row
        assert row["review_status"] == "source_checked", row
        assert row["source_url"].startswith("https://pubchem.ncbi.nlm.nih.gov/compound/"), row

    totals = {}
    for name in ("rfq_cases", "coa_cases", "consistency_cases", "retrieval_cases"):
        cases = json.loads((EVALS / f"{name}.json").read_text(encoding="utf-8"))
        assert cases, name
        for case in cases:
            p = case.get("provenance", {})
            assert p.get("source_type") == "synthetic", (name, case.get("id"), p)
            assert p.get("split") == "legacy_tuned", (name, case.get("id"), p)
            assert p.get("holdout_eligible") is False, (name, case.get("id"), p)
        totals[name] = len(cases)

    print(json.dumps({
        "status": "passed",
        "public_identity_records": len(records),
        "evaluation_cases": totals,
        "note": "This validates provenance labels and boundaries, not chemical identity correctness or real-world model accuracy."
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
