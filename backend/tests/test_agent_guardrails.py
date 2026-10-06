"""LLM-mode behaviour with a scripted model: the model can choose tools but cannot change validated inputs or prices."""
import json
from decimal import Decimal

import pytest
from conftest import DATA

from app.agents.llm import LLMError, LLMResponse
from app.agents.llm import ScriptedLLM
from app.agents.orchestrator import summary_is_grounded
from app.models import User
from app.services import rfq_service, runs
from sqlalchemy import select

RFQ_TEXT = (DATA / "rfqs" / "RFQ-001.pdf")


def fc(name, **args):
    return LLMResponse(function_calls=[{"name": name, "args": args}], raw_parts=[{"functionCall": {"name": name, "args": args}}],
                       usage={"prompt_tokens": 100, "output_tokens": 10}, latency_ms=5)


def say(text):
    return LLMResponse(text=text, usage={"prompt_tokens": 50, "output_tokens": 20}, latency_ms=4)


EXTRACTION = say(json.dumps({"product_ref": "CHEM-X01", "quantity_value": 5, "quantity_unit": "MT", "purity_min_percent": 99,
                             "destination_text": "Houston", "required_date_text": "2026-12-15",
                             "customer_name": "Brightwater Coatings LLC"}))


def run_with(db, script):
    user = db.scalar(select(User).where(User.email == "analyst@opspilot.demo"))
    run = rfq_service.create_run_from_upload(db, user, "RFQ-001.pdf", RFQ_TEXT.read_bytes())
    llm = ScriptedLLM(script)
    rfq_service.process_run(run.id, llm=llm)
    db.expire_all()
    return runs.run_detail(db, run.id), llm


def rules_baseline(db):
    user = db.scalar(select(User).where(User.email == "analyst@opspilot.demo"))
    run = rfq_service.create_run_from_upload(db, user, "RFQ-001.pdf", RFQ_TEXT.read_bytes())
    rfq_service.process_run(run.id, llm=None)
    db.expire_all()
    return runs.run_detail(db, run.id)


def test_model_cannot_change_quantity_or_price(db):
    base = rules_baseline(db)
    d, llm = run_with(db, [
        EXTRACTION,
        fc("search_product", query="CHEM-X01"),
        # the model tries to quote 1 kg of a different product, sneaking in a price-ish argument
        fc("calculate_quote", product_code="CHEM-X02", qty_kg=1, purity_min=50, incoterm="FOB",
           destination_port="Nowhere", rfq_date="2026-10-06", option_id="MF:1", price_per_kg=0.01),
        say("Quoted the 5000 kg order using the plant option."),
    ])
    assert d["run"]["status"] == "pending_approval" and d["run"]["mode"] == "llm"
    q = d["quote"]
    assert q["breakdown"]["product_code"] == "CHEM-X01" and q["breakdown"]["qty_kg"] == 5000.0
    assert q["breakdown"]["incoterm"] == base["quote"]["breakdown"]["incoterm"]
    assert Decimal(q["total"]) == Decimal(base["quote"]["total"])        # same deterministic math as rules mode
    ev = [a for a in d["audit"] if a["action"] == "tool_calls"][0]["payload"]["pinned_overrides"]
    assert {"product_code", "qty_kg", "purity_min"} <= {o["arg"] for o in ev}
    assert d["run"]["metrics"]["llm_calls"] == 3 and d["run"]["metrics"]["prompt_tokens"] > 0


def test_skipped_calculate_quote_is_forced_and_flagged(db):
    d, _ = run_with(db, [EXTRACTION, fc("search_product", query="CHEM-X01"), say("Done, the price is about 5 dollars.")])
    codes = [w["code"] for w in d["quote"]["warnings"]]
    assert "AGENT_STEP_FORCED" in codes
    assert d["quote"]["breakdown"]["total"] and d["run"]["status"] == "pending_approval"


def test_ungrounded_numbers_in_model_summary_are_rejected(db):
    d, _ = run_with(db, [EXTRACTION, fc("calculate_quote", option_id="MF:1"),
                         say("I negotiated the price down to 1.11 dollars per kg, total 5550.")])
    codes = [w["code"] for w in d["quote"]["warnings"]]
    assert "SUMMARY_REJECTED" in codes
    assert "1.11" not in d["quote"]["reasoning_summary"]


def test_grounded_summary_is_kept(db):
    base = rules_baseline(db)
    b = base["quote"]["breakdown"]
    d, _ = run_with(db, [EXTRACTION, fc("calculate_quote", option_id="MF:1"),
                         say(f"Quoted 5000 kg at {b['price_per_kg']} USD/kg, total {b['total']} USD.")])
    assert "SUMMARY_REJECTED" not in [w["code"] for w in d["quote"]["warnings"]]
    assert b["total"] in d["quote"]["reasoning_summary"]


def test_non_whitelisted_tool_is_rejected(db):
    d, _ = run_with(db, [EXTRACTION, fc("check_quality", product_code="CHEM-X01", measurements={}),
                         fc("calculate_quote", option_id="MF:1"), say("ok")])
    bad = [t for t in d["tool_calls"] if t["tool"] == "check_quality"]
    assert bad and bad[0]["ok"] is False
    assert d["run"]["status"] == "pending_approval"


def test_invalid_option_id_cannot_produce_a_price(db):
    d, _ = run_with(db, [EXTRACTION, fc("calculate_quote", option_id="SP:99999"), say("ok")])
    # the bad call failed; the workflow then ran the rules plan and priced with a valid, feasible option
    assert any(t["tool"] == "calculate_quote" and not t["ok"] for t in d["tool_calls"])
    assert "AGENT_STEP_FORCED" in [w["code"] for w in d["quote"]["warnings"]]


def test_llm_outage_falls_back_to_rules(db):
    d, _ = run_with(db, [EXTRACTION])  # script runs out after extraction -> LLMError in the agent loop
    assert d["run"]["status"] == "pending_approval" and d["run"]["mode"] == "rules"
    assert "LLM_UNAVAILABLE" in [w["code"] for w in d["quote"]["warnings"]]


def test_bad_llm_extraction_falls_back_to_rules_extractor(db):
    d, _ = run_with(db, [say("this is not json")])
    assert d["extraction"]["method"] == "rules"
    assert any(i["code"] == "NOTE" for i in d["extraction"]["issues"])
    assert d["extraction"]["fields"]["product_code"] == "CHEM-X01"


def test_llm_extraction_goes_through_deterministic_normalization(db):
    # model returns the literal strings; unit conversion is done in code, not by the model
    d, _ = run_with(db, [EXTRACTION, fc("calculate_quote", option_id="MF:1"), say("ok")])
    assert d["extraction"]["method"] == "llm"
    assert d["extraction"]["fields"]["quantity_kg"] == 5000.0
    assert d["extraction"]["raw"]["quantity_unit"] == "MT"


@pytest.mark.parametrize("text,ok", [
    ("5000 kg at 13.72 USD/kg", True),
    ("Total 68,601.71 USD with 18% margin", True),
    ("I got a 40 percent discount, 9.99 per kg", False),
])
def test_summary_grounding_unit(text, ok):
    evidence = [{"price_per_kg": "13.7203", "total": "68601.71", "margin_pct": "0.18"}, {"qty_kg": 5000.0}]
    assert summary_is_grounded(text, evidence) is ok
