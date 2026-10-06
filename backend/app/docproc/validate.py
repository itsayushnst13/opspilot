"""Upload validation: extension allow-list, size limits, magic-byte checks, zip-bomb guard."""
from __future__ import annotations

import io
import os
import re
import zipfile

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv", ".xlsx"}
MAX_UNCOMPRESSED_XLSX = 50 * 1024 * 1024


class UploadError(Exception):
    """Raised for rejected uploads. `status_code` maps to the HTTP response."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def safe_filename(name: str | None) -> str:
    base = os.path.basename((name or "upload").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .") or "upload"
    return base[:120]


def validate_upload(filename: str | None, content: bytes, max_bytes: int,
                    allowed: set[str] = ALLOWED_EXTENSIONS) -> tuple[str, str]:
    """Return (safe_filename, extension) or raise UploadError."""
    name = safe_filename(filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed:
        raise UploadError(f"File type '{ext or 'none'}' is not allowed. Allowed: {', '.join(sorted(allowed))}", 415)
    if len(content) == 0:
        raise UploadError("File is empty", 400)
    if len(content) > max_bytes:
        raise UploadError(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit", 413)
    if ext == ".pdf":
        if b"%PDF-" not in content[:1024]:
            raise UploadError("File content is not a valid PDF", 415)
    elif ext == ".xlsx":
        _check_xlsx(content)
    else:
        if b"\x00" in content:
            raise UploadError("File contains binary data but has a text extension", 415)
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadError("Text files must be UTF-8 encoded", 415) from None
    return name, ext


def _check_xlsx(content: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise UploadError("File content is not a valid XLSX workbook", 415) from None
    names = zf.namelist()
    if "xl/workbook.xml" not in names:
        raise UploadError("File content is not a valid XLSX workbook", 415)
    if any(n.startswith("/") or ".." in n.split("/") for n in names):
        raise UploadError("Workbook contains unsafe paths", 415)
    if sum(i.file_size for i in zf.infolist()) > MAX_UNCOMPRESSED_XLSX:
        raise UploadError("Workbook expands to an unsafe size", 413)
