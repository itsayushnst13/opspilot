"""COA workflow: upload -> parse -> extract -> deterministic comparison -> verdict (review by a human)."""
from __future__ import annotations

import time

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.extract_coa import extract_raw_llm, extract_raw_rules, normalize_coa
from ..agents.llm import LLMError, get_llm
from ..core.config import get_settings
from ..core.db import SessionLocal
from ..core.logging import log
from ..docproc.parsers import ParseError, parse_bytes
from ..docproc.validate import validate_upload
from ..models import COACheck, Product, ToolCall, UploadedFile, User, WorkflowRun
from ..tools.pricing_engine import ToolError
from ..tools.registry import ToolRegistry
import logging

from . import audit, runs, storage

logger = logging.getLogger("opspilot.coa")


def create_run(db: Session, user: User, filename: str | None, content: bytes) -> WorkflowRun:
    s = get_settings()
    name, ext = validate_upload(filename, content, s.max_upload_bytes, allowed={".pdf", ".txt"})
    run = runs.new_run(db, "coa", user.email, s.effective_mode)
    up = storage.save_upload(db, run.id, name, ext, content)
    audit.append(db, run.id, user.email, "coa_uploaded", {"filename": name, "size": up.size, "sha256": up.sha256})
    db.commit()
    return run


def process_run(run_id: str, llm="default") -> None:
    db = SessionLocal()
    started = time.perf_counter()
    run = db.get(WorkflowRun, run_id)
    if run is None:
        db.close()
        return
    try:
        client = get_llm() if llm == "default" else llm
        s = get_settings()
        file = db.scalar(select(UploadedFile).where(UploadedFile.run_id == run_id))
        runs.set_stage(db, run, "parsing")
        try:
            parsed = parse_bytes(file.filename, storage.read_upload(file.stored_name), s.max_pdf_pages, s.max_sheet_rows)
        except ParseError as exc:
            audit.append(db, run_id, "system", "workflow_failed", {"stage": "parsing", "error": str(exc)})
            runs.finish(db, run, "failed", started, error=str(exc))
            return
        runs.set_stage(db, run, "extracting")
        method, usage, note = "rules", {}, None
        raw = None
        if client is not None:
            try:
                raw, usage = extract_raw_llm(parsed.text, client)
                method = "llm"
            except (LLMError, ValueError) as exc:
                note = f"LLM extraction failed ({exc.__class__.__name__}); regex rules were used instead"
        if raw is None:
            raw = extract_raw_rules(parsed.text, [n for (n,) in db.execute(select(Product.name))])
        norm = normalize_coa(raw, db)
        audit.append(db, run_id, "ai", "coa_extracted", {"method": method, "product_code": norm["product_code"],
                                                          "batch_no": norm["batch_no"], "params": norm["params"],
                                                          "issues": norm["issues"] + ([note] if note else [])})
        db.commit()
        if norm["product_code"] is None:
            db.add(COACheck(run_id=run_id, product_code=None, batch_no=norm["batch_no"], verdict="REVIEW REQUIRED",
                            results=[], explanation="REVIEW REQUIRED: the product could not be identified from the COA, so it cannot be compared with a specification.",
                            extracted=jsonable_encoder(norm)))
            verdict = "REVIEW REQUIRED"
            audit.append(db, run_id, "system", "coa_verdict", {"verdict": verdict, "reason": "product unidentified"})
            runs.finish(db, run, "completed", started, metrics={"extraction_method": method, "verdict": verdict})
            return
        runs.set_stage(db, run, "checking")
        reg = ToolRegistry(db, recorder=lambda c: db.add(ToolCall(
            run_id=run_id, seq=c["seq"], tool=c["tool"], args=jsonable_encoder(c["args"]),
            result=jsonable_encoder(c["result"]), ok=c["ok"], error=c["error"], duration_ms=c["duration_ms"])))
        res = reg.call("check_quality", {"product_code": norm["product_code"], "batch_no": norm["batch_no"],
                                          "measurements": norm["params"]})
        if "error" in res:
            raise ToolError(res["error"])
        db.add(COACheck(run_id=run_id, product_code=norm["product_code"], batch_no=norm["batch_no"],
                        verdict=res["verdict"], results=jsonable_encoder(res["results"]),
                        explanation=res["explanation"], extracted=jsonable_encoder(norm)))
        audit.append(db, run_id, "system", "coa_verdict", {"verdict": res["verdict"], "batch_no": norm["batch_no"],
                                                           "failed": [r["parameter"] for r in res["results"] if r["status"] != "PASS"]})
        runs.finish(db, run, "completed", started, metrics={
            "extraction_method": method, "verdict": res["verdict"], "tool_ms": round(reg.total_ms, 1),
            "tool_calls": reg.seq, "prompt_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0), "llm_ms": round(usage.get("llm_ms", 0), 1)})
        log(logger, "coa run finished", run_id=run_id, verdict=res["verdict"], latency_ms=run.latency_ms)
    except Exception as exc:
        db.rollback()
        logger.exception("coa run failed", extra={"ctx": {"run_id": run_id}})
        run = db.get(WorkflowRun, run_id)
        audit.append(db, run_id, "system", "workflow_failed", {"error": exc.__class__.__name__})
        runs.finish(db, run, "failed", started, error=f"Processing failed ({exc.__class__.__name__}). See server logs.")
    finally:
        db.close()
