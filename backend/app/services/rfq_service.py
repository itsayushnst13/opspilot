"""RFQ workflow: upload -> parse -> extract -> agent (RAG + tools) -> suggested quote -> human approval."""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.extract_rfq import (RawRFQ, detect_injection, extract_raw_llm, extract_raw_rules, normalize_rfq)
from ..agents.llm import LLMClient, LLMError, get_llm
from ..agents.orchestrator import RFQOrchestrator
from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.logging import log
from ..docproc.parsers import ParseError, parse_bytes
from ..docproc.validate import UploadError, validate_upload
from ..models import (Extraction, Product, Quote, ShippingRate, ToolCall, UploadedFile, User, WorkflowRun)
from ..tools.registry import RFQ_AGENT_TOOLS, ToolRegistry
from ..tools.warnings import warn
from . import audit, runs, storage

logger = logging.getLogger("opspilot.rfq")
MAX_TEXT_CHARS = 20_000


def create_run_from_upload(db: Session, user: User, filename: str | None, content: bytes) -> WorkflowRun:
    s = get_settings()
    name, ext = validate_upload(filename, content, s.max_upload_bytes, allowed={".pdf", ".txt"})
    run = runs.new_run(db, "rfq", user.email, s.effective_mode)
    up = storage.save_upload(db, run.id, name, ext, content)
    audit.append(db, run.id, user.email, "rfq_uploaded", {"filename": name, "size": up.size, "sha256": up.sha256})
    db.commit()
    return run


def create_run_from_text(db: Session, user: User, text: str) -> WorkflowRun:
    text = (text or "").strip()
    if not text:
        raise UploadError("RFQ text is empty", 400)
    if len(text) > MAX_TEXT_CHARS:
        raise UploadError(f"RFQ text exceeds {MAX_TEXT_CHARS} characters", 413)
    return create_run_from_upload(db, user, "typed-rfq.txt", text.encode("utf-8"))


def _recorder(db: Session, run_id: str) -> Callable[[dict], None]:
    def rec(call: dict) -> None:
        db.add(ToolCall(run_id=run_id, seq=call["seq"], tool=call["tool"], args=jsonable_encoder(call["args"]),
                        result=jsonable_encoder(call["result"]), ok=call["ok"], error=call["error"],
                        duration_ms=call["duration_ms"]))
    return rec


def _extract(db: Session, text: str, llm: LLMClient | None) -> tuple[RawRFQ, str, dict, list[str]]:
    names = [n for (n,) in db.execute(select(Product.name))]
    ports = sorted({p for (p,) in db.execute(select(ShippingRate.dest_port))})
    notes: list[str] = []
    if llm is not None:
        try:
            raw, usage = extract_raw_llm(text, llm)
            return raw, "llm", usage, notes
        except (LLMError, ValueError) as exc:
            notes.append(f"LLM extraction failed ({exc.__class__.__name__}); regex rules were used instead")
    return extract_raw_rules(text, names, ports), "rules", {}, notes


