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


def test_a_driver_needs_a_phone_for_the_app(admin_client, company):
    """A driver can be recorded before his phone is known (an imported list), but gets the app only with one."""
    r = admin_client.post(
        "/api/v1/employees",
        json={"employee_number": "D0", "name": name("س", "S"), "company_id": company["id"], "is_driver": True},
    )
    assert r.status_code == 201 and r.json()["app_access"] == "none", r.text
    d = r.json()
    r = admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "active"})
    assert r.status_code == 422 and r.json()["code"] == "driver_phone_required"
    r = admin_client.patch(f"/api/v1/employees/{d['id']}", json={"version": d["version"], "phone": "+96550001234"})
    assert r.status_code == 200, r.text
    d = admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "active"}).json()
    assert d["app_access"] == "active"
    r = admin_client.patch(f"/api/v1/employees/{d['id']}", json={"version": d["version"], "phone": None})
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


def test_the_nationality_is_picked_from_the_list(admin_client, new_client, company, db):
    listed = admin_client.get("/api/v1/nationalities").json()
    assert {"value": "الهند", "ar": "الهند", "en": "India"} in listed and len(listed) > 190
    assert new_client().get("/api/v1/nationalities").status_code == 401
    base = {"employee_number": "N1", "name": name("ن", "N"), "company_id": company["id"]}
    r = admin_client.post("/api/v1/employees", json=base | {"nationality": "هندي"})  # typed, not picked
    assert r.status_code == 422 and r.json()["code"] == "nationality_unknown"
    e = make_employee(admin_client, company["id"], nationality="الهند")
    db.execute(
        text("UPDATE people.employees SET nationality = 'هندي' WHERE employee_number = :n"), {"n": e["employee_number"]}
    )
    db.commit()  # written before the list
    e = admin_client.get(f"/api/v1/employees/{e['id']}").json()
    r = admin_client.patch(
        f"/api/v1/employees/{e['id']}", json={"version": e["version"], "nationality": "هندي", "department": "x"}
    )
    assert r.status_code == 200 and r.json()["nationality"] == "هندي"  # kept until someone changes it
    r = admin_client.patch(f"/api/v1/employees/{e['id']}", json={"version": r.json()["version"], "nationality": "مصري"})
    assert r.status_code == 422 and r.json()["code"] == "nationality_unknown"
    r = admin_client.patch(f"/api/v1/employees/{e['id']}", json={"version": e["version"] + 1, "nationality": "مصر"})
    assert r.status_code == 200 and r.json()["nationality"] == "مصر"


def test_an_iban_copied_from_a_banking_app_is_cleaned(admin_client, company):
    lrm, nbsp = chr(0x200E), chr(0xA0)
    copied = f"{lrm}kw81{nbsp}CBKU-0000 0000 0000 1234 5601 01{lrm}"
    e = make_employee(admin_client, company["id"], iban=copied)
    assert e["iban"] == "KW81CBKU0000000000001234560101"


def test_drivers_put_on_a_platform_from_the_list(admin_client, new_client, companies, db):
    """«تعيين منصة» on the drivers chosen in the list: all at once, staff skipped, a driver moved off his platform loses
    his ID on it; each change audited; employees.update and the user's companies only."""
    plats = {p["code"]: p for p in admin_client.get("/api/v1/payroll/platforms").json()}
    keeta, talabat = plats["keeta"]["id"], plats["talabat"]["id"]
    a, b = companies["a"]["id"], companies["b"]["id"]
    moved = make_driver(admin_client, a, platform_id=talabat, platform_driver_id="T-1")
    new = make_driver(admin_client, a)
    staff = make_employee(admin_client, a)
    there = make_driver(admin_client, a, platform_id=keeta, platform_driver_id="K-1")
    ids = [moved["id"], new["id"], staff["id"], there["id"], new["id"]]

    r = admin_client.post("/api/v1/employees/platform", json={"employee_ids": ids, "platform_id": keeta})
    assert r.status_code == 200 and r.json() == {"updated": 2, "unchanged": 1, "skipped": 1}, r.text
    on = {e: admin_client.get(f"/api/v1/employees/{e}").json() for e in (moved["id"], new["id"], there["id"])}
    assert [(x["platform_id"], x["platform_driver_id"]) for x in on.values()] == [
        (keeta, None),
        (keeta, None),
        (keeta, "K-1"),
    ]
    assert admin_client.get(f"/api/v1/employees/{staff['id']}").json()["platform_id"] is None
    audited = db.execute(
        text("SELECT entity_id::text, before, after FROM audit.events WHERE action = 'employee.updated'")
    ).all()
    assert {row[0]: (row[1]["platform_id"], row[2]["platform_id"]) for row in audited} == {
        moved["id"]: (talabat, keeta),
        new["id"]: (None, keeta),
    }

    r = admin_client.post("/api/v1/employees/platform", json={"employee_ids": [new["id"]], "platform_id": None})
    assert r.json()["updated"] == 1 and admin_client.get(f"/api/v1/employees/{new['id']}").json()["platform_id"] is None
    stopped = admin_client.patch(
        f"/api/v1/payroll/platforms/{talabat}", json={"version": plats["talabat"]["version"], "is_active": False}
    )
    assert stopped.status_code == 200, stopped.text
    for platform_id in (talabat, 999_999):  # a stopped platform takes no new drivers
        r = admin_client.post("/api/v1/employees/platform", json={"employee_ids": ids, "platform_id": platform_id})
        assert r.status_code == 422 and r.json()["code"] == "platform_not_found", r.text

    other = make_driver(admin_client, b)
    make_user(admin_client, "hr_b", permissions=["employees.view", "employees.update"], company_ids=[b])
    c = new_client()
    login(c, "hr_b")
    r = c.post("/api/v1/employees/platform", json={"employee_ids": [other["id"], moved["id"]], "platform_id": talabat})
    assert r.status_code == 422  # the platform first
    r = c.post("/api/v1/employees/platform", json={"employee_ids": [other["id"], moved["id"]], "platform_id": keeta})
    assert r.status_code == 404 and r.json()["code"] == "employee_not_found", r.text
    assert admin_client.get(f"/api/v1/employees/{other['id']}").json()["platform_id"] is None  # all or nothing
    assert c.post("/api/v1/employees/platform", json={"employee_ids": [other["id"]], "platform_id": keeta}).json() == {
        "updated": 1,
        "unchanged": 0,
        "skipped": 0,
    }
    make_user(admin_client, "viewer", permissions=["employees.view"])
    c = new_client()
    login(c, "viewer")
    r = c.post("/api/v1/employees/platform", json={"employee_ids": [other["id"]], "platform_id": None})
    assert r.status_code == 403
