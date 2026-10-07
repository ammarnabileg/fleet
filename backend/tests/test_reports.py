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
    assert dash["drivers"] == {"on_duty": 1, "signal_lost": 1}  # no position for an hour
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
