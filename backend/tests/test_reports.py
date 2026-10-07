"""Dashboard (BRD FR-DSH) and basic reports: each number within the user's companies, each section behind its
permission; CSV exports open correctly in Excel and cannot carry formulas."""

from datetime import UTC, datetime, timedelta

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, name


def driver_report(client, h, cash, orders=20):
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={"business_date": str(today()), "orders_count": orders, "cash_amount": cash, "screenshot_sha256": shot},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_dashboard_numbers(admin_client, client, companies):
    a = companies["a"]["id"]
    v1, _ = make_vehicle(admin_client, a), make_vehicle(admin_client, a)
    d = make_driver(admin_client, a)
    h = bearer(bind_device(client, d["phone"]))
    hand_over(admin_client, v1, d, started_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat())
    driver_report(client, h, "95.500", orders=31)  # above the 80.000 limit: an alert
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "5"})
    admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "employee",
            "owner_id": d["id"],
            "type_code": "residence",
            "expiry_date": str(today() + timedelta(days=10)),
        },
    )
    dash = admin_client.get("/api/v1/dashboard").json()
    assert dash["vehicles"]["assigned"] == 1 and dash["vehicles"]["available"] == 1
    assert (dash["drivers"]["on_duty"], dash["drivers"]["signal_lost"]) == (1, 1)  # no position for an hour
    assert dash["daily_reports"]["today_sent"] == 1 and dash["daily_reports"]["today_orders"] == 31
    assert dash["daily_reports"]["waiting_review"] == 1
    assert dash["cash"]["held_by_drivers"] == "90.500" and dash["cash"]["unapproved"] == "95.500"
    assert dash["cash"]["deposited_today"] == "5.000" and dash["cash"]["over_limit"] == 1
    assert dash["documents"] == {"expiring": 1, "expired": 0}
    assert dash["alerts"]["warning"] >= 1


def test_sections_follow_permissions_and_scope(admin_client, client, new_client, companies):
    d = make_driver(admin_client, companies["a"]["id"])
    driver_report(client, bearer(bind_device(client, d["phone"])), "10")
    make_user(admin_client, "boss_only", permissions=["dashboard.view"])
    c = new_client()
    login(c, "boss_only")
    assert set(c.get("/api/v1/dashboard").json()) == {"as_of", "alerts"}
    make_user(
        admin_client,
        "ops_b",
        permissions=["dashboard.view", "daily_reports.view", "cash.view"],
        company_ids=[companies["b"]["id"]],
    )
    c = new_client()
    login(c, "ops_b")
    dash = c.get("/api/v1/dashboard").json()
    assert dash["daily_reports"]["today_sent"] == 0 and dash["cash"]["held_by_drivers"] == "0"
    make_user(admin_client, "nobody", permissions=["vehicles.view"])
    c = new_client()
    login(c, "nobody")
    assert c.get("/api/v1/dashboard").status_code == 403


def test_daily_summary_and_csv_export(admin_client, client, new_client, companies):
    a = companies["a"]["id"]
    d = make_driver(admin_client, a, name=name("=HYPERLINK(1)", "=HYPERLINK(1)"))
    driver_report(client, bearer(bind_device(client, d["phone"])), "12.250", orders=9)
    params = {"date_from": str(today() - timedelta(days=7)), "date_to": str(today())}
    summary = admin_client.get("/api/v1/reports/daily-summary", params=params).json()
    assert summary["rows"][0]["orders"] == 9 and summary["rows"][0]["reported_cash"] == "12.250"
    assert summary["totals"]["waiting"] == 1
    csv = admin_client.get("/api/v1/reports/daily-summary", params=params | {"format": "csv"})
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    body = csv.content.decode("utf-8")
    assert body.startswith("﻿") and "'=HYPERLINK(1)" in body and ",12.250," in body
    balances = admin_client.get("/api/v1/reports/cash-balances").content.decode("utf-8")
    assert "'=HYPERLINK(1),0.000,12.250,12.250," in balances
    make_user(admin_client, "analyst", permissions=["reports.view"])
    c = new_client()
    login(c, "analyst")
    assert c.get("/api/v1/reports/daily-summary", params=params).status_code == 200
    r = c.get("/api/v1/reports/daily-summary", params=params | {"format": "csv"})
    assert r.status_code == 403 and r.json()["params"]["permission"] == "reports.export"
    long = {"date_from": str(today() - timedelta(days=200)), "date_to": str(today())}
    assert admin_client.get("/api/v1/reports/daily-summary", params=long).json()["code"] == "range_too_long"


def test_the_dashboard_s_last_seven_days(admin_client, client, db, companies):
    from sqlalchemy import text

    a = companies["a"]["id"]
    t = today()

    def report(d, back, cash, orders):
        h = bearer(bind_device(client, d["phone"]))
        shot = client.post(
            "/api/v1/driver/files",
            params={"source": "upload"},
            headers=h,
            files={"file": ("s.jpg", jpeg(), "image/jpeg")},
        ).json()["sha256"]
        day = str(t - timedelta(days=min(back, 1)))
        body = {"business_date": day, "orders_count": orders, "cash_amount": cash, "screenshot_sha256": shot}
        r = client.post("/api/v1/driver/reports", headers=h, json=body)
        assert r.status_code == 201, r.text
        if back > 1:  # the app sends two days back at most: older ones are moved here
            db.execute(
                text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :p"),
                {"d": t - timedelta(days=back), "p": r.json()["id"]},
            )
            db.commit()
        return r.json()

    ali, omar, sami = (make_driver(admin_client, a) for _ in range(3))
    report(ali, 0, "10.500", 12)
    report(omar, 0, "4.250", 5)
    report(ali, 6, "7.000", 9)  # the first of the seven days
    report(omar, 7, "99.000", 99)  # before them
    refused = report(sami, 1, "50.000", 50)
    r = admin_client.post(f"/api/v1/daily-reports/{refused['id']}/reject", json={"reason": "wrong screenshot"})
    assert r.status_code == 200, r.text
    week = admin_client.get("/api/v1/dashboard").json()["week"]
    assert [x["day"] for x in week] == [str(t - timedelta(days=n)) for n in range(6, -1, -1)]
    assert [(x["reports"], x["orders"], x["cash"]) for x in week] == [(1, 9, "7.000")] + [(0, 0, "0.000")] * 5 + [
        (2, 17, "14.750")
    ]


