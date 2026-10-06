"""Append-only, hash-chained audit log."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import AuditLog

GENESIS = "0" * 64


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _utc_naive(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is not None:
        ts = ts.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return ts


def _digest(prev: str, ts: dt.datetime, run_id: str | None, actor: str, action: str, payload: dict) -> str:
    body = _canonical({"ts": _utc_naive(ts).isoformat(), "run_id": run_id, "actor": actor,
                       "action": action, "payload": payload})
    return hashlib.sha256((prev + body).encode()).hexdigest()


def append(db: Session, run_id: str | None, actor: str, action: str, payload: dict | None = None) -> AuditLog:
    """Add an audit entry in the caller's transaction (commit is the caller's job)."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(727001)"))  # serialise chain writes
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS
    clean = json.loads(json.dumps(payload or {}, default=str))
    ts = dt.datetime.now(dt.timezone.utc)
    row = AuditLog(ts=ts, run_id=run_id, actor=actor, action=action, payload=clean, prev_hash=prev,
                   hash=_digest(prev, ts, run_id, actor, action, clean))
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> dict:
    prev, n = GENESIS, 0
    for row in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        n += 1
        expected = _digest(prev, row.ts, row.run_id, row.actor, row.action, row.payload)
        if row.prev_hash != prev or row.hash != expected:
            return {"ok": False, "checked": n, "first_bad_id": row.id}
        prev = row.hash
    return {"ok": True, "checked": n, "first_bad_id": None}
