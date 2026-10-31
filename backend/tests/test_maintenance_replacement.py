"""A replacement car while the driver's own is at the center: a custody of its own kind next to his own (which he
keeps), the car he works with meanwhile, never overlapping another custody of the same car or another replacement of
his, and ended in the same step as he collects his own car (or by the office before)."""

from datetime import UTC, datetime

import pytest

from tests.conftest import make_driver, make_vehicle, upload
from tests.test_maintenance import M, camera, make_setup, ready, receive, sent
from tests.test_maintenance_direct import DRIVER, custodies, report, return_to_office, start_day


@pytest.fixture
def s(admin_client, client, new_client, company):
    out = make_setup(admin_client, client, new_client, company)
    out["spare"] = make_vehicle(admin_client, company["id"], km=5_000)
    return out


def give(admin_client, s, rid, km=5_000, vehicle=None):
    body = {"vehicle_id": (vehicle or s["spare"])["id"], "odometer_km": km, "photo_sha256": upload(admin_client)}
    return admin_client.post(f"{M}/requests/{rid}/replacement", json=body)


def open_custodies(admin_client, driver):
    rows = admin_client.get("/api/v1/custodies", params={"open": True}).json()
    return {c["kind"]: c for c in rows if c["driver"] and c["driver"]["id"] == driver["id"]}


def test_a_replacement_while_the_car_is_at_the_center_ends_when_he_collects_it(admin_client, client, company, s):
    rid = sent(client, s)
    r = give(admin_client, s, rid)
    assert r.status_code == 409 and r.json()["code"] == "replacement_not_at_center"  # not received yet
    receive(s, rid)
    r = give(admin_client, s, rid, vehicle=s["vehicle"])
    assert r.status_code == 422 and r.json()["code"] == "replacement_same_vehicle"
    r = give(admin_client, s, rid)
    assert r.status_code == 200, r.text
    detail = r.json()
    [given] = detail["replacements"]
    assert (given["kind"], given["vehicle"]["id"], given["ended_at"]) == ("replacement", s["spare"]["id"], None)
    assert detail["custody"]["vehicle"]["id"] == s["vehicle"]["id"] and detail["custody"]["ended_at"] is None

    # he keeps his own car's custody and holds the replacement: the car he works with meanwhile
    held = open_custodies(admin_client, s["driver"])
    assert set(held) == {"normal", "replacement"}
    assert admin_client.get(f"/api/v1/vehicles/{s['spare']['id']}").json()["status"] == "assigned"
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "maintenance"
    today_ = client.get("/api/v1/driver/today", headers=s["h"]).json()["custody"]
    assert (today_["plate_number"], today_["replacement"], today_["in_maintenance"]) == (
        s["spare"]["plate_number"],
        True,
        False,
    )
    assert report(client, s).status_code == 201  # a work day: no "car at the center" refusal
    r = start_day(client, s, km=5_010)
    assert r.status_code == 201, r.text
    readings = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": s["spare"]["id"]}).json()
    assert {x["kind"] for x in readings} == {"handover", "start_day"}

    # no overlaps: a second replacement, the spare to someone else, another car to him, a transfer
    other_spare = make_vehicle(admin_client, company["id"], km=1_000)
    r = give(admin_client, s, rid, vehicle=other_spare)
    assert r.status_code == 409 and r.json()["code"] == "driver_has_replacement"
    other = make_driver(admin_client, company["id"])
    body = {"vehicle_id": s["spare"]["id"], "driver_id": other["id"], "odometer_km": 5_020}
    r = admin_client.post("/api/v1/custodies", json=body | {"photo_sha256": upload(admin_client)})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_has_custody"
    body = {"vehicle_id": other_spare["id"], "driver_id": s["driver"]["id"], "odometer_km": 1_000}
    r = admin_client.post("/api/v1/custodies", json=body | {"photo_sha256": upload(admin_client)})
    assert r.status_code == 409 and r.json()["code"] == "driver_has_custody"
    r = admin_client.get(
        "/api/v1/custodies/transfer-check", params={"vehicle_id": s["spare"]["id"], "driver_id": other["id"]}
    )
    assert r.status_code == 409 and r.json()["code"] == "replacement_custody"

    # ready: he hands the replacement back as he collects his own, in one step
    ready(s, rid)
    [mine] = [x for x in client.get(DRIVER, headers=s["h"]).json() if x["id"] == rid]
    assert (mine["pickup_in_app"], mine["replacement_plate"]) == (True, s["spare"]["plate_number"])
    now = datetime.now(UTC).isoformat()
    body = {"odometer_km": 20_170, "odometer_photo": camera(client, s["h"]), "picked_up_at": now}
    r = client.post(f"{DRIVER}/{rid}/picked-up", json=body, headers=s["h"])
    assert r.status_code == 422 and r.json()["code"] == "replacement_reading_required"
    assert r.json()["params"]["plate"] == s["spare"]["plate_number"]
    body |= {"replacement_odometer_km": 5_090, "replacement_odometer_photo": upload(admin_client)}
    r = client.post(f"{DRIVER}/{rid}/picked-up", json=body, headers=s["h"])
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"  # his camera only
    body["replacement_odometer_photo"] = camera(client, s["h"])
    r = client.post(f"{DRIVER}/{rid}/picked-up", json=body, headers=s["h"])
    assert r.status_code == 200, r.text
    assert set(open_custodies(admin_client, s["driver"])) == {"normal"}
    assert admin_client.get(f"/api/v1/vehicles/{s['spare']['id']}").json()["status"] == "available"
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "assigned"
    assert (
        client.get("/api/v1/driver/today", headers=s["h"]).json()["custody"]["plate_number"]
        == (s["vehicle"]["plate_number"])
    )
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    [given] = detail["replacements"]
    assert given["ended_at"] is not None
    assert detail["pickup"]["km"] == 20_170 and detail["pickup"]["by"] == "driver"
    notes = [e["note"] for e in detail["events"] if e["note"] and e["note"].startswith(":replacement")]
    assert notes == [
        f":replacement_given {s['spare']['plate_number']}",
        f":replacement_returned {s['spare']['plate_number']}",
    ]
    spare_readings = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": s["spare"]["id"]}).json()
    assert max(x["effective_km"] for x in spare_readings) == 5_090

    # both ways: the request from each custody
    for custody in (given, detail["custody"]):
        rows = admin_client.get(f"{M}/requests", params={"custody_id": custody["id"]}).json()
        assert [x["id"] for x in rows] == [rid]


