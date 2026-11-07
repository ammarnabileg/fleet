"""Business consistency across modules, with isolated synthetic data: what one action changes elsewhere, and that it
happens once. A report approved (and corrected) moves the driver's balance and the books by the same amount; a
receipt cancelled gives the cash back to the driver once, tells him, and stops asking him to confirm it; a corrected
odometer reading carries to the readings and alerts that depended on it."""

from datetime import timedelta
from decimal import Decimal as D

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, jpeg, make_driver, make_vehicle, upload

F = "/api/v1/finance"


def phone(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    return d | {"h": bearer(bind_device(client, d["phone"]))}


def report(client, d, cash, day=None):
    shot = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=d["h"],
        files={"file": ("s.jpg", jpeg(), "image/jpeg")},
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=d["h"],
        json={
            "business_date": str(day or today()),
            "orders_count": 20,
            "cash_amount": cash,
            "screenshot_sha256": shot,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def balance(admin_client, d) -> tuple[D, D]:
    s = admin_client.get(f"/api/v1/cash/drivers/{d['id']}/statement").json()
    return D(s["posted"]), D(s["pending"])


def receipt_journal(admin_client, d, receipt_no):
    lines = admin_client.get(f"/api/v1/cash/drivers/{d['id']}/statement").json()["lines"]
    return next(x for x in lines if x["kind"] == "deposit" and x.get("receipt_no") in (receipt_no, None))


# ------------------------------------------------------------------ a report approved: the balance and the books


def test_a_corrected_report_moves_the_balance_and_the_books_by_the_same_amount(admin_client, client, company):
    d = phone(admin_client, client, company)
    rid = report(client, d, "40.500")
    assert balance(admin_client, d) == (D("0"), D("40.500"))  # unapproved until reviewed
    r = admin_client.post(
        f"/api/v1/daily-reports/{rid}/approve", json={"cash_amount": "38.500", "reason": "عدّ الكاش: 38.500"}
    )
    assert r.status_code == 200, r.text
    assert balance(admin_client, d) == (D("38.500"), D("0"))
    # approved again (a double click, a retry): nothing twice
    assert admin_client.post(f"/api/v1/daily-reports/{rid}/approve", json={}).status_code == 409
    assert balance(admin_client, d) == (D("38.500"), D("0"))
    assert admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "30"}).status_code == 201
    assert balance(admin_client, d) == (D("8.500"), D("0"))

    # the books: the cash journals entered, approved; the driver cash account is what the drivers hold
    first = today().replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    period = {"date_from": str(first), "date_to": str(last)}
    assert admin_client.post(f"{F}/entries/post", json=period).status_code == 200
    assert admin_client.post(f"{F}/entries/approve", json=period).status_code == 200
    roles = {x["role"]: x["account_id"] for x in admin_client.get(f"{F}/roles").json()}
    tb = {b["account"]["id"]: D(b["closing"]) for b in admin_client.get(f"{F}/trial-balance", params=period).json()}
    held = sum(D(b["posted"]) for b in admin_client.get("/api/v1/cash/balances").json())
    assert tb[roles["driver_cash"]] == held == D("8.500")
    assert sum(tb.values()) == 0


# ------------------------------------------------------------------ a receipt cancelled


def test_a_cancelled_receipt_gives_the_cash_back_once_and_is_not_asked_for(admin_client, client, company, db):
    from sqlalchemy import text

    d = phone(admin_client, client, company)
    admin_client.post("/api/v1/cash/adjustments", json={"driver_id": d["id"], "amount": "50", "reason": "رصيد سابق"})
    r = admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "20"})
    assert r.status_code == 201, r.text
    receipt = r.json()
    assert balance(admin_client, d)[0] == D("30.000")
    treasury = D(admin_client.get("/api/v1/cash/treasury").json()[0]["treasury"])
    journal = db.execute(
        text(
            "SELECT j.public_id FROM cash.journals j JOIN cash.receipts r ON r.id = j.source_id "
            "WHERE j.kind = 'deposit' AND j.source_type = 'receipt' AND r.public_id = :p"
        ),
        {"p": receipt["id"]},
    ).scalar()
    r = admin_client.post(f"/api/v1/cash/journals/{journal}/reverse", json={"reason": "الإيصال طُبع لسائق خطأ"})
    assert r.status_code == 201, r.text
    again = admin_client.post(f"/api/v1/cash/journals/{journal}/reverse", json={"reason": "مرة أخرى"})
    assert again.status_code == 409
    # the cash is his again, once; the treasury gives it back once
    assert balance(admin_client, d)[0] == D("50.000")
    assert D(admin_client.get("/api/v1/cash/treasury").json()[0]["treasury"]) == treasury - D("20")

    # he is told, and the receipt shows cancelled with nothing to confirm; the office stops asking about it
    mine = client.get("/api/v1/driver/cash", headers=d["h"]).json()["receipts"]
    assert [(x["receipt_no"], x["reversed"]) for x in mine] == [(receipt["receipt_no"], True)]
    notes = client.get("/api/v1/driver/notifications", headers=d["h"]).json()["items"]
    assert notes[0]["kind"] == "receipt_reversed" and "الإيصال طُبع لسائق خطأ" in notes[0]["message"]
    db.execute(text("UPDATE cash.receipts SET created_at = now() - interval '25 hours'"))
    db.commit()
    assert client.get("/api/v1/driver/cash", headers=d["h"]).json()["receipts"][0]["unconfirmed_late"] is False
    assert admin_client.get("/api/v1/cash/receipts/unconfirmed").json() == []
    # the cash report counts it as reversed, not as collected
    params = {"date_from": str(today() - timedelta(days=2)), "date_to": str(today())}
    (row,) = admin_client.get("/api/v1/reports/cash", params=params).json()["collectors"]
    assert (row["receipts"], row["amount"], row["reversed"]) == (0, "0.000", 1)


