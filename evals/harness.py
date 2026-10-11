"""Shared eval setup: isolated database, real synthetic data, real pipeline."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATASETS = ROOT / "evals" / "datasets"
REFERENCE_DATE = "2026-10-01"  # the date the synthetic price lists and eval cases were generated against


def load(name: str):
    return json.loads((DATASETS / f"{name}.json").read_text())


def setup(use_llm: bool = False, gemini_embeddings: bool = False) -> Path:
    """Point the app at a throwaway SQLite DB + storage dir and load reference data and the knowledge base."""
    tmp = Path(tempfile.mkdtemp(prefix="opspilot-eval-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp / 'eval.db'}"
    os.environ["STORAGE_DIR"] = str(tmp / "storage")
    os.environ["REFERENCE_DATE"] = REFERENCE_DATE
    os.environ["JWT_SECRET"] = "eval-secret-eval-secret-eval-secret-0123"
    if use_llm:
        if not os.environ.get("GEMINI_API_KEY"):
            sys.exit("--llm needs GEMINI_API_KEY in the environment")
        os.environ["LLM_MODE"] = "llm"
        # Embeddings have their own quota and are not what --llm is measuring. Keeping the
        # deterministic embedder also makes retrieval identical to the rules-mode run.
        os.environ["EMBEDDER"] = "gemini" if gemini_embeddings else "hashing"
    else:
        os.environ["LLM_MODE"] = "rules"
        os.environ["EMBEDDER"] = "hashing"
        os.environ.pop("GEMINI_API_KEY", None)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.bootstrap import bootstrap

    bootstrap()
    return tmp


def analyst(db):
    from sqlalchemy import select

    from app.models import User

    return db.scalar(select(User).where(User.email == "analyst@opspilot.demo"))


_MIN_GAP_S = 0.0
_last_call = [0.0]


def set_rate_limit(rpm: float) -> None:
    """Space pipeline runs out to stay under a per-minute model quota (0 = no pacing)."""
    global _MIN_GAP_S
    _MIN_GAP_S = 60.0 / rpm if rpm and rpm > 0 else 0.0


def _pace() -> None:
    if _MIN_GAP_S:
        wait = _last_call[0] + _MIN_GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    _last_call[0] = time.monotonic()


def run_rfq_file(rel: str) -> dict:
    """Run one RFQ file through the real upload + background-job pipeline; return the run detail."""
    from app.core.db import SessionLocal
    from app.services import rfq_service, runs

    _pace()
    path = DATA / rel
    with SessionLocal() as db:
        run = rfq_service.create_run_from_upload(db, analyst(db), path.name, path.read_bytes())
        rid = run.id
    rfq_service.process_run(rid)
    with SessionLocal() as db:
        return runs.run_detail(db, rid)


def run_coa_file(rel: str) -> dict:
    from app.core.db import SessionLocal
    from app.services import coa_service, runs

    _pace()
    path = DATA / rel
    with SessionLocal() as db:
        run = coa_service.create_run(db, analyst(db), path.name, path.read_bytes())
        rid = run.id
    coa_service.process_run(rid)
    with SessionLocal() as db:
        return runs.run_detail(db, rid)


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, max(0, round(p * (len(vals) - 1))))], 1)


def rate(n: int, d: int) -> dict:
    return {"passed": n, "total": d, "rate": round(n / d, 4) if d else None}
