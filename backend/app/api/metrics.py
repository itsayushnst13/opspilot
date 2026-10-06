"""Dashboard + observability aggregates computed from workflow_runs / tool_calls (no separate metrics store)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import get_current_user
from ..models import Quote, ToolCall, User, WorkflowRun
from ..services import runs

router = APIRouter(prefix="/api", tags=["metrics"])


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    idx = min(len(vals) - 1, max(0, round(p * (len(vals) - 1))))
    return round(vals[idx], 1)


def compute_metrics(db: Session) -> dict:
    all_runs = db.scalars(select(WorkflowRun)).all()
    done = [r for r in all_runs if r.latency_ms is not None and r.status != "processing"]
    lat = [float(r.latency_ms) for r in done]

    def m(key):  # numeric metrics from runs that have them
        return [float(r.metrics[key]) for r in all_runs if isinstance(r.metrics, dict) and isinstance(r.metrics.get(key), (int, float))]

    by_type: dict[str, dict[str, int]] = {}
    for r in all_runs:
        by_type.setdefault(r.type, {}).setdefault(r.status, 0)
        by_type[r.type][r.status] += 1
    tools = db.execute(select(ToolCall.tool, func.count(), func.avg(ToolCall.duration_ms)).group_by(ToolCall.tool)).all()
    failed = dict(db.execute(select(ToolCall.tool, func.count()).where(ToolCall.ok.is_(False)).group_by(ToolCall.tool)).all())
    return {
        "runs_total": len(all_runs), "by_type": by_type,
        "failed_runs": sum(1 for r in all_runs if r.status == "failed"),
        "latency_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "mean": round(statistics.fmean(lat), 1) if lat else None,
                       "n": len(lat)},
        "llm_ms_total": round(sum(m("llm_ms")), 1), "tool_ms_total": round(sum(m("tool_ms")), 1),
        "tool_calls_total": int(sum(m("tool_calls"))),
        "prompt_tokens": int(sum(m("prompt_tokens"))), "output_tokens": int(sum(m("output_tokens"))),
        "tools": [{"tool": t, "calls": n, "avg_ms": round(float(avg or 0), 2), "failed": failed.get(t, 0)} for t, n, avg in tools],
    }


@router.get("/metrics")
def metrics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return compute_metrics(db)


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recent = db.scalars(select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(10)).all()
    pending = db.scalars(select(WorkflowRun).where(WorkflowRun.type == "rfq", WorkflowRun.status == "pending_approval")
                         .order_by(WorkflowRun.created_at)).all()
    quotes = {q.run_id: q for q in db.scalars(select(Quote).where(Quote.run_id.in_([r.id for r in pending])))} if pending else {}
    s = get_settings()
    return {"mode": s.effective_mode, "model": s.gemini_model if s.effective_mode == "llm" else None,
            "metrics": compute_metrics(db), "recent": [runs.run_summary(r) for r in recent],
            "pending_approvals": [{**runs.run_summary(r), "total": str(quotes[r.id].total) if r.id in quotes else None,
                                    "warnings": [w["code"] for w in quotes[r.id].warnings] if r.id in quotes else []}
                                   for r in pending]}


def results_path() -> Path:
    return get_settings().data_dir.parent / "evals" / "results" / "latest.json"


@router.get("/evals/latest")
def latest_eval(user: User = Depends(get_current_user)):
    p = results_path()
    if not p.exists():
        raise HTTPException(404, "No evaluation results yet. Run: python evals/run_all.py")
    return json.loads(p.read_text())