# ------------------------------------------------------------------ an odometer reading corrected


def _return(admin_client, custody, km):
    r = admin_client.post(
        f"/api/v1/custodies/{custody['id']}/return", json={"odometer_km": km, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text


def _pending(admin_client, v):
    return [
        x
        for x in admin_client.get("/api/v1/odometer/readings", params={"review_status": "pending"}).json()
        if x["vehicle_plate"] == v["plate_number"]
    ]


def test_a_corrected_reading_carries_to_the_reading_after_it_and_closes_its_alerts(admin_client, company):
    from datetime import UTC, datetime

    v = make_vehicle(admin_client, company["id"], km=10_000)
    a, b = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, a, km=10_000, started_at=(datetime.now(UTC) - timedelta(hours=3)).isoformat())
    # the return typed with an extra digit: far above the day's limit
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return",
        json={
            "odometer_km": 101_200,
            "photo_sha256": upload(admin_client),
            "ended_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    # the next driver takes it at the true reading: lower than the typo, sent to review because of it
    hand_over(admin_client, v, b, km=10_123)
    flagged = {x["kind"]: x for x in _pending(admin_client, v)}
    assert flagged["handover"]["flags"] == ["lower_than_previous"]
    assert "daily_limit" in flagged["return"]["flags"]
    alerts = {x["entity_id"] for x in admin_client.get("/api/v1/alerts").json() if x["kind"].startswith("odometer")}
    assert {flagged["return"]["id"], flagged["handover"]["id"]} <= alerts

    # the typo corrected: the handover after it is right after all, its review and its alert go with the cause
    r = admin_client.post(
        f"/api/v1/odometer/readings/{flagged['return']['id']}/review",
        json={"corrected_km": 10_120, "reason": "الصورة تقرأ 10120"},
    )
    assert r.status_code == 200, r.text
    assert _pending(admin_client, v) == []
    after = {x["kind"]: x for x in admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v["id"]}).json()}
    assert after["handover"]["flags"] == [] and after["handover"]["review_status"] == "ok"
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["last_odometer_km"] == 10_123
    open_ = {x["entity_id"] for x in admin_client.get("/api/v1/alerts").json() if x["kind"].startswith("odometer")}
    assert not open_ & {flagged["return"]["id"], flagged["handover"]["id"]}


