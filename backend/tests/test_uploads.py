import io
import zipfile

import pytest
from conftest import DATA

from app.docproc.validate import UploadError, safe_filename, validate_upload

MB = 1024 * 1024


def post(client, headers, name, content, ctype="application/pdf", url="/api/rfq"):
    return client.post(url, files={"file": (name, content, ctype)}, headers=headers)


def test_rejects_bad_extension_and_content(client, analyst):
    assert post(client, analyst, "evil.exe", b"MZ....").status_code == 415
    assert post(client, analyst, "x.pdf", b"this is not a pdf").status_code == 415
    assert post(client, analyst, "x.txt", b"\x00\x01\x02binary").status_code == 415
    assert post(client, analyst, "x.pdf", b"").status_code == 400
    assert post(client, analyst, "noext", b"hello").status_code == 415


def test_rejects_oversize(client, analyst):
    big = b"%PDF-1.4\n" + b"0" * (6 * MB)
    assert post(client, analyst, "big.pdf", big).status_code == 413


def test_text_rfq_limits(client, analyst):
    assert client.post("/api/rfq/text", json={"text": "   "}, headers=analyst).status_code in (400, 422)
    assert client.post("/api/rfq/text", json={"text": "x" * 20_001}, headers=analyst).status_code == 422


def test_unreadable_pdf_fails_visibly(client, analyst):
    r = post(client, analyst, "broken.pdf", b"%PDF-1.4\nnot really a pdf\n%%EOF")
    assert r.status_code == 202
    d = client.get(f"/api/rfq/{r.json()['run_id']}", headers=analyst).json()
    assert d["run"]["status"] == "failed" and d["run"]["error"]
    assert "Traceback" not in d["run"]["error"]
    assert any(a["action"] == "workflow_failed" for a in d["audit"])


def test_filename_traversal_is_neutralised():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\win.ini") == "win.ini"
    assert "/" not in safe_filename("a/b/c.pdf")
    name, ext = validate_upload("../../x.pdf", b"%PDF-1.4 hi", 1000, {".pdf"})
    assert name == "x.pdf" and ext == ".pdf"


def test_xlsx_checks():
    with pytest.raises(UploadError):
        validate_upload("a.xlsx", b"not a zip", 1000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "x")
    with pytest.raises(UploadError):
        validate_upload("a.xlsx", buf.getvalue(), 10_000)
    good = (DATA / "pricing" / "margin_rules.xlsx").read_bytes()
    assert validate_upload("m.xlsx", good, 5 * MB)[1] == ".xlsx"


def test_stored_name_is_run_id_not_client_name(client, analyst, db):
    from app.models import UploadedFile
    from sqlalchemy import select

    r = post(client, analyst, "../../sneaky name.pdf", (DATA / "rfqs" / "RFQ-003.pdf").read_bytes())
    row = db.scalar(select(UploadedFile).where(UploadedFile.run_id == r.json()["run_id"]))
    assert row.stored_name == f"{r.json()['run_id']}.pdf" and row.filename == "sneaky name.pdf"
