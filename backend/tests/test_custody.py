"""Vehicles owned by a company; UAT-11: custody never overlaps; UAT-12: who had the vehicle at time T;
UAT-18 (fleet part): ending service while holding a vehicle alerts."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import bind_device, hand_over, login, make_driver, make_user, make_vehicle, upload


def now():
    return datetime.now(UTC)


def test_plate_is_unique_ignoring_spaces_and_case(admin_client, company):
    make_vehicle(admin_client, company["id"], plate_number="12 ab 345")
    r = admin_client.post("/api/v1/vehicles", json={"plate_number": "12AB345", "company_id": company["id"]})
    assert r.status_code == 409 and r.json()["code"] == "plate_taken"


def test_handover_and_return(admin_client, company, db):
    v = make_vehicle(admin_client, company["id"], km=50_000)
    d = make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, d, km=50_010)
    vehicle = admin_client.get(f"/api/v1/vehicles/{v['id']}").json()
    assert vehicle["status"] == "assigned" and vehicle["last_odometer_km"] == 50_010
    assert vehicle["custody"]["driver"]["id"] == d["id"]
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return", json={"odometer_km": 50_200, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200 and r.json()["ended_at"]
    vehicle = admin_client.get(f"/api/v1/vehicles/{v['id']}").json()
    assert vehicle["status"] == "available" and vehicle["last_odometer_km"] == 50_200 and vehicle["custody"] is None
    detail = admin_client.get(f"/api/v1/custodies/{c['id']}").json()
    assert [(x["kind"], x["value_km"]) for x in detail["readings"]] == [("handover", 50_010), ("return", 50_200)]
    again = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return", json={"odometer_km": 50_300, "photo_sha256": upload(admin_client)}
    )
    assert again.status_code == 409 and again.json()["code"] == "custody_closed"
    events = [e for (e,) in db.execute(text("SELECT event_type FROM integrations.outbox ORDER BY id"))]
    assert events.count("custody.started") == 1 and events.count("custody.ended") == 1


def test_uat11_custody_never_overlaps(admin_client, company):
    v1, v2 = make_vehicle(admin_client, company["id"]), make_vehicle(admin_client, company["id"])
    d1, d2 = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    hand_over(admin_client, v1, d1)
    body = {"odometer_km": 10_000, "photo_sha256": upload(admin_client)}
    r = admin_client.post("/api/v1/custodies", json=body | {"vehicle_id": v1["id"], "driver_id": d2["id"]})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_has_custody"
    r = admin_client.post("/api/v1/custodies", json=body | {"vehicle_id": v2["id"], "driver_id": d1["id"]})
    assert r.status_code == 409 and r.json()["code"] == "driver_has_custody"
    # backdated: an open period that starts earlier still overlaps
    r = admin_client.post(
        "/api/v1/custodies",
        json=body
        | {"vehicle_id": v1["id"], "driver_id": d2["id"], "started_at": (now() - timedelta(days=2)).isoformat()},
    )
    assert r.status_code == 409


def test_the_database_itself_refuses_overlaps(admin_client, company, db):
    v = make_vehicle(admin_client, company["id"])
    d1, d2 = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    hand_over(admin_client, v, d1)
    vid, did = db.execute(
        text("SELECT v.id, e.id FROM fleet.vehicles v, people.employees e WHERE v.public_id = :v AND e.public_id = :d"),
        {"v": v["id"], "d": d2["id"]},
    ).one()
    with pytest.raises(IntegrityError, match="custodies_vehicle_overlap"):
        db.execute(
            text(
                "INSERT INTO fleet.custodies (vehicle_id, driver_id, company_id, started_at, handed_over_by) "
                "VALUES (:v, :d, 1, now() - interval '1 hour', 1)"
            ),
            {"v": vid, "d": did},
        )


def test_uat12_who_had_the_vehicle_at_time_t(admin_client, company):
    v = make_vehicle(admin_client, company["id"])
    d1, d2 = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    t0 = now() - timedelta(days=3)
    c1 = hand_over(admin_client, v, d1, started_at=t0.isoformat())
    admin_client.post(
        f"/api/v1/custodies/{c1['id']}/return",
        json={
            "odometer_km": 10_100,
            "photo_sha256": upload(admin_client),
            "ended_at": (t0 + timedelta(days=1)).isoformat(),
        },
    )
    hand_over(admin_client, v, d2, km=10_100, started_at=(t0 + timedelta(days=2)).isoformat())

    def at(t):
        return admin_client.get(f"/api/v1/vehicles/{v['id']}/custody-at", params={"at": t.isoformat()})

    assert at(t0 + timedelta(hours=5)).json()["driver"]["id"] == d1["id"]
    assert at(t0 + timedelta(days=1)).status_code == 404  # returned at exactly that moment
    assert at(t0 + timedelta(days=1, hours=12)).json()["code"] == "no_custody_at_time"
    assert at(now()).json()["driver"]["id"] == d2["id"]


def test_handover_checks_the_driver_and_the_vehicle(admin_client, company):
    from app.core.clock import today

    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "employee",
            "owner_id": d["id"],
            "type_code": "driving_license",
            "expiry_date": str(today() - timedelta(days=1)),
        },
    )
    body = {"vehicle_id": v["id"], "driver_id": d["id"], "odometer_km": 10_000, "photo_sha256": upload(admin_client)}
    r = admin_client.post("/api/v1/custodies", json=body)
    assert r.status_code == 422 and r.json()["code"] == "driving_license_expired"
    clerk = make_driver(admin_client, company["id"], app=False)
    admin_client.post(f"/api/v1/employees/{clerk['id']}/status", json={"status_code": "on_leave"})
    r = admin_client.post("/api/v1/custodies", json=body | {"driver_id": clerk["id"]})
    assert r.status_code == 422 and r.json()["code"] == "driver_not_working"
    admin_client.patch(f"/api/v1/vehicles/{v['id']}", json={"version": v["version"], "status": "maintenance"})
    other = make_driver(admin_client, company["id"])
    r = admin_client.post("/api/v1/custodies", json=body | {"driver_id": other["id"]})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_not_available"
    r = admin_client.post("/api/v1/custodies", json=body | {"started_at": (now() + timedelta(hours=1)).isoformat()})
    assert r.json()["code"] == "time_in_future"
    clean = {"vehicle_id": make_vehicle(admin_client, company["id"])["id"], "driver_id": other["id"]}
    r = admin_client.post("/api/v1/custodies", json=body | clean | {"photo_sha256": upload(admin_client, b"%PDF-1.4")})
    assert r.status_code == 422 and r.json()["code"] == "photo_must_be_image"
    assert (
        admin_client.post("/api/v1/custodies", json=body | clean | {"photo_sha256": upload(admin_client)}).status_code
        == 201
    )


def test_emergency_handover_needs_permission_reason_and_review(admin_client, new_client, company):
    from app.core.clock import today

    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    admin_client.post(
        "/api/v1/documents",
        json={
            "owner_type": "employee",
            "owner_id": d["id"],
            "type_code": "driving_license",
            "expiry_date": str(today() - timedelta(days=1)),
        },
    )
    make_user(
        admin_client, "night_sup", permissions=["custody.assign", "custody.view", "vehicles.view", "employees.view"]
    )
    c = new_client()
    login(c, "night_sup")
    body = {
        "vehicle_id": v["id"],
        "driver_id": d["id"],
        "odometer_km": 10_000,
        "photo_sha256": upload(c),
        "kind": "emergency",
        "reason": "night shift, licence renewal in progress",
    }
    r = c.post("/api/v1/custodies", json=body)
    assert r.status_code == 403 and r.json()["params"]["permission"] == "custody.emergency"
    r = admin_client.post("/api/v1/custodies", json=body | {"reason": None})
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    r = admin_client.post("/api/v1/custodies", json=body)
    assert r.status_code == 201 and r.json()["needs_review"] and r.json()["kind"] == "emergency"
    alerts = admin_client.get("/api/v1/alerts").json()
    assert [a["kind"] for a in alerts] == ["emergency_custody"]
    assert c.get("/api/v1/alerts").json()[0]["kind"] == "emergency_custody"  # custody.assign holders see it
    pending = admin_client.get("/api/v1/custodies", params={"needs_review": True}).json()
    assert [x["id"] for x in pending] == [r.json()["id"]]
    reviewed = admin_client.post(f"/api/v1/custodies/{r.json()['id']}/review", json={"note": "checked licence"})
    assert reviewed.status_code == 200 and not reviewed.json()["needs_review"]


def test_a_vehicle_in_custody_keeps_its_status_and_company(admin_client, companies):
    a, b = companies["a"], companies["b"]
    v = make_vehicle(admin_client, a["id"])
    hand_over(admin_client, v, make_driver(admin_client, a["id"]))
    v = admin_client.get(f"/api/v1/vehicles/{v['id']}").json()
    for change in ({"status": "maintenance"}, {"company_id": b["id"]}):
        r = admin_client.patch(f"/api/v1/vehicles/{v['id']}", json={"version": v["version"], **change})
        assert r.status_code == 409 and r.json()["code"] == "vehicle_in_custody"
    r = admin_client.patch(f"/api/v1/vehicles/{v['id']}", json={"version": v["version"], "color": "white"})
    assert r.status_code == 200


def test_uat18_ending_service_with_a_vehicle_alerts_and_cuts_the_app(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    hand_over(admin_client, v, d)
    tokens = bind_device(client, d["phone"])
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/api/v1/driver/today", headers=headers).status_code == 200
    admin_client.post(f"/api/v1/employees/{d['id']}/status", json={"status_code": "terminated"})
    assert client.get("/api/v1/driver/today", headers=headers).status_code == 401  # device revoked
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
    assert [a["kind"] for a in alerts] == ["driver_left_with_vehicle"]
    assert v["plate_number"] in alerts[0]["message"]
    devices = admin_client.get(f"/api/v1/employees/{d['id']}/devices").json()
    assert devices[0]["revoked_reason"] == "employment_ended"


def test_vehicles_and_custody_are_company_scoped(admin_client, new_client, companies):
    a, b = companies["a"], companies["b"]
    vb = make_vehicle(admin_client, b["id"])
    cb = hand_over(admin_client, vb, make_driver(admin_client, b["id"]))
    make_user(
        admin_client, "fleet_a", permissions=["vehicles.view", "custody.view", "custody.assign"], company_ids=[a["id"]]
    )
    c = new_client()
    login(c, "fleet_a")
    assert c.get(f"/api/v1/vehicles/{vb['id']}").status_code == 404
    assert c.get(f"/api/v1/custodies/{cb['id']}").status_code == 404
    assert c.get("/api/v1/vehicles").json() == [] and c.get("/api/v1/custodies").json() == []
    r = c.post(f"/api/v1/custodies/{cb['id']}/return", json={"odometer_km": 1, "photo_sha256": upload(c)})
    assert r.status_code == 404
    r = c.post("/api/v1/vehicles", json={"plate_number": "999", "company_id": b["id"]})
    assert r.status_code == 403
