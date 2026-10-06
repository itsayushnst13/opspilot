"""Idempotent startup: create tables, load reference data, demo users and the knowledge base."""
from __future__ import annotations

import logging

from ..core.config import get_settings
from ..core.db import SessionLocal, init_db
from ..core.logging import log
from ..rag.embed import get_embedder
from ..rag.ingest import ingest_directory
from . import seed

logger = logging.getLogger("opspilot.bootstrap")


def bootstrap(session_factory=SessionLocal, bind=None) -> dict:
    s = get_settings()
    init_db(bind)
    with session_factory() as db:
        ref = seed.seed_reference_data(db, s.data_dir)
        db.commit()
        users = seed.seed_users(db)
        db.commit()
        kb = ingest_directory(db, s.data_dir, get_embedder(s))
    out = {"reference": ref, "users_created": users, "kb": kb}
    log(logger, "bootstrap complete", **{k: str(v) for k, v in out.items()})
    return out
