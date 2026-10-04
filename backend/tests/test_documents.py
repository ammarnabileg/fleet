"""Official documents with expiry, renewals kept as history, expiry alerts; files checked by content."""

from datetime import timedelta

from app.core.clock import today
from app.core.config import get_settings
from tests.conftest import login, make_driver, make_employee, make_user, make_vehicle, upload

PDF = b"%PDF-1.7\n" + b"0" * 100


def test_document_with_file_and_renewal_history(admin_client, company):
    e = make_employee(admin_client, company["id"])
    sha = upload(admin_client, PDF, name="residence.pdf")
    body = {
        "owner_type": "employee",
        "owner_id": e["id"],
        "type_code": "residence",
        "number": "R-1",
        "expiry_date": str(today() + timedelta(days=200)),
        "file_sha256": sha,
    }
    first = admin_client.post("/api/v1/documents", json=body)
    assert first.status_code == 201 and first.json()["has_file"]
    renewed = admin_client.post(
        "/api/v1/documents", json=body | {"number": "R-2", "expiry_date": str(today() + timedelta(days=565))}
    )
    assert renewed.status_code == 201
    current = admin_client.get("/api/v1/documents", params={"owner_type": "employee", "owner_id": e["id"]}).json()
    assert [d["number"] for d in current] == ["R-2"]
    history = admin_client.get(
        "/api/v1/documents", params={"owner_type": "employee", "owner_id": e["id"], "history": True}
    ).json()
    assert [(d["number"], d["is_current"]) for d in history] == [("R-2", True), ("R-1", False)]
    r = admin_client.get(f"/api/v1/documents/{first.json()['id']}/file")
    assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"


def test_document_rules(admin_client, company):
    e = make_employee(admin_client, company["id"])
    v = make_vehicle(admin_client, company["id"])
    base = {"owner_type": "employee", "owner_id": e["id"]}
    cases = [
        (base | {"type_code": "registration", "expiry_date": "2030-01-01"}, "document_type_mismatch"),
        (base | {"type_code": "residence"}, "expiry_date_required"),
        (
            base | {"type_code": "residence", "issue_date": "2026-01-02", "expiry_date": "2026-01-01"},
            "expiry_before_issue",
        ),
        (base | {"type_code": "nope", "expiry_date": "2030-01-01"}, "document_type_not_found"),
        (base | {"type_code": "residence", "expiry_date": "2030-01-01", "file_sha256": "a" * 64}, "file_not_found"),
    ]
    for body, code in cases:
        r = admin_client.post("/api/v1/documents", json=body)
        assert r.status_code == 422 and r.json()["code"] == code, (code, r.text)
    assert admin_client.post("/api/v1/documents", json=base | {"type_code": "contract"}).status_code == 201
    soon = today() + timedelta(days=100)
    r = admin_client.post(
        "/api/v1/documents",
        json={"owner_type": "vehicle", "owner_id": v["id"], "type_code": "insurance", "expiry_date": str(soon)},
    )
    assert r.status_code == 201
    r = admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "company",
            "owner_id": company["public_id"],
            "type_code": "commercial_license",
            "expiry_date": str(soon),
        },
    )
    assert r.status_code == 201
    owners = {
        d["owner_type"]: (d["owner_id"], d["owner_name"])
        for d in admin_client.get("/api/v1/documents/expiring", params={"within_days": 365}).json()
    }
    assert owners == {
        "vehicle": (v["id"], v["plate_number"]),
        "company": (company["public_id"], company["name"]),
    }  # the contract has no expiry, so it never expires


def test_documents_follow_the_owners_company_scope(admin_client, new_client, companies):
    a, b = companies["a"], companies["b"]
    e = make_employee(admin_client, b["id"])
    doc = admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "employee",
            "owner_id": e["id"],
            "type_code": "passport",
            "expiry_date": str(today() + timedelta(days=100)),
            "file_sha256": upload(admin_client, PDF),
        },
    ).json()
    make_user(admin_client, "docs_a", permissions=["documents.view", "documents.manage"], company_ids=[a["id"]])
    c = new_client()
    login(c, "docs_a")
    r = c.get("/api/v1/documents", params={"owner_type": "employee", "owner_id": e["id"]})
    assert r.status_code == 404 and r.json()["code"] == "owner_not_found"
    assert c.get(f"/api/v1/documents/{doc['id']}/file").status_code == 404
    assert (
        c.post(
            "/api/v1/documents",
            json={"owner_type": "employee", "owner_id": e["id"], "type_code": "passport", "expiry_date": "2031-01-01"},
        ).status_code
        == 404
    )
    assert c.get("/api/v1/documents/expiring", params={"within_days": 365}).json() == []
    assert len(admin_client.get("/api/v1/documents/expiring", params={"within_days": 365}).json()) == 1


def test_expiry_scan_alerts_once_and_renewal_closes_it(admin_client, new_client, company, db):
    from app.modules.documents import service as documents

    d = make_driver(admin_client, company["id"], app=False)
    body = {
        "owner_type": "employee",
        "owner_id": d["id"],
        "type_code": "driving_license",
        "expiry_date": str(today() + timedelta(days=10)),
    }
    admin_client.post("/api/v1/documents", json=body)
    expiring = admin_client.get("/api/v1/documents/expiring", params={"within_days": 30}).json()
    assert len(expiring) == 1 and expiring[0]["type_code"] == "driving_license"
    assert (expiring[0]["owner_id"], expiring[0]["owner_name"]) == (d["id"], d["name"])  # whose it is
    assert documents.scan_expiring(db, lambda t, i: "x") == 1
    assert documents.scan_expiring(db, lambda t, i: "x") == 0  # still open: not repeated
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
    assert [a["kind"] for a in alerts] == ["document_expiring"]
    assert "Driving licence" in alerts[0]["message"] and "{" not in alerts[0]["message"]
    make_user(admin_client, "no_docs", permissions=["employees.view"])
    c = new_client()
    login(c, "no_docs")
    assert c.get("/api/v1/alerts").json() == []
    admin_client.post("/api/v1/documents", json=body | {"expiry_date": str(today() + timedelta(days=700))})
    assert admin_client.get("/api/v1/alerts").json() == []


def test_uploads_are_checked_by_content(admin_client, new_client, company):
    r = admin_client.post("/api/v1/files", files={"file": ("x.jpg", b"MZ\x90\x00 not an image", "image/jpeg")})
    assert r.status_code == 415 and r.json()["code"] == "file_type_not_allowed"
    assert admin_client.post("/api/v1/files", files={"file": ("x.jpg", b"", "image/jpeg")}).status_code == 422
    settings = get_settings()
    settings.max_upload_mb = 1
    try:
        r = admin_client.post("/api/v1/files", files={"file": ("big.pdf", PDF + b"0" * 1024 * 1024, "application/pdf")})
        assert r.status_code == 413 and r.json()["params"]["max_mb"] == 1
    finally:
        settings.max_upload_mb = 10
    same = upload(admin_client, PDF)
    assert upload(admin_client, PDF) == same  # stored once, named by its content
    make_user(admin_client, "viewer", permissions=["vehicles.view"])
    c = new_client()
    login(c, "viewer")
    assert c.post("/api/v1/files", files={"file": ("a.pdf", PDF, "application/pdf")}).status_code == 403
