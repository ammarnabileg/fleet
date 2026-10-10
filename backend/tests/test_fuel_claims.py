"""Fuel the driver paid from the cash he holds: claimed from the app with a camera photo of the receipt, reviewed by the
accountant who may correct the amount. Only when the driver's pay scheme puts fuel on the company does an approval
lower his cash (Dr fuel 5120 / Cr drivers' cash 1130); fuel on the driver, or a company fuel card, records nothing."""

import uuid
from datetime import timedelta

import pytest

from app.core.clock import today, utcnow
from app.modules.payroll.service import add_months
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload

P = "/api/v1/payroll"
C = "/api/v1/cash/fuel-claims"
DRIVER = "/api/v1/driver/fuel"
MONTH = today().replace(day=1)


def camera(client, h, *, source="camera", data=None, name="r.jpg") -> str:
    r = client.post(
        "/api/v1/driver/files", params={"source": source}, headers=h, files={"file": (name, data or jpeg(), "x/y")}
    )
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def scheme(admin_client, platform_id, code, covers) -> dict:
    body = {
        "platform_id": platform_id,
        "code": code,
        "name": {"ar": code, "en": code},
        "calculator": "per_order",
        "per_order": "0.350",
        "company_covers": covers,
    }
    r = admin_client.post(f"{P}/schemes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def assign(admin_client, s, driver, month=MONTH):
    r = admin_client.post(f"{P}/schemes/{s['id']}/assign", json={"employee_ids": [driver["id"]], "month": str(month)})
    assert r.json()["set"] == 1, r.text


@pytest.fixture
def world(admin_client, company):
    r = admin_client.post(f"{P}/platforms", json={"code": "plat", "name": {"ar": "p", "en": "p"}, "pay_basic": False})
    assert r.status_code == 201, r.text
    platform = r.json()
    return {
        "platform": platform,
        "gas": scheme(admin_client, platform["id"], "gas", ["gas", "sim"]),
        "own": scheme(admin_client, platform["id"], "own", ["housing"]),
    }


def driver_of(admin_client, client, company, world, *, covers=True, custody=True, **extra) -> dict:
    d = make_driver(admin_client, company["id"], platform_id=world["platform"]["id"], **extra)
    assign(admin_client, world["gas" if covers else "own"], d)
    v = None
    if custody:
        v = make_vehicle(admin_client, company["id"])
        hand_over(admin_client, v, d, started_at=(utcnow() - timedelta(days=3)).isoformat())
    return {"driver": d, "vehicle": v, "h": bearer(bind_device(client, d["phone"]))}


def claim(client, s, *, amount="7.250", minutes_ago=30, receipt=None, **extra):
    body = {
        "client_ref": str(uuid.uuid4()),
        "paid_at": (utcnow() - timedelta(minutes=minutes_ago)).isoformat(),
        "amount": amount,
        "receipt_sha256": receipt or camera(client, s["h"]),
    } | extra
    return client.post(DRIVER, headers=s["h"], json=body)


def balance(client, s) -> str:
    return client.get("/api/v1/driver/cash", headers=s["h"]).json()["total"]


def test_a_covered_claim_waits_then_its_approval_lowers_the_drivers_cash_and_enters_the_books(
    admin_client, client, company, world
):
    s = driver_of(admin_client, client, company, world)
    r = admin_client.post(
        "/api/v1/cash/adjustments", json={"driver_id": s["driver"]["id"], "amount": "30.000", "reason": "opening"}
    )
    assert r.status_code == 201, r.text
    view = client.get(DRIVER, headers=s["h"]).json()
    assert (view["allowed"], view["reason"], view["max_amount"], view["claims"]) == (True, None, "50.000", [])

    r = claim(client, s, amount="7.250", odometer_km=12_345, notes="Salmiya")
    assert r.status_code == 201, r.text
    mine = r.json()
    assert (mine["status"], mine["amount"], mine["odometer_km"], mine["vehicle_plate"]) == (
        "pending",
        "7.250",
        12_345,
        s["vehicle"]["plate_number"],
    )
    assert balance(client, s) == "30.000"  # nothing in the cash until approved
    [alert] = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "fuel_claim"]
    assert alert["entity_type"] == "fuel_claim" and alert["entity_id"] == mine["id"]

    [row] = admin_client.get(C, params={"status": "pending"}).json()
    assert (row["id"], row["covered"], row["driver"]["id"], row["journal_id"]) == (
        mine["id"],
        True,
        s["driver"]["id"],
        None,
    )
    assert admin_client.get(f"{C}/pending-count").json() == {"count": 1}
    photo = admin_client.get(row["receipt_url"])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"

    # a corrected amount needs a note
    r = admin_client.post(f"{C}/{mine['id']}/approve", json={"amount": "7.000"})
    assert r.status_code == 422 and r.json()["code"] == "reason_required"
    r = admin_client.post(f"{C}/{mine['id']}/approve", json={"amount": "7.000", "note": "the receipt says 7.000"})
    assert r.status_code == 200, r.text
    done = r.json()
    assert (done["status"], done["approved_amount"], done["decision_note"]) == (
        "approved",
        "7.000",
        "the receipt says 7.000",
    )
    assert balance(client, s) == "23.000"
    r = admin_client.post(f"{C}/{mine['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "fuel_decided"
    r = admin_client.post(f"{C}/{mine['id']}/reject", json={"reason": "too late"})
    assert r.status_code == 409 and r.json()["code"] == "fuel_decided"
    assert [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "fuel_claim"] == []
    assert admin_client.get(f"{C}/pending-count").json() == {"count": 0}

    # the driver's statement and the app's cash tab show it as a fuel movement
    st = admin_client.get(f"/api/v1/cash/drivers/{s['driver']['id']}/statement").json()
    assert (st["lines"][0]["kind"], st["lines"][0]["status"], st["lines"][0]["amount"]) == ("fuel", "posted", "-7.000")
    assert st["lines"][0]["journal_id"] == done["journal_id"]
    lines = client.get("/api/v1/driver/cash", headers=s["h"]).json()["lines"]
    assert (lines[0]["kind"], lines[0]["amount"]) == ("fuel", "-7.000")
    view = client.get(DRIVER, headers=s["h"]).json()
    assert [(c["status"], c["approved_amount"]) for c in view["claims"]] == [("approved", "7.000")]
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()["items"]
    assert any(n["kind"] == "fuel_approved" and "7.000" in n["message"] for n in notices)

    # in the books: Dr fuel (5120) / Cr drivers' cash (1130)
    first = MONTH
    last = add_months(MONTH, 1) - timedelta(days=1)
    period = {"date_from": str(first), "date_to": str(last)}
    r = admin_client.post("/api/v1/finance/entries/post", json=period)
    assert r.status_code == 200 and r.json()["errors"] == [], r.text
    found = []
    for e in admin_client.get("/api/v1/finance/entries", params=period).json():
        lines = admin_client.get(f"/api/v1/finance/entries/{e['id']}").json()["lines"]
        if any(ln["account"]["code"] == "5120" for ln in lines):
            found.append([(ln["account"]["code"], ln["debit"], ln["credit"]) for ln in lines])
    assert found == [[("5120", "7.000", "0.000"), ("1130", "0.000", "7.000")]]

    # a wrong approval is undone by reversing its journal
    r = admin_client.post(f"/api/v1/cash/journals/{done['journal_id']}/reverse", json={"reason": "wrong driver"})
    assert r.status_code == 201, r.text
    assert balance(client, s) == "30.000"


def test_a_rejection_needs_its_reason_and_records_nothing(admin_client, client, company, world):
    s = driver_of(admin_client, client, company, world)
    mine = claim(client, s).json()
    r = admin_client.post(f"{C}/{mine['id']}/reject", json={"reason": ""})
    assert r.status_code == 422
    r = admin_client.post(f"{C}/{mine['id']}/reject", json={"reason": "not our station"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["journal_id"] is None
    assert balance(client, s) == "0.000"
    assert client.get(DRIVER, headers=s["h"]).json()["claims"][0]["decision_note"] == "not our station"
    notices = client.get("/api/v1/driver/notifications", headers=s["h"]).json()["items"]
    assert any(n["kind"] == "fuel_rejected" and "not our station" in n["message"] for n in notices)


def test_fuel_on_the_driver_a_fuel_card_or_no_car_is_refused(admin_client, client, company, world):
    own = driver_of(admin_client, client, company, world, covers=False)
    assert client.get(DRIVER, headers=own["h"]).json()["reason"] == "not_covered"
    r = claim(client, own)
    assert r.status_code == 409 and r.json()["code"] == "fuel_not_covered"

    card = driver_of(admin_client, client, company, world, fuel_card=True)
    assert card["driver"]["fuel_card"] is True
    view = client.get(DRIVER, headers=card["h"]).json()
    assert (view["allowed"], view["reason"]) == (False, "fuel_card")
    r = claim(client, card)
    assert r.status_code == 409 and r.json()["code"] == "fuel_card_driver"
    assert client.get("/api/v1/driver/profile", headers=card["h"]).json()["fuel_card"] is True

    walker = driver_of(admin_client, client, company, world, custody=False)
    assert client.get(DRIVER, headers=walker["h"]).json()["reason"] == "no_vehicle"
    r = claim(client, walker)
    assert r.status_code == 409 and r.json()["code"] == "fuel_no_vehicle"

    # no scheme at all: fuel is his
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    assert client.get(DRIVER, headers=h).json()["reason"] == "not_covered"
    assert admin_client.get(C).json() == []


def test_the_claim_itself_is_checked(admin_client, client, company, world):
    s = driver_of(admin_client, client, company, world)
    r = claim(client, s, minutes_ago=8 * 24 * 60)
    assert r.status_code == 422 and r.json()["code"] == "fuel_too_old"
    r = claim(client, s, minutes_ago=-60)
    assert r.status_code == 422 and r.json()["code"] == "time_in_future"
    r = claim(client, s, amount="50.001")
    assert r.status_code == 422 and r.json()["code"] == "fuel_amount_too_high"
    r = claim(client, s, amount="0")
    assert r.status_code == 422
    r = claim(client, s, odometer_km=-1)
    assert r.status_code == 422
    r = claim(client, s, receipt=camera(client, s["h"], source="upload"))  # from the gallery
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    pdf = camera(client, s["h"], source="upload", data=b"%PDF-1.4 " + uuid.uuid4().bytes, name="r.pdf")
    r = claim(client, s, receipt=pdf)
    assert r.status_code == 422 and r.json()["code"] == "photo_must_be_image"
    other = driver_of(admin_client, client, company, world)
    r = claim(client, s, receipt=camera(client, other["h"]))  # another phone's photo
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"
    r = claim(client, s, receipt=upload(admin_client))
    assert r.status_code == 422 and r.json()["code"] == "file_not_yours"

    sent = {
        "client_ref": str(uuid.uuid4()),
        "paid_at": utcnow().isoformat(),
        "amount": "5.000",
        "receipt_sha256": camera(client, s["h"]),
    }
    assert client.post(DRIVER, headers=s["h"], json=sent).status_code == 201
    r = client.post(DRIVER, headers=s["h"], json=sent)  # the outbox resends
    assert r.status_code == 409 and r.json()["code"] == "fuel_exists"
    r = claim(client, s, receipt=sent["receipt_sha256"])  # the same receipt again
    assert r.status_code == 409 and r.json()["code"] == "fuel_receipt_used"
    r = client.post(DRIVER, headers=s["h"], json=sent | {"client_ref": str(uuid.uuid4()), "extra": 1})
    assert r.status_code == 422

    # the setting moves the maximum
    version = admin_client.get("/api/v1/settings").json()["cash"]["version"]
    r = admin_client.put("/api/v1/settings/cash", json={"version": version, "value": {"fuel_max_amount": "60.000"}})
    assert r.status_code == 200, r.text
    assert claim(client, s, amount="55.000").status_code == 201


def test_coverage_changed_before_approval_leaves_it_to_be_rejected(admin_client, client, company, world):
    s = driver_of(admin_client, client, company, world)
    mine = claim(client, s).json()
    assign(admin_client, world["own"], s["driver"])  # this month on a scheme where fuel is his
    [row] = admin_client.get(C).json()
    assert row["covered"] is False
    r = admin_client.post(f"{C}/{mine['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["code"] == "fuel_not_covered"
    assert admin_client.get(C).json()[0]["status"] == "pending"
    assert balance(client, s) == "0.000"
    assert admin_client.post(f"{C}/{mine['id']}/reject", json={"reason": "fuel is his"}).status_code == 200


def test_the_screen_can_be_hidden(admin_client, client, company, world):
    s = driver_of(admin_client, client, company, world)
    version = admin_client.get("/api/v1/settings").json()["driver_app"]["version"]
    r = admin_client.put(
        "/api/v1/settings/driver_app", json={"version": version, "value": {"hidden_screens": ["fuel"]}}
    )
    assert r.status_code == 200, r.text
    r = client.get(DRIVER, headers=s["h"])
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
    r = claim(client, s)
    assert r.status_code == 403 and r.json()["code"] == "screen_off"


def test_who_sees_and_who_decides(admin_client, client, new_client, companies, world):
    a, b = companies["a"], companies["b"]
    s = driver_of(admin_client, client, a, world)
    mine = claim(client, s).json()

    make_user(admin_client, "viewer", permissions=["cash.view"])
    viewer = new_client()
    login(viewer, "viewer")
    assert [r["id"] for r in viewer.get(C).json()] == [mine["id"]]
    r = viewer.post(f"{C}/{mine['id']}/approve", json={})
    assert r.status_code == 403
    assert viewer.post(f"{C}/{mine['id']}/reject", json={"reason": "no"}).status_code == 403

    make_user(admin_client, "nobody", permissions=["daily_reports.view"])
    nobody = new_client()
    login(nobody, "nobody")
    assert nobody.get(C).status_code == 403
    assert nobody.get(f"{C}/{mine['id']}/receipt").status_code == 403

    make_user(admin_client, "other", permissions=["cash.fuel_review"], company_ids=[b["id"]])
    other = new_client()
    login(other, "other")
    assert other.get(C).json() == []  # another company's driver
    assert other.get(f"{C}/{mine['id']}/receipt").status_code == 404
    r = other.post(f"{C}/{mine['id']}/approve", json={})
    assert r.status_code == 404 and r.json()["code"] == "fuel_claim_not_found"

    make_user(admin_client, "reviewer", permissions=["cash.fuel_review"], company_ids=[a["id"]])
    reviewer = new_client()
    login(reviewer, "reviewer")
    assert reviewer.get(C, params={"driver_id": s["driver"]["id"]}).json()[0]["id"] == mine["id"]
    assert reviewer.get(C, params={"from": str(today() + timedelta(days=1))}).json() == []
    r = reviewer.post(f"{C}/{mine['id']}/approve", json={})
    assert r.status_code == 200 and r.json()["approved_amount"] == "7.250"


def test_the_role_templates_hold_the_review(admin_client):
    roles = {r["code"]: r for r in admin_client.get("/api/v1/roles").json()}
    assert "cash.fuel_review" in roles["accountant"]["permissions"]
    assert "cash.fuel_review" in roles["management"]["permissions"]


def test_a_reversed_fuel_approval_reopens_the_claim_to_approve_at_the_right_amount(
    admin_client, client, company, world
):
    s = driver_of(admin_client, client, company, world)
    mine = claim(client, s, amount="9.000").json()
    done = admin_client.post(f"{C}/{mine['id']}/approve", json={}).json()
    assert balance(client, s) == "-9.000"
    r = admin_client.post(f"/api/v1/cash/journals/{done['journal_id']}/reverse", json={"reason": "it was 6.000"})
    assert r.status_code == 201, r.text
    assert balance(client, s) == "0.000"
    [row] = admin_client.get(C, params={"status": "pending"}).json()  # waiting again, its alert back
    assert (row["id"], row["approved_amount"], row["journal_id"]) == (mine["id"], None, None)
    assert [a["entity_id"] for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "fuel_claim"] == [
        mine["id"]
    ]
    r = admin_client.post(f"{C}/{mine['id']}/approve", json={"amount": "6.000", "note": "the receipt says 6.000"})
    assert r.status_code == 200, r.text
    assert balance(client, s) == "-6.000"
    view = client.get(DRIVER, headers=s["h"]).json()
    assert [(c["status"], c["approved_amount"]) for c in view["claims"]] == [("approved", "6.000")]
