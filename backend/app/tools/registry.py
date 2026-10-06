"""Tool registry: validated, whitelisted, timed, and recorded tool execution."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..core.schema import to_gemini_schema
from . import catalog, doc_validation, kb, quality
from .pricing_engine import ToolError


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[Session, Any], dict]


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("search_product", "Find catalogue products by code or name. Returns ranked matches with scores.",
         catalog.SearchProductArgs, catalog.search_product),
    Tool("get_product_spec", "Get specification limits, hazmat class and available purity grades for a product.",
         catalog.ProductSpecArgs, catalog.get_product_spec),
    Tool("get_supplier_price", "List feasible supplier price options (with option ids) for a product, quantity and purity.",
         catalog.SourceArgs, catalog.get_supplier_price),
    Tool("get_manufacturing_cost", "List feasible in-house manufacturing options (with option ids).",
         catalog.SourceArgs, catalog.get_manufacturing_cost),
    Tool("get_shipping_cost", "Get ocean freight, transit time and hazmat surcharge for an origin country and destination port.",
         catalog.ShippingArgs, catalog.get_shipping_cost),
    Tool("recommend_source", "Rank all feasible sources including shipping and deadline, and recommend the cheapest one that meets the delivery date.",
         catalog.RecommendArgs, catalog.recommend_source),
    Tool("calculate_quote", "Deterministically price the RFQ for a chosen source option_id. The only way to produce a price.",
         catalog.CalcQuoteArgs, catalog.calculate_quote),
    Tool("search_knowledge_base", "Search specification sheets, supplier profiles, shipping notes and policies. Returns passages with citations.",
         kb.SearchKBArgs, kb.search_knowledge_base),
    Tool("check_quality", "Compare certificate-of-analysis measurements to the product specification.",
         quality.CheckQualityArgs, quality.check_quality),
    Tool("validate_documents", "Check export documents for cross-document mismatches.",
         doc_validation.ValidateDocsArgs, doc_validation.validate_documents),
]}

RFQ_AGENT_TOOLS = ["search_product", "get_product_spec", "search_knowledge_base", "get_supplier_price", "get_manufacturing_cost",
                   "recommend_source", "get_shipping_cost", "calculate_quote"]


class ToolRegistry:
    """Executes tools for one workflow run. Only whitelisted tools can be called."""

    def __init__(self, db: Session, allowed: list[str] | None = None,
                 recorder: Callable[[dict], None] | None = None):
        self.db = db
        self.allowed = set(allowed) if allowed is not None else set(TOOLS)
        self.recorder = recorder
        self.seq = 0
        self.total_ms = 0.0

    def declarations(self, names: list[str] | None = None) -> list[dict]:
        out = []
        for name in names or sorted(self.allowed):
            t = TOOLS[name]
            out.append({"name": t.name, "description": t.description,
                        "parameters": to_gemini_schema(t.args_model.model_json_schema())})
        return out

    def call(self, name: str, args: dict, forced: bool = False) -> dict:
        self.seq += 1
        started = time.perf_counter()
        ok, error, result = True, None, {}
        try:
            if name not in self.allowed or name not in TOOLS:
                raise ToolError(f"Tool '{name}' is not allowed")
            tool = TOOLS[name]
            try:
                parsed = tool.args_model.model_validate(args)
            except ValidationError as exc:
                raise ToolError("Invalid arguments: " + "; ".join(
                    f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())) from None
            result = tool.fn(self.db, parsed)
        except ToolError as exc:
            ok, error, result = False, str(exc), {"error": str(exc)}
        duration = (time.perf_counter() - started) * 1000
        self.total_ms += duration
        if self.recorder:
            self.recorder({"seq": self.seq, "tool": name, "args": args, "result": result, "ok": ok,
                           "error": error, "duration_ms": round(duration, 2), "forced": forced})
        return result
