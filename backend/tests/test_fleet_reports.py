"""Maintenance and accidents reports (BRD FR-RPT-05, FR-RPT-06), built on real cycles through the API."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle, upload
from tests.test_accidents import estimate, refer, report
from tests.test_maintenance import center, portal_client

M, P, R = "/api/v1/maintenance", "/api/v1/portal", "/api/v1/reports"
NOW = datetime.now(UTC)


def period(days=29):
    return {"date_from": str(today() - timedelta(days=days)), "date_to": str(today())}


def at_center(admin_client, vehicle, c) -> str:
    body = {"vehicle_id": vehicle["id"], "kind": "mechanical", "description": "Noise", "center_id": c["id"]}
    r = admin_client.post(f"{M}/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def received(portal, rid, km, *, days_ago=0):
    body = {"odometer_km": km, "odometer_photo": upload(portal)}
    if days_ago:
        body["received_at"] = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    r = portal.post(f"{P}/requests/{rid}/receive", json=body)
    assert r.status_code == 200, r.text


def repaired_and_collected(portal, rid, km, number, items) -> str:
    """Ready with its invoice and the last reading (nobody holds these cars), then collected: the invoice's id."""
    total = sum(float(i.get("quantity", 1)) * float(i["unit_price"]) for i in items)
    body = {
        "number": number,
        "invoice_date": str(today()),
        "total": f"{total:.3f}",
        "file_sha256": upload(portal, b"%PDF-1.4 " + uuid.uuid4().bytes, name="inv.pdf"),
        "items": items,
        "final_odometer_km": km,
        "final_odometer_photo": upload(portal),
    }
    r = portal.post(f"{P}/requests/{rid}/ready", json=body)
    assert r.status_code == 200, r.text
    assert portal.post(f"{P}/requests/{rid}/picked-up").status_code == 200
    return r.json()["invoices"][-1]["id"]


