"""Safe file storage for uploads and generated documents."""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import UploadedFile


def storage_path(*parts: str) -> Path:
    base = get_settings().storage_dir.resolve()
    p = base.joinpath(*parts).resolve()
    if base not in p.parents and p != base:
        raise ValueError("path escapes storage directory")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(db: Session, run_id: str, filename: str, ext: str, content: bytes) -> UploadedFile:
    stored = f"{run_id}{ext}"  # never use the client-supplied name on disk
    storage_path("uploads", stored).write_bytes(content)
    mime = {".pdf": "application/pdf", ".txt": "text/plain", ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[ext]
    row = UploadedFile(run_id=run_id, filename=filename, stored_name=stored, mime=mime, size=len(content),
                       sha256=hashlib.sha256(content).hexdigest())
    db.add(row)
    db.flush()
    return row


def read_upload(stored_name: str) -> bytes:
    return storage_path("uploads", stored_name).read_bytes()
