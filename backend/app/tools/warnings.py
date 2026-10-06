"""Warning catalog shared by the pricing tools, orchestrator and UI."""
from __future__ import annotations

SEVERITY = {
    "MISSING_FIELD": "critical", "UNKNOWN_PRODUCT": "critical", "PURITY_UNAVAILABLE": "critical",
    "NO_FEASIBLE_SOURCE": "critical", "NO_SHIPPING_RATE": "critical", "DEADLINE_INFEASIBLE": "critical",
    "PROMPT_INJECTION_SUSPECTED": "critical",
    "DEADLINE_TIGHT": "warning", "PRICE_VALIDITY_SHORT": "warning", "INCOTERM_ASSUMED": "warning",
    "DEVIATION_FROM_HISTORY": "warning", "OPTION_NOT_CHEAPEST": "warning", "PURITY_ASSUMED": "warning",
    "UNIT_ASSUMED": "warning", "DATE_AMBIGUOUS": "warning", "AGENT_STEP_FORCED": "warning",
    "HAZMAT": "info", "LLM_UNAVAILABLE": "info", "SUMMARY_REJECTED": "info", "DELIVERY_DATE_MISSING": "info", "UNIT_CONVERTED": "info",
}

DEFAULT_MESSAGES = {
    "MISSING_FIELD": "Required information is missing from the RFQ.",
    "UNKNOWN_PRODUCT": "The requested product is not in the catalogue.",
    "PURITY_UNAVAILABLE": "No source offers the requested purity.",
    "NO_FEASIBLE_SOURCE": "No supplier or plant can supply this quantity/purity on valid prices.",
    "NO_SHIPPING_RATE": "No shipping rate exists for this origin and destination.",
    "DEADLINE_INFEASIBLE": "No source can meet the requested delivery date.",
    "PROMPT_INJECTION_SUSPECTED": "The RFQ contains text that looks like instructions to the system. It was ignored.",
    "DEADLINE_TIGHT": "Delivery date can be met with less than 7 days of slack.",
    "PRICE_VALIDITY_SHORT": "The selected price expires within the 14-day quote validity period.",
    "INCOTERM_ASSUMED": "Incoterm was missing or unsupported; CIF was assumed.",
    "DEVIATION_FROM_HISTORY": "Price differs by more than 15% from the median of previous quotes.",
    "OPTION_NOT_CHEAPEST": "The selected source is not the cheapest feasible option.",
    "PURITY_ASSUMED": "No purity was requested; the product specification minimum was used.",
    "UNIT_ASSUMED": "The quantity unit was ambiguous and was interpreted as metric tonnes.",
    "DATE_AMBIGUOUS": "The date format was ambiguous (day/month); month-first was assumed.",
    "AGENT_STEP_FORCED": "A required step was not completed by the agent and was run by the workflow.",
    "LLM_UNAVAILABLE": "The language model was unavailable; the deterministic rules plan was used instead.",
    "SUMMARY_REJECTED": "The model's summary contained numbers not found in tool results, so a template summary was used.",
    "HAZMAT": "Dangerous goods: hazmat surcharge and documentation apply.",
    "DELIVERY_DATE_MISSING": "No delivery date was given, so no deadline check was made.",
    "UNIT_CONVERTED": "Quantity was converted to kilograms.",
}

# codes that the pricing-level evals compare against the reference engine
EVAL_CODES = {"MISSING_FIELD", "UNKNOWN_PRODUCT", "PURITY_UNAVAILABLE", "NO_FEASIBLE_SOURCE", "NO_SHIPPING_RATE",
              "DEADLINE_INFEASIBLE", "DEADLINE_TIGHT", "PRICE_VALIDITY_SHORT", "INCOTERM_ASSUMED",
              "DEVIATION_FROM_HISTORY", "PURITY_ASSUMED", "HAZMAT", "DELIVERY_DATE_MISSING",
              "PROMPT_INJECTION_SUSPECTED"}


def warn(code: str, message: str | None = None) -> dict:
    return {"code": code, "severity": SEVERITY[code], "message": message or DEFAULT_MESSAGES[code]}


def has_critical(warnings: list[dict]) -> bool:
    return any(w["severity"] == "critical" for w in warnings)
