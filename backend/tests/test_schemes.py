"""Pay schemes (docs/payroll-schemes.md): a platform's schemes as data, who is on which month by month, the drivers'
requests from the app decided in the dashboard, and the monthly run paying each driver on his scheme."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.conftest import bearer, bind_device, login, make_driver, make_user

P = "/api/v1/payroll"
MONTH = today().replace(day=1)
NEXT = add_months(MONTH, 1)
IBAN = "KW81CBKU0000000000001234560101"
KEETA = {
    "code": "standard",
    "name": {"ar": "كيتا الأساسي", "en": "Keeta standard"},
    "calculator": "tiered_target",
    "per_order": "0.350",
    "missing_order_rate": "0.350",
    "reduced_rate": "0.200",
    "steps": [
        {"kind": "tier_bonus", "threshold": 450, "amount": "50"},
        {"kind": "tier_bonus", "threshold": 540, "amount": "90"},
        {"kind": "tier_bonus", "threshold": 620, "amount": "130"},
        {"kind": "tier_bonus", "threshold": 710, "amount": "200"},
        {"kind": "marks_deduction", "threshold": 3, "amount": "10"},
        {"kind": "marks_deduction", "threshold": 4, "amount": "30"},
        {"kind": "marks_reduce", "threshold": 5},
    ],
}
BATCH = {
    "code": "batch",
    "name": {"ar": "نظام الباتش", "en": "Batch"},
    "calculator": "batch",
    "steps": [
        {"kind": "batch_rate", "threshold": n, "amount": a} for n, a in ((1, "0.700"), (2, "0.675"), (3, "0.600"))
    ],
}


def fixed(code, price, covers, **extra):
    return {
        "code": code,
        "name": {"ar": code, "en": code},
        "calculator": "per_order",
        "per_order": price,
        "company_covers": covers,
    } | extra


def platform(admin_client, code):
    r = admin_client.post(f"{P}/platforms", json={"code": code, "name": {"ar": code, "en": code}, "pay_basic": False})
    assert r.status_code == 201, r.text
    return r.json()


def scheme(admin_client, platform_id, body):
    r = admin_client.post(f"{P}/schemes", json={"platform_id": platform_id} | body)
    assert r.status_code == 201, r.text
    return r.json()


def assign(admin_client, s, *drivers, month=MONTH):
    return admin_client.post(
        f"{P}/schemes/{s['id']}/assign", json={"employee_ids": [d["id"] for d in drivers], "month": str(month)}
    )


@pytest.fixture
def setup(admin_client, company):
    keeta, talabat = platform(admin_client, "keeta"), platform(admin_client, "talabat")
    s = {
        "keeta": scheme(admin_client, keeta["id"], KEETA),
        "batch": scheme(admin_client, talabat["id"], BATCH),
        "fixed_1": scheme(
            admin_client, talabat["id"], fixed("fixed_1", "0.350", ["maintenance", "housing", "gas", "sim"])
        ),
        "fixed_2": scheme(admin_client, talabat["id"], fixed("fixed_2", "0.550", ["maintenance", "housing"])),
        "office_only": scheme(admin_client, talabat["id"], fixed("vip", "0.900", [], driver_selectable=False)),
    }
    return {"keeta": keeta, "talabat": talabat, "schemes": s}


def test_schemes_are_data_checked_for_their_calculator(admin_client, new_client, setup):
    talabat = setup["talabat"]["id"]
    bad = [
        ({"calculator": "per_order"}, "field_required"),  # no price
        ({"calculator": "tiered_target", "per_order": "0.350"}, "field_required"),  # no reduced price
        ({"calculator": "batch"}, "field_required"),  # no batch prices
        (
            {
                "calculator": "per_order",
                "per_order": "1",
                "steps": [{"kind": "tier_bonus", "threshold": 1, "amount": "1"}],
            },
            "scheme_step_invalid",
        ),  # fmt: skip
        (
            {
                "calculator": "tiered_target",
                "per_order": "1",
                "reduced_rate": "1",
                "steps": [{"kind": "marks_reduce", "threshold": 5, "amount": "1"}],
            },
            "scheme_step_invalid",
        ),  # fmt: skip
    ]
    for body, code in bad:
        r = admin_client.post(
            f"{P}/schemes", json={"platform_id": talabat, "code": "x_1", "name": {"ar": "س", "en": "x"}} | body
        )
        assert r.status_code == 422 and r.json()["code"] == code, (body, r.text)
    r = admin_client.post(f"{P}/schemes", json={"platform_id": talabat} | BATCH)
    assert r.status_code == 409 and r.json()["code"] == "scheme_code_taken"

    listed = admin_client.get(f"{P}/schemes", params={"platform_id": setup["keeta"]["id"]}).json()
    assert [s["code"] for s in listed] == ["standard"] and len(listed[0]["steps"]) == 7
    assert listed[0]["floor_at_zero"] and not listed[0]["bonus_when_reduced"]  # the client's defaults

    make_user(admin_client, "payroll_viewer", permissions=["payroll.view"])
    c = new_client()
    login(c, "payroll_viewer")
    assert c.get(f"{P}/schemes").status_code == 200
    assert c.post(f"{P}/schemes", json={"platform_id": talabat} | fixed("y_1", "1", [])).status_code == 403


def test_a_driver_is_on_one_scheme_per_month_and_paid_months_never_change(admin_client, company, setup, db, owner_db):
    s = setup["schemes"]
    d = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    r = assign(admin_client, s["keeta"], d)  # another platform's scheme
    assert r.json()["set"] == 0 and r.json()["skipped"][0]["code"] == "scheme_platform_mismatch"
    assert assign(admin_client, s["fixed_1"], d).json()["set"] == 1
    assert assign(admin_client, s["fixed_2"], d, month=NEXT).json()["set"] == 1  # scheduled for next month
    hist = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [(h["scheme"]["code"], h["valid_from"], h["valid_to"]) for h in hist] == [
        ("fixed_2", str(NEXT), None),
        ("fixed_1", str(MONTH), str(NEXT)),
    ]
    assert assign(admin_client, s["batch"], d).json()["set"] == 1  # from this month: replaces what was set from it on
    hist = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [(h["scheme"]["code"], h["valid_from"], h["valid_to"]) for h in hist] == [("batch", str(MONTH), None)]

    # this month's payroll approved: this month and earlier stay as paid; next month can still change
    owner_db.execute(
        text(
            "INSERT INTO payroll.runs (company_id, month, status, cap_percent, cap_base, prepared_by, approved_at) "
            "VALUES (:c, :m, 'approved', 50, 'gross', 1, now())"
        ),
        {"c": company["id"], "m": MONTH},
    )
    owner_db.commit()
    r = assign(admin_client, s["fixed_1"], d)
    assert r.json()["skipped"][0]["code"] == "payroll_locked"
    assert assign(admin_client, s["fixed_1"], d, month=NEXT).json()["set"] == 1

    # a scheme drivers are on keeps its prices: a new price is a new scheme
    r = admin_client.patch(f"{P}/schemes/{s['fixed_1']['id']}", json={"version": 1, "per_order": "0.400"})
    assert r.status_code == 409 and r.json()["code"] == "scheme_in_use"
    r = admin_client.patch(f"{P}/schemes/{s['fixed_1']['id']}", json={"version": 1, "driver_selectable": False})
    assert r.status_code == 200 and r.json()["driver_selectable"] is False
    r = admin_client.patch(f"{P}/schemes/{s['fixed_2']['id']}", json={"version": 1, "per_order": "0.560"})
    assert r.status_code == 200 and r.json()["per_order"] == "0.560"  # no driver on it any more


def test_the_driver_asks_from_the_app_and_the_office_decides(admin_client, client, company, setup, new_client):
    s = setup["schemes"]
    d = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    h = bearer(bind_device(client, d["phone"]))
    assign(admin_client, s["fixed_1"], d)
    view = client.get("/api/v1/driver/schemes", headers=h).json()
    assert view["current"]["code"] == "fixed_1" and view["next_month"] is None and view["request"] is None
    assert {x["code"] for x in view["schemes"]} == {"batch", "fixed_1", "fixed_2"}  # the office-only one is not offered
    assert view["schemes"][0]["steps"] is not None and "company_covers" in view["schemes"][0]
    assert "drivers" not in view["schemes"][0]  # the terms, not how many are on it

    ask = lambda code, **kw: client.post(  # noqa: E731
        "/api/v1/driver/scheme-requests", headers=h, json={"scheme_id": s[code]["id"]} | kw
    )
    assert ask("keeta").json()["code"] == "scheme_not_available"  # another platform's
    assert ask("office_only").json()["code"] == "scheme_not_available"
    assert ask("fixed_1").json()["code"] == "scheme_already_yours"
    r = ask("fixed_2", note="أريد سعراً أعلى")
    assert r.status_code == 201 and r.json()["request"]["status"] == "pending", r.text
    assert r.json()["request"]["effective_month"] == str(NEXT)
    assert ask("batch").json()["code"] == "scheme_request_pending"  # one open request at a time

    assert admin_client.get(f"{P}/scheme-requests/counts").json() == {"pending": 1}
    queue = admin_client.get(f"{P}/scheme-requests", params={"status": "pending"}).json()
    assert [(q["current"]["code"], q["requested"]["code"]) for q in queue] == [("fixed_1", "fixed_2")]
    make_user(admin_client, "payroll_viewer", permissions=["payroll.view"])
    viewer = new_client()
    login(viewer, "payroll_viewer")
    assert viewer.post(f"{P}/scheme-requests/{queue[0]['id']}/approve", json={}).status_code == 403
    r = admin_client.post(f"{P}/scheme-requests/{queue[0]['id']}/approve", json={"note": "موافق"})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    assert admin_client.post(f"{P}/scheme-requests/{queue[0]['id']}/approve", json={}).json()["code"] == (
        "scheme_request_decided"
    )
    view = client.get("/api/v1/driver/schemes", headers=h).json()
    assert (view["current"]["code"], view["next_month"]["code"]) == ("fixed_1", "fixed_2")  # this month stays

    # rejected with the reason the driver reads; or cancelled by him
    r = ask("batch")
    rid = r.json()["request"]["id"]
    assert admin_client.post(f"{P}/scheme-requests/{rid}/reject", json={}).status_code == 422  # a reason is required
    r = admin_client.post(f"{P}/scheme-requests/{rid}/reject", json={"note": "الباتش للمنطقة الشمالية فقط"})
    assert r.json()["status"] == "rejected"
    assert client.get("/api/v1/driver/schemes", headers=h).json()["request"]["admin_note"] == (
        "الباتش للمنطقة الشمالية فقط"
    )
    rid = ask("batch").json()["request"]["id"]
    assert client.delete(f"/api/v1/driver/scheme-requests/{rid}", headers=h).json()["request"]["status"] == "rejected"
    assert admin_client.get(f"{P}/scheme-requests/counts").json() == {"pending": 0}


def test_an_approved_request_waits_for_the_first_month_still_open(admin_client, client, company, setup, owner_db):
    s = setup["schemes"]
    d = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    h = bearer(bind_device(client, d["phone"]))
    rid = client.post("/api/v1/driver/scheme-requests", headers=h, json={"scheme_id": s["fixed_2"]["id"]}).json()[
        "request"
    ]["id"]
    owner_db.execute(
        text(
            "INSERT INTO payroll.runs (company_id, month, status, cap_percent, cap_base, prepared_by, approved_at) "
            "VALUES (:c, :m, 'approved', 50, 'gross', 1, now())"
        ),
        {"c": company["id"], "m": NEXT},
    )
    owner_db.commit()
    r = admin_client.post(f"{P}/scheme-requests/{rid}/approve", json={})
    assert r.status_code == 200 and r.json()["effective_month"] == str(add_months(NEXT, 1)), r.text


def test_the_run_pays_each_driver_on_his_scheme(admin_client, company, setup):
    version = admin_client.get("/api/v1/settings").json()["payroll"]["version"]
    admin_client.put(
        "/api/v1/settings/payroll",
        json={"version": version, "value": {"max_deduction_percent": "50.00", "deduction_cap_base": "gross"}},
    )
    s = setup["schemes"]
    kp, tp = setup["keeta"]["id"], setup["talabat"]["id"]
    talabat = setup["talabat"]
    r = admin_client.patch(f"{P}/platforms/{tp}", json={"version": talabat["version"], "pay_basic": True})
    assert r.status_code == 200, r.text  # the platform's own rule pays a basic salary: a scheme does not
    drivers = {
        n: make_driver(admin_client, company["id"], platform_id=p, iban=IBAN, basic_salary="300.000")
        for n, p in (("k1", kp), ("k2", kp), ("k3", kp), ("t1", tp), ("t2", tp), ("none", tp), ("moved", kp))
    }
    assign(admin_client, s["keeta"], drivers["k1"], drivers["k2"], drivers["k3"], drivers["moved"])
    assign(admin_client, s["batch"], drivers["t1"])
    assign(admin_client, s["fixed_2"], drivers["t2"])
    moved = admin_client.get(f"/api/v1/employees/{drivers['moved']['id']}").json()
    r = admin_client.patch(f"/api/v1/employees/{moved['id']}", json={"version": moved["version"], "platform_id": tp})
    assert r.status_code == 200, r.text  # now on the other platform: his Keeta scheme does not apply

    def month(driver, **figures):
        r = admin_client.post(f"{P}/statements", json={"employee_id": driver["id"], "month": str(MONTH)} | figures)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def needs(statement_id):  # what the reviewer is asked to enter for the driver's scheme
        on = admin_client.get(f"{P}/statements/{statement_id}").json()["scheme"]
        return on and on["needs"]

    month(drivers["k1"], orders=560, attendance_marks=2, star_day_failed=False)
    month(drivers["k2"], orders=100, attendance_marks=0, star_day_failed=True)
    k3 = month(drivers["k3"], orders=500)  # the marks and star day not entered
    t1 = month(drivers["t1"], orders=450, batch_level=2)
    t2 = month(drivers["t2"], orders=380)
    none = month(drivers["none"], orders=300)
    month(drivers["moved"], orders=300)
    assert (needs(k3), needs(t1), needs(t2), needs(none)) == (
        ["attendance_marks", "star_day_failed"],
        ["batch_level"],
        [],
        None,
    )

    run = admin_client.post(f"{P}/runs", json={"company_id": company["id"], "month": MONTH.isoformat()}).json()
    lines = {x["employee"]["id"]: x for x in run["lines"]}
    k1 = lines[drivers["k1"]["id"]]
    assert (k1["gross"], k1["net"], k1["flags"]) == ("286.000", "286.000", [])
    assert (k1["cells"]["orders_pay"], k1["cells"]["tier_bonus"], k1["cells"]["scheme"]) == (
        "196.000",
        "90.000",
        "كيتا الأساسي",
    )
    assert [b["code"] for b in k1["breakdown"]] == ["orders_pay", "tier_bonus"]
    k2 = lines[drivers["k2"]["id"]]  # 20.000 earned, 112.000 of penalties: ends at zero, 92.000 not taken
    assert (k2["gross"], k2["deductions"], k2["net"]) == ("20.000", "20.000", "0.000")
    assert k2["cells"]["uncovered_penalty"] == "92.000" and k2["cells"]["missing_target"] == "112.000"
    assert lines[drivers["k3"]["id"]]["flags"] == ["figures_missing"]
    t1 = lines[drivers["t1"]["id"]]
    assert (t1["gross"], t1["cells"]["batch_level"]) == ("303.750", 2)
    assert lines[drivers["t2"]["id"]]["gross"] == "209.000"
    assert lines[drivers["none"]["id"]]["flags"] == ["scheme_missing"]  # his platform has schemes: none is an error
    assert lines[drivers["moved"]["id"]]["flags"] == ["scheme_missing"]
    assert run["blocking"] == 3
    assert Decimal(k1["cells"]["orders_pay"]) + Decimal(k1["cells"]["tier_bonus"]) == Decimal(k1["gross"])


def test_the_driver_chooses_his_scheme_in_self_registration(admin_client, client, company, setup):
    from tests.conftest import make_vehicle
    from tests.test_onboarding import activate, full_draft, save, submission_id

    s = setup["schemes"]
    d = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    make_vehicle(admin_client, company["id"], km=39_000, plate_number="45 678")
    h, _ = activate(admin_client, client, d)
    view = client.get("/api/v1/driver/onboarding", headers=h).json()
    assert view["scheme_required"] and {x["code"] for x in view["schemes"]} == {"batch", "fixed_1", "fixed_2"}
    assert "drivers" not in view["schemes"][0] and view["schemes"][0]["company_covers"] is not None

    draft = full_draft(client, h, "45678")
    save(client, h, draft)
    r = client.post("/api/v1/driver/onboarding/submit", headers=h)
    assert r.status_code == 422 and "scheme" in r.json()["params"]["missing"], r.text
    save(client, h, draft | {"scheme_id": s["office_only"]["id"]})  # not offered to drivers
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).status_code == 422
    save(client, h, draft | {"scheme_id": s["fixed_2"]["id"]})
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).json()["status"] == "submitted"

    assert admin_client.post(f"/api/v1/onboarding/{submission_id(admin_client)}/approve").status_code == 200
    hist = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [(x["scheme"]["code"], x["valid_from"], x["source"]) for x in hist] == [
        ("fixed_2", str(MONTH), "registration")
    ]


def test_an_office_assignment_is_not_overridden_by_the_registration_choice(admin_client, company, setup, db):
    from app.modules.payroll import service as payroll
    from app.modules.people import service as people

    s = setup["schemes"]
    d = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    assign(admin_client, s["fixed_1"], d)
    driver = people.ref_by_public_id(db, d["id"], all_companies=True, company_ids=())
    assert payroll.scheme_from_registration(db, driver, s["fixed_2"]["id"], actor_user_id=1) is False
    db.commit()
    hist = admin_client.get(f"/api/v1/employees/{d['id']}/schemes").json()
    assert [x["scheme"]["code"] for x in hist] == ["fixed_1"]

    # a choice that no longer holds at the review (another platform's scheme, or one withdrawn) does not block the
    # registration: he is left without a scheme, which his payroll line says, and the office sets one
    other = make_driver(admin_client, company["id"], platform_id=setup["talabat"]["id"])
    driver = people.ref_by_public_id(db, other["id"], all_companies=True, company_ids=())
    assert payroll.scheme_from_registration(db, driver, s["keeta"]["id"], actor_user_id=1) is False
    assert payroll.scheme_from_registration(db, driver, s["office_only"]["id"], actor_user_id=1) is False
    assert payroll.scheme_from_registration(db, driver, s["fixed_2"]["id"], actor_user_id=1) is True
