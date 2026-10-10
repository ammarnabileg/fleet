"""What the driver is told in the app (BRD FR-NTF-01/02, FR-CSH-04, FR-MNT-10, UAT-05, UAT-20): every event that
concerns him leaves a notice in his own list, in his language, read or unread; nobody else's."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, jpeg, make_driver, make_vehicle, upload
from tests.test_finance import month, payroll_settings

N = "/api/v1/driver/notifications"


def notices(client, h, lang="ar") -> dict:
    r = client.get(N, headers=h | {"Accept-Language": lang})
    assert r.status_code == 200, r.text
    return r.json()


def kinds(client, h) -> list[str]:
    return [n["kind"] for n in notices(client, h)["items"]]


def driver_with_app(admin_client, client, company, **extra):
    d = make_driver(admin_client, company["id"], **extra)
    return d, bearer(bind_device(client, d["phone"]))


def report(client, h, cash="20") -> dict:
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={"business_date": str(today()), "orders_count": 9, "cash_amount": cash, "screenshot_sha256": shot},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_receipt_and_the_review_of_a_report_reach_the_driver_alone(admin_client, client, new_client, company):
    d, h = driver_with_app(admin_client, client, company)
    other = new_client()
    _, h2 = driver_with_app(admin_client, other, company)
    assert notices(client, h) == {"unread": 0, "items": []}

    r = admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "15"})
    assert r.status_code == 201, r.text
    first = notices(client, h)
    assert first["unread"] == 1 and first["items"][0]["kind"] == "receipt_issued"
    assert "15.000" in first["items"][0]["message"] and str(r.json()["receipt_no"]) in first["items"][0]["message"]
    assert first["items"][0]["entity_type"] == "receipt" and first["items"][0]["entity_id"] == r.json()["id"]
    assert "receipt no." in notices(client, h, "en")["items"][0]["message"]  # in the app's language

    # the cash corrected with its reason; another day's report refused with its reason
    rep = report(client, h, "20")
    r = admin_client.post(
        f"/api/v1/daily-reports/{rep['id']}/approve", json={"cash_amount": "18", "reason": "عد الكاش"}
    )
    assert r.status_code == 200, r.text
    msg = notices(client, h)["items"][0]
    assert msg["kind"] == "report_corrected" and "18.000" in msg["message"] and "20.000" in msg["message"]
    rep2 = report(client, h2, "7")
    admin_client.post(f"/api/v1/daily-reports/{rep2['id']}/reject", json={"reason": "اللقطة غير واضحة"})
    assert kinds(client, h) == ["report_corrected", "receipt_issued"]  # not the other driver's
    assert kinds(other, h2) == ["report_rejected"] and "اللقطة غير واضحة" in notices(other, h2)["items"][0]["message"]

    # read one, then all; an approval as reported tells nothing
    one = notices(client, h)["items"][1]["id"]
    assert client.post(f"{N}/read", headers=h, json={"ids": [one]}).json() == {"count": 1}
    assert notices(client, h)["unread"] == 1
    assert client.post(f"{N}/read", headers=h2, json={"ids": [one]}).json() == {"count": 0}  # not his
    assert client.post(f"{N}/read", headers=h, json={}).json() == {"count": 1}
    assert notices(client, h)["unread"] == 0 and all(n["read"] for n in notices(client, h)["items"])
    assert client.get(N).status_code == 401


def test_maintenance_decisions_and_the_vehicle_ready(admin_client, client, new_client, company, owner_db):
    """The office's decisions reach the driver for a request through the office (his car is in an accident); the
    center's "ready" for every request."""
    from sqlalchemy import text

    from tests.test_maintenance import M, center, driver_request, portal_client, quote, ready, receive

    vehicle = make_vehicle(admin_client, company["id"], km=20_000)
    d, h = driver_with_app(admin_client, client, company)
    hand_over(admin_client, vehicle, d, km=20_000)
    c = center(admin_client)
    s = {"h": h, "center": c, "portal": portal_client(admin_client, new_client, c, "noor7")}
    owner_db.execute(text("UPDATE fleet.vehicles SET status = 'accident' WHERE public_id = :v"), {"v": vehicle["id"]})
    owner_db.commit()
    first = driver_request(client, s).json()
    admin_client.post(f"{M}/requests/{first['id']}/reject", json={"reason": "تم إصلاحها في الموقع"})
    second = driver_request(client, s).json()
    assert admin_client.post(f"{M}/requests/{second['id']}/approve", json={}).status_code == 200
    assert admin_client.post(f"{M}/requests/{second['id']}/refer", json={"center_id": c["id"]}).status_code == 200
    assert receive(s, second["id"]).status_code == 200
    assert quote(s, second["id"], "10.000").json()["status"] == "in_repair"  # within the limit
    assert ready(s, second["id"]).status_code == 200
    items = notices(client, h)["items"]
    assert [n["kind"] for n in items] == [
        "maintenance_ready",
        "maintenance_approved",
        "maintenance_rejected",
        "vehicle_handed_over",  # the car handed to him at the start: the app reads "my car" again
    ]
    assert c["name"] in items[0]["message"] and str(second["number"]) in items[0]["message"]
    assert "تم إصلاحها في الموقع" in items[2]["message"]


