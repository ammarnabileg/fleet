"""A driver without a car registers one from the app: the plate, his odometer reading and its camera photo. It waits
for the office (the client's decision); approved, his custody starts from the claim's reading and time."""

import uuid
from datetime import timedelta

from app.core.clock import utcnow
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload

CLAIM = "/api/v1/driver/vehicle-claims"
V = "/api/v1/vehicle-claims"


def camera(client, h) -> str:
    r = client.post("/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def told(client, h) -> list[str]:
    return [n["kind"] for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"]]


def on_phone(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    return d, bearer(bind_device(client, d["phone"]))


def ask(client, h, plate, km=10_020, **extra):
    body = {
        "plate": plate,
        "odometer_km": km,
        "photo_sha256": camera(client, h),
        "recorded_at": (utcnow() - timedelta(minutes=5)).isoformat(),
        "client_ref": str(uuid.uuid4()),
        **extra,
    }
    return client.post(CLAIM, headers=h, json=body), body


def test_a_claim_waits_then_is_approved_with_its_reading_and_time(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"], plate_number="44-12345", km=10_000)
    d, h = on_phone(admin_client, client, company)
    side = camera(client, h)
    r, body = ask(client, h, "٤٤–١٢٣٤٥", photos=[side])
    assert r.status_code == 201, r.text
    claim = r.json()["claim"]
    assert (claim["status"], claim["plate"], claim["odometer_km"]) == ("pending", "44-12345", 10_020)
    assert r.json()["vehicle"] is None
    # sent again (the outbox retrying): recognised, not a second claim
    again = client.post(CLAIM, headers=h, json=body)
    assert again.status_code == 409 and again.json()["code"] == "vehicle_claim_exists"
    other, _ = ask(client, h, "44-12345")
    assert other.status_code == 409 and other.json()["code"] == "vehicle_claim_exists"  # one waiting at a time
    # no custody yet: he cannot start his day
    assert client.get("/api/v1/driver/today", headers=h).json()["custody"] is None
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["status"] == "available"

    (alert,) = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "vehicle_claim_requested"]
    assert "44-12345" in alert["message"] and "10020" in alert["message"].replace(",", "")
    assert alert["entity_type"] == "vehicle" and alert["entity_id"] == v["id"]
    (row,) = admin_client.get(V).json()
    assert row["driver"]["id"] == d["id"] and row["vehicle_id"] == v["id"] and row["vehicle_last_km"] == 10_000
    assert row["photos"] == [{"position": "other", "sha256": side}]
    assert admin_client.get(f"{V}/{row['id']}/photo").status_code == 200
    assert admin_client.get(f"{V}/{row['id']}/photos/{side}").status_code == 200
    assert admin_client.get(f"{V}/{row['id']}/photos/{'0' * 64}").status_code == 404

    r = admin_client.post(f"{V}/{row['id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["custody_id"]
    c = admin_client.get(f"/api/v1/custodies/{r.json()['custody_id']}").json()
    assert c["driver"]["id"] == d["id"] and c["started_at"][:19] == body["recorded_at"][:19]
    assert [(x["kind"], x["value_km"], x["source"]) for x in c["readings"]] == [("handover", 10_020, "device")]
    assert c["photos"] == [{"stage": "handover", "position": "other", "sha256": side}]
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["status"] == "assigned"
    assert [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "vehicle_claim_requested"] == []
    assert told(client, h)[0] == "vehicle_claim_approved"
    mine = client.get("/api/v1/driver/vehicle", headers=h).json()
    assert mine["vehicle"]["plate_number"] == "44-12345"
    assert client.get("/api/v1/driver/today", headers=h).json()["custody"]["plate_number"] == "44-12345"
    again = admin_client.post(f"{V}/{row['id']}/approve", json={})
    assert again.status_code == 409 and again.json()["code"] == "vehicle_claim_decided"
    assert admin_client.get(V).json() == []
    assert [x["status"] for x in admin_client.get(V, params={"status": "all"}).json()] == ["approved"]


def test_the_refusals_when_registering(admin_client, client, companies):
    a, b = companies["a"], companies["b"]
    free = make_vehicle(admin_client, a["id"], plate_number="51-100")
    held = make_vehicle(admin_client, a["id"], plate_number="51-200")
    broken = make_vehicle(admin_client, a["id"], plate_number="51-300", status="maintenance")
    make_vehicle(admin_client, b["id"], plate_number="51-400")
    hand_over(admin_client, held, make_driver(admin_client, a["id"]))
    d, h = on_phone(admin_client, client, a)

    def code(r):
        return (r.status_code, r.json()["code"])

    assert code(ask(client, h, "51-999")[0]) == (422, "vehicle_plate_not_found")
    assert code(ask(client, h, "51-400")[0]) == (422, "vehicle_plate_not_found")  # another company's
    assert code(ask(client, h, "51-200")[0]) == (409, "vehicle_held_by_other")
    assert code(ask(client, h, "51-300")[0]) == (409, "vehicle_not_available")
    # the photo: from this phone's camera only
    r, _ = ask(client, h, "51-100", photo_sha256=upload(admin_client))
    assert code(r) == (422, "photo_not_from_camera")
    _, h2 = on_phone(admin_client, client, a)
    r, _ = ask(client, h, "51-100", photo_sha256=camera(client, h2))
    assert code(r) == (422, "photo_not_from_camera")
    r, _ = ask(client, h, "51-100", photos=[upload(admin_client)])
    assert code(r) == (422, "photo_not_from_camera")
    r, _ = ask(client, h, "51-100", recorded_at=(utcnow() - timedelta(days=3)).isoformat())
    assert code(r) == (422, "invalid_recorded_at")
    assert client.post(CLAIM, headers=h, json={"plate": "51-100"}).status_code == 422
    assert admin_client.get(V, params={"status": "all"}).json() == []
    # he holds a car already
    hand_over(admin_client, free, d)
    other = make_vehicle(admin_client, a["id"], plate_number="51-500")
    assert code(ask(client, h, other["plate_number"])[0]) == (409, "driver_has_custody")
    assert broken["status"] == "maintenance"


def test_approval_after_the_car_was_taken_stays_pending_and_a_refusal_needs_a_reason(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"], plate_number="61-100")
    d, h = on_phone(admin_client, client, company)
    r, _ = ask(client, h, "61-100")
    assert r.status_code == 201, r.text
    (row,) = admin_client.get(V).json()
    hand_over(admin_client, v, make_driver(admin_client, company["id"]))  # the office gave it to someone else
    assert admin_client.get(V).json()[0]["holder"] is not None
    r = admin_client.post(f"{V}/{row['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_has_custody"
    assert admin_client.get(V).json()[0]["status"] == "pending"
    assert client.get("/api/v1/driver/vehicle", headers=h).json()["claim"]["status"] == "pending"

    r = admin_client.post(f"{V}/{row['id']}/reject", json={})
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    r = admin_client.post(f"{V}/{row['id']}/reject", json={"note": "العربية اتسلمت لسواق تاني"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "vehicle_claim_requested"] == []
    assert told(client, h)[0] == "vehicle_claim_rejected"
    notice = client.get("/api/v1/driver/notifications", headers=h).json()["items"][0]["message"]
    assert "العربية اتسلمت لسواق تاني" in notice and "61-100" in notice
    mine = client.get("/api/v1/driver/vehicle", headers=h).json()
    assert (mine["claim"]["status"], mine["claim"]["note"]) == ("rejected", "العربية اتسلمت لسواق تاني")
    # he may register a car again
    make_vehicle(admin_client, company["id"], plate_number="61-200")
    assert ask(client, h, "61-200")[0].status_code == 201
    assert d["id"]


def test_permissions_and_company_scope(admin_client, client, new_client, companies):
    a, b = companies["a"], companies["b"]
    make_vehicle(admin_client, b["id"], plate_number="71-100")
    _, h = on_phone(admin_client, client, b)
    r, _ = ask(client, h, "71-100")
    assert r.status_code == 201, r.text
    (row,) = admin_client.get(V).json()
    make_user(admin_client, "claims_a", permissions=["custody.view", "custody.assign"], company_ids=[a["id"]])
    make_user(admin_client, "claims_view", permissions=["custody.view"])
    sup = new_client()
    login(sup, "claims_a")
    assert sup.get(V).json() == []
    assert sup.post(f"{V}/{row['id']}/approve", json={}).status_code == 404
    assert sup.get(f"{V}/{row['id']}/photo").status_code == 404
    assert sup.get("/api/v1/alerts").json() == []
    viewer = new_client()
    login(viewer, "claims_view")
    assert len(viewer.get(V).json()) == 1
    assert viewer.post(f"{V}/{row['id']}/approve", json={}).status_code == 403
    assert viewer.post(f"{V}/{row['id']}/reject", json={"note": "مش متاحة"}).status_code == 403
    assert admin_client.get(V, params={"status": "nope"}).status_code == 422
