import json

import pytest
from sqlalchemy import select, text

from app.models import AuditLog
from app.services import audit


def test_chain_is_valid_and_detects_tampering(client, analyst, db):
    from conftest import upload_rfq

    upload_rfq(client, analyst, "RFQ-004.pdf")
    assert audit.verify_chain(db)["ok"] is True
    target = db.scalars(select(AuditLog).where(AuditLog.action == "fields_extracted").order_by(AuditLog.id.desc())).first()
    # the ORM refuses updates/deletes ...
    target.payload = {"tampered": True}
    with pytest.raises(RuntimeError):
        db.flush()
    db.rollback()
    with pytest.raises(RuntimeError):
        db.delete(db.get(AuditLog, target.id))
        db.flush()
    db.rollback()
    # ... and a direct SQL edit (bypassing the ORM) is caught by the hash chain
    cast = "cast(:p as json)" if db.get_bind().dialect.name == "postgresql" else ":p"
    sql = text(f"update audit_log set payload = {cast} where id = :i")
    original = db.execute(text("select payload from audit_log where id = :i"), {"i": target.id}).scalar()
    original = original if isinstance(original, str) else json.dumps(original)
    db.execute(sql, {"p": '{"tampered": true}', "i": target.id})
    db.commit()
    db.expire_all()  # re-read from the database, not the identity map
    try:
        res = audit.verify_chain(db)
        assert res["ok"] is False and res["first_bad_id"] == target.id
    finally:  # restore so other tests keep a valid chain
        db.execute(sql, {"p": original, "i": target.id})
        db.commit()
        db.expire_all()
    assert audit.verify_chain(db)["ok"] is True


def test_concurrent_writers_keep_chain_valid(db):
    """Postgres only: the advisory lock serialises appends so parallel workflows cannot fork the chain."""
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("advisory lock only applies to PostgreSQL")
    import threading

    from app.core.db import SessionLocal

    def work(n):
        with SessionLocal() as s:
            for i in range(10):
                audit.append(s, None, f"worker{n}", "concurrency_test", {"i": i})
                s.commit()

    ts = [threading.Thread(target=work, args=(n,)) for n in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    db.expire_all()
    assert audit.verify_chain(db)["ok"] is True
