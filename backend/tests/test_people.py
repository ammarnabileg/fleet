"""Employees on the papers of a legal entity, configurable statuses with history, salary protection;
UAT-18 (people part): ending service disables the driver app."""

import json

from sqlalchemy import text

from tests.conftest import login, make_driver, make_employee, make_user, name


def test_employee_belongs_to_a_company_and_defaults_to_the_main_branch(admin_client, company):
    e = make_employee(admin_client, company["id"], civil_id="290010112345", basic_salary="350.500", iban=None)
    assert e["company_id"] == company["id"] and e["status_code"] == "active" and e["app_access"] == "none"
    main = next(b for b in admin_client.get("/api/v1/branches").json() if b["is_default"])
    assert e["branch_id"] == main["id"]
    assert e["basic_salary"] == "350.500"


def test_salary_is_hidden_and_protected_without_view_salary(admin_client, new_client, company, db):
    e = make_employee(admin_client, company["id"], basic_salary="400.000", iban="KW81CBKU0000000000001234560101")
    make_user(admin_client, "hr_clerk", permissions=["employees.view", "employees.create", "employees.update"])
    c = new_client()
    login(c, "hr_clerk")
    seen = c.get(f"/api/v1/employees/{e['id']}").json()
    assert seen["basic_salary"] is None and seen["iban"] is None
    assert all(x["basic_salary"] is None for x in c.get("/api/v1/employees").json())
    r = c.patch(f"/api/v1/employees/{e['id']}", json={"version": e["version"], "basic_salary": "1.000"})
    assert r.status_code == 403 and r.json()["params"]["permission"] == "employees.view_salary"
    r = c.post(
        "/api/v1/employees",
        json={"employee_number": "X1", "name": name("س", "S"), "company_id": company["id"], "basic_salary": "10"},
    )
    assert r.status_code == 403
    # other fields can still be changed, and the audit log never holds the salary itself
    r = c.patch(f"/api/v1/employees/{e['id']}", json={"version": e["version"], "job_title": "Driver"})
    assert r.status_code == 200 and r.json()["basic_salary"] is None
    r = admin_client.patch(f"/api/v1/employees/{e['id']}", json={"version": r.json()["version"], "basic_salary": "450"})
    assert r.status_code == 200 and r.json()["basic_salary"] == "450.000"
    snapshots = [
        s
        for row in db.execute(text("SELECT before, after FROM audit.events WHERE entity_type = 'employee'"))
        for s in row
    ]
    snapshots = [s for s in snapshots if s]
    assert snapshots and not any({"basic_salary", "iban"} & s.keys() for s in snapshots)
    dump = " ".join(json.dumps(s) for s in snapshots)  # exact amounts: a random UUID can contain "450", never "450.0"
    assert "400.0" not in dump and "450.0" not in dump and "KW81" not in dump
    assert any(s.get("salary_fields_changed") == ["basic_salary"] for s in snapshots)


def test_employees_are_company_scoped(admin_client, new_client, companies):
    a, b = companies["a"], companies["b"]
    in_b = make_employee(admin_client, b["id"])
    make_user(admin_client, "sup_a", permissions=["employees.view", "employees.create"], company_ids=[a["id"]])
    c = new_client()
    login(c, "sup_a")
    assert c.get(f"/api/v1/employees/{in_b['id']}").status_code == 404
    assert {e["company_id"] for e in c.get("/api/v1/employees").json()} <= {a["id"]}
    r = c.post("/api/v1/employees", json={"employee_number": "Z9", "name": name("س", "S"), "company_id": b["id"]})
    assert r.status_code == 403 and r.json()["code"] == "company_out_of_scope"


