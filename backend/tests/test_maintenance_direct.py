"""Maintenance straight to the center (settings: maintenance.direct_to_center): the driver picks the center and the
request reaches it at once, with no office approval or referral; the center repairs without a quote, uploads its
invoice before calling the driver, and the driver's pickup in the app gives him the vehicle back."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import bearer, bind_device, hand_over, make_driver, make_vehicle, upload
from tests.test_maintenance import (
    M,
    P,
    approved_and_referred,
    camera,
    center,
    complete,
    driver_request,
    invoice,
    make_setup,
    quote,
    receive,
    statuses,
)

DRIVER = "/api/v1/driver/maintenance"


@pytest.fixture
def s(admin_client, client, new_client, company):
    return make_setup(admin_client, client, new_client, company)


def direct(admin_client, on: bool = True) -> None:
    current = admin_client.get("/api/v1/settings").json()["maintenance"]
    r = admin_client.put(
        "/api/v1/settings/maintenance",
        json={"version": current["version"], "value": current["value"] | {"direct_to_center": on}},
    )
    assert r.status_code == 200, r.text


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


def test_from_the_driver_to_the_center_and_back_with_no_office_step(admin_client, client, s):
    closed = center(admin_client, "Closed Garage")
    deactivate(admin_client, closed)
    assert client.get(f"{DRIVER}/form", headers=s["h"]).json() == {"direct_to_center": False, "centers": []}
    direct(admin_client)
    form = client.get(f"{DRIVER}/form", headers=s["h"]).json()
    assert form["direct_to_center"] is True
    assert [c["name"] for c in form["centers"]] == [s["center"]["name"]]  # active centers only
    assert form["centers"][0]["specialty"] == "mechanical"

    r = driver_request(client, s, center_id=s["center"]["id"])
    assert r.status_code == 201, r.text
    mine = r.json()
    assert (mine["status"], mine["center"]["name"]) == ("referred", s["center"]["name"])
    rid = mine["id"]
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert [(e["status"], e["by"]) for e in detail["events"]] == [("requested", "driver"), ("referred", "driver")]
    # nothing waits for the office: no "waiting for approval" alert
    kinds = [a["kind"] for a in admin_client.get("/api/v1/alerts").json()]
    assert "maintenance_requested" not in kinds
    # the center sees it as new, and knows the mode
    assert [(x["id"], x["is_new"]) for x in s["portal"].get(f"{P}/requests").json()] == [(rid, True)]
    assert s["portal"].get(f"{P}/me").json()["direct_to_center"] is True

    # reception, the repair started without a quote, done
    assert receive(s, rid).status_code == 200
    r = s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "in_repair"})
    assert r.status_code == 200, r.text
    assert complete(s, rid).status_code == 200
    # the invoice before the driver is called
    r = s["portal"].post(f"{P}/requests/{rid}/ready", json={})
    assert r.status_code == 409 and r.json()["code"] == "invoice_required"
    assert invoice(s, rid).status_code == 201
    assert s["portal"].post(f"{P}/requests/{rid}/ready", json={}).status_code == 200
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()
    assert notices["items"][0]["kind"] == "maintenance_ready"

    # the driver collects it: the vehicle is his again, his day can start
    assert client.get("/api/v1/driver/today", headers=s["h"]).json()["custody"] is None
    office_photo = upload(admin_client)
    r = pickup(client, s, rid, photo=office_photo)
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    r = pickup(client, s, rid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "picked_up"
    today = client.get("/api/v1/driver/today", headers=s["h"]).json()
    assert today["custody"]["plate_number"] == s["vehicle"]["plate_number"]
    assert today["custody"]["last_odometer_km"] == 20_170
    vehicle = admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()
    assert vehicle["status"] == "assigned"
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "already_picked_up"  # the app's queue retrying

    # finance approves the center's invoice when it settles with it: the request closes
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert detail["status"] == "picked_up"
    inv = detail["invoices"][0]
    assert admin_client.post(f"{M}/invoices/{inv['id']}/approve").status_code == 200
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert statuses(detail) == [
        "requested",
        "referred",
        "received",
        "in_repair",
        "completed",
        "ready",
        "picked_up",
        "closed",
    ]


def test_direct_mode_rules(admin_client, client, new_client, s, company):
    # with the mode off a chosen center is ignored: the office approves and refers as before
    r = driver_request(client, s, center_id=s["center"]["id"])
    assert r.status_code == 201 and r.json()["status"] == "requested"
    admin_client.post(f"{M}/requests/{r.json()['id']}/cancel", json={"reason": "sent twice"})
    # and the center cannot skip the quote
    direct(admin_client)
    other = center(admin_client, "Shut Garage")
    deactivate(admin_client, other)
    r = driver_request(client, s, center_id=other["id"])
    assert r.status_code == 409 and r.json()["code"] == "center_inactive"
    # an app that sends no center (an older one) goes through the office
    r = driver_request(client, s)
    assert r.status_code == 201 and r.json()["status"] == "requested"
    admin_client.post(f"{M}/requests/{r.json()['id']}/cancel", json={"reason": "old app"})
    r = driver_request(client, s, center_id=s["center"]["id"])
    assert r.status_code == 201 and r.json()["status"] == "referred"
    rid = r.json()["id"]
    r = driver_request(client, s, center_id=s["center"]["id"])
    assert r.status_code == 409 and r.json()["code"] == "vehicle_at_center"
    # before it is ready, the driver cannot collect it; another driver never can
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "invalid_maintenance_status"
    receive(s, rid)
    assert complete(s, rid).status_code == 200  # a short job: from the reception to done
    invoice(s, rid)
    s["portal"].post(f"{P}/requests/{rid}/ready", json={})
    stranger = make_driver(admin_client, company["id"])
    other_client = new_client()
    h2 = bearer(bind_device(other_client, stranger["phone"]))
    r = other_client.post(
        f"{DRIVER}/{rid}/picked-up",
        json={"odometer_km": 20_170, "odometer_photo": camera(other_client, h2)},
        headers=h2,
    )
    assert r.status_code == 404
    # a driver who took another car meanwhile is refused: the office hands this one over
    spare = make_vehicle(admin_client, company["id"], km=5_000)
    hand_over(admin_client, spare, s["driver"], km=5_000)
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "driver_has_custody"
    assert admin_client.get(f"{M}/requests/{rid}").json()["status"] == "ready"


def test_the_default_flow_is_unchanged(admin_client, client, s):
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    r = s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "in_repair"})
    assert r.status_code == 409  # the repair starts through a quote
    r = complete(s, rid)
    assert r.status_code == 409
    assert s["portal"].get(f"{P}/me").json()["direct_to_center"] is False


def ready_for_pickup(admin_client, client, s) -> str:
    direct(admin_client)
    rid = driver_request(client, s, center_id=s["center"]["id"]).json()["id"]
    receive(s, rid)
    complete(s, rid)
    invoice(s, rid)
    assert s["portal"].post(f"{P}/requests/{rid}/ready", json={}).status_code == 200
    return rid


def test_the_request_keeps_its_way_whatever_the_switch_says_later(admin_client, client, s):
    rid = ready_for_pickup(admin_client, client, s)
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert (detail["direct"], detail["source"]) == (True, "driver")
    direct(admin_client, False)  # turned off meanwhile: this request still ends with the driver's own pickup
    early = datetime.now(UTC) - timedelta(days=1)
    r = pickup(client, s, rid, at=early)  # before the car was ready: refused
    assert r.status_code == 422 and r.json()["code"] == "invalid_recorded_at"
    assert pickup(client, s, rid).status_code == 200
    # a request through the office, while the switch is off, keeps the office's rules
    office = driver_request(client, s)
    assert office.status_code == 201 and office.json()["status"] == "requested"
    assert admin_client.get(f"{M}/requests/{office.json()['id']}").json()["direct"] is False


def test_a_pickup_the_office_recorded_is_not_reported_to_the_driver_as_his(admin_client, client, s):
    rid = ready_for_pickup(admin_client, client, s)
    assert admin_client.post(f"{M}/requests/{rid}/picked-up").status_code == 200
    r = pickup(client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "pickup_by_office"  # the office hands the car over


def test_a_refused_quote_is_not_bypassed(admin_client, client, s):
    direct(admin_client)
    rid = driver_request(client, s, center_id=s["center"]["id"]).json()["id"]
    receive(s, rid)
    assert quote(s, rid, "900.000").json()["status"] == "quote_pending"  # above the limit: the office decides
    qid = admin_client.get(f"{M}/requests/{rid}").json()["quotes"][0]["id"]
    r = admin_client.post(f"{M}/quotes/{qid}/reject", json={"reason": "Too expensive"})
    assert r.json()["status"] == "inspection"
    r = s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "in_repair"})
    assert r.status_code == 409
    assert complete(s, rid).status_code == 409
    # a quote within the limit, approved at once, lets the repair start
    assert quote(s, rid, "80.000").json()["status"] == "in_repair"


def test_a_vehicle_in_an_accident_and_a_center_nobody_can_open_go_through_the_office(admin_client, client, s, owner_db):
    from sqlalchemy import text  # noqa: PLC0415

    direct(admin_client)
    empty = center(admin_client, "No Portal Garage")  # active, but no account to receive the car
    form = client.get(f"{DRIVER}/form", headers=s["h"]).json()
    assert empty["id"] not in [c["id"] for c in form["centers"]]
    r = driver_request(client, s, center_id=empty["id"])
    assert r.status_code == 409 and r.json()["code"] == "center_inactive"
    owner_db.execute(
        text("UPDATE fleet.vehicles SET status = 'accident' WHERE public_id = :v"), {"v": s["vehicle"]["id"]}
    )
    owner_db.commit()
    r = driver_request(client, s, center_id=s["center"]["id"])
    assert r.status_code == 201 and r.json()["status"] == "requested"  # the accident's repair is the office's