def test_an_accident_charged_a_fine_charged_and_a_deduction(admin_client, client, new_client, company):
    from tests.test_accidents import A, estimate, refer, reported
    from tests.test_maintenance import center, portal_client

    vehicle = make_vehicle(admin_client, company["id"], km=30_000)
    d, h = driver_with_app(admin_client, client, company)
    hand_over(admin_client, vehicle, d, km=30_000, started_at=(datetime.now(UTC) - timedelta(hours=2)).isoformat())
    c = center(admin_client, "Body Shop Two")
    s = {"h": h, "center": c, "portal": portal_client(admin_client, new_client, c, "body7")}
    aid = reported(client, s, police=True)
    refer(admin_client, s, aid)
    assert estimate(s, aid, "150.000").status_code == 200
    assert admin_client.post(f"{A}/{aid}/estimate/approve").status_code == 200
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "driver", "installments": 3})
    assert r.status_code == 200, r.text
    msg = notices(client, h)["items"][0]
    assert msg["kind"] == "accident_charged" and "150.000" in msg["message"] and "3" in msg["message"]

    fine = admin_client.post(
        "/api/v1/fines",
        json={
            "vehicle_id": vehicle["id"],
            "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "violation": "Speeding",
            "amount": "30",
        },
    ).json()
    assert admin_client.post(f"/api/v1/fines/{fine['id']}/charge", json={"installments": 2}).status_code == 200
    r = admin_client.post(
        "/api/v1/deductions",
        json={"employee_id": d["id"], "source_type": "sim", "reason": "شريحة بيانات", "total": "5"},
    )
    assert r.status_code == 201, r.text
    items = notices(client, h)["items"]
    assert [n["kind"] for n in items[:2]] == ["deduction_added", "fine_charged"]
    assert "شريحة بيانات" in items[0]["message"] and "30.000" in items[1]["message"]


@pytest.mark.usefixtures("payroll_live")  # approves a run: the gate passed
def test_a_payslip_ready_and_a_document_about_to_expire(admin_client, client, company, db):
    from app.modules.documents import service as documents

    d, h = driver_with_app(admin_client, client, company, basic_salary="200.000", payment_method="cash")
    payroll_settings(admin_client)
    first, _ = month()
    run = admin_client.post("/api/v1/payroll/runs", json={"company_id": company["id"], "month": str(first)}).json()
    assert admin_client.post(f"/api/v1/payroll/runs/{run['id']}/approve").status_code == 200
    msg = notices(client, h)["items"][0]
    assert msg["kind"] == "payslip_ready" and first.strftime("%m-%Y") in msg["message"]

    admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "employee",
            "owner_id": d["id"],
            "type_code": "driving_license",
            "expiry_date": str(today() + timedelta(days=10)),
            "file_sha256": upload(admin_client),
        },
    )
    documents.scan_expiring(db, lambda t, i: "x")
    documents.scan_expiring(db, lambda t, i: "x")  # daily: told once per document and date
    items = notices(client, h)["items"]
    assert [n["kind"] for n in items] == ["document_expiring", "payslip_ready"]
    assert "10" in items[0]["message"] and str(today() + timedelta(days=10)) in items[0]["message"]
