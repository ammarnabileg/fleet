"""Printing: the cash receipt (the driver found by plate, civil ID or name; what it was issued with kept on it) and
the print templates (validated, versioned with rollback, a company's override, who may change them)."""

import pytest

from tests.conftest import hand_over, make_driver, make_user, make_vehicle

T = "/api/v1/print-templates"


@pytest.fixture
def held(admin_client, company):
    d = make_driver(admin_client, company["id"], civil_id="290010112345")
    v = make_vehicle(admin_client, company["id"], plate_number="12/3456")
    hand_over(admin_client, v, d)
    return d, v


def search(admin_client, q):
    r = admin_client.get("/api/v1/cash/receipt-drivers", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_receipt_driver_is_found_by_plate_civil_id_or_name(admin_client, company, held):
    d, _ = held
    other = make_driver(admin_client, company["id"])
    for q in ("123456", "12 3456", "١٢/٣٤٥٦", "290010112345", "٢٩٠٠١٠١١٢٣٤٥", d["name"]["ar"], d["name"]["en"].upper()):
        found = search(admin_client, q)
        assert [x["id"] for x in found] == [d["id"]], q
        assert found[0]["plate_number"] == "12/3456" and found[0]["civil_id"] == "290010112345"
    assert other["id"] not in [x["id"] for x in search(admin_client, "123456")]
    assert search(admin_client, " / ") == []


def test_the_receipt_keeps_what_it_was_issued_with(admin_client, company, held, db):
    d, v = held
    r = admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "10"})
    assert r.status_code == 201, r.text
    rc = r.json()
    assert rc["plate_number"] == "12/3456" and rc["civil_id"] == "290010112345"
    assert rc["driver_name"] == d["name"] and rc["company_id"] == company["id"] and rc["issued_by"]
    db.execute(
        __import__("sqlalchemy").text("UPDATE fleet.vehicles SET plate_number = '99999' WHERE public_id = :p"),
        {"p": v["id"]},
    )
    db.commit()
    again = admin_client.get(f"/api/v1/cash/receipts/{rc['id']}").json()
    assert again["plate_number"] == "12/3456" and again["receipt_no"] == rc["receipt_no"]
    statement = admin_client.get(f"/api/v1/cash/drivers/{d['id']}/statement").json()
    assert rc["id"] in [ln["receipt_id"] for ln in statement["lines"]]
    # lists do not carry the civil ID
    assert "civil_id" not in admin_client.get("/api/v1/cash/receipts/unconfirmed").text


def tpl(admin_client):
    return admin_client.get(T).json()


def test_templates_are_validated_versioned_and_rolled_back(admin_client):
    m = tpl(admin_client)
    assert m["config_version"] == 0 and m["default"]["footer"]["text"] == "صفحة {page} من {pages}"
    t = m["default"]
    bad = admin_client.put(
        f"{T}/default", json={"template": t | {"footer": t["footer"] | {"text": "{nope}"}}, "config_version": 0}
    )
    assert bad.status_code == 422 and bad.json()["code"] == "print_template_variable_unknown"
    bad = admin_client.put(f"{T}/default", json={"template": t | {"extra": 1}, "config_version": 0})
    assert bad.status_code == 422 and bad.json()["code"] == "print_template_invalid"
    bad = admin_client.put(
        f"{T}/default", json={"template": t | {"watermark": t["watermark"] | {"opacity": 2}}, "config_version": 0}
    )
    assert bad.status_code == 422

    def publish(text_, version):
        body = {"template": t | {"footer": t["footer"] | {"text": text_}}, "config_version": version}
        r = admin_client.put(f"{T}/default", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    assert publish("one {page}", 0)["config_version"] == 1
    assert publish("two {pages}", 1)["config_version"] == 2
    stale = admin_client.put(f"{T}/default", json={"template": t, "config_version": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "print_config_changed"
    back = admin_client.post(f"{T}/rollback", json={"config_version": 2}).json()
    assert back["config_version"] == 3 and back["default"]["footer"]["text"] == "one {page}"
    back = admin_client.post(f"{T}/rollback", json={"config_version": 3}).json()
    assert back["default"]["footer"]["text"] == "صفحة {page} من {pages}"
    assert admin_client.post(f"{T}/rollback", json={"config_version": 4}).status_code == 409


def test_a_company_override_and_the_identity_in_the_header(admin_client, company, companies):
    t = tpl(admin_client)["default"]
    own = t | {"header": t["header"] | {"lines": ["CR {cr_number}"]}, "page": t["page"] | {"accent": "#AA0000"}}
    r = admin_client.put(f"{T}/companies/{company['id']}", json={"template": own, "config_version": 0})
    assert r.status_code == 200, r.text
    mine = admin_client.get("/api/v1/print/layout", params={"company_id": company["id"]}).json()
    assert mine["template"]["page"]["accent"] == "#AA0000"
    assert mine["identity"]["company"] == company["name"]["ar"]
    other = companies["b"]
    theirs = admin_client.get("/api/v1/print/layout", params={"company_id": other["id"]}).json()
    assert theirs["template"]["page"]["accent"] == t["page"]["accent"]
    group = admin_client.get("/api/v1/print/layout").json()
    assert group["company_id"] is None and group["identity"]["company"]
    off = admin_client.put(f"{T}/companies/{company['id']}", json={"template": None, "config_version": 1}).json()
    assert off["companies"] == {}


def test_images_and_permissions(admin_client, new_client, company):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = admin_client.post(f"{T}/images", files={"file": ("logo.png", png, "image/png")})
    assert r.status_code == 201, r.text
    sha = r.json()["sha256"]
    t = tpl(admin_client)["default"]
    ok = admin_client.put(
        f"{T}/default", json={"template": t | {"header": t["header"] | {"logo": sha}}, "config_version": 0}
    )
    assert ok.status_code == 200
    layout = admin_client.get("/api/v1/print/layout").json()
    assert layout["images"]["logo"].startswith("data:image/png;base64,")
    big = admin_client.post(f"{T}/images", files={"file": ("big.png", png + b"0" * 1_000_001, "image/png")})
    assert big.status_code == 413
    pdf = admin_client.post(f"{T}/images", files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert pdf.status_code == 415

    make_user(admin_client, "viewer1", permissions=["settings.view"])
    viewer = new_client()
    from tests.conftest import login

    login(viewer, "viewer1")
    assert viewer.get(T).status_code == 200
    assert viewer.put(f"{T}/default", json={"template": t, "config_version": 1}).status_code == 403
    make_user(admin_client, "cashier1", permissions=["cash.view"])
    cashier = new_client()
    login(cashier, "cashier1")
    assert cashier.get(T).status_code == 403
    assert cashier.get("/api/v1/print/layout").status_code == 200
