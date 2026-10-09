"""M3: maintenance requests, centers and their portal, quotes and invoices (BRD 5.9, 5.10, UAT-20..23)."""

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.core.clock import today
from tests.conftest import (
    PASSWORD,
    bearer,
    bind_device,
    hand_over,
    jpeg,
    login,
    make_driver,
    make_user,
    make_vehicle,
    upload,
)

M = "/api/v1/maintenance"
P = "/api/v1/portal"


def camera(client, h) -> str:
    r = client.post("/api/v1/driver/files", headers=h, files={"file": ("p.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def center(admin_client, name="Al Noor Garage") -> dict:
    r = admin_client.post(f"{M}/centers", json={"name": name, "specialty": "mechanical", "phone": "+96522220000"})
    assert r.status_code == 201, r.text
    return r.json()


def portal_client(admin_client, new_client, c, username) -> object:
    r = admin_client.post(
        f"{M}/centers/{c['id']}/users",
        json={"username": username, "full_name": f"{username} user", "password": PASSWORD},
    )
    assert r.status_code == 201, r.text
    client = new_client()
    login(client, username)
    return client


@pytest.fixture
def setup(admin_client, client, new_client, company):
    return make_setup(admin_client, client, new_client, company)


def make_setup(admin_client, client, new_client, company) -> dict:
    """A driver holding a vehicle, with the app; a center with one portal account."""
    vehicle = make_vehicle(admin_client, company["id"], km=20_000)
    driver = make_driver(admin_client, company["id"])
    hand_over(admin_client, vehicle, driver, km=20_000)
    h = bearer(bind_device(client, driver["phone"]))
    c = center(admin_client)
    portal = portal_client(admin_client, new_client, c, "noor1")
    return {"vehicle": vehicle, "driver": driver, "h": h, "center": c, "portal": portal}


def driver_request(client, s, **extra):
    body = {
        "client_ref": str(uuid.uuid4()),
        "kind": "mechanical",
        "description": "Noise from the front wheel",
        "odometer_km": 20_100,
        "photos": [camera(client, s["h"])],
    } | extra
    return client.post("/api/v1/driver/maintenance", json=body, headers=s["h"])


def approved_and_referred(admin_client, client, s) -> str:
    r = driver_request(client, s)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert admin_client.post(f"{M}/requests/{rid}/approve", json={}).status_code == 200
    r = admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": s["center"]["id"]})
    assert r.status_code == 200, r.text
    return rid


def receive(s, rid, km=20_150):
    portal = s["portal"]
    body = {"odometer_km": km, "odometer_photo": upload(portal), "condition_note": "scratch rear left"}
    return portal.post(f"{P}/requests/{rid}/receive", json=body | {"photos": [upload(portal)]})


def quote(s, rid, amount, items=None):
    items = items or [{"kind": "part", "description": "Wheel bearing", "quantity": "1", "unit_price": amount}]
    return s["portal"].post(f"{P}/requests/{rid}/quote", json={"amount": amount, "items": items})


def complete(s, rid, km=20_160):
    portal = s["portal"]
    body = {"repair_details": "Bearing replaced", "final_odometer_km": km, "final_odometer_photo": upload(portal)}
    return portal.post(f"{P}/requests/{rid}/complete", json=body)


def invoice(s, rid, *, number="INV-100", total="45.000", **extra):
    portal = s["portal"]
    body = {
        "request_id": rid,
        "number": number,
        "invoice_date": str(today()),
        "total": total,
        "file_sha256": upload(portal, b"%PDF-1.4 " + uuid.uuid4().bytes, name="inv.pdf"),
        "items": [
            {"kind": "part", "description": "Wheel bearing", "quantity": "1", "unit_price": "30.000"},
            {"kind": "labour", "description": "Labour", "unit_price": str(D(total or "45.000") - D("30.000"))},
        ],
    } | extra
    return portal.post(f"{P}/invoices", json=body)


def statuses(detail):
    return [e["status"] for e in detail["events"]]


def test_uat20_the_whole_cycle_from_the_driver_to_a_closed_request(admin_client, client, setup, db):
    s = setup
    rid = approved_and_referred(admin_client, client, s)

    # the center sees it as new, with the vehicle but not the driver
    listed = s["portal"].get(f"{P}/requests").json()
    assert [(x["id"], x["is_new"], x["driver"]) for x in listed] == [(rid, True, None)]
    assert listed[0]["vehicle"]["plate_number"] == s["vehicle"]["plate_number"]
    assert s["portal"].get(f"{P}/requests/{rid}").status_code == 200
    assert s["portal"].get(f"{P}/requests").json()[0]["is_new"] is False

    # reception: the custody ends at the center with its reading; tracking stops; the vehicle is in maintenance
    r = receive(s, rid)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received" and r.json()["received_km"] == 20_150
    vehicle = admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()
    assert vehicle["status"] == "maintenance"
    custodies = admin_client.get("/api/v1/custodies", params={"vehicle_id": s["vehicle"]["id"]}).json()
    assert custodies[0]["ended_at"] is not None
    assert client.get("/api/v1/driver/today", headers=s["h"]).json().get("custody") is None

    # within the approval limit (100.000) the quote is approved at once and the repair starts
    r = quote(s, rid, "45.000")
    assert r.json()["status"] == "in_repair" and r.json()["quotes"][0]["auto_approved"] is True
    assert s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "waiting_parts"}).status_code == 200
    assert s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "in_repair"}).status_code == 200
    r = complete(s, rid)
    assert r.status_code == 200, r.text
    r = s["portal"].post(f"{P}/requests/{rid}/ready", json={"note": "Come any time before 9 pm"})
    assert r.json()["status"] == "ready"

    # the office is alerted, the driver sees it in the app with the center's address
    alerts = admin_client.get("/api/v1/alerts").json()
    assert any(a["kind"] == "maintenance_ready" for a in alerts)
    mine = client.get("/api/v1/driver/maintenance", headers=s["h"]).json()
    assert mine[0]["status"] == "ready" and mine[0]["center"]["name"] == "Al Noor Garage"

    # picked up: available again; closed only once the invoice is approved (settings default)
    r = admin_client.post(f"{M}/requests/{rid}/picked-up")
    assert r.json()["status"] == "picked_up"
    assert admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"] == "available"
    inv = invoice(s, rid)
    assert inv.status_code == 201, inv.text
    assert inv.json()["flags"] == []
    r = admin_client.post(f"{M}/invoices/{inv.json()['id']}/approve")
    assert r.json()["status"] == "approved"
    detail = admin_client.get(f"{M}/requests/{rid}").json()
    assert detail["status"] == "closed"
    assert statuses(detail) == [
        "requested",
        "approved",
        "referred",
        "received",
        "in_repair",
        "waiting_parts",
        "in_repair",
        "completed",
        "ready",
        "picked_up",
        "closed",
    ]
    # time at the center and in each status (FR-MNT-09)
    assert detail["stay_seconds"] is not None and detail["stay_seconds"] >= 0
    assert [d["status"] for d in detail["durations"]][:2] == ["received", "in_repair"]
    # the center's readings are in the vehicle's chain
    kinds = (
        db.execute(
            text(
                "SELECT kind FROM fleet.odometer_readings r JOIN fleet.vehicles v ON v.id = r.vehicle_id "
                "WHERE v.public_id = :v ORDER BY recorded_at"
            ),
            {"v": s["vehicle"]["id"]},
        )
        .scalars()
        .all()
    )
    assert kinds == ["handover", "return", "maintenance_out"]
    # finance pays the center
    r = admin_client.post(f"{M}/invoices/{inv.json()['id']}/paid", json={"payment_ref": "TRX-9"})
    assert r.json()["payment_status"] == "paid"


