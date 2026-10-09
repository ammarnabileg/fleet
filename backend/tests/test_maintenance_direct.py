"""Maintenance, the simple flow: the driver (or the office) picks the center and the request reaches it at once, with no
approval or referral; the center receives the car, which stays in the driver's custody (he does not work with it
meanwhile); the center marks it ready with its invoice, which waits for the management; the driver collects it and
confirms it in the app. The office records the pickup only of a car nobody holds."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.clock import KUWAIT, today
from app.modules.fleet import service as fleet
from tests.conftest import bearer, bind_device, hand_over, jpeg, make_driver, make_vehicle, upload
from tests.test_maintenance import (
    M,
    P,
    camera,
    center,
    driver_request,
    make_setup,
    portal_client,
    ready,
    receive,
    sent,
    statuses,
)

DRIVER = "/api/v1/driver/maintenance"


@pytest.fixture
def s(admin_client, client, new_client, company):
    return make_setup(admin_client, client, new_client, company)


def deactivate(admin_client, c) -> None:
    r = admin_client.put(f"{M}/centers/{c['id']}", json={"version": c["version"], "is_active": False})
    assert r.status_code == 200, r.text


def pickup(client, s, rid, km=20_170, photo=None, at=None):
    body = {
        "odometer_km": km,
        "odometer_photo": photo or camera(client, s["h"]),
        "picked_up_at": (at or datetime.now(UTC)).isoformat(),
    }
    return client.post(f"{DRIVER}/{rid}/picked-up", json=body, headers=s["h"])


def start_day(client, s, km=20_180, at=None):
    body = {"kind": "start_day", "value_km": km, "photo_sha256": camera(client, s["h"])}
    body["recorded_at"] = (at or datetime.now(UTC)).isoformat()
    return client.post("/api/v1/driver/odometer", json=body, headers=s["h"])


def report(client, s):
    shot = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=s["h"],
        files={"file": ("s.jpg", jpeg(), "image/jpeg")},
    ).json()["sha256"]
    body = {"business_date": str(today()), "orders_count": 1, "cash_amount": "1", "screenshot_sha256": shot}
    return client.post("/api/v1/driver/reports", headers=s["h"], json=body)


def custodies(admin_client, vehicle):
    return admin_client.get("/api/v1/custodies", params={"vehicle_id": vehicle["id"]}).json()


def alerts(admin_client):
    return [a["kind"] for a in admin_client.get("/api/v1/alerts").json()]


def return_to_office(admin_client, s, km=20_150, at=None):
    (c,) = [x for x in custodies(admin_client, s["vehicle"]) if x["ended_at"] is None]
    body = {"odometer_km": km, "photo_sha256": upload(admin_client)} | ({"ended_at": at} if at else {})
    r = admin_client.post(f"/api/v1/custodies/{c['id']}/return", json=body)
    assert r.status_code == 200, r.text


def test_from_the_driver_to_the_center_and_back_in_his_custody(admin_client, client, s):
    closed = center(admin_client, "Closed Garage")
    deactivate(admin_client, closed)
    form = client.get(f"{DRIVER}/form", headers=s["h"]).json()
    assert form["direct_to_center"] is True
    assert [c["name"] for c in form["centers"]] == [s["center"]["name"]]  # active centers only
    assert form["centers"][0]["specialty"] == "mechanical"

    # the driver picks the center: it is there at once, nothing waits for the office
    r = driver_request(client, s)
    assert r.status_code == 201, r.text
    mine = r.json()
    assert (mine["status"], mine["center"]["name"]) == ("referred", s["center"]["name"])
    rid = mine["id"]
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert [(e["status"], e["by"], e["note"]) for e in detail["events"]] == [("requested", "driver", "Al Noor Garage")]
    assert (detail["direct"], detail["source"]) == (True, "driver")
    assert "maintenance_requested" not in alerts(admin_client)
    assert [(x["id"], x["is_new"]) for x in s["portal"].get(f"{P}/requests").json()] == [(rid, True)]

    # the reception: the car stays his, "in maintenance"; he does not work with it meanwhile
    assert receive(s, rid).status_code == 200
    vehicle = admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()
    assert vehicle["status"] == "maintenance"
    (held,) = custodies(admin_client, s["vehicle"])
    assert held["ended_at"] is None
    today_ = client.get("/api/v1/driver/today", headers=s["h"]).json()
    assert today_["custody"]["in_maintenance"] is True
    assert today_["custody"]["maintenance_center"] == "Al Noor Garage"
    r = start_day(client, s)
    assert r.status_code == 409 and r.json()["code"] == "vehicle_in_maintenance"
    r = report(client, s)
    assert r.status_code == 409 and r.json()["code"] == "vehicle_in_maintenance"
    beat = client.post("/api/v1/driver/status", headers=s["h"], json={"gps_enabled": False}).json()
    assert beat["tracking_required"] is False
    assert "gps_off" not in alerts(admin_client)

    # ready, with the invoice: the driver is told; the office has nothing to collect
    r = ready(s, rid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready" and r.json()["invoices"][0]["status"] == "pending"
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()
    assert notices["items"][0]["kind"] == "maintenance_ready"
    assert "maintenance_ready" not in alerts(admin_client)
    assert client.get(DRIVER, headers=s["h"]).json()[0]["pickup_in_app"] is True
    # neither the office nor the center records his pickup
    r = admin_client.post(f"{M}/requests/{rid}/picked-up")
    assert r.status_code == 409 and r.json()["code"] == "pickup_by_driver"
    r = s["portal"].post(f"{P}/requests/{rid}/picked-up")
    assert r.status_code == 409 and r.json()["code"] == "pickup_by_driver"

    # he collects it: his reading, no new custody; his day can start
    r = pickup(client, s, rid, photo=upload(admin_client))
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    r = pickup(client, s, rid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "picked_up"
    assert [c["id"] for c in custodies(admin_client, s["vehicle"])] == [held["id"]]
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "assigned"
    today_ = client.get("/api/v1/driver/today", headers=s["h"]).json()
    assert today_["custody"]["in_maintenance"] is False and today_["custody"]["last_odometer_km"] == 20_170
    assert start_day(client, s).status_code == 201
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "already_picked_up"  # the app's queue retrying

    # the management approves the invoice: the request closes
    inv = admin_client.get(f"{M}/requests/{rid}").json()["invoices"][0]
    assert admin_client.post(f"{M}/invoices/{inv['id']}/approve").status_code == 200
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert statuses(detail) == ["requested", "received", "ready", "picked_up", "closed"]


def test_the_request_needs_an_open_center(admin_client, client, new_client, s, company):
    r = driver_request(client, s, center_id=None)
    assert r.status_code == 422 and r.json()["code"] == "center_required"
    other = center(admin_client, "Shut Garage")
    deactivate(admin_client, other)
    r = driver_request(client, s, center_id=other["id"])
    assert r.status_code == 409 and r.json()["code"] == "center_inactive"
    empty = center(admin_client, "No Portal Garage")  # active, but no account to receive the car
    assert empty["id"] not in [c["id"] for c in client.get(f"{DRIVER}/form", headers=s["h"]).json()["centers"]]
    r = driver_request(client, s, center_id=empty["id"])
    assert r.status_code == 409 and r.json()["code"] == "center_inactive"
    rid = sent(client, s)
    r = driver_request(client, s)
    assert r.status_code == 409 and r.json()["code"] == "vehicle_at_center"
    # before it is ready, the driver cannot collect it; another driver never can
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "invalid_maintenance_status"
    receive(s, rid)
    ready(s, rid)
    stranger = make_driver(admin_client, company["id"])
    other_client = new_client()
    h2 = bearer(bind_device(other_client, stranger["phone"]))
    r = other_client.post(
        f"{DRIVER}/{rid}/picked-up",
        json={"odometer_km": 20_170, "odometer_photo": camera(other_client, h2)},
        headers=h2,
    )
    assert r.status_code == 404
    early = datetime.now(UTC) - timedelta(days=1)
    r = pickup(client, s, rid, at=early)  # before the car was ready: refused
    assert r.status_code == 422 and r.json()["code"] == "invalid_recorded_at"


def test_the_office_sends_it_to_the_center_it_picks(admin_client, client, s):
    body = {"vehicle_id": s["vehicle"]["id"], "kind": "tyres", "description": "Front tyres worn"}
    r = admin_client.post(f"{M}/requests", json=body)
    assert r.status_code == 422 and r.json()["code"] == "center_required"
    r = admin_client.post(f"{M}/requests", json=body | {"center_id": s["center"]["id"]})
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["status"], out["source"], out["center"]["name"]) == ("referred", "office", "Al Noor Garage")
    assert [(e["status"], e["note"]) for e in out["events"]] == [("requested", "Al Noor Garage")]
    assert [x["id"] for x in s["portal"].get(f"{P}/requests").json()] == [out["id"]]
    # the driver who holds the car follows it in the app and collects it
    receive(s, out["id"])
    ready(s, out["id"])
    mine = client.get(DRIVER, headers=s["h"]).json()
    assert [(x["id"], x["pickup_in_app"]) for x in mine] == [(out["id"], True)]
    assert pickup(client, s, out["id"]).status_code == 200


def test_the_office_records_the_pickup_when_the_driver_no_longer_holds_the_car(admin_client, client, s):
    rid = sent(client, s)
    receive(s, rid, km=20_150)
    # the office takes it back while it is at the center: still in maintenance, nobody's
    return_to_office(admin_client, s)
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "maintenance"
    assert admin_client.get(f"{M}/requests/{rid}").json()["driver_collects"] is False
    # the company collects it: the center gives its last reading
    r = ready(s, rid)
    assert r.status_code == 422 and r.json()["code"] == "final_reading_required"
    r = ready(s, rid, final_odometer_km=20_190, final_odometer_photo=upload(s["portal"]))  # 40 km of test drives
    assert r.status_code == 200, r.text
    assert "maintenance_ready" in alerts(admin_client)
    assert client.get(DRIVER, headers=s["h"]).json()[0]["pickup_in_app"] is False
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "pickup_by_office"
    r = admin_client.post(f"{M}/requests/{rid}/picked-up")
    assert r.status_code == 200 and r.json()["status"] == "picked_up"
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "available"
    # the next handover is compared with the center's last reading: a test drive is not distance off duty
    driver = make_driver(admin_client, s["vehicle"]["company_id"])
    hand_over(admin_client, s["vehicle"], driver, km=20_191)
    readings = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": s["vehicle"]["id"]}).json()
    handover = next(r for r in readings if r["kind"] == "handover" and r["value_km"] == 20_191)
    assert handover["flags"] == []


def test_a_request_from_before_whose_reception_ended_the_custody_gives_the_car_back(admin_client, client, s):
    """Before the simple flow the reception ended the driver's custody; he collects the car in the app and it is
    his again (a new custody), unless he holds another one by then."""
    rid = sent(client, s)
    receive(s, rid)
    received_at = admin_client.get(f"{M}/requests/{rid}").json()["received_at"]
    return_to_office(admin_client, s, at=received_at)  # as the old reception did, at that very moment
    ready(s, rid, final_odometer_km=20_160, final_odometer_photo=upload(s["portal"]))
    assert client.get(DRIVER, headers=s["h"]).json()[0]["pickup_in_app"] is True
    spare = make_vehicle(admin_client, s["vehicle"]["company_id"], km=5_000)
    hand_over(admin_client, spare, s["driver"], km=5_000)
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "driver_has_custody"
    assert admin_client.get(f"{M}/requests/{rid}").json()["status"] == "ready"
    (c,) = [x for x in custodies(admin_client, spare) if x["ended_at"] is None]
    body = {"odometer_km": 5_010, "photo_sha256": upload(admin_client)}
    assert admin_client.post(f"/api/v1/custodies/{c['id']}/return", json=body).status_code == 200
    assert pickup(client, s, rid).status_code == 200
    mine = client.get("/api/v1/driver/today", headers=s["h"]).json()["custody"]
    assert mine["plate_number"] == s["vehicle"]["plate_number"]
    assert len(custodies(admin_client, s["vehicle"])) == 2


def test_closing_at_pickup_when_the_settings_say_so(admin_client, client, s):
    current = admin_client.get("/api/v1/settings").json()["maintenance"]
    r = admin_client.put(
        "/api/v1/settings/maintenance",
        json={"version": current["version"], "value": current["value"] | {"close_requires_invoice": False}},
    )
    assert r.status_code == 200, r.text
    rid = sent(client, s)
    receive(s, rid)
    ready(s, rid)
    assert pickup(client, s, rid).json()["status"] == "closed"


def test_a_car_at_the_center_keeps_its_custody(admin_client, client, s, company):
    """No handover, transfer or swap moves a car that is at a center: it stays with its driver until he collects
    it (the office may take it back first)."""
    rid = sent(client, s)
    receive(s, rid)
    a = make_driver(admin_client, company["id"])
    body = {"vehicle_id": s["vehicle"]["id"], "driver_id": a["id"], "mode": "release", "odometer_km": 20_150}
    r = admin_client.post("/api/v1/custodies/transfer", json=body | {"photo_sha256": upload(admin_client)})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_in_maintenance_transfer"
    # nor a car the taker holds while it is at the center
    x = make_vehicle(admin_client, company["id"], km=7_000)
    body = {"vehicle_id": x["id"], "driver_id": s["driver"]["id"], "mode": "release", "odometer_km": 7_000}
    body |= {"photo_sha256": upload(admin_client), "other_odometer_km": 20_150}
    r = admin_client.post("/api/v1/custodies/transfer", json=body | {"other_photo_sha256": upload(admin_client)})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_in_maintenance_transfer"
    r = admin_client.post(
        "/api/v1/custodies",
        json={
            "vehicle_id": s["vehicle"]["id"],
            "driver_id": a["id"],
            "odometer_km": 20_150,
            "photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 409
    assert [c["ended_at"] for c in custodies(admin_client, s["vehicle"])] == [None]


def test_tracking_rests_while_the_car_is_at_the_center(admin_client, client, s):
    rid = sent(client, s)
    before = datetime.now(UTC)
    receive(s, rid)

    def send(seq, t):
        point = {"seq": seq, "recorded_at": t.isoformat(), "lat": 29.3759, "lng": 47.9774, "speed_kmh": 40}
        body = {"sent_at": datetime.now(UTC).isoformat(), "points": [point]}
        return client.post("/api/v1/driver/positions", headers=s["h"], json=body).json()

    assert send(1, before)["stored_seqs"] == [1]  # sent late, from before the reception
    ack = send(2, datetime.now(UTC))
    assert ack["stored_seqs"] == [] and ack["rejected"] == [{"seq": 2, "reason": "in_maintenance"}]
    live = admin_client.get("/api/v1/tracking/live").json()
    (car,) = [x for x in live if x["vehicle"]["id"] == s["vehicle"]["id"]]
    assert (car["in_maintenance"], car["signal_lost"]) == (True, False)


def test_days_wholly_at_the_center_are_not_work_days(admin_client, client, new_client, company, db):
    """Attendance: a day the car spent wholly at the center is not a day he held a car to work with (left for the
    office to classify, like any day without a start)."""
    vehicle = make_vehicle(admin_client, company["id"], km=20_000)
    driver = make_driver(admin_client, company["id"])
    hand_over(admin_client, vehicle, driver, km=20_000, started_at=(datetime.now(UTC) - timedelta(days=6)).isoformat())
    s = {"vehicle": vehicle, "driver": driver, "h": bearer(bind_device(client, driver["phone"]))}
    s["center"] = center(admin_client)
    s["portal"] = portal_client(admin_client, new_client, s["center"], "days1")
    rid = sent(client, s)
    arrived = datetime.combine(today() - timedelta(days=4), datetime.min.time(), tzinfo=KUWAIT) + timedelta(hours=15)
    body = {"odometer_km": 20_100, "odometer_photo": upload(s["portal"]), "received_at": arrived.isoformat()}
    assert s["portal"].post(f"{P}/requests/{rid}/receive", json=body).status_code == 200
    ready(s, rid)
    assert pickup(client, s, rid).status_code == 200
    driver_id = db.execute(text("SELECT id FROM people.employees WHERE public_id = :p"), {"p": driver["id"]}).scalar()
    first = today() - timedelta(days=6)
    at_center = {today() - timedelta(days=d) for d in (3, 2, 1)}
    assert fleet.days_at_center(db, [driver_id], first, today())[driver_id] == at_center
    held = fleet.held_days(db, [driver_id], first, today())[driver_id]
    assert held == {first + timedelta(days=d) for d in range(7)} - at_center
    # the day it arrived and the day he collected it count: he had it part of the day
    assert today() - timedelta(days=4) in held and today() in held


def test_a_vehicle_in_an_accident_goes_through_the_office(admin_client, client, s, owner_db):
    owner_db.execute(
        text("UPDATE fleet.vehicles SET status = 'accident' WHERE public_id = :v"), {"v": s["vehicle"]["id"]}
    )
    owner_db.commit()
    r = driver_request(client, s, client_ref=str(uuid.uuid4()))
    assert r.status_code == 201 and r.json()["status"] == "requested"  # the accident's repair is the office's
    assert r.json()["center"] is None
    assert "maintenance_requested" in alerts(admin_client)
    # whether or not he picked a center
    r = driver_request(client, s, center_id=None)
    assert r.status_code == 201 and r.json()["status"] == "requested"