def test_unique_numbers_give_precise_errors(admin_client, company):
    e = make_employee(admin_client, company["id"], civil_id="290010112346")
    d = make_driver(admin_client, company["id"], app=False)
    for field, value, code in (
        ("employee_number", e["employee_number"], "employee_number_taken"),
        ("civil_id", "290010112346", "civil_id_taken"),
        ("phone", d["phone"], "phone_taken"),
    ):
        body = {"employee_number": f"N-{field}", "name": name("س", "S"), "company_id": company["id"], field: value}
        r = admin_client.post("/api/v1/employees", json=body)
        assert r.status_code == 409 and r.json()["code"] == code, r.text


def test_a_driver_needs_a_phone(admin_client, company):
    r = admin_client.post(
        "/api/v1/employees",
        json={"employee_number": "D0", "name": name("س", "S"), "company_id": company["id"], "is_driver": True},
    )
    assert r.status_code == 422 and r.json()["code"] == "driver_phone_required"


def test_status_change_keeps_history_and_ending_service_disables_the_app(admin_client, company, db):
    d = make_driver(admin_client, company["id"])
    assert d["app_access"] == "active"
    r = admin_client.post(f"/api/v1/employees/{d['id']}/status", json={"status_code": "on_leave", "note": "annual"})
    assert r.status_code == 200 and r.json()["app_access"] == "active"
    r = admin_client.post(f"/api/v1/employees/{d['id']}/status", json={"status_code": "resigned"})
    assert r.status_code == 200 and r.json()["app_access"] == "disabled" and r.json()["is_terminal"]
    history = admin_client.get(f"/api/v1/employees/{d['id']}/status-history").json()
    assert [h["status_code"] for h in history] == ["resigned", "on_leave", "active"]
    assert history[1]["note"] == "annual"
    events = db.execute(text("SELECT payload FROM integrations.outbox WHERE event_type = 'employee.status_changed'"))
    assert [p["status_code"] for (p,) in events] == ["on_leave", "resigned"]
    # re-activating the app needs a working status first
    r = admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "active"})
    assert r.status_code == 422 and r.json()["code"] == "employment_ended"
    assert admin_client.post(f"/api/v1/employees/{d['id']}/status", json={"status_code": "resigned"}).status_code == 422


def test_statuses_are_configurable(admin_client, company):
    r = admin_client.post(
        "/api/v1/employment-statuses",
        json={"code": "absconded", "name": name("متغيب", "Absconded"), "is_terminal": True},
    )
    assert r.status_code == 201
    d = make_driver(admin_client, company["id"])
    r = admin_client.post(f"/api/v1/employees/{d['id']}/status", json={"status_code": "absconded"})
    assert r.json()["app_access"] == "disabled"
    r = admin_client.patch("/api/v1/employment-statuses/absconded", json={"is_active": False})
    assert r.status_code == 200
    e = make_employee(admin_client, company["id"])
    r = admin_client.post(f"/api/v1/employees/{e['id']}/status", json={"status_code": "absconded"})
    assert r.status_code == 422 and r.json()["code"] == "status_not_found"


def test_external_reference_for_a_future_hr_link(admin_client, company):
    a, b = make_employee(admin_client, company["id"]), make_employee(admin_client, company["id"])
    url = f"/api/v1/employees/{a['id']}/external-refs/hr"
    assert admin_client.put(url, json={"external_id": "HR-1"}).status_code == 204
    assert admin_client.put(url, json={"external_id": "HR-2"}).status_code == 204  # replaces
    r = admin_client.put(f"/api/v1/employees/{b['id']}/external-refs/hr", json={"external_id": "HR-2"})
    assert r.status_code == 409 and r.json()["code"] == "external_ref_taken"


def test_search_by_number_name_or_phone(admin_client, company):
    d = make_driver(admin_client, company["id"], app=False)
    for q in (d["employee_number"], d["phone"][-6:], d["name"]["en"]):
        found = admin_client.get("/api/v1/employees", params={"q": q}).json()
        assert [e["id"] for e in found] == [d["id"]], q
    assert admin_client.get("/api/v1/employees", params={"q": "%"}).json() == []
