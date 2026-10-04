"""M3: traffic fines (BRD FR-VEH-06, FR-PAY-02; UAT-12 in practice: a fine at a given time names who was driving)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.conftest import (
    bearer,
    bind_device,
    hand_over,
    login,
    make_driver,
    make_user,
    make_vehicle,
    upload,
)

F = "/api/v1/fines"
NOW = datetime.now(UTC)


@pytest.fixture
def setup(admin_client, company):
    """A vehicle held by one driver from 5 h ago to 3 h ago, then by a second driver from 1 h ago."""
    vehicle = make_vehicle(admin_client, company["id"], km=1_000)
    first, second = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    c1 = hand_over(admin_client, vehicle, first, km=1_000, started_at=(NOW - timedelta(hours=5)).isoformat())
    r = admin_client.post(
        f"/api/v1/custodies/{c1['id']}/return",
        json={
            "odometer_km": 1_040,
            "photo_sha256": upload(admin_client),
            "ended_at": (NOW - timedelta(hours=3)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    hand_over(admin_client, vehicle, second, km=1_040, started_at=(NOW - timedelta(hours=1)).isoformat())
    return {"vehicle": vehicle, "first": first, "second": second}


def fine(client, s, at, **extra):
    body = {
        "vehicle_id": s["vehicle"]["id"],
        "occurred_at": at.isoformat(),
        "violation": "Speeding 120/80",
        "amount": "30.000",
    }
    return client.post(F, json=body | extra)


def registered(client, s, at, **extra) -> dict:
    r = fine(client, s, at, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def test_a_fine_names_the_driver_who_held_the_vehicle_at_that_time(admin_client, setup):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4), reference_no="TR-1001", location_text="Gulf Road")
    two = registered(admin_client, s, NOW - timedelta(minutes=20), reference_no="TR-1002")
    assert one["driver"]["id"] == s["first"]["id"]
    assert two["driver"]["id"] == s["second"]["id"]
    assert (one["status"], one["can_decide"], one["amount"]) == ("open", True, "30.000")
    # between the two custodies nobody held it: no driver, an alert, and it cannot be charged
    gap = registered(admin_client, s, NOW - timedelta(hours=2))
    assert gap["driver"] is None
    alerts = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "fine_no_driver"]
    assert len(alerts) == 1 and str(gap["number"]) in alerts[0]["message"]
    r = admin_client.post(f"{F}/{gap['id']}/charge", json={"installments": 1})
    assert r.status_code == 409 and r.json()["code"] == "fine_has_no_driver"
    r = admin_client.post(f"{F}/{gap['id']}/company", json={"reason": "The vehicle was parked at the office"})
    assert r.json()["status"] == "company" and r.json()["can_decide"] is False
    assert not [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "fine_no_driver"]
    # the vehicle file lists its fines, the newest first
    rows = admin_client.get(F, params={"vehicle_id": s["vehicle"]["id"]}).json()
    assert [x["number"] for x in rows] == [two["number"], gap["number"], one["number"]]


def test_charged_to_the_driver_as_an_approved_deduction_the_driver_sees(admin_client, client, new_client, setup):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4), amount="45.000")
    make_user(admin_client, "fines_sup", permissions=["fines.view", "fines.manage"])
    make_user(admin_client, "fines_hr", permissions=["fines.view", "deductions.view", "deductions.manage"])
    sup, hr = new_client(), new_client()
    login(sup, "fines_sup")
    login(hr, "fines_hr")
    # registering fines does not let anyone create deductions
    assert sup.post(f"{F}/{one['id']}/charge", json={"installments": 3}).status_code == 403
    r = hr.post(f"{F}/{one['id']}/charge", json={"installments": 3})
    assert r.status_code == 200, r.text
    d = r.json()["deduction"]
    assert (r.json()["status"], d["total"], d["source_type"], d["installments"]) == ("charged", "45.000", "fine", 3)
    assert [x["amount"] for x in d["schedule"]] == ["15.000"] * 3
    assert d["start_month"] == str(add_months(today(), 1))
    assert d["reason"] == f"#{one['number']} Speeding 120/80"
    assert hr.post(f"{F}/{one['id']}/charge", json={"installments": 1}).json()["code"] == "fine_not_open"
    assert sup.post(f"{F}/{one['id']}/company", json={"reason": "changed my mind"}).json()["code"] == "fine_not_open"
    # the driver sees the fine and the installments in the app
    h = bearer(bind_device(client, s["first"]["phone"]))
    mine = client.get("/api/v1/driver/fines", headers=h).json()
    assert [(x["number"], x["status"], x["deduction"]["total"]) for x in mine] == [(one["number"], "charged", "45.000")]
    assert client.get("/api/v1/driver/deductions", headers=h).json()[0]["source_type"] == "fine"
    # the other driver sees nothing of it, and a cancelled fine disappears from the app
    h2 = bearer(bind_device(client, s["second"]["phone"]))
    assert client.get("/api/v1/driver/fines", headers=h2).json() == []
    wrong = registered(admin_client, s, NOW - timedelta(minutes=10))
    assert [x["id"] for x in client.get("/api/v1/driver/fines", headers=h2).json()] == [wrong["id"]]
    admin_client.post(f"{F}/{wrong['id']}/cancel", json={"reason": "Entered on the wrong vehicle"})
    assert client.get("/api/v1/driver/fines", headers=h2).json() == []


def test_a_cancelled_deduction_lets_the_fine_be_decided_again(admin_client, setup):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4))
    d = admin_client.post(f"{F}/{one['id']}/charge", json={"installments": 2}).json()["deduction"]
    r = admin_client.post(f"{F}/{one['id']}/cancel", json={"reason": "Entered twice"})
    assert r.status_code == 409 and r.json()["code"] == "fine_charged"
    admin_client.post(f"/api/v1/deductions/{d['id']}/cancel", json={"reason": "The driver appealed and won"})
    again = admin_client.get(f"{F}/{one['id']}").json()
    assert (again["status"], again["can_decide"], again["deduction"]["status"]) == ("charged", True, "cancelled")
    # charged again: a new deduction (the cancelled one stays in payroll's history)
    r = admin_client.post(f"{F}/{one['id']}/charge", json={"installments": 1})
    assert r.status_code == 200 and r.json()["deduction"]["id"] != d["id"]
    assert len(admin_client.get("/api/v1/deductions", params={"status": "cancelled"}).json()) == 1


def test_a_ticket_number_is_entered_once(admin_client, setup):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4), reference_no="TR-77")
    r = fine(admin_client, s, NOW - timedelta(hours=4), reference_no="tr-77")
    assert r.status_code == 409 and r.json()["code"] == "fine_exists"
    admin_client.post(f"{F}/{one['id']}/cancel", json={"reason": "Wrong vehicle"})
    assert fine(admin_client, s, NOW - timedelta(hours=4), reference_no="TR-77").status_code == 201


def test_time_amount_and_ticket_scan(admin_client, setup):
    s = setup
    assert fine(admin_client, s, NOW + timedelta(hours=1)).json()["code"] == "time_in_future"
    assert fine(admin_client, s, NOW - timedelta(days=6 * 365)).json()["code"] == "time_too_old"
    assert fine(admin_client, s, NOW - timedelta(hours=4), amount="0").status_code == 422
    sha = upload(admin_client, b"%PDF-1.4 ticket", name="ticket.pdf")
    one = registered(admin_client, s, NOW - timedelta(hours=4), file_sha256=sha)
    r = admin_client.get(f"{F}/{one['id']}/file")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    two = registered(admin_client, s, NOW - timedelta(hours=4))
    assert admin_client.get(f"{F}/{two['id']}/file").status_code == 404


def test_paying_the_traffic_department_is_recorded_apart(admin_client, new_client, setup):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4))
    two = registered(admin_client, s, NOW - timedelta(minutes=30), amount="10.000")
    make_user(admin_client, "fines_acc", permissions=["fines.view", "finance.create"])
    acc = new_client()
    login(acc, "fines_acc")
    assert [x["id"] for x in acc.get(F, params={"unpaid": True}).json()] == [two["id"], one["id"]]
    r = acc.post(f"{F}/{one['id']}/paid", json={"payment_ref": "MOI-5521"})
    assert r.status_code == 200 and r.json()["paid_at"] is not None and r.json()["status"] == "open"
    assert acc.post(f"{F}/{one['id']}/paid", json={}).json()["code"] == "fine_paid"
    assert [x["id"] for x in acc.get(F, params={"unpaid": True}).json()] == [two["id"]]
    assert acc.post(f"{F}/{two['id']}/cancel", json={"reason": "no permission"}).status_code == 403
    admin_client.post(f"{F}/{two['id']}/cancel", json={"reason": "Not our vehicle"})
    assert admin_client.post(f"{F}/{two['id']}/paid", json={}).json()["code"] == "fine_not_open"
    assert acc.get(F, params={"unpaid": True}).json() == []  # a cancelled fine is owed to nobody
    dash = admin_client.get("/api/v1/dashboard").json()["fines"]
    assert dash == {"open": 1, "no_driver": 0, "unpaid": 0, "unpaid_total": "0"}


def test_company_scope_and_filters(admin_client, new_client, setup, companies):
    s = setup
    one = registered(admin_client, s, NOW - timedelta(hours=4))
    gap = registered(admin_client, s, NOW - timedelta(hours=2))
    make_user(
        admin_client,
        "fines_b",
        permissions=["fines.view", "fines.manage", "deductions.manage", "finance.create"],
        company_ids=[companies["b"]["id"]],
    )
    b = new_client()
    login(b, "fines_b")
    assert b.get(F).json() == []
    assert b.get(f"{F}/{one['id']}").status_code == 404
    for action, body in (
        ("charge", {"installments": 1}),
        ("company", {"reason": "nope"}),
        ("cancel", {"reason": "nope"}),
        ("paid", {}),
    ):
        assert b.post(f"{F}/{one['id']}/{action}", json=body).status_code == 404, action
    assert fine(b, s, NOW - timedelta(hours=4)).status_code == 404  # another company's vehicle
    assert [x["id"] for x in admin_client.get(F, params={"no_driver": True}).json()] == [gap["id"]]
    assert [x["id"] for x in admin_client.get(F, params={"driver_id": s["first"]["id"]}).json()] == [one["id"]]
    assert len(admin_client.get(F, params={"status": "open"}).json()) == 2
    dash = admin_client.get("/api/v1/dashboard").json()["fines"]
    assert dash == {"open": 2, "no_driver": 1, "unpaid": 2, "unpaid_total": "60.000"}


def test_role_templates_who_works_with_fines(owner_db):
    rows = owner_db.execute(
        text(
            "SELECT r.code, p.permission FROM identity.role_permissions p JOIN identity.roles r ON r.id = p.role_id "
            "WHERE p.permission LIKE 'fines.%' ORDER BY 1, 2"
        )
    ).all()
    assert ("supervisor", "fines.manage") in rows
    assert ("hr", "fines.view") in rows and ("accountant", "fines.view") in rows
    assert ("hr", "fines.manage") not in rows
