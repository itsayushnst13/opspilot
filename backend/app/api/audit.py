from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import get_current_user
from ..models import AuditLog, User
from ..services import audit as audit_svc
from ..services import runs

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(run_id: str | None = None, action: str | None = None, actor: str | None = None, limit: int = 200,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 1000)
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if run_id:
        stmt = stmt.where(AuditLog.run_id == run_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    total = db.scalar(select(func.count()).select_from(AuditLog))
    items = [{"id": a.id, "ts": a.ts.isoformat(), "run_id": a.run_id, "actor": a.actor, "action": a.action,
              "payload": a.payload, "prev_hash": a.prev_hash, "hash": a.hash} for a in db.scalars(stmt)]
    return {"total": total, "items": items}


@router.get("/verify")
def verify(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return audit_svc.verify_chain(db)
