from sqlalchemy import text

from tests.conftest import login, make_user, name


def test_company_is_a_legal_entity(admin_client):
    r = admin_client.post(
        "/api/v1/companies",
        json={
            "name": name("أجواد للتوصيل", "Ajwad Delivery"),
            "trade_name": name("أجواد", "Ajwad"),
            "cr_number": "123456",
            "license_number": "L-77",
            "license_expiry": "2027-03-31",
            "pam_file_number": "PAM-9",
        },
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert (
        c["name"]["en"] == "Ajwad Delivery" and c["license_expiry"] == "2027-03-31" and c["pam_file_number"] == "PAM-9"
    )
    dup = admin_client.post("/api/v1/companies", json={"name": name("أخرى", "Other"), "cr_number": "123456"})
    assert dup.status_code == 409 and dup.json()["code"] == "cr_number_taken"
    r = admin_client.patch(
        f"/api/v1/companies/{c['public_id']}", json={"version": c["version"], "license_expiry": "2028-03-31"}
    )
    assert r.status_code == 200 and r.json()["version"] == c["version"] + 1
    stale = admin_client.patch(f"/api/v1/companies/{c['public_id']}", json={"version": c["version"], "phone": "1"})
    assert stale.status_code == 409


def test_company_scope(admin_client, new_client, companies, db):
    """BRD 5.1: a user limited to company A cannot see company B (it looks like it does not exist)."""
    a, b = companies["a"], companies["b"]
    make_user(admin_client, "a_user", permissions=["companies.view", "companies.create"], company_ids=[a["id"]])
    c = new_client()
    login(c, "a_user")
    assert [x["public_id"] for x in c.get("/api/v1/companies").json()] == [a["public_id"]]
    assert [x["public_id"] for x in c.get("/api/v1/companies/options").json()] == [a["public_id"]]
    assert c.get(f"/api/v1/companies/{a['public_id']}").status_code == 200
    r = c.get(f"/api/v1/companies/{b['public_id']}")
    assert r.status_code == 404 and r.json()["code"] == "company_not_found"
    assert c.get("/api/v1/companies/not-a-uuid").status_code == 422
    r = c.post("/api/v1/companies", json={"name": name("ج", "C")})
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"
    audit_company = db.execute(
        text("SELECT company_id FROM audit.events WHERE action = 'company.created' ORDER BY id LIMIT 1")
    ).scalar()
    assert audit_company == a["id"]


def test_branches_are_operational_only(admin_client, new_client):
    branches = admin_client.get("/api/v1/branches").json()
    assert len(branches) == 1 and branches[0]["is_default"] and branches[0]["name"]["ar"] == "الفرع الرئيسي"
    r = admin_client.post("/api/v1/branches", json={"name": name("فرع الفحيحيل", "Fahaheel")})
    assert r.status_code == 201
    new = r.json()
    r = admin_client.patch(f"/api/v1/branches/{new['public_id']}", json={"version": new["version"], "is_default": True})
    assert r.status_code == 200 and r.json()["is_default"]
    assert [b["is_default"] for b in admin_client.get("/api/v1/branches").json()].count(True) == 1
    make_user(admin_client, "anyone")
    c = new_client()
    login(c, "anyone")
    assert len(c.get("/api/v1/branches").json()) == 2  # no scope on branches