def test_drivers_hr_approvals_and_each_company_on_the_dashboard(admin_client, client, new_client, companies, db):
    """FR-DSH-02/03/04/06/07, FR-CMP-03: the drivers at work, without a vehicle and who started the day; today's
    reports approved and missing; the treasury; the employees by status and the month's payroll; the decisions
    waiting for the user; and each company's figures kept apart."""
    from tests.test_approvals import configure, step
    from tests.test_finance import expense, payroll_settings
    from tests.test_report_evidence import read

    a, b = companies["a"]["id"], companies["b"]["id"]
    phones = {}
    for key, company in (("d1", a), ("d2", a), ("d3", b)):
        d = make_driver(admin_client, company)
        c = new_client()
        phones[key] = (d, c, bearer(bind_device(c, d["phone"])))
    for key, company in (("d1", a), ("d3", b)):
        d, c, h = phones[key]
        v = make_vehicle(admin_client, company, km=1_000)
        hand_over(admin_client, v, d, km=1_000, started_at=(datetime.now(UTC) - timedelta(hours=2)).isoformat())
        assert read(c, h, "start_day", 1_010).status_code == 201
    d1, c1, h1 = phones["d1"]
    assert read(c1, h1, "end_day", 1_090).status_code == 201
    report = driver_report(c1, h1, "30", orders=12)
    assert admin_client.post(f"/api/v1/daily-reports/{report['id']}/approve", json={}).status_code == 200
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": d1["id"], "amount": "10"})
    shot = c1.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h1, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    body = {"business_date": str(today() - timedelta(days=1)), "orders_count": 4, "cash_amount": "7"}
    yesterday = c1.post("/api/v1/driver/reports", headers=h1, json=body | {"screenshot_sha256": shot}).json()
    r = admin_client.post(f"/api/v1/daily-reports/{yesterday['id']}/reject", json={"reason": "لقطة يوم آخر"})
    assert r.status_code == 200  # its cash never counts
    # a driver who took a vehicle and never started the day; one who resigned
    d4 = make_driver(admin_client, a)
    hand_over(admin_client, make_vehicle(admin_client, a, km=500), d4, km=500)
    d5 = make_driver(admin_client, a)
    assert (
        admin_client.post(f"/api/v1/employees/{d5['id']}/status", json={"status_code": "resigned"}).status_code == 200
    )
    from app.modules.daily_ops import service as daily

    assert daily.scan_missing(db) == 1  # d3 started and sent nothing: the oldest open alert

    dash = admin_client.get("/api/v1/dashboard").json()
    drv = dash["drivers"]
    assert (drv["total"], drv["working"], drv["without_vehicle"], drv["started_today"], drv["on_duty"]) == (
        4,
        4,
        1,
        2,
        3,
    )
    rep = dash["daily_reports"]
    assert (rep["today_sent"], rep["today_approved"], rep["today_missing"]) == (1, 1, 1)  # d3 started, sent nothing
    assert dash["cash"]["drivers_holding"] == 1 and dash["cash"]["treasury"] == "10.000"
    statuses = {s["code"]: s["count"] for s in dash["hr"]["statuses"]}
    assert sum(statuses.values()) >= 3 and all(isinstance(n, int) for n in statuses.values())
    pay = dash["hr"]["payroll"]
    assert pay["month"] == str(today().replace(day=1)) and pay["draft"] == pay["approved"] == 0
    assert dash["alerts_oldest"] is not None
    rows = {r["company_id"]: r for r in dash["by_company"]}
    assert (rows[a]["on_duty"], rows[a]["reports_today"], rows[a]["orders_today"], rows[a]["vehicles"]) == (2, 1, 12, 2)
    assert (rows[b]["on_duty"], rows[b]["reports_today"], rows[b]["cash_held"]) == (1, 0, "0.000")
    assert rows[a]["cash_held"] == "20.000"  # 30 approved, 10 handed in

    # a user of one company: no table of companies, no other company's driver
    make_user(admin_client, "ops_a", permissions=["dashboard.view", "custody.view"], company_ids=[a])
    c = new_client()
    login(c, "ops_a")
    mine = c.get("/api/v1/dashboard").json()
    assert "by_company" not in mine and mine["drivers"]["total"] == 3

    # the payroll started for one company; a decision waiting for the checker
    payroll_settings(admin_client)
    r = admin_client.post("/api/v1/payroll/runs", json={"company_id": a, "month": str(today().replace(day=1))})
    assert r.status_code == 201, r.text
    configure(admin_client, "expense", [step("المحاسب", role="accountant")])
    make_user(admin_client, "chk2", permissions=["dashboard.view", "approvals.view", "finance.view"], role="accountant")
    expense(admin_client, a)
    checker = new_client()
    login(checker, "chk2")
    waiting = checker.get("/api/v1/dashboard").json()["approvals"]
    assert waiting["waiting"] == 1 and waiting["oldest"] is not None
    pay = admin_client.get("/api/v1/dashboard").json()["hr"]["payroll"]
    assert pay["draft"] == 1 and pay["not_started"] == len(admin_client.get("/api/v1/companies").json()) - 1
