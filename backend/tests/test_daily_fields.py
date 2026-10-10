"""What the driver sends at the end of each day is his platform's to say: orders and cash for one, orders and whether
the platform counted the day (a valid day, from the platform app's day summary) for another. Payroll builds the month
from the approved daily reports, so that platform needs no monthly statement; a report still waiting for review
blocks the month."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.clock import today
from tests.conftest import bearer, bind_device, jpeg, make_driver

P = "/api/v1/payroll"
MONTH = today().replace(day=1)
IBAN = "KW81CBKU0000000000001234560101"


def platform(admin_client, code, **rule):
    r = admin_client.post(f"{P}/platforms", json={"code": code, "name": {"ar": code, "en": code}} | rule)
    assert r.status_code == 201, r.text
    return r.json()


def driver_on(admin_client, client, company, p, **extra):
    d = make_driver(admin_client, company["id"], platform_id=p["id"], **extra)
    return d, bearer(bind_device(client, d["phone"]))


def send(client, h, day, **fields):
    r = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    )
    body = {"business_date": str(day), "screenshot_sha256": r.json()["sha256"]} | fields
    return client.post("/api/v1/driver/reports", headers=h, json=body)


@pytest.fixture
def two(admin_client):
    by_day = platform(admin_client, "by_day", daily_fields=["valid_day", "orders", "valid_day"])
    by_cash = platform(admin_client, "by_cash")
    return by_day, by_cash


def test_each_platform_asks_its_own_daily_fields(admin_client, client, company, two):
    by_day, by_cash = two
    assert by_day["daily_fields"] == ["orders", "valid_day"]  # once each, in the app's order
    assert by_cash["daily_fields"] == ["orders", "cash"]  # the default: as before
    _, hk = driver_on(admin_client, client, company, by_day)
    _, ht = driver_on(admin_client, client, company, by_cash)
    form = client.get("/api/v1/driver/reports/form", headers=hk).json()
    assert form == {"fields": ["orders", "valid_day"], "screenshot": True, "end_reading": True}
    assert client.get("/api/v1/driver/reports/form", headers=ht).json()["fields"] == ["orders", "cash"]

    r = send(client, hk, today(), orders_count=22)
    assert r.status_code == 422 and r.json()["params"]["field"] == "valid_day", r.text
    r = send(client, hk, today(), orders_count=22, valid_day=False)
    assert r.status_code == 201 and r.json()["valid_day"] is False and Decimal(r.json()["cash_amount"]) == 0, r.text

    r = send(client, ht, today(), orders_count=30)
    assert r.status_code == 422 and r.json()["params"]["field"] == "cash_amount"
    r = send(client, ht, today(), orders_count=30, cash_amount="12.500", valid_day=True)
    assert r.status_code == 201 and r.json()["valid_day"] is None  # not asked: not kept
    listed = admin_client.get("/api/v1/daily-reports", params={"status": "submitted"}).json()
    assert sorted(str(x["valid_day"]) for x in listed) == ["False", "None"]

    # the office changes what a platform asks: the next report follows
    r = admin_client.patch(f"{P}/platforms/{by_cash['id']}", json={"version": by_cash["version"], "daily_fields": []})
    assert r.status_code == 200 and r.json()["daily_fields"] == []
    assert client.get("/api/v1/driver/reports/form", headers=ht).json()["fields"] == []


def test_the_month_comes_from_the_approved_daily_reports(admin_client, client, company, two, owner_db):
    version = admin_client.get("/api/v1/settings").json()["payroll"]["version"]
    admin_client.put(
        "/api/v1/settings/payroll",
        json={"version": version, "value": {"max_deduction_percent": "50.00", "deduction_cap_base": "gross"}},
    )
    by_day = platform(
        admin_client, "keeps_days", daily_fields=["orders", "valid_day"], per_order="0.350", invalid_days="daily_wage"
    )
    d, h = driver_on(admin_client, client, company, by_day, basic_salary="300.000", iban=IBAN)
    sent = [
        send(client, h, today() - timedelta(days=back), orders_count=n, valid_day=v).json()
        for back, n, v in ((2, 20, True), (1, 25, True), (0, 5, False))
    ]
    for i, report in enumerate(sent):  # the first three days of this month, whatever today is
        owner_db.execute(
            text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :id"),
            {"d": MONTH + timedelta(days=i), "id": report["id"]},
        )
    owner_db.commit()
    for report in sent:
        assert admin_client.post(f"/api/v1/daily-reports/{report['id']}/approve", json={}).status_code == 200

    run = admin_client.post(f"{P}/runs", json={"company_id": company["id"], "month": MONTH.isoformat()}).json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == d["id"])
    cells = line["cells"]
    assert (cells["working_days"], cells["valid_days"], cells["orders"]) == (3, 2, 50)
    assert cells["invalid_days_deduction"] == "10.000"  # one day the platform did not count x 300 / 30
    assert (line["gross"], line["net"], line["flags"]) == ("317.500", "307.500", [])  # no monthly statement needed

    # a report still waiting for review: its orders, valid day and cash are not counted yet, so the month waits
    late = send(client, h, today(), orders_count=9, valid_day=True).json()
    owner_db.execute(
        text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :id"),
        {"d": MONTH + timedelta(days=3), "id": late["id"]},
    )
    owner_db.commit()
    run = admin_client.post(f"{P}/runs/{run['id']}/recompute").json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == d["id"])
    assert line["flags"] == ["daily_pending"] and line["cells"]["orders"] == 50
    r = admin_client.post(f"{P}/runs/{run['id']}/approve")
    assert r.status_code == 409 and r.json()["code"] == "run_has_blocking"
    admin_client.post(f"/api/v1/daily-reports/{late['id']}/approve", json={})
    run = admin_client.post(f"{P}/runs/{run['id']}/recompute").json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == d["id"])
    assert (line["cells"]["valid_days"], line["cells"]["orders"], line["flags"]) == (3, 59, [])

    # he started again that day and his second session's report is approved: its orders add to the day, the day
    # still counts once, as worked and as valid
    owner_db.execute(
        text(
            "INSERT INTO daily_ops.reports (employee_id, company_id, business_date, session, orders_count, valid_day,"
            " status) SELECT employee_id, company_id, business_date, 2, 4, true, 'approved' FROM daily_ops.reports"
            " WHERE public_id = :id"
        ),
        {"id": late["id"]},
    )
    owner_db.commit()
    run = admin_client.post(f"{P}/runs/{run['id']}/recompute").json()
    line = next(x for x in run["lines"] if x["employee"]["id"] == d["id"])
    cells = line["cells"]
    assert (cells["working_days"], cells["valid_days"], cells["orders"], line["flags"]) == (4, 3, 63, [])


def test_the_seeded_platforms_ask_what_each_counts(admin_client, client, company):
    """A fresh install has the two platforms: the daily report of a driver on the first asks only whether the platform
    counted his day valid, on the second his orders and cash; the screenshot as the settings say (required)."""
    plats = {p["code"]: p for p in admin_client.get(f"{P}/platforms").json()}
    keeta, talabat = plats["keeta"], plats["talabat"]
    assert (keeta["name"], keeta["is_active"]) == ({"ar": "كيتا", "en": "Keeta"}, True)
    assert (talabat["name"], talabat["is_active"]) == ({"ar": "طلبات", "en": "Talabat"}, True)
    assert (keeta["daily_fields"], keeta["driver_fields"]) == (["valid_day"], ["valid_days", "orders", "hours"])
    assert (talabat["daily_fields"], talabat["driver_fields"]) == (["orders", "cash"], ["orders"])
    _, hk = driver_on(admin_client, client, company, keeta)
    _, ht = driver_on(admin_client, client, company, talabat)
    form = client.get("/api/v1/driver/reports/form", headers=hk).json()
    assert (form["fields"], form["screenshot"]) == (["valid_day"], True)
    form = client.get("/api/v1/driver/reports/form", headers=ht).json()
    assert (form["fields"], form["screenshot"]) == (["orders", "cash"], True)

    r = send(client, hk, today())
    assert r.status_code == 422 and r.json()["params"]["field"] == "valid_day", r.text
    r = send(client, hk, today(), valid_day=True)  # neither orders nor cash asked
    assert r.status_code == 201 and r.json()["valid_day"] is True, r.text
    r = send(client, ht, today(), orders_count=18)
    assert r.status_code == 422 and r.json()["params"]["field"] == "cash_amount", r.text
    assert send(client, ht, today(), orders_count=18, cash_amount="4.250").status_code == 201