def process_run(run_id: str, llm: LLMClient | None | str = "default") -> None:
    """Background job: runs the whole pipeline with its own DB session."""
    db = SessionLocal()
    started = time.perf_counter()
    run = db.get(WorkflowRun, run_id)
    if run is None:
        db.close()
        return
    actor = run.created_by
    try:
        llm_client = get_llm() if llm == "default" else llm
        file = db.scalar(select(UploadedFile).where(UploadedFile.run_id == run_id))
        runs.set_stage(db, run, "parsing")
        s = get_settings()
        try:
            parsed = parse_bytes(file.filename, storage.read_upload(file.stored_name), s.max_pdf_pages, s.max_sheet_rows)
        except ParseError as exc:
            audit.append(db, run_id, "system", "workflow_failed", {"stage": "parsing", "error": str(exc)})
            runs.finish(db, run, "failed", started, error=str(exc))
            return
        text = parsed.text

        runs.set_stage(db, run, "extracting")
        t0 = time.perf_counter()
        raw, method, ex_usage, notes = _extract(db, text, llm_client)
        fields, issues = normalize_rfq(raw, db, s.today)
        extra = []
        for i in issues:
            if i["code"] in ("UNIT_ASSUMED", "UNIT_CONVERTED", "DATE_AMBIGUOUS", "MISSING_FIELD", "UNKNOWN_PRODUCT"):
                extra.append(warn(i["code"], i["message"]))
        if detect_injection(text):
            extra.append(warn("PROMPT_INJECTION_SUSPECTED"))
        extraction_ms = (time.perf_counter() - t0) * 1000
        ex = Extraction(run_id=run_id, method=method, raw=jsonable_encoder(raw), fields=jsonable_encoder(fields),
                        missing=[], issues=issues + [{"code": "NOTE", "message": n} for n in notes])
        db.add(ex)
        audit.append(db, run_id, "ai", "fields_extracted",
                     {"method": method, "fields": jsonable_encoder(fields), "issues": [i["code"] for i in issues],
                      "injection_suspected": any(w["code"] == "PROMPT_INJECTION_SUSPECTED" for w in extra)})
        db.commit()

        runs.set_stage(db, run, "agent")
        t1 = time.perf_counter()
        registry = ToolRegistry(db, allowed=RFQ_AGENT_TOOLS, recorder=_recorder(db, run_id))
        orch = RFQOrchestrator(registry, llm_client)
        result = orch.run(fields, extra)
        agent_ms = (time.perf_counter() - t1) * 1000

        ex.missing = result["missing"]
        run.mode = result["mode"]
        kb_sources = [{"kind": "kb", "ref": p["citation"], "what": p["title"], "score": p["score"]}
                      for p in result.get("knowledge", [])]
        data_sources = [{"kind": "data", **src} for src in result["sources"]]
        audit.append(db, run_id, "system", "knowledge_retrieved", {"citations": [k["ref"] for k in kb_sources]})
        audit.append(db, run_id, "system", "tool_calls",
                     {"calls": [{"tool": e["name"], "forced": e["forced"], "ok": "error" not in e["result"]} for e in orch.log],
                      "pinned_overrides": result["pinned_overrides"]})
        if result["status"] == "ready_for_review" and result["breakdown"]:
            b = result["breakdown"]
            db.add(Quote(run_id=run_id, status="pending_approval", breakdown=jsonable_encoder(b),
                         price_per_kg=b["price_per_kg"], total=b["total"], currency=b["currency"],
                         warnings=result["warnings"], sources=data_sources + kb_sources,
                         reasoning_summary=result["reasoning_summary"]))
            audit.append(db, run_id, "system", "quote_calculated",
                         {"price_per_kg": b["price_per_kg"], "total": b["total"], "lines": b["lines"],
                          "selected_option": result["selected_option"]["option_id"]})
            status = "pending_approval"
        else:
            status = "needs_info"
            run.metrics = {**(run.metrics or {}), "needs_info": {"missing": result["missing"],
                                                                  "warnings": result["warnings"],
                                                                  "summary": result["reasoning_summary"]}}
        audit.append(db, run_id, "ai", "ai_decision",
                     {"status": status, "mode": result["mode"], "summary_source": result["summary_source"],
                      "warnings": [w["code"] for w in result["warnings"]]})
        u = result["usage"]
        runs.finish(db, run, status, started, metrics={
            "extraction_ms": round(extraction_ms, 1), "agent_ms": round(agent_ms, 1),
            "tool_ms": round(registry.total_ms, 1), "tool_calls": registry.seq, "llm_calls": u["llm_calls"],
            "llm_ms": round(u["llm_ms"], 1), "prompt_tokens": u["prompt_tokens"] + ex_usage.get("prompt_tokens", 0),
            "output_tokens": u["output_tokens"] + ex_usage.get("output_tokens", 0),
            "extraction_method": method, "needs_info": (run.metrics or {}).get("needs_info")})
        log(logger, "rfq run finished", run_id=run_id, status=status, mode=result["mode"],
            latency_ms=run.latency_ms, tool_calls=registry.seq)
    except Exception as exc:  # unexpected: record, never leak internals to the client
        db.rollback()
        logger.exception("rfq run failed", extra={"ctx": {"run_id": run_id}})
        run = db.get(WorkflowRun, run_id)
        audit.append(db, run_id, "system", "workflow_failed", {"error": exc.__class__.__name__})
        runs.finish(db, run, "failed", started, error=f"Processing failed ({exc.__class__.__name__}). See server logs.")
    finally:
        db.close()