def test_the_next_handover_compares_with_the_reading_after_the_repair(admin_client, client, setup):
    """A test drive at the center is not distance off duty (BR-07)."""
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid, km=20_150)
    quote(s, rid, "20.000")
    complete(s, rid, km=20_190)  # 40 km of test drives
    s["portal"].post(f"{P}/requests/{rid}/ready", json={})
    s["portal"].post(f"{P}/requests/{rid}/picked-up")
    driver = make_driver(admin_client, s["vehicle"]["company_id"])
    hand_over(admin_client, s["vehicle"], driver, km=20_191)
    readings = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": s["vehicle"]["id"]}).json()
    handover = next(r for r in readings if r["kind"] == "handover" and r["value_km"] == 20_191)
    assert handover["flags"] == []


def test_photos_come_in_the_order_they_were_taken(admin_client, client, setup, db):
    """The driver's, then the reception's, then after the repair: not by their hash. On a large table the database
    reads them through the primary key (request, hash), which is to say in a random order; the photos are chosen so
    that their hashes sort the other way round, and the read is made the way a large table is read."""
    from hashlib import sha256

    def photo(rank):  # rank 0: the highest hash of 50 candidates, rank 1: middling, rank 2: the lowest
        options = sorted((jpeg() for _ in range(50)), key=lambda b: sha256(b).hexdigest(), reverse=True)
        return options[[0, 25, 49][rank]]

    s = setup
    up = lambda c, data, path: c.post(path, files={"file": ("p.jpg", data, "image/jpeg")}).json()["sha256"]  # noqa: E731
    shot = client.post(
        "/api/v1/driver/files", headers=s["h"], files={"file": ("p.jpg", photo(0), "image/jpeg")}
    ).json()["sha256"]
    r = driver_request(client, s, photos=[shot])
    rid = r.json()["id"]
    assert admin_client.post(f"{M}/requests/{rid}/approve", json={}).status_code == 200
    assert admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": s["center"]["id"]}).status_code == 200
    portal = s["portal"]
    body = {"odometer_km": 20_150, "odometer_photo": up(portal, photo(1), "/api/v1/files")}
    assert portal.post(f"{P}/requests/{rid}/receive", json=body).status_code == 200
    quote(s, rid, "20.000")
    body = {"repair_details": "Bearing replaced", "final_odometer_km": 20_160, "final_odometer_photo": None}
    body["final_odometer_photo"] = up(portal, photo(2), "/api/v1/files")
    assert portal.post(f"{P}/requests/{rid}/complete", json=body).status_code == 200
    stages = [p["stage"] for p in admin_client.get(f"{M}/requests/{rid}").json()["photos"]]
    assert stages == ["request", "reception", "repair"]
    from app.modules.maintenance import service

    db.execute(text("SET LOCAL enable_seqscan = off"))  # as on a table with many requests: through the index
    db.execute(text("SET LOCAL enable_bitmapscan = off"))
    detail = service.get_request(db, uuid.UUID(rid), all_companies=True, company_ids=())
    assert [p["stage"] for p in detail["photos"]] == ["request", "reception", "repair"]


