"""Test setup: a throwaway SQLite file DB (or TEST_DATABASE_URL for Postgres) and the real synthetic data."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="opspilot-test-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ["STORAGE_DIR"] = str(_tmp / "storage")
os.environ["LLM_MODE"] = "rules"
os.environ.pop("GEMINI_API_KEY", None)
os.environ["REFERENCE_DATE"] = "2026-10-01"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"
PASSWORD = "opspilot-demo"


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    from app.api.deps import reset_limits

    reset_limits()


def _login(client, who: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{who}@opspilot.demo", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def analyst(client):
    return _login(client, "analyst")


@pytest.fixture(scope="session")
def approver(client):
    return _login(client, "approver")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin")


@pytest.fixture
def db(client):
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        yield s


def upload_rfq(client, headers, name="RFQ-001.pdf"):
    path = DATA / "rfqs" / name
    r = client.post("/api/rfq", files={"file": (name, path.read_bytes(), "application/pdf")}, headers=headers)
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


def rfq_detail(client, headers, run_id):
    r = client.get(f"/api/rfq/{run_id}", headers=headers)
    assert r.status_code == 200
    return r.json()