def test_the_office_takes_the_replacement_back_before_it_records_a_pickup(admin_client, client, s):
    rid = sent(client, s)
    receive(s, rid)
    assert give(admin_client, s, rid).status_code == 200
    return_to_office(admin_client, s, km=20_150)  # the office takes his own car back while it is at the center
    portal = s["portal"]
    body = {"number": "INV-9", "total": "40.000", "file_sha256": upload(portal), "final_odometer_km": 20_160}
    r = portal.post(f"/api/v1/portal/requests/{rid}/ready", json=body | {"final_odometer_photo": upload(portal)})
    assert r.status_code == 200, r.text
    r = admin_client.post(f"{M}/requests/{rid}/picked-up")
    assert r.status_code == 409 and r.json()["code"] == "replacement_open"
    r = admin_client.post(
        f"{M}/requests/{rid}/replacement/return", json={"odometer_km": 5_050, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["replacements"][0]["ended_at"] is not None
    again = {"odometer_km": 5_060, "photo_sha256": upload(admin_client)}
    r = admin_client.post(f"{M}/requests/{rid}/replacement/return", json=again)
    assert r.status_code == 409 and r.json()["code"] == "no_replacement"
    assert admin_client.post(f"{M}/requests/{rid}/picked-up").status_code == 200
    assert custodies(admin_client, s["spare"])[0]["ended_at"] is not None


def test_a_replacement_car_settles_neither_his_change_request_nor_counts_as_its_handover(admin_client, client, s):
    """He asked to change to the spare; the spare given as a replacement while his own is at the center is not the
    change: the request stays open (not done, not closed), and is not reported as handed over."""
    ask = {"requested_plate": s["spare"]["plate_number"], "reason": "المكيف لا يعمل"}
    r = client.post("/api/v1/driver/vehicle-change-requests", headers=s["h"], json=ask)
    assert r.status_code in (200, 201), r.text
    rid = sent(client, s)
    receive(s, rid)
    assert give(admin_client, s, rid).status_code == 200
    [row] = admin_client.get("/api/v1/vehicle-change-requests", params={"status": "all"}).json()
    assert row["status"] == "pending" and row["handed_over_at"] is None
    mine = client.get("/api/v1/driver/vehicle", headers=s["h"]).json()
    assert mine["change_request"]["status"] == "pending"
    assert mine["vehicle"]["plate_number"] == s["vehicle"]["plate_number"]
