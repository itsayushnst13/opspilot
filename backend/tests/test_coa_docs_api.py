import json

import pytest
from conftest import DATA

COAS = json.loads((DATA.parent / "evals" / "datasets" / "coa_cases.json").read_text())


def run_coa(client, headers, name):
    r = client.post("/api/quality/coa", files={"file": (name, (DATA / "coas" / name).read_bytes(), "application/pdf")}, headers=headers)
    assert r.status_code == 202, r.text
    return client.get(f"/api/quality/{r.json()['run_id']}", headers=headers).json()


@pytest.mark.parametrize("case", [COAS[0], COAS[7], COAS[12]], ids=lambda c: c["id"])
def test_coa_verdicts(client, analyst, case):
    d = run_coa(client, analyst, case["file"].split("/")[-1])
    assert d["run"]["status"] == "completed"
    assert d["coa"]["verdict"] == case["expected"]["verdict"]
    assert d["coa"]["explanation"]
    got = {r["parameter"]: r["status"] for r in d["coa"]["results"]}
    assert {k: got.get(k) for k in case["expected"]["statuses"]} == case["expected"]["statuses"]
    assert any(a["action"] == "coa_verdict" for a in d["audit"])


def test_coa_text_missing_parameter_and_batch(client, analyst):
    txt = b"Certificate of Analysis\nProduct: CHEM-X01\nPurity: 99.4 %\n"
    r = client.post("/api/quality/coa", files={"file": ("c.txt", txt, "text/plain")}, headers=analyst)
    d = client.get(f"/api/quality/{r.json()['run_id']}", headers=analyst).json()
    assert d["coa"]["verdict"] == "REVIEW REQUIRED"  # missing batch and missing required parameters
    assert "not reported" in d["coa"]["explanation"] or "missing" in d["coa"]["explanation"].lower()


def test_coa_unknown_product_is_review(client, analyst):
    txt = b"Certificate of Analysis\nBatch: B26-1111\nPurity: 99.4 %\n"
    r = client.post("/api/quality/coa", files={"file": ("c.txt", txt, "text/plain")}, headers=analyst)
    d = client.get(f"/api/quality/{r.json()['run_id']}", headers=analyst).json()
    assert d["coa"]["verdict"] == "REVIEW REQUIRED" and d["coa"]["product_code"] is None


# ---------------------------------------------------------------- export documents
def test_documents_consistent_set_then_edit_blocks_and_fix_unblocks(client, analyst):
    order = client.get("/api/documents/sample-order", headers=analyst).json()
    g = client.post("/api/documents/generate", json={"order": order}, headers=analyst)
    assert g.status_code == 201, g.text
    run_id = g.json()["run_id"]
    assert g.json()["status"] == "completed" and g.json()["findings"] == []
    d = client.get(f"/api/documents/{run_id}", headers=analyst).json()
    assert {x["doc_type"] for x in d["documents"]} == {"commercial_invoice", "packing_list", "certificate_of_origin", "shipping_instruction"}
    for t in ("commercial_invoice", "packing_list", "certificate_of_origin", "shipping_instruction"):
        pdf = client.get(f"/api/documents/{run_id}/{t}.pdf", headers=analyst)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # introduce the classic 5000 vs 5200 kg mismatch on the packing list
    e = client.patch(f"/api/documents/{run_id}", json={"doc_type": "packing_list", "field": "net_quantity_kg", "value": 5200}, headers=analyst)
    assert e.status_code == 200
    body = e.json()
    assert body["status"] == "blocked"
    assert any(f["field"] == "net_quantity_kg" and {f["value_a"], f["value_b"]} == {"5000.0", "5200.0"} for f in body["findings"])
    assert client.get(f"/api/documents/{run_id}/commercial_invoice.pdf", headers=analyst).status_code == 409

    fix = client.patch(f"/api/documents/{run_id}", json={"doc_type": "packing_list", "field": "net_quantity_kg", "value": 5000}, headers=analyst)
    assert fix.json()["status"] == "completed"
    assert client.get(f"/api/documents/{run_id}/packing_list.pdf", headers=analyst).status_code == 200
    acts = [a["action"] for a in client.get(f"/api/documents/{run_id}", headers=analyst).json()["audit"]]
    assert acts.count("document_edited") == 2 and "documents_blocked" in acts


def test_document_edit_validation(client, analyst):
    order = client.get("/api/documents/sample-order", headers=analyst).json()
    run_id = client.post("/api/documents/generate", json={"order": order}, headers=analyst).json()["run_id"]
    bad = lambda **kw: client.patch(f"/api/documents/{run_id}", json=kw, headers=analyst).status_code  # noqa: E731
    assert bad(doc_type="packing_list", field="invoice_no", value="x") == 422        # not editable
    assert bad(doc_type="packing_list", field="net_quantity_kg", value="abc") == 422
    assert bad(doc_type="packing_list", field="net_quantity_kg", value=-5) == 422
    assert bad(doc_type="nonexistent", field="net_quantity_kg", value=5) == 404
    assert bad(doc_type="certificate_of_origin", field="gross_weight_kg", value=5) == 422  # field not on that doc


def test_documents_from_quote_requires_approval(client, analyst, approver):
    from conftest import upload_rfq

    rid = upload_rfq(client, analyst)
    assert client.post("/api/documents/generate", json={"quote_run_id": rid}, headers=analyst).status_code == 409
    assert client.post(f"/api/rfq/{rid}/decision", json={"decision": "approved"}, headers=approver).status_code == 200
    g = client.post("/api/documents/generate", json={"quote_run_id": rid}, headers=analyst)
    assert g.status_code == 201 and g.json()["status"] == "completed", g.text
    assert client.post("/api/documents/generate", json={}, headers=analyst).status_code == 422