def test_a_reading_after_a_correction_that_is_still_wrong_stays_for_review(admin_client, company):
    """Re-checked, not waved through: still lower than the corrected value, it keeps waiting with that flag."""
    from datetime import UTC, datetime

    v = make_vehicle(admin_client, company["id"], km=10_000)
    a, b = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, a, km=10_000, started_at=(datetime.now(UTC) - timedelta(hours=3)).isoformat())
    admin_client.post(
        f"/api/v1/custodies/{c['id']}/return",
        json={
            "odometer_km": 101_200,
            "photo_sha256": upload(admin_client),
            "ended_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        },
    )
    hand_over(admin_client, v, b, km=10_050)
    ret = next(x for x in _pending(admin_client, v) if x["kind"] == "return")
    admin_client.post(
        f"/api/v1/odometer/readings/{ret['id']}/review", json={"corrected_km": 10_120, "reason": "الصورة تقرأ 10120"}
    )
    (left,) = _pending(admin_client, v)
    assert left["kind"] == "handover" and left["flags"] == ["lower_than_previous"]


# ------------------------------------------------------------------ permissions saved, applied to the users at once


def test_a_role_saved_applies_at_once_to_every_user_who_has_it(admin_client, new_client, company):
    from tests.conftest import login, make_user

    make_user(admin_client, "clerk1", permissions=["vehicles.view"], role="clerk")
    make_user(admin_client, "clerk2", role="clerk")
    one, two = new_client(), new_client()
    login(one, "clerk1")
    login(two, "clerk2")
    assert one.get("/api/v1/vehicles").status_code == two.get("/api/v1/vehicles").status_code == 200
    assert one.get("/api/v1/employees").status_code == 403
    role = next(r for r in admin_client.get("/api/v1/roles").json() if r["code"] == "clerk")
    r = admin_client.patch("/api/v1/roles/clerk", json={"version": role["version"], "permissions": ["employees.view"]})
    assert r.status_code == 200, r.text
    # signed in already: the new permissions on the next request, no sign-in again
    for c in (one, two):
        assert c.get("/api/v1/vehicles").status_code == 403
        assert c.get("/api/v1/employees").status_code == 200
        assert set(c.get("/api/v1/auth/me").json()["permissions"]) == {"employees.view"}


def test_a_user_moved_to_another_company_sees_only_it_from_the_next_request(admin_client, new_client, companies):
    from tests.conftest import login, make_user

    a, b = companies["a"]["id"], companies["b"]["id"]
    va, vb = make_vehicle(admin_client, a), make_vehicle(admin_client, b)
    user = make_user(admin_client, "mover", permissions=["vehicles.view", "vehicles.update"], company_ids=[a])
    c = new_client()
    login(c, "mover")
    assert [x["id"] for x in c.get("/api/v1/vehicles").json()] == [va["id"]]
    r = admin_client.patch(f"/api/v1/users/{user['public_id']}", json={"version": user["version"], "company_ids": [b]})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in c.get("/api/v1/vehicles").json()] == [vb["id"]]
    assert c.get(f"/api/v1/vehicles/{va['id']}").status_code == 404
    edit = c.patch(f"/api/v1/vehicles/{va['id']}", json={"version": 1, "color": "أحمر"})
    assert edit.status_code == 404


# ------------------------------------------------------------------ companies kept apart: view, edit, export


def test_a_company_user_neither_sees_nor_changes_nor_exports_another_company(
    admin_client, client, new_client, companies
):
    from tests.conftest import login, make_user

    a, b = companies["a"], companies["b"]
    da, db_ = phone(admin_client, client, a), phone(admin_client, client, b)
    ra, rb = report(client, da, "11"), report(client, db_, "22")
    perms = [
        "daily_reports.view",
        "daily_reports.review",
        "cash.view",
        "cash.collect",
        "cash.adjust",
        "reports.view",
        "reports.export",
        "vehicles.view",
        "employees.view",
    ]
    make_user(admin_client, "only_a", permissions=perms, company_ids=[a["id"]])
    c = new_client()
    login(c, "only_a")
    # view
    assert {x["id"] for x in c.get("/api/v1/daily-reports", params={"status": "submitted"}).json()} == {ra}
    assert c.get(f"/api/v1/cash/drivers/{db_['id']}/statement").status_code == 404
    # change
    assert c.post(f"/api/v1/daily-reports/{rb}/approve", json={}).status_code == 404
    assert c.post("/api/v1/cash/receipts", json={"driver_id": db_["id"], "amount": "5"}).status_code == 404
    adj = c.post("/api/v1/cash/adjustments", json={"driver_id": db_["id"], "amount": "5", "reason": "تجربة عزل"})
    assert adj.status_code == 404
    assert c.post(f"/api/v1/daily-reports/{ra}/approve", json={}).status_code == 200
    admin_client.post(f"/api/v1/daily-reports/{rb}/approve", json={})
    # export: his company only, and the other company refused as a filter
    period = {"date_from": str(today() - timedelta(days=1)), "date_to": str(today())}
    csv = c.get("/api/v1/reports/daily-summary", params=period | {"format": "csv"}).content.decode("utf-8")
    assert da["employee_number"] in csv and db_["employee_number"] not in csv
    other = c.get("/api/v1/reports/daily-summary", params=period | {"format": "csv", "company_id": b["id"]})
    assert other.status_code in (403, 404)
    balances = c.get("/api/v1/reports/cash-balances").content.decode("utf-8")
    assert "11.000" in balances and "22.000" not in balances
    rows = c.get("/api/v1/reports/cash", params=period).json()["aging"]["rows"]
    assert [r["driver"]["id"] for r in rows] == [da["id"]]


