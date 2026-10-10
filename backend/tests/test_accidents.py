"""M3: accidents (BRD 5.11, UAT-24..26) and the deductions payroll will apply (BRD 5.14, first part)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.payroll.service import add_months, schedule
from tests.conftest import (
    bearer,
    bind_device,
    hand_over,
    make_driver,
    make_user,
    make_vehicle,
    upload,
)
from tests.test_maintenance import camera, center, portal_client

A = "/api/v1/accidents"
P = "/api/v1/portal"
M = "/api/v1/maintenance"


@pytest.fixture
def setup(admin_client, client, new_client, company):
    """A driver holding a vehicle, with the app; a center with one portal account."""
    vehicle = make_vehicle(admin_client, company["id"], km=30_000)
    driver = make_driver(admin_client, company["id"])
    custody = hand_over(admin_client, vehicle, driver, km=30_000)
    h = bearer(bind_device(client, driver["phone"]))
    c = center(admin_client, "Body Shop One")
    portal = portal_client(admin_client, new_client, c, "body1")
    return {"vehicle": vehicle, "driver": driver, "custody": custody, "h": h, "center": c, "portal": portal}


def report(client, s, *, photos=3, police=False, **extra):
    body = {
        "client_ref": str(uuid.uuid4()),
        "lat": 29.3759,
        "lng": 47.9774,
        "description": "Hit from behind at a traffic light",
        "injuries": False,
        "other_party": "White pickup, plate 12345",
        "photos": [camera(client, s["h"]) for _ in range(photos)],
    } | extra
    if police:
        body["police_report"] = camera(client, s["h"])
        body["police_report_no"] = "PR-77"
    return client.post("/api/v1/driver/accidents", json=body, headers=s["h"])


def reported(client, s, **extra) -> str:
    r = report(client, s, **extra)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def refer(admin_client, s, aid):
    r = admin_client.post(f"{A}/{aid}/refer", json={"center_id": s["center"]["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def estimate(s, aid, total="150.000", items=None, **extra):
    items = items or [
        {"kind": "part", "description": "Rear bumper", "quantity": "1", "unit_price": "110.000"},
        {"kind": "labour", "description": "Paint and fitting", "unit_price": str(D(total) - D("110.000"))},
    ]
    return s["portal"].post(f"{P}/accidents/{aid}/estimate", json={"total": total, "items": items} | extra)


def estimated_and_approved(admin_client, client, s, *, police=True, total="150.000") -> str:
    aid = reported(client, s, police=police)
    refer(admin_client, s, aid)
    assert estimate(s, aid, total).status_code == 200
    r = admin_client.post(f"{A}/{aid}/estimate/approve")
    assert r.status_code == 200, r.text
    return aid


def police_pdf(admin_client) -> str:
    return upload(admin_client, b"%PDF-1.4 " + uuid.uuid4().bytes, name="police.pdf")


def vehicle_status(admin_client, s) -> str:
    return admin_client.get(f"/api/v1/vehicles/{s['vehicle']['id']}").json()["status"]


def next_month() -> date:
    return add_months(today(), 1)


# ------------------------------------------------------------------ the BRD's acceptance tests


def test_uat24_no_outcome_without_the_police_report(admin_client, client, setup, owner_db):
    s = setup
    aid = estimated_and_approved(admin_client, client, s, police=False)
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["has_police_report"] is False and detail["stage"] == "awaiting_outcome"
    listed = admin_client.get(A, params={"no_police_report": True}).json()
    assert [x["id"] for x in listed] == [aid]

    body = {"liability": "driver", "installments": 3}
    r = admin_client.post(f"{A}/{aid}/outcome", json=body)
    assert r.status_code == 409 and r.json()["code"] == "police_report_required"
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "none"})
    assert r.status_code == 409 and r.json()["code"] == "police_report_required"
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["liability"] is None and detail["deduction"] is None and detail["has_police_report"] is False

    # the database refuses it too, whoever writes
    with pytest.raises(Exception, match="accidents_outcome_check"):
        owner_db.execute(text("UPDATE accidents.accidents SET liability = 'none' WHERE public_id = :a"), {"a": aid})

    # with the report attached, the outcome goes through
    r = admin_client.post(
        f"{A}/{aid}/police-report", json={"file_sha256": police_pdf(admin_client), "number": "9/2026"}
    )
    assert r.status_code == 200 and r.json()["has_police_report"] is True
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "none", "note": "The other party was at fault"})
    assert r.status_code == 200, r.text
    assert r.json()["liability"] == "none" and r.json()["deduction"] is None


def test_uat25_the_report_reaches_the_chosen_center_which_estimates_and_waits_for_the_manager(
    admin_client, client, new_client, setup
):
    s = setup
    other = center(admin_client, "Other Garage")
    other_portal = portal_client(admin_client, new_client, other, "other1")
    aid = reported(client, s)

    # the vehicle is "in an accident", the driver from the custody log, the office alerted
    assert vehicle_status(admin_client, s) == "accident"
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["driver"]["id"] == s["driver"]["id"] and detail["source"] == "driver"
    assert detail["stage"] == "reported" and len(detail["photos"]) == 3
    assert detail["lat"] == 29.3759 and detail["other_party"] == "White pickup, plate 12345"
    alerts = admin_client.get("/api/v1/alerts").json()
    assert any(a["kind"] == "accident_reported" for a in alerts)

    # referred to the center the maintenance manager chose: it sees it as new, with the photos, not the driver
    assert s["portal"].get(f"{P}/accidents").json() == []
    refer(admin_client, s, aid)
    listed = s["portal"].get(f"{P}/accidents").json()
    assert [(x["id"], x["is_new"]) for x in listed] == [(aid, True)]
    seen = s["portal"].get(f"{P}/accidents/{aid}").json()
    assert "driver" not in seen and "other_party" not in seen and "liability" not in seen
    assert len(seen["photos"]) == 3
    photo = s["portal"].get(f"{P}/accidents/{aid}/files/{seen['photos'][0]}")
    assert photo.status_code == 200
    assert s["portal"].get(f"{P}/accidents").json()[0]["is_new"] is False
    # another center sees nothing, not even that it exists
    assert other_portal.get(f"{P}/accidents").json() == []
    assert other_portal.get(f"{P}/accidents/{aid}").status_code == 404
    assert other_portal.get(f"{P}/accidents/{aid}/files/{seen['photos'][0]}").status_code == 404

    # the center enters the damage item by item; it waits for the maintenance manager
    r = estimate(s, aid, notes="Bumper and paint", photos=[upload(s["portal"])])
    assert r.status_code == 200, r.text
    assert r.json()["estimate_status"] == "pending" and r.json()["estimate_total"] == "150.000"
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["stage"] == "estimate_pending" and len(detail["photos"]) == 4
    assert [i["amount"] for i in detail["estimate_items"]] == ["110.000", "40.000"]
    alerts = admin_client.get("/api/v1/alerts").json()
    assert any(a["kind"] == "accident_estimate_submitted" for a in alerts)
    # the center cannot send another while it waits, and the accident cannot go elsewhere meanwhile
    assert estimate(s, aid).json()["code"] == "estimate_not_expected"
    r = admin_client.post(f"{A}/{aid}/refer", json={"center_id": other["id"]})
    assert r.status_code == 409 and r.json()["code"] == "estimate_pending"
    # not usable for a deduction before the approval (FR-ACC-05)
    admin_client.post(f"{A}/{aid}/police-report", json={"file_sha256": police_pdf(admin_client)})
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "driver", "installments": 3})
    assert r.status_code == 409 and r.json()["code"] == "estimate_not_approved"

    r = admin_client.post(f"{A}/{aid}/estimate/approve")
    assert r.json()["estimate_status"] == "approved" and r.json()["stage"] == "awaiting_outcome"
    assert s["portal"].get(f"{P}/accidents").json() == []  # done: in its history
    assert [x["id"] for x in s["portal"].get(f"{P}/accidents", params={"active": False}).json()] == [aid]


def test_uat26_150_over_3_installments_is_50_on_each_payslip(admin_client, client, setup):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    start = next_month()
    r = admin_client.post(
        f"{A}/{aid}/outcome",
        json={"liability": "driver", "installments": 3, "start_month": str(start), "note": "Rear-ended a car"},
    )
    assert r.status_code == 200, r.text
    d = r.json()["deduction"]
    assert d["total"] == "150.000" and d["installments"] == 3 and d["source_type"] == "accident"
    assert d["schedule"] == [
        {"month": str(start), "amount": "50.000"},
        {"month": str(add_months(start, 1)), "amount": "50.000"},
        {"month": str(add_months(start, 2)), "amount": "50.000"},
    ]
    assert r.json()["liability_percent"] == "100.00" and r.json()["deduction_total"] == "150.000"

    # payroll reads it month by month
    for i in range(3):
        month = admin_client.get("/api/v1/deductions", params={"month": str(add_months(start, i))}).json()
        assert [(x["employee"]["id"], x["schedule"][i]["amount"]) for x in month] == [(s["driver"]["id"], "50.000")]
    assert admin_client.get("/api/v1/deductions", params={"month": str(add_months(start, 3))}).json() == []

    # the driver sees it in the app
    mine = client.get("/api/v1/driver/accidents", headers=s["h"]).json()
    assert mine[0]["liability"] == "driver" and mine[0]["deduction"]["total"] == "150.000"
    assert [x["amount"] for x in mine[0]["deduction"]["schedule"]] == ["50.000"] * 3
    assert client.get("/api/v1/driver/deductions", headers=s["h"]).json()[0]["total"] == "150.000"


# ------------------------------------------------------------------ the rest of the flow


def test_installments_round_down_and_the_last_takes_the_remainder():
    start = date(2026, 11, 1)
    assert [x["amount"] for x in schedule(D("100.000"), 3, start)] == [D("33.333"), D("33.333"), D("33.334")]
    assert [x["month"] for x in schedule(D("10.000"), 3, date(2026, 11, 1))] == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]
    assert sum(x["amount"] for x in schedule(D("0.005"), 2, start)) == D("0.005")


def test_shared_liability_charges_the_percentage(admin_client, client, setup):
    s = setup
    aid = estimated_and_approved(admin_client, client, s, total="155.000")
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "shared", "installments": 2})
    assert r.status_code == 422 and r.json()["code"] == "liability_percent_required"
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "shared", "percent": "100", "installments": 2})
    assert r.status_code == 422 and r.json()["code"] == "shared_percent_below_100"
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "driver"})
    assert r.status_code == 422 and r.json()["code"] == "installments_required"
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "shared", "percent": "33.33", "installments": 2})
    assert r.status_code == 200, r.text
    d = r.json()["deduction"]
    assert d["total"] == "51.662"  # 155.000 x 33.33% = 51.6615, rounded half up
    assert [x["amount"] for x in d["schedule"]] == ["25.831", "25.831"]
    assert d["start_month"] == str(next_month())  # next month when not given
    # recorded once
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "none"})
    assert r.status_code == 409 and r.json()["code"] == "outcome_recorded"
    # the police report is the evidence of the decision now
    r = admin_client.post(f"{A}/{aid}/police-report", json={"file_sha256": police_pdf(admin_client)})
    assert r.status_code == 409 and r.json()["code"] == "outcome_recorded"


def test_the_repair_goes_to_the_same_center_and_its_invoice_is_the_actual_cost(admin_client, client, setup, db):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    r = admin_client.post(f"{A}/{aid}/repair")
    assert r.status_code == 200, r.text
    repair = r.json()["repair"]
    assert repair["status"] == "referred" and repair["actual_cost"] is None
    assert admin_client.post(f"{A}/{aid}/repair").json()["code"] == "repair_exists"

    # the center receives it: the car stays with its driver, and the repair starts without a second quote
    rid = repair["id"]
    portal = s["portal"]
    body = {"odometer_km": 30_100, "odometer_photo": upload(portal)}
    r = portal.post(f"{P}/requests/{rid}/receive", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_repair" and r.json()["quotes"][0]["amount"] == "150.000"
    assert [e["status"] for e in r.json()["events"]] == ["requested", "approved", "referred", "received", "in_repair"]
    assert vehicle_status(admin_client, s) == "maintenance"
    assert admin_client.get(f"/api/v1/custodies/{s['custody']['id']}").json()["ended_at"] is None

    # ready with its invoice, which differs from the estimate: flagged, and the accident shows the difference once
    # approved
    r = portal.post(
        f"{P}/requests/{rid}/ready",
        json={
            "number": "B-1",
            "invoice_date": str(today()),
            "total": "162.500",
            "file_sha256": upload(portal, b"%PDF-1.4 " + uuid.uuid4().bytes, name="inv.pdf"),
            "items": [{"kind": "part", "description": "Bumper", "unit_price": "162.500"}],
        },
    )
    assert r.status_code == 200, r.text
    (inv,) = r.json()["invoices"]
    assert inv["flags"] == ["differs_from_quote"]
    pending = admin_client.get(f"{A}/{aid}").json()["repair"]
    assert pending["actual_cost"] is None and pending["invoices_pending"] == 1
    # the driver collects it from the app: his again to work with
    body = {"odometer_km": 30_110, "odometer_photo": camera(client, s["h"])}
    r = client.post(f"/api/v1/driver/maintenance/{rid}/picked-up", json=body, headers=s["h"])
    assert r.status_code == 200, r.text
    assert vehicle_status(admin_client, s) == "assigned"
    admin_client.post(f"{M}/invoices/{inv['id']}/approve")
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["repair"]["actual_cost"] == "162.500" and detail["cost_difference"] == "12.500"


def test_closing_and_cancelling_release_the_vehicle(admin_client, client, setup, company):
    s = setup
    aid = reported(client, s, police=True)
    assert vehicle_status(admin_client, s) == "accident"
    # a damaged vehicle is not handed over normally
    other = make_driver(admin_client, company["id"])
    r = admin_client.post(
        f"/api/v1/custodies/{s['custody']['id']}/return",
        json={"odometer_km": 30_010, "photo_sha256": upload(admin_client)},
    )
    assert r.status_code == 200, r.text
    assert vehicle_status(admin_client, s) == "accident"
    r = admin_client.post(
        "/api/v1/custodies",
        json={
            "vehicle_id": s["vehicle"]["id"],
            "driver_id": other["id"],
            "odometer_km": 30_010,
            "photo_sha256": upload(admin_client),
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "vehicle_not_available"

    r = admin_client.post(f"{A}/{aid}/close", json={})
    assert r.status_code == 409 and r.json()["code"] == "outcome_required"
    admin_client.post(f"{A}/{aid}/outcome", json={"liability": "none"})
    r = admin_client.post(f"{A}/{aid}/close", json={"note": "No damage worth repairing"})
    assert r.json()["status"] == "closed" and r.json()["stage"] == "closed"
    assert vehicle_status(admin_client, s) == "available"
    assert not [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"].startswith("accident_")]
    r = admin_client.post(f"{A}/{aid}/refer", json={"center_id": s["center"]["id"]})
    assert r.status_code == 409 and r.json()["code"] == "accident_not_open"

    # reported in error, while the driver still holds the vehicle: back to "assigned"
    hand_over(admin_client, s["vehicle"], other, km=30_010)
    h2 = bearer(bind_device(client, other["phone"]))
    aid2 = reported(client, s | {"h": h2})
    assert vehicle_status(admin_client, s) == "accident"
    r = admin_client.post(f"{A}/{aid2}/cancel", json={"reason": "Wrong button"})
    assert r.json()["status"] == "cancelled"
    assert vehicle_status(admin_client, s) == "assigned"
    assert client.get("/api/v1/driver/accidents", headers=h2).json() == []


def test_cancel_is_refused_once_charged_or_sent_for_repair(admin_client, client, setup):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    admin_client.post(f"{A}/{aid}/repair")
    r = admin_client.post(f"{A}/{aid}/cancel", json={"reason": "Not ours"})
    assert r.status_code == 409 and r.json()["code"] == "repair_exists"


def test_the_driver_report_needs_photos_from_this_phone_and_the_vehicle_held_then(admin_client, client, setup, company):
    s = setup
    r = report(client, s, photos=2)
    assert r.status_code == 422 and r.json()["code"] == "accident_photos_required"
    assert r.json()["params"]["min"] == 3
    # uploaded by the office, not this phone's camera
    body = {"client_ref": str(uuid.uuid4()), "description": "x", "photos": [upload(admin_client) for _ in range(3)]}
    r = client.post("/api/v1/driver/accidents", json=body, headers=s["h"])
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    # a retry is recognised
    ref = str(uuid.uuid4())
    assert report(client, s, client_ref=ref).status_code == 201
    r = report(client, s, client_ref=ref)
    assert r.status_code == 409 and r.json()["code"] == "accident_exists"
    # in the future, or too old for the app
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert report(client, s, occurred_at=soon).json()["code"] == "time_in_future"
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    assert report(client, s, occurred_at=old).json()["code"] == "time_too_old"
    # a driver without a vehicle at that time
    driver2 = make_driver(admin_client, company["id"])
    h2 = bearer(bind_device(client, driver2["phone"]))
    r = report(client, s | {"h": h2})
    assert r.status_code == 409 and r.json()["code"] == "no_vehicle_in_custody"
    # the number of photos is a setting
    current = admin_client.get("/api/v1/settings").json()["accidents"]
    r = admin_client.put(
        "/api/v1/settings/accidents",
        json={"version": current["version"], "value": current["value"] | {"min_photos": 1}},
    )
    assert r.status_code == 200, r.text
    assert report(client, s, photos=1).status_code == 201


def test_the_office_reports_for_the_driver_who_held_the_vehicle_at_that_time(admin_client, setup, company):
    s = setup
    vehicle = make_vehicle(admin_client, company["id"], km=1_000)
    first, second = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    now = datetime.now(UTC)
    c1 = hand_over(admin_client, vehicle, first, km=1_000, started_at=(now - timedelta(hours=5)).isoformat())
    r = admin_client.post(
        f"/api/v1/custodies/{c1['id']}/return",
        json={
            "odometer_km": 1_050,
            "photo_sha256": upload(admin_client),
            "ended_at": (now - timedelta(hours=3)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    hand_over(admin_client, vehicle, second, km=1_050, started_at=(now - timedelta(hours=1)).isoformat())

    def office(at, **extra):
        body = {"vehicle_id": vehicle["id"], "occurred_at": at.isoformat(), "description": "Scratch found"} | extra
        return admin_client.post(A, json=body)

    r = office(now - timedelta(hours=4), photos=[upload(admin_client)], police_report=police_pdf(admin_client))
    assert r.status_code == 201, r.text
    assert r.json()["driver"]["id"] == first["id"] and r.json()["source"] == "office"
    assert r.json()["has_police_report"] is True
    assert office(now - timedelta(minutes=5)).json()["driver"]["id"] == second["id"]
    nobody = office(now - timedelta(days=2))
    assert nobody.status_code == 201 and nobody.json()["driver"] is None
    # nobody to charge without a driver
    aid = nobody.json()["id"]
    admin_client.post(f"{A}/{aid}/police-report", json={"file_sha256": police_pdf(admin_client)})
    admin_client.post(f"{A}/{aid}/refer", json={"center_id": s["center"]["id"]})
    estimate(s, aid)
    admin_client.post(f"{A}/{aid}/estimate/approve")
    r = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "driver", "installments": 1})
    assert r.status_code == 409 and r.json()["code"] == "accident_has_no_driver"
    # injuries are a critical alert
    office(now - timedelta(minutes=1), injuries=True, injuries_note="Driver taken to hospital")
    alerts = admin_client.get("/api/v1/alerts").json()
    assert [a["severity"] for a in alerts if a["kind"] == "accident_injuries"] == ["critical"]


def test_the_driver_sends_the_police_report_later(admin_client, client, setup):
    s = setup
    aid = reported(client, s)
    mine = client.get("/api/v1/driver/accidents", headers=s["h"]).json()
    assert mine[0]["has_police_report"] is False
    path = f"/api/v1/driver/accidents/{aid}/police-report"
    r = client.post(path, json={"file_sha256": upload(admin_client)}, headers=s["h"])  # not from this phone
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    # from the phone's files (FR-APP-06): a PDF or a picture from the gallery, not only the camera
    pdf = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=s["h"],
        files={"file": ("police.pdf", b"%PDF-1.4 " + uuid.uuid4().bytes, "application/pdf")},
    )
    assert pdf.status_code == 201, pdf.text
    sha = pdf.json()["sha256"]
    r = client.post(path, json={"file_sha256": sha, "number": "PR-1"}, headers=s["h"])
    assert r.status_code == 200, r.text
    assert r.json()["has_police_report"] is True
    assert client.post(path, json={"file_sha256": sha}, headers=s["h"]).status_code == 200  # a retry
    r = client.post(path, json={"file_sha256": camera(client, s["h"])}, headers=s["h"])
    assert r.status_code == 409 and r.json()["code"] == "police_report_exists"
    detail = admin_client.get(f"{A}/{aid}").json()
    assert detail["police_report_no"] == "PR-1"
    assert admin_client.get(f"{A}/{aid}/files/{sha}").status_code == 200
    # the center does not get the police report
    refer(admin_client, s, aid)
    assert s["portal"].get(f"{P}/accidents/{aid}/files/{sha}").status_code == 404


def test_a_rejected_estimate_goes_back_to_the_center_or_to_another(admin_client, client, new_client, setup):
    s = setup
    aid = reported(client, s)
    refer(admin_client, s, aid)
    bad = [{"kind": "part", "description": "Bumper", "unit_price": "100.000"}]
    r = estimate(s, aid, total="150.000", items=bad)
    assert r.status_code == 422 and r.json()["code"] == "estimate_items_mismatch"
    estimate(s, aid, total="300.000")
    r = admin_client.post(f"{A}/{aid}/estimate/reject", json={"reason": "Too expensive for a bumper"})
    assert r.json()["estimate_status"] == "rejected" and r.json()["stage"] == "estimate_rejected"
    seen = s["portal"].get(f"{P}/accidents/{aid}").json()
    assert seen["estimate_reason"] == "Too expensive for a bumper"
    assert estimate(s, aid, total="180.000").json()["estimate_status"] == "pending"
    admin_client.post(f"{A}/{aid}/estimate/reject", json={"reason": "Still too much"})
    assert admin_client.post(f"{A}/{aid}/estimate/approve").json()["code"] == "estimate_not_pending"

    other = center(admin_client, "Second Opinion")
    other_portal = portal_client(admin_client, new_client, other, "second1")
    r = admin_client.post(f"{A}/{aid}/refer", json={"center_id": other["id"]})
    assert r.json()["center"]["name"] == "Second Opinion" and r.json()["estimate_status"] == "none"
    assert s["portal"].get(f"{P}/accidents/{aid}").status_code == 404  # the first center lost it
    r = estimate({"portal": other_portal}, aid, total="140.000")
    assert r.status_code == 200, r.text
    events = [e["kind"] for e in admin_client.get(f"{A}/{aid}").json()["events"]]
    assert events == [
        "reported",
        "referred",
        "estimate_submitted",
        "estimate_rejected",
        "estimate_submitted",
        "estimate_rejected",
        "referred",
        "estimate_submitted",
    ]


def test_a_start_month_in_the_past_is_refused(admin_client, client, setup):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    past = add_months(today(), -1)
    body = {"liability": "driver", "installments": 1, "start_month": str(past)}
    r = admin_client.post(f"{A}/{aid}/outcome", json=body)
    assert r.status_code == 422 and r.json()["code"] == "start_month_in_past"
    body["start_month"] = str(today())  # any day of the current month: from this month
    r = admin_client.post(f"{A}/{aid}/outcome", json=body)
    assert r.json()["deduction"]["start_month"] == str(today().replace(day=1))


def test_cancelling_a_deduction(admin_client, client, setup):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    d = admin_client.post(f"{A}/{aid}/outcome", json={"liability": "driver", "installments": 3}).json()["deduction"]
    r = admin_client.post(f"/api/v1/deductions/{d['id']}/cancel", json={"reason": "Insurance paid it"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert admin_client.post(f"/api/v1/deductions/{d['id']}/cancel", json={"reason": "again"}).status_code == 409
    assert client.get("/api/v1/driver/deductions", headers=s["h"]).json() == []
    assert client.get("/api/v1/driver/accidents", headers=s["h"]).json()[0]["deduction"] is None
    assert admin_client.get(f"{A}/{aid}").json()["deduction_total"] is None
    assert admin_client.get("/api/v1/deductions", params={"status": "cancelled"}).json()[0]["id"] == d["id"]


def test_permissions_and_company_scope(admin_client, client, new_client, setup, companies):
    s = setup
    aid = estimated_and_approved(admin_client, client, s)
    make_user(
        admin_client, "acc_b", permissions=["accidents.view", "accidents.approve"], company_ids=[companies["b"]["id"]]
    )
    make_user(admin_client, "acc_mm", permissions=["accidents.view", "accidents.update"])
    make_user(admin_client, "acc_sup", permissions=["accidents.view", "accidents.create"])
    b, mm, sup = new_client(), new_client(), new_client()
    from tests.conftest import login

    login(b, "acc_b")
    login(mm, "acc_mm")
    login(sup, "acc_sup")
    # another company's user does not see it
    assert b.get(A).json() == []
    assert b.get(f"{A}/{aid}").status_code == 404
    assert b.post(f"{A}/{aid}/outcome", json={"liability": "none"}).status_code == 404
    # the maintenance manager refers and approves estimates but does not decide the liability
    r = mm.post(f"{A}/{aid}/outcome", json={"liability": "none"})
    assert r.status_code == 403
    # the supervisor reports and attaches, nothing more
    assert sup.post(f"{A}/{aid}/refer", json={"center_id": s["center"]["id"]}).status_code == 403
    assert sup.post(f"{A}/{aid}/police-report", json={"file_sha256": upload(sup)}).status_code == 200
    # deductions need their own permissions
    assert mm.get("/api/v1/deductions").status_code == 403
    # a center account sees nothing of the office API
    assert s["portal"].get(A).status_code == 403
    assert s["portal"].get(f"{A}/{aid}").status_code == 403


def test_alert_for_a_missing_police_report_and_the_dashboard(admin_client, client, setup, owner_db, db):
    from app.modules.accidents import service

    s = setup
    aid = reported(client, s)
    assert service.scan_police_reports(db) == 0  # not late yet
    owner_db.execute(
        text("UPDATE accidents.accidents SET created_at = now() - interval '3 days' WHERE public_id = :a"), {"a": aid}
    )
    owner_db.commit()
    assert service.scan_police_reports(db) == 1
    assert service.scan_police_reports(db) == 0  # one open alert per accident
    alerts = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "accident_awaiting_police_report"]
    assert len(alerts) == 1 and alerts[0]["params"]["days"] == 3
    dash = admin_client.get("/api/v1/dashboard").json()["accidents"]
    assert dash == {"open": 1, "no_police_report": 1, "estimate_pending": 0, "awaiting_outcome": 0, "this_month": 1}
    # attaching the report closes the alert
    admin_client.post(f"{A}/{aid}/police-report", json={"file_sha256": police_pdf(admin_client)})
    assert not [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "accident_awaiting_police_report"]