def test_uat21_a_center_sees_only_what_was_referred_to_it(admin_client, client, new_client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    other = portal_client(admin_client, new_client, center(admin_client, "Other Garage"), "other1")
    assert other.get(f"{P}/requests").json() == []
    assert other.get(f"{P}/requests/{rid}").status_code == 404
    body = {"odometer_km": 20_150, "odometer_photo": upload(other)}
    assert other.post(f"{P}/requests/{rid}/receive", json=body).status_code == 404
    photo = admin_client.get(f"{M}/requests/{rid}").json()["photos"][0]["sha256"]
    assert other.get(f"{P}/requests/{rid}/files/{photo}").status_code == 404
    assert s["portal"].get(f"{P}/requests/{rid}/files/{photo}").status_code == 200
    # nothing outside the portal either
    assert other.get(f"{M}/requests").status_code == 403
    assert other.get("/api/v1/vehicles").status_code == 403
    assert other.get("/api/v1/employees").status_code == 403
    # a disabled account loses access at once
    users = admin_client.get(f"{M}/centers/{s['center']['id']}/users").json()
    r = admin_client.put(f"{M}/centers/{s['center']['id']}/users/{users[0]['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()[0]["is_active"] is False
    assert s["portal"].get(f"{P}/requests").status_code == 401


def test_uat22_an_invoice_needs_its_file_number_and_total(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    quote(s, rid, "45.000")
    complete(s, rid)
    for missing, code in (
        ("file_sha256", "invoice_file_required"),
        ("number", "invoice_number_required"),
        ("total", "invoice_total_required"),
    ):
        r = invoice(s, rid, **{missing: None})
        assert r.status_code == 422 and r.json()["code"] == code, (missing, r.text)
    r = invoice(s, rid, total="50.000", items=[{"kind": "part", "description": "x", "unit_price": "45.000"}])
    assert r.json()["code"] == "invoice_items_mismatch"
    assert invoice(s, rid, invoice_date=str(today() + timedelta(days=1))).json()["code"] == "invoice_date_in_future"
    assert invoice(s, rid).status_code == 201


def test_uat23_a_repeated_invoice_number_is_accepted_flagged_and_alerted(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    quote(s, rid, "45.000")
    complete(s, rid)
    first = invoice(s, rid, number="A-77")
    second = invoice(s, rid, number="a-77")  # same number, other case
    assert first.json()["flags"] == [] and second.json()["flags"] == ["duplicate_number"]
    kinds = [a["kind"] for a in admin_client.get("/api/v1/alerts").json()]
    assert "maintenance_invoice_duplicate" in kinds
    # once rejected, the number is free again
    admin_client.post(f"{M}/invoices/{second.json()['id']}/reject", json={"reason": "Entered twice"})
    admin_client.post(f"{M}/invoices/{first.json()['id']}/reject", json={"reason": "Wrong total"})
    assert invoice(s, rid, number="A-77").json()["flags"] == []


def test_above_the_limit_the_repair_waits_for_the_manager(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    assert s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "inspection"}).status_code == 200
    r = quote(s, rid, "250.000")
    assert r.json()["status"] == "quote_pending"
    assert any(a["kind"] == "maintenance_quote_pending" for a in admin_client.get("/api/v1/alerts").json())
    # the center cannot start on its own, nor send a second quote meanwhile
    r = s["portal"].post(f"{P}/requests/{rid}/status", json={"status": "in_repair"})
    assert r.status_code == 409
    assert quote(s, rid, "240.000").status_code == 409
    qid = admin_client.get(f"{M}/requests/{rid}").json()["quotes"][0]["id"]
    assert admin_client.post(f"{M}/quotes/{qid}/reject", json={}).status_code == 422  # a reason is required
    r = admin_client.post(f"{M}/quotes/{qid}/reject", json={"reason": "Too expensive, use a used part"})
    assert r.json()["status"] == "inspection"
    r = quote(s, rid, "180.000")
    qid = [q for q in r.json()["quotes"] if q["status"] == "pending"][0]["id"]
    r = admin_client.post(f"{M}/quotes/{qid}/approve")
    assert r.json()["status"] == "in_repair"
    assert admin_client.post(f"{M}/quotes/{qid}/approve").status_code == 409
    # an invoice different from the approved quote is flagged (FR-INV-04)
    complete(s, rid)
    inv = invoice(s, rid, total="195.000")
    assert inv.json()["flags"] == ["differs_from_quote"] and inv.json()["quote_amount"] == "180.000"


def test_the_quote_items_must_add_up(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    items = [{"kind": "part", "description": "Pads", "quantity": "2", "unit_price": "10.000"}]
    r = quote(s, rid, "25.000", items=items)
    assert r.status_code == 422 and r.json()["code"] == "quote_items_mismatch"


def test_approval_rejection_and_cancel_rules(admin_client, client, setup):
    s = setup
    rid = driver_request(client, s).json()["id"]
    assert any(a["kind"] == "maintenance_requested" for a in admin_client.get("/api/v1/alerts").json())
    # not referable before approval, rejection needs a reason, a decision is made once
    r = admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": s["center"]["id"]})
    assert r.status_code == 409
    assert admin_client.post(f"{M}/requests/{rid}/reject", json={"reason": ""}).status_code == 422
    r = admin_client.post(f"{M}/requests/{rid}/reject", json={"reason": "Already fixed last week"})
    assert r.json()["status"] == "rejected"
    assert admin_client.post(f"{M}/requests/{rid}/approve", json={}).status_code == 409
    mine = client.get("/api/v1/driver/maintenance", headers=s["h"]).json()
    assert mine[0]["status"] == "rejected" and mine[0]["decision_note"] == "Already fixed last week"
    # once at the center it cannot be cancelled
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    assert admin_client.post(f"{M}/requests/{rid}/cancel", json={"reason": "Changed mind"}).status_code == 409


def test_a_vehicle_is_at_one_center_at_a_time(admin_client, client, setup):
    s = setup
    approved_and_referred(admin_client, client, s)
    rid = driver_request(client, s).json()["id"]
    admin_client.post(f"{M}/requests/{rid}/approve", json={})
    r = admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": s["center"]["id"]})
    assert r.status_code == 409 and r.json()["code"] == "vehicle_at_center"


def test_an_emergency_is_repaired_first_and_reviewed_afterwards(admin_client, client, setup):
    s = setup
    body = {"vehicle_id": s["vehicle"]["id"], "kind": "battery", "description": "Will not start", "emergency": True}
    r = admin_client.post(f"{M}/requests", json=body)
    assert r.status_code == 201 and r.json()["status"] == "approved"
    rid = r.json()["id"]
    assert r.json()["driver"]["id"] == s["driver"]["id"]  # the driver holding it
    assert any(a["kind"] == "maintenance_emergency" for a in admin_client.get("/api/v1/alerts").json())
    assert admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": s["center"]["id"]}).status_code == 200
    r = admin_client.post(f"{M}/requests/{rid}/review-emergency", json={"note": "Justified"})
    assert r.json()["emergency_reviewed"] is True
    assert admin_client.post(f"{M}/requests/{rid}/review-emergency", json={}).status_code == 409
    assert not any(a["kind"] == "maintenance_emergency" for a in admin_client.get("/api/v1/alerts").json())


def test_driver_requests_are_safe_to_retry_and_need_a_vehicle(admin_client, client, setup, company):
    s = setup
    ref = str(uuid.uuid4())
    assert driver_request(client, s, client_ref=ref).status_code == 201
    r = driver_request(client, s, client_ref=ref)
    assert r.status_code == 409 and r.json()["code"] == "request_exists"
    # photos from this phone's camera only
    r = driver_request(client, s, photos=[upload(admin_client)])
    assert r.json()["code"] == "file_not_yours"
    walker = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, walker["phone"]))
    r = client.post(
        "/api/v1/driver/maintenance",
        headers=h,
        json={"client_ref": str(uuid.uuid4()), "kind": "other", "description": "x"},
    )
    assert r.status_code == 409 and r.json()["code"] == "no_vehicle_in_custody"


def test_permissions_and_company_scope(admin_client, client, new_client, setup, companies):
    s = setup
    rid = driver_request(client, s).json()["id"]
    make_user(admin_client, "viewer_b", permissions=["maintenance.view"], company_ids=[companies["b"]["id"]])
    make_user(admin_client, "viewer_a", permissions=["maintenance.view"], company_ids=[companies["a"]["id"]])
    b, a = new_client(), new_client()
    login(b, "viewer_b")
    login(a, "viewer_a")
    assert b.get(f"{M}/requests").json() == []
    assert b.get(f"{M}/requests/{rid}").status_code == 404
    assert a.get(f"{M}/requests/{rid}").status_code == 200
    assert a.post(f"{M}/requests/{rid}/approve", json={}).status_code == 403
    assert a.post(f"{M}/centers", json={"name": "Mine"}).status_code == 403


def test_center_accounts_by_the_maintenance_manager_and_the_role_guard(admin_client, new_client, owner_db):
    """The manager does not hold the portal permissions, yet may create center accounts (and only those)."""
    c = center(admin_client)
    r = admin_client.post(
        "/api/v1/users",
        json={
            "username": "maint_mgr",
            "full_name": "Maintenance Manager",
            "password": PASSWORD,
            "role_codes": ["maintenance_manager"],
            "all_companies": True,
            "company_ids": [],
        },
    )
    assert r.status_code == 201, r.text
    manager = new_client()
    login(manager, "maint_mgr")
    body = {"username": "garage1", "full_name": "Garage One", "password": PASSWORD}
    assert manager.post(f"{M}/centers/{c['id']}/users", json=body).status_code == 201
    assert manager.post(f"{M}/centers/{c['id']}/users", json=body).json()["code"] == "username_taken"
    # someone widened the portal role: the exception closes
    owner_db.execute(
        text(
            "INSERT INTO identity.role_permissions (role_id, permission) "
            "SELECT id, 'employees.view' FROM identity.roles WHERE code = 'maintenance_center'"
        )
    )
    owner_db.commit()
    r = manager.post(f"{M}/centers/{c['id']}/users", json=body | {"username": "garage2"})
    assert r.status_code == 409 and r.json()["code"] == "portal_role_changed"


def test_closing_at_pickup_when_the_settings_say_so(admin_client, client, setup):
    s = setup
    current = admin_client.get("/api/v1/settings").json()["maintenance"]
    r = admin_client.put(
        "/api/v1/settings/maintenance",
        json={"version": current["version"], "value": current["value"] | {"close_requires_invoice": False}},
    )
    assert r.status_code == 200, r.text
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    quote(s, rid, "45.000")
    complete(s, rid)
    s["portal"].post(f"{P}/requests/{rid}/ready", json={})
    r = s["portal"].post(f"{P}/requests/{rid}/picked-up")
    assert r.json()["status"] == "closed"


def test_dashboard_counts_and_office_invoice(admin_client, client, setup, company):
    s = setup
    driver_request(client, s)
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    counts = admin_client.get("/api/v1/dashboard").json()["maintenance"]
    assert counts == {"pending_approval": 1, "under_repair": 1, "ready": 0, "referred": 0}
    # the accountant enters an invoice from a center without a request (company given)
    body = {
        "center_id": s["center"]["id"],
        "company_id": company["id"],
        "number": "X-1",
        "invoice_date": str(today()),
        "total": "12.500",
        "file_sha256": upload(admin_client),
        "items": [{"kind": "other", "description": "Towing", "unit_price": "12.500"}],
    }
    r = admin_client.post(f"{M}/invoices", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["request"] is None
    listed = admin_client.get(f"{M}/invoices", params={"status": "pending"}).json()
    assert [i["number"] for i in listed] == ["X-1"]
    assert admin_client.get(f"{M}/invoices/{r.json()['id']}/file").status_code == 200
    # paid only once approved
    assert admin_client.post(f"{M}/invoices/{r.json()['id']}/paid", json={}).status_code == 409


def test_a_quote_exactly_at_the_limit_needs_no_approval(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    assert quote(s, rid, "100.000").json()["status"] == "in_repair"


def test_decisions_and_files_stay_inside_their_company_and_center(admin_client, client, new_client, setup, companies):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    receive(s, rid)
    quote(s, rid, "300.000")
    qid = admin_client.get(f"{M}/requests/{rid}").json()["quotes"][0]["id"]
    perms = ["maintenance.view", "maintenance.approve", "invoices.view", "invoices.approve"]
    make_user(admin_client, "approver_b", permissions=perms, company_ids=[companies["b"]["id"]])
    b = new_client()
    login(b, "approver_b")
    assert b.post(f"{M}/quotes/{qid}/approve").status_code == 404
    assert admin_client.post(f"{M}/quotes/{qid}/approve").status_code == 200
    complete(s, rid)
    inv = invoice(s, rid).json()
    assert b.post(f"{M}/invoices/{inv['id']}/approve").status_code == 404
    assert b.get(f"{M}/invoices").json() == []
    other_center = center(admin_client, "Third Garage")
    other = portal_client(admin_client, new_client, other_center, "third1")
    assert other.get(f"{P}/invoices").json() == []
    assert other.get(f"{P}/invoices/{inv['id']}/file").status_code == 404
    assert s["portal"].get(f"{P}/invoices/{inv['id']}/file").status_code == 200
    # an account of another center cannot be switched off from this center's page
    theirs = admin_client.get(f"{M}/centers/{other_center['id']}/users").json()[0]["id"]
    r = admin_client.put(f"{M}/centers/{s['center']['id']}/users/{theirs}", json={"is_active": False})
    assert r.status_code == 404


def test_status_steps_cannot_be_skipped_or_repeated(admin_client, client, setup):
    s = setup
    rid = approved_and_referred(admin_client, client, s)
    # a center's photos are its own uploads
    body = {"odometer_km": 20_150, "odometer_photo": upload(admin_client)}
    r = s["portal"].post(f"{P}/requests/{rid}/receive", json=body)
    assert r.status_code == 422 and r.json()["code"] == "file_uploaded_by_other_account"
    assert receive(s, rid).status_code == 200
    assert receive(s, rid).status_code == 409  # received once
    quote(s, rid, "20.000")
    assert admin_client.post(f"{M}/requests/{rid}/picked-up").status_code == 409  # not ready yet
    assert s["portal"].post(f"{P}/requests/{rid}/ready", json={}).status_code == 409  # not completed yet
    # a request is decided once, whichever the decision (the driver no longer holds it: the office asks)
    body = {"vehicle_id": s["vehicle"]["id"], "kind": "tyres", "description": "Front tyres worn"}
    other = admin_client.post(f"{M}/requests", json=body).json()["id"]
    assert admin_client.post(f"{M}/requests/{other}/reject", json={"reason": "Duplicate request"}).status_code == 200
    assert admin_client.post(f"{M}/requests/{other}/reject", json={"reason": "Duplicate again"}).status_code == 409


def test_an_inactive_center_gets_no_referrals_and_its_portal_closes(admin_client, client, setup):
    s = setup
    c = s["center"]
    r = admin_client.put(f"{M}/centers/{c['id']}", json={"version": c["version"], "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert s["portal"].get(f"{P}/requests").json()["code"] == "center_inactive"
    rid = driver_request(client, s).json()["id"]
    admin_client.post(f"{M}/requests/{rid}/approve", json={})
    r = admin_client.post(f"{M}/requests/{rid}/refer", json={"center_id": c["id"]})
    assert r.status_code == 409 and r.json()["code"] == "center_inactive"


def test_a_center_account_is_made_from_its_center_and_an_unlinked_one_can_be_linked(admin_client, new_client, owner_db):
    """A portal-only account made from the users page belongs to no center, so the portal refuses it: the users
    page refuses to make one, and the center's page takes over one made before that."""
    c = center(admin_client)
    body = {"full_name": "Garage Desk", "password": PASSWORD, "all_companies": False, "company_ids": []}
    r = admin_client.post("/api/v1/users", json=body | {"username": "desk1", "role_codes": ["maintenance_center"]})
    assert r.status_code == 422 and r.json()["code"] == "portal_account_from_center"
    # an office account can't become one by editing either
    r = admin_client.post("/api/v1/users", json=body | {"username": "desk2", "role_codes": ["maintenance_manager"]})
    assert r.status_code == 201, r.text
    u = r.json()
    r = admin_client.patch(
        f"/api/v1/users/{u['public_id']}", json={"version": u["version"], "role_codes": ["maintenance_center"]}
    )
    assert r.status_code == 422 and r.json()["code"] == "portal_account_from_center"
    # one made before the rule: portal role only, linked nowhere
    owner_db.execute(
        text(
            "UPDATE identity.user_roles SET role_id = (SELECT id FROM identity.roles WHERE code = 'maintenance_center')"
            " WHERE user_id = (SELECT id FROM identity.users WHERE username = 'desk2')"
        )
    )
    owner_db.commit()
    orphan = new_client()
    login(orphan, "desk2")
    assert orphan.get(f"{P}/me").json()["code"] == "not_a_center_account"
    link = f"{M}/centers/{c['id']}/users/link"
    assert admin_client.post(link, json={"username": "nobody"}).json()["code"] == "user_not_found"
    assert admin_client.post(link, json={"username": "admin"}).json()["code"] == "not_a_portal_account"
    r = admin_client.post(link, json={"username": "DESK2"})
    assert r.status_code == 200 and [x["username"] for x in r.json()] == ["desk2"]
    assert orphan.get(f"{P}/me").json()["name"] == c["name"]
    assert admin_client.post(link, json={"username": "desk2"}).json()["code"] == "center_user_linked"