# ------------------------------------------------------------------ expired documents shown


def test_every_expired_and_expiring_document_is_listed_as_the_dashboard_counts_them(admin_client, company, owner_db):
    """The list stopped at 200, oldest first: with many expired, those about to expire (the ones still to act on)
    were cut, and the page said "200" while the dashboard counted more."""
    from sqlalchemy import text

    owner_db.execute(
        text(
            "INSERT INTO fleet.vehicles (plate_number, company_id, branch_id) "
            "SELECT 'EXP-' || n, :c, (SELECT id FROM org.branches ORDER BY id LIMIT 1) FROM generate_series(1, 230) n"
        ),
        {"c": company["id"]},
    )
    owner_db.execute(
        text(
            "INSERT INTO documents.documents (type_code, owner_type, owner_id, company_id, expiry_date) "
            "SELECT 'registration', 'vehicle', id, company_id, current_date - (1 + id % 300)::int "
            "FROM fleet.vehicles WHERE plate_number LIKE 'EXP-%'"
        )
    )
    owner_db.commit()
    soon = make_vehicle(admin_client, company["id"])
    r = admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "vehicle",
            "owner_id": soon["id"],
            "type_code": "registration",
            "expiry_date": str(today() + timedelta(days=3)),
            "file_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 201, r.text
    listed = admin_client.get("/api/v1/documents/expiring", params={"within_days": 30}).json()
    dash = admin_client.get("/api/v1/dashboard").json()["documents"]
    assert len(listed) == dash["expired"] + dash["expiring"] == 231
    assert soon["id"] in {d["owner_id"] for d in listed}
    assert sum(1 for d in listed if d["expiry_date"] < str(today())) == dash["expired"] == 230


# ------------------------------------------------------------------ exports: the rows on screen, with the same filters


def _csv(admin_client, path, params) -> list[list[str]]:
    import csv
    import io

    r = admin_client.get(path, params=params | {"format": "csv"})
    assert r.status_code == 200, r.text
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))[1:]


def test_every_export_has_the_rows_and_totals_of_the_screen_for_the_same_filters(admin_client, client, companies):
    a, b = companies["a"], companies["b"]
    d1, d2, d3 = phone(admin_client, client, a), phone(admin_client, client, a), phone(admin_client, client, b)
    v1 = make_vehicle(admin_client, a["id"])
    hand_over(admin_client, v1, d1)
    for d, cash, day in ((d1, "10.250", 1), (d1, "4", 0), (d2, "7.500", 0), (d3, "30", 0)):
        rid = report(client, d, cash, day=today() - timedelta(days=day))
        admin_client.post(f"/api/v1/daily-reports/{rid}/approve", json={})
    period = {"date_from": str(today() - timedelta(days=3)), "date_to": str(today())}
    R = "/api/v1/reports"
    cases = [
        ("daily-summary", {}, "drivers", lambda j: j["rows"]),
        ("daily-summary", {"driver_id": d1["id"]}, "drivers", lambda j: j["rows"]),
        ("daily-summary", {"company_id": a["id"]}, "days", lambda j: j["by_day"]),
        ("daily-summary", {}, "companies", lambda j: j["by_company"]),
        ("fleet", {"vehicle_id": v1["id"]}, "vehicles", lambda j: j["by_vehicle"]),
        ("fleet", {"company_id": b["id"]}, "vehicles", lambda j: j["by_vehicle"]),
        ("kilometers", {"driver_id": d1["id"]}, "drivers", lambda j: j["by_driver"]),
        ("cash", {"driver_id": d2["id"]}, "aging", lambda j: j["aging"]["rows"]),
        ("cash", {"company_id": a["id"]}, "aging", lambda j: j["aging"]["rows"]),
    ]
    for path, filters, section, rows_of in cases:
        params = period | filters | {"section": section}
        shown = rows_of(admin_client.get(f"{R}/{path}", params=params).json())
        exported = _csv(admin_client, f"{R}/{path}", params)
        assert len(exported) == len(shown), (path, filters, section, len(exported), len(shown))
    # the money adds up the same
    j = admin_client.get(f"{R}/daily-summary", params=period | {"company_id": a["id"]}).json()
    rows = _csv(admin_client, f"{R}/daily-summary", period | {"company_id": a["id"]})
    assert sum(D(r[5]) for r in rows) == sum(D(r["approved_cash"]) for r in j["rows"]) == D("21.750")
