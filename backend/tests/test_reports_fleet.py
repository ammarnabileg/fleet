"""The fleet report (BRD FR-RPT-01): vehicles by status, those with no driver, each vehicle's days with a driver and
its daily use; and the daily work report (FR-RPT-02): reports sent, late and refused, orders and cash, by driver, by
day and by company. The numbers are worked out by hand from a known history."""

import io
from datetime import timedelta

import openpyxl

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload
from tests.test_reports_more import at

R = "/api/v1/reports"


def report(client, h, day, orders, cash):
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={"business_date": str(day), "orders_count": orders, "cash_amount": cash, "screenshot_sha256": shot},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_daily_work_by_driver_by_day_and_by_company(admin_client, client, new_client, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    da, db_ = make_driver(admin_client, a), make_driver(admin_client, b)
    ha = bearer(bind_device(client, da["phone"]))
    other = new_client()
    hb = bearer(bind_device(other, db_["phone"]))
    yesterday = today() - timedelta(days=1)
    report(client, ha, yesterday, 3, "2")  # sent today: late
    report(client, ha, today(), 10, "5")
    refused = report(other, hb, today(), 7, "4")
    admin_client.post(f"/api/v1/daily-reports/{refused['id']}/reject", json={"reason": "لقطة قديمة"})

    params = {"date_from": str(yesterday), "date_to": str(today())}
    data = admin_client.get(f"{R}/daily-summary", params=params).json()
    rows = {r["driver"]["id"]: r for r in data["rows"]}
    assert (rows[da["id"]]["days"], rows[da["id"]]["late"], rows[da["id"]]["orders"]) == (2, 1, 13)
    assert (rows[db_["id"]]["days"], rows[db_["id"]]["rejected"], rows[db_["id"]]["late"]) == (0, 1, 0)
    assert data["totals"]["late"] == 1
    days = {d["day"]: d for d in data["by_day"]}
    assert [days[str(yesterday)][k] for k in ("sent", "late", "rejected", "orders")] == [1, 1, 0, 3]
    assert [days[str(today())][k] for k in ("sent", "late", "rejected", "orders", "reported_cash")] == [
        1,
        0,
        1,
        10,
        "5.000",
    ]
    by_company = {c["company_id"]: c for c in data["by_company"]}
    assert (by_company[a]["sent"], by_company[a]["late"], by_company[a]["reported_cash"]) == (2, 1, "7.000")
    assert (by_company[b]["sent"], by_company[b]["rejected"], by_company[b]["orders"]) == (0, 1, 0)
    assert by_company[a]["name"] == companies["a"]["name"]

    # one company: the others are not in it
    only_b = admin_client.get(f"{R}/daily-summary", params=params | {"company_id": b}).json()
    assert [c["company_id"] for c in only_b["by_company"]] == [b] and only_b["totals"]["late"] == 0

    # one driver: the groups follow the filter too
    only_a = admin_client.get(f"{R}/daily-summary", params=params | {"driver_id": da["id"]}).json()
    assert [(d["sent"], d["rejected"]) for d in only_a["by_day"]] == [(1, 0), (1, 0)]

    # each section exported
    for section, first in (("days", "day"), ("companies", "company"), ("drivers", "employee_number")):
        r = admin_client.get(f"{R}/daily-summary", params=params | {"format": "csv", "section": section})
        assert r.status_code == 200 and r.content.decode("utf-8").lstrip("﻿").startswith(first)
    sheet = openpyxl.load_workbook(
        io.BytesIO(
            admin_client.get(f"{R}/daily-summary", params=params | {"format": "xlsx", "section": "days"}).content
        )
    ).active
    assert [c.value for c in sheet[1]][:3] == ["اليوم", "مرسلة", "متأخرة"]
    assert [c.value for c in sheet[2]][:3] == [str(yesterday), 1, 1]


def test_fleet_by_status_without_a_driver_and_daily_use(admin_client, new_client, company):
    cid = company["id"]
    first = today() - timedelta(days=3)
    held, lent, idle, parked = (make_vehicle(admin_client, cid) for _ in range(4))
    d1, d2 = make_driver(admin_client, cid), make_driver(admin_client, cid)
    hand_over(admin_client, held, d1, started_at=at(first, 9).isoformat())  # every day of the four
    c = hand_over(admin_client, lent, d2, started_at=at(first + timedelta(days=1), 10).isoformat())
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return",
        json={
            "odometer_km": 10_050,
            "photo_sha256": upload(admin_client),
            "ended_at": at(first + timedelta(days=2), 10).isoformat(),
        },
    )
    assert r.status_code == 200, r.text  # two days: the second and third
    parked = admin_client.get(f"/api/v1/vehicles/{parked['id']}").json()
    r = admin_client.patch(
        f"/api/v1/vehicles/{parked['id']}", json={"version": parked["version"], "status": "inactive"}
    )
    assert r.status_code == 200, r.text

    params = {"date_from": str(first), "date_to": str(today()), "company_id": cid}
    data = admin_client.get(f"{R}/fleet", params=params).json()
    assert data["statuses"] == {"available": 2, "assigned": 1, "maintenance": 0, "accident": 0, "inactive": 1}
    assert data["without_driver"] == 2  # out of service is not "without a driver"
    rows = {r["vehicle"]["id"]: r for r in data["by_vehicle"]}
    assert (rows[held["id"]]["days_held"], rows[held["id"]]["use_percent"], rows[held["id"]]["driver"]["id"]) == (
        4,
        "100.0",
        d1["id"],
    )
    assert (rows[lent["id"]]["days_held"], rows[lent["id"]]["use_percent"], rows[lent["id"]]["driver"]) == (
        2,
        "50.0",
        None,
    )
    assert (rows[idle["id"]]["days_held"], rows[idle["id"]]["use_percent"]) == (0, "0.0")
    assert rows[parked["id"]]["use_percent"] is None
    assert data["use_percent"] == "50.0"  # 6 of 12 vehicle-days
    assert [(d["in_use"], d["vehicles"]) for d in data["by_day"]] == [(1, 3), (2, 3), (2, 3), (1, 3)]

    one = admin_client.get(f"{R}/fleet", params=params | {"vehicle_id": lent["id"]}).json()
    assert [r["vehicle"]["id"] for r in one["by_vehicle"]] == [lent["id"]]
    sheet = openpyxl.load_workbook(
        io.BytesIO(admin_client.get(f"{R}/fleet", params=params | {"format": "xlsx"}).content)
    ).active
    header = [c.value for c in sheet[1]]
    assert header[0] == "اللوحة" and header[3:] == ["الحالة", "السائق", "أيام في العهدة", "نسبة الاستخدام %"]

    make_user(admin_client, "analyst2", permissions=["reports.view"])
    c = new_client()
    login(c, "analyst2")
    r = c.get(f"{R}/fleet", params=params)
    assert r.status_code == 403 and r.json()["params"]["permission"] == "vehicles.view"