def invoice(portal, rid, number, items):
    total = sum(float(i.get("quantity", 1)) * float(i["unit_price"]) for i in items)
    body = {
        "request_id": rid,
        "number": number,
        "invoice_date": str(today()),
        "total": f"{total:.3f}",
        "file_sha256": upload(portal, b"%PDF-1.4 " + uuid.uuid4().bytes, name="inv.pdf"),
        "items": items,
    }
    r = portal.post(f"{P}/invoices", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def garages(admin_client, new_client):
    a, b = center(admin_client, "Garage A"), center(admin_client, "Garage B")
    return {
        "a": a,
        "b": b,
        "pa": portal_client(admin_client, new_client, a, "garagea"),
        "pb": portal_client(admin_client, new_client, b, "garageb"),
    }


def test_maintenance_time_at_the_centers_cost_by_center_and_vehicle_and_the_parts(admin_client, company, garages):
    g = garages
    v1, v2, v3 = (make_vehicle(admin_client, company["id"], km=10_000) for _ in range(3))
    # v1 at garage A: a day there, collected, invoice 45 (a part and labour), approved
    r1 = at_center(admin_client, v1, g["a"])
    received(g["pa"], r1, 10_010, days_ago=1)
    i1 = repaired_and_collected(
        g["pa"],
        r1,
        10_020,
        "A-1",
        [
            {"kind": "part", "description": "Wheel bearing", "unit_price": "30.000"},
            {"kind": "labour", "description": "Labour", "unit_price": "15.000"},
        ],
    )
    admin_client.post(f"{M}/invoices/{i1}/approve")
    # v2 at garage A: there for 3 days and still there
    r2 = at_center(admin_client, v2, g["a"])
    received(g["pa"], r2, 10_010, days_ago=3)
    # v3 at garage B: collected; one invoice approved, one rejected, one waiting
    r3 = at_center(admin_client, v3, g["b"])
    received(g["pb"], r3, 10_010, days_ago=3)
    b1 = [
        {"kind": "part", "description": "wheel bearing ", "quantity": "2", "unit_price": "40.000"},
        {"kind": "labour", "description": "Labour", "unit_price": "20.000"},
    ]
    i3 = repaired_and_collected(g["pb"], r3, 10_030, "B-1", b1)
    # one rejected, one still waiting: the request stays open, so all three can be entered
    bad = invoice(g["pb"], r3, "B-2", [{"kind": "part", "description": "Turbo", "unit_price": "900.000"}])
    admin_client.post(f"{M}/invoices/{bad}/reject", json={"reason": "Not on this car"})
    invoice(g["pb"], r3, "B-3", [{"kind": "part", "description": "Turbo", "unit_price": "800.000"}])
    admin_client.post(f"{M}/invoices/{i3}/approve")

    rep = admin_client.get(f"{R}/maintenance", params=period()).json()
    by = {x["center"]["name"]: x for x in rep["by_center"]}
    a, b = by["Garage A"], by["Garage B"]
    assert (a["received"], a["still_there"], a["invoices"], a["cost"]) == (2, 1, 1, "45.000")
    assert (b["received"], b["still_there"], b["invoices"], b["cost"], b["avg_cost"]) == (1, 0, 1, "100.000", "100.000")
    assert 3 * 86400 - 60 < b["max_stay_seconds"] < 3 * 86400 + 600  # v3: three days, as received
    assert a["max_stay_seconds"] > 3 * 86400 - 60  # the vehicle still there counts until now
    assert rep["totals"] | {"avg_stay_seconds": None} == {
        "received": 3,
        "still_there": 1,
        "avg_stay_seconds": None,
        "invoices": 2,
        "cost": "145.000",
        "parts": "110.000",
        "labour": "35.000",
        "other": "0.000",
    }
    vehicles = {x["vehicle"]["plate_number"]: x for x in rep["by_vehicle"]}
    assert vehicles[v3["plate_number"]]["cost"] == "100.000" and vehicles[v2["plate_number"]]["cost"] == "0.000"
    assert rep["by_vehicle"][0]["vehicle"]["plate_number"] == v3["plate_number"]  # the costliest first
    # the same part, written differently by two centers, is one line; the rejected and waiting invoices are not there
    assert rep["parts"] == [{"description": "Wheel bearing", "quantity": "3.000", "amount": "110.000", "invoices": 2}]

    csv = admin_client.get(f"{R}/maintenance", params=period() | {"format": "csv", "section": "parts"})
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    assert csv.content.decode("utf-8-sig").splitlines() == [
        "part,quantity,amount,invoices",
        "Wheel bearing,3,110.000,2",
    ]
    lines = (
        admin_client.get(f"{R}/maintenance", params=period() | {"format": "csv"})
        .content.decode("utf-8-sig")
        .splitlines()
    )
    assert lines[0].startswith("center,received,still_there") and len(lines) == 3
    # an earlier period has none of it
    old = {"date_from": str(today() - timedelta(days=60)), "date_to": str(today() - timedelta(days=30))}
    assert admin_client.get(f"{R}/maintenance", params=old).json()["by_center"] == []


def test_report_periods_permissions_and_company_scope(admin_client, new_client, company, companies, garages):
    v = make_vehicle(admin_client, company["id"], km=10_000)
    rid = at_center(admin_client, v, garages["a"])
    received(garages["pa"], rid, 10_010)
    too_long = {"date_from": str(today() - timedelta(days=366)), "date_to": str(today())}
    r = admin_client.get(f"{R}/maintenance", params=too_long)
    assert r.status_code == 422 and r.json()["code"] == "range_too_long_days" and r.json()["params"]["days"] == 366
    backwards = {"date_from": str(today()), "date_to": str(today() - timedelta(days=1))}
    assert admin_client.get(f"{R}/accidents", params=backwards).json()["code"] == "invalid_range"
    make_user(admin_client, "rep_only", permissions=["reports.view"])
    make_user(admin_client, "mnt_only", permissions=["maintenance.view", "accidents.view"])
    make_user(
        admin_client,
        "rep_b",
        permissions=["reports.view", "maintenance.view", "accidents.view"],
        company_ids=[companies["b"]["id"]],
    )
    make_user(admin_client, "rep_noexport", permissions=["reports.view", "maintenance.view"])
    c1, c2, c3, c4 = new_client(), new_client(), new_client(), new_client()
    for c, u in ((c1, "rep_only"), (c2, "mnt_only"), (c3, "rep_b"), (c4, "rep_noexport")):
        login(c, u)
    for path in ("maintenance", "accidents"):
        assert c1.get(f"{R}/{path}", params=period()).status_code == 403, path
        assert c2.get(f"{R}/{path}", params=period()).status_code == 403, path
    assert c3.get(f"{R}/maintenance", params=period()).json()["by_center"] == []
    assert c4.get(f"{R}/maintenance", params=period()).status_code == 200
    assert c4.get(f"{R}/maintenance", params=period() | {"format": "csv"}).status_code == 403  # reports.export


def test_accidents_by_driver_vehicle_and_outcome_estimate_against_actual_and_deductions(
    admin_client, client, new_client, company
):
    vehicle = make_vehicle(admin_client, company["id"], km=30_000)
    driver = make_driver(admin_client, company["id"])
    hand_over(admin_client, vehicle, driver, km=30_000)
    garage = center(admin_client, "Body Shop")
    s = {
        "vehicle": vehicle,
        "driver": driver,
        "h": bearer(bind_device(client, driver["phone"])),
        "center": garage,
        "portal": portal_client(admin_client, new_client, garage, "bodyrep"),
    }
    # 1. the driver's accident: estimate 150 approved, the driver liable over 3 months, repaired for 162.500
    one = report(client, s, police=True).json()["id"]
    refer(admin_client, s, one)
    estimate(s, one, "150.000")
    admin_client.post(f"/api/v1/accidents/{one}/estimate/approve")
    admin_client.post(f"/api/v1/accidents/{one}/outcome", json={"liability": "driver", "installments": 3})
    rid = admin_client.post(f"/api/v1/accidents/{one}/repair").json()["repair"]["id"]
    portal = s["portal"]
    received(portal, rid, 30_100)
    body = {"repair_details": "Bumper", "final_odometer_km": 30_105, "final_odometer_photo": upload(portal)}
    portal.post(f"{P}/requests/{rid}/complete", json=body)
    portal.post(f"{P}/requests/{rid}/ready", json={})
    portal.post(f"{P}/requests/{rid}/picked-up")
    wrong = invoice(portal, rid, "BS-0", [{"kind": "part", "description": "Engine", "unit_price": "999.000"}])
    admin_client.post(f"{M}/invoices/{wrong}/reject", json={"reason": "Not this repair"})
    bumper = [{"kind": "part", "description": "Bumper", "unit_price": "162.500"}]
    admin_client.post(f"{M}/invoices/{invoice(portal, rid, 'BS-1', bumper)}/approve")
    # 2. an office report on a vehicle nobody held, still without a police report
    other = make_vehicle(admin_client, company["id"], km=5_000)
    two = admin_client.post(
        "/api/v1/accidents", json={"vehicle_id": other["id"], "description": "Found scratched", "injuries": True}
    ).json()["id"]
    refer(admin_client, s, two)
    pending = estimate(s, two, "99.000", items=[{"kind": "part", "description": "Paint", "unit_price": "99.000"}])
    assert pending.json()["estimate_status"] == "pending"  # waiting for the manager: not an approved estimate yet
    # 5. with its police report, and the driver not liable
    five = admin_client.post(
        "/api/v1/accidents",
        json={"vehicle_id": other["id"], "description": "Hit while parked", "police_report": upload(admin_client)},
    ).json()["id"]
    assert admin_client.post(f"/api/v1/accidents/{five}/outcome", json={"liability": "none"}).status_code == 200
    # 3. cancelled: not counted; 4. forty days ago, still without a police report
    three = admin_client.post("/api/v1/accidents", json={"vehicle_id": other["id"], "description": "Wrong"}).json()[
        "id"
    ]
    admin_client.post(f"/api/v1/accidents/{three}/cancel", json={"reason": "Entered by mistake"})
    old = (NOW - timedelta(days=40)).isoformat()
    four = admin_client.post(
        "/api/v1/accidents", json={"vehicle_id": other["id"], "description": "Old dent", "occurred_at": old}
    ).json()["id"]

    rep = admin_client.get(f"{R}/accidents", params=period()).json()
    assert rep["totals"] == {
        "accidents": 3,
        "injuries": 1,
        "estimate": "150.000",
        "actual_cost": "162.500",
        "deduction": "150.000",
        "waiting_police_report": 2,
    }
    assert rep["by_outcome"] == {"pending": 1, "none": 1, "driver": 1, "shared": 0}
    lines = {x["id"]: x for x in rep["accidents"]}
    assert set(lines) == {one, two, five}
    assert (lines[one]["estimate"], lines[one]["actual_cost"], lines[one]["difference"], lines[one]["deduction"]) == (
        "150.000",
        "162.500",
        "12.500",
        "150.000",
    )
    assert lines[two]["driver"] is None and lines[two]["estimate"] is None
    drivers = {(x["driver"] or {}).get("id"): x for x in rep["by_driver"]}
    assert (
        drivers[driver["id"]]["accidents"],
        drivers[driver["id"]]["liable"],
        drivers[driver["id"]]["deduction"],
    ) == (1, 1, "150.000")
    assert (drivers[None]["accidents"], drivers[None]["liable"]) == (2, 0)  # "not liable" is not liable
    assert [x["vehicle"]["plate_number"] for x in rep["by_vehicle"]] in (
        [vehicle["plate_number"], other["plate_number"]],
        [other["plate_number"], vehicle["plate_number"]],
    )
    # waiting for the police report: every open one, whatever its date
    assert [x["id"] for x in rep["waiting_police_report"]] == [two, four] or [
        x["id"] for x in rep["waiting_police_report"]
    ] == [four, two]
    longer = admin_client.get(f"{R}/accidents", params=period(60)).json()
    assert longer["totals"]["accidents"] == 4
    csv = (
        admin_client.get(f"{R}/accidents", params=period() | {"format": "csv"}).content.decode("utf-8-sig").splitlines()
    )
    assert (
        csv[0] == "number,occurred_at,plate,driver,injuries,police_report,liability,liability_percent,"
        "estimate,actual_cost,difference,deduction,status"
    )
    assert len(csv) == 4 and any(",driver,100,150.000,162.500,12.500,150.000,open" in row for row in csv)
    # a cancelled deduction no longer counts
    deduction = admin_client.get(f"/api/v1/accidents/{one}").json()["deduction"]["id"]
    admin_client.post(f"/api/v1/deductions/{deduction}/cancel", json={"reason": "Insurance paid"})
    after = admin_client.get(f"{R}/accidents", params=period()).json()
    assert after["totals"]["deduction"] == "0.000"
    assert {x["id"]: x["deduction"] for x in after["accidents"]}[one] is None
