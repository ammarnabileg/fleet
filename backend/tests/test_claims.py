"""A driver imported without a phone signs in once with his civil ID and the office's initial password, registers his
phone with a WhatsApp code, then goes through the self-registration review like after an activation link. Without
phone codes (a client setting) he chooses his own password instead and signs in with it on any phone."""

import re
import uuid

import pytest
from sqlalchemy import text

from app.core import messaging
from tests.conftest import bearer, login, make_driver, make_employee, make_user, make_vehicle

A = "/api/v1/driver/auth/claim"
CIVIL = "286092015272"
PASSWORD = "12345678"


@pytest.fixture
def imported(admin_client, company):
    """A driver as the import leaves him: civil ID and profession, no phone, no app."""
    r = admin_client.post(
        "/api/v1/employees",
        json={
            "employee_number": "E00001",
            "name": {"ar": "الفاتح مختار", "en": "Alfatih"},
            "company_id": company["id"],
            "is_driver": True,
            "civil_id": CIVIL,
            "job_title": "سائق / سيارة خصوصي",
        },
    )
    assert r.status_code == 201 and r.json()["app_access"] == "none", r.text
    return r.json()


def set_claim(client, *employees, password=PASSWORD, days=14):
    r = client.post(
        "/api/v1/driver-claims", json={"employee_ids": [e["id"] for e in employees], "password": password, "days": days}
    )
    assert r.status_code == 200, r.text
    return r.json()


def code_for(phone):
    msg = next(m.text for m in reversed(messaging.provider().sent) if m.to == phone)
    return re.search(r"\b(\d{6})\b", msg).group(1)


def start(client, civil=CIVIL, password=PASSWORD, device="phone-0001"):
    return client.post(A, json={"civil_id": civil, "password": password, "device_uid": device})


def test_civil_id_then_phone_then_code_then_self_registration(admin_client, client, imported, db):
    out = set_claim(admin_client, imported)
    assert out["set"] == 1 and out["skipped"] == []
    r = start(client)
    assert r.status_code == 200, r.text
    claim = r.json()
    assert claim["name"]["ar"] == "الفاتح مختار" and claim["next"] == "phone"
    token = claim["claim_token"]

    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": "+96550001111"})
    assert r.status_code == 200 and r.json()["sent_to"] == "+965••••1111", r.text
    assert admin_client.get(f"/api/v1/employees/{imported['id']}").json()["phone"] is None  # not before the code
    r = client.post(f"{A}/verify", json={"claim_token": token, "device_uid": "phone-0001", "code": "000000"})
    assert r.status_code == 401 and r.json()["code"] == "otp_invalid"
    r = client.post(
        f"{A}/verify",
        json={
            "claim_token": token,
            "device_uid": "phone-0001",
            "code": code_for("+96550001111"),
            "model": "Galaxy A14",
        },
    )
    assert r.status_code == 200, r.text
    h = bearer(r.json())

    emp = admin_client.get(f"/api/v1/employees/{imported['id']}").json()
    assert (emp["phone"], emp["app_access"]) == ("+96550001111", "active")
    view = client.get("/api/v1/driver/onboarding", headers=h).json()
    assert view["required"] and view["status"] == "draft"  # documents and IBAN next, then the review
    status = admin_client.get(f"/api/v1/employees/{imported['id']}/claim").json()
    assert status["open"] is False and status["used_phone"] == "+965••••1111" and status["used_at"]
    devices = admin_client.get(f"/api/v1/employees/{imported['id']}/devices").json()
    assert [d["model"] for d in devices] == ["Galaxy A14"]
    actions = {a for (a,) in db.execute(text("SELECT action FROM audit.events"))}
    assert {"driver.claim_set", "driver.claimed", "employee.app_claimed", "device.bound"} <= actions

    # used once: the same civil ID and password no longer work; the phone signs in with its code from now on
    assert start(client).json()["code"] == "claim_invalid"


def test_wrong_answers_say_nothing_and_lock(admin_client, client, imported):
    set_claim(admin_client, imported)
    unknown = start(client, civil="290010112341")
    wrong = start(client, password="87654321")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()  # an unknown civil ID and a wrong password look the same
    for _ in range(3):
        start(client, password="00000000")
    r = start(client, password="11111111")  # the fifth wrong one locks
    assert r.json()["code"] == "claim_invalid"
    assert start(client).status_code == 401, "locked for 30 minutes even with the right password"
    assert admin_client.get(f"/api/v1/employees/{imported['id']}/claim").json()["locked"] is True


def test_failed_tries_per_address_are_capped(client, admin_client, imported):
    set_claim(admin_client, imported)
    for i in range(20):
        start(client, civil=f"2900101{i:05d}")
    r = start(client)
    assert r.status_code == 429 and r.json()["code"] == "claim_rate_limited"


def test_the_claim_session_is_this_phone_only_and_short(admin_client, client, imported, owner_db):
    set_claim(admin_client, imported)
    token = start(client).json()["claim_token"]
    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "another-phone", "phone": "+96550002222"})
    assert r.status_code == 401 and r.json()["code"] == "claim_session_invalid"
    other = make_driver(admin_client, imported["company_id"])
    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": other["phone"]})
    assert r.status_code == 409 and r.json()["code"] == "phone_taken"
    for _ in range(3):
        client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": "+96550002222"})
    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": "+96550002222"})
    assert r.status_code == 429 and r.json()["code"] == "otp_rate_limited"
    for _ in range(3):
        client.post(f"{A}/verify", json={"claim_token": token, "device_uid": "phone-0001", "code": "000000"})
    good = code_for("+96550002222")
    r = client.post(f"{A}/verify", json={"claim_token": token, "device_uid": "phone-0001", "code": good})
    assert r.status_code == 429 and r.json()["code"] == "otp_locked"
    owner_db.execute(text("UPDATE identity.driver_claims SET session_expires_at = now() - interval '1 second'"))
    owner_db.commit()
    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": "+96550002222"})
    assert r.json()["code"] == "claim_session_invalid"


def test_an_expired_or_revoked_password_is_refused(admin_client, client, imported, owner_db):
    set_claim(admin_client, imported, days=1)
    owner_db.execute(text("UPDATE identity.driver_claims SET expires_at = now() - interval '1 second'"))
    owner_db.commit()
    assert start(client).json()["code"] == "claim_invalid"
    set_claim(admin_client, imported)  # set again: open
    assert start(client).status_code == 200
    assert admin_client.delete(f"/api/v1/employees/{imported['id']}/claim").status_code == 204
    assert start(client).json()["code"] == "claim_invalid"
    assert admin_client.delete(f"/api/v1/employees/{imported['id']}/claim").json()["code"] == "claim_not_found"


def test_who_can_get_an_initial_password(admin_client, client, imported, company, new_client):
    bound = make_driver(admin_client, company["id"])
    from tests.conftest import bind_device

    bind_device(new_client(), bound["phone"])
    office = make_employee(admin_client, company["id"])
    out = set_claim(admin_client, imported, bound, office)
    assert out["set"] == 1
    assert sorted(s["code"] for s in out["skipped"]) == ["device_already_bound", "not_a_driver"]
    r = admin_client.post("/api/v1/driver-claims", json={"employee_ids": [imported["id"]], "password": "1234567"})
    assert r.status_code == 422  # at least 8 characters
    r = admin_client.post("/api/v1/driver-claims", json={"employee_ids": [str(uuid.uuid4())], "password": PASSWORD})
    assert r.status_code == 404
    make_user(admin_client, "viewer", permissions=["employees.view"])
    c = new_client()
    login(c, "viewer")
    r = c.post("/api/v1/driver-claims", json={"employee_ids": [imported["id"]], "password": PASSWORD})
    assert r.status_code == 403


def test_a_suspended_driver_cannot_claim(admin_client, client, imported, owner_db):
    set_claim(admin_client, imported)
    owner_db.execute(
        text("UPDATE people.employees SET phone = '+96550009999', app_access = 'suspended' WHERE civil_id = :c"),
        {"c": CIVIL},
    )
    owner_db.commit()
    assert start(client).json()["code"] == "claim_invalid"


def test_no_longer_a_driver_means_no_claim(admin_client, client, imported):
    set_claim(admin_client, imported)
    r = admin_client.patch(
        f"/api/v1/employees/{imported['id']}", json={"version": imported["version"], "is_driver": False}
    )
    assert r.status_code == 200, r.text
    assert start(client).json()["code"] == "claim_invalid"


# ------------------------------------------------------------------ without phone codes


def phone_codes(client, on: bool):
    version = client.get("/api/v1/settings").json()["driver_sign_in"]["version"]
    r = client.put("/api/v1/settings/driver_sign_in", json={"version": version, "value": {"phone_codes": on}})
    assert r.status_code == 200, r.text


def choose(client, token, password, device="phone-0001", model=None):
    body = {"claim_token": token, "device_uid": device, "password": password}
    return client.post(f"{A}/password", json=body | ({"model": model} if model else {}))


def own_sign_in(client, password, device, model=None):
    body = {"civil_id": CIVIL, "password": password, "device_uid": device}
    return client.post(A, json=body | ({"model": model} if model else {}))


def test_without_phone_codes_he_chooses_a_password_and_signs_in_with_it_on_any_phone(
    admin_client, client, imported, db
):
    assert client.get("/api/v1/driver/auth/methods").json() == {"phone_codes": True}
    phone_codes(admin_client, False)
    assert client.get("/api/v1/driver/auth/methods").json() == {"phone_codes": False}
    set_claim(admin_client, imported)
    claim = start(client).json()
    assert claim["next"] == "password" and claim["tokens"] is None
    token = claim["claim_token"]
    r = client.post(f"{A}/phone", json={"claim_token": token, "device_uid": "phone-0001", "phone": "+96550001111"})
    assert r.status_code == 409 and r.json()["code"] == "sign_in_method_changed"
    assert messaging.provider().sent == []  # no code goes anywhere
    for weak in (PASSWORD, CIVIL):  # the shared password and the civil ID everyone knows
        r = choose(client, token, weak)
        assert r.status_code == 422 and r.json()["code"] == "password_not_allowed", r.text
    r = choose(client, token, "my-own-pass-1", model="Galaxy A14")
    assert r.status_code == 200, r.text
    first = bearer(r.json())

    emp = admin_client.get(f"/api/v1/employees/{imported['id']}").json()
    assert (emp["phone"], emp["app_access"]) == (None, "active")  # the phone is the office's to record
    assert client.get("/api/v1/driver/onboarding", headers=first).json()["status"] == "draft"
    status = admin_client.get(f"/api/v1/employees/{imported['id']}/claim").json()
    assert status["open"] is False and status["used_phone"] is None and status["own_password_set_at"]
    assert start(client).json()["code"] == "claim_invalid"  # the initial password is spent

    # next month, another phone: his civil ID and his own password, nothing else
    r = own_sign_in(client, "my-own-pass-1", "phone-0002", model="Redmi 12")
    assert r.status_code == 200 and r.json()["next"] == "done" and r.json()["claim_token"] is None, r.text
    second = bearer(r.json()["tokens"])
    assert client.get("/api/v1/driver/onboarding", headers=second).status_code == 200
    assert client.get("/api/v1/driver/onboarding", headers=first).status_code == 401  # one phone at a time
    devices = admin_client.get(f"/api/v1/employees/{imported['id']}/devices").json()
    assert sorted((d["model"], d["revoked_at"] is None) for d in devices) == [("Galaxy A14", False), ("Redmi 12", True)]

    # a number may be someone else's SIM next month: no sign-in by phone code at all
    r = client.post("/api/v1/driver/auth/otp", json={"phone": "+96550001111", "device_uid": "phone-0003"})
    assert r.status_code == 403 and r.json()["code"] == "phone_sign_in_off"
    r = client.post(
        "/api/v1/driver/auth/verify", json={"phone": "+96550001111", "device_uid": "phone-0003", "code": "123456"}
    )
    assert r.status_code == 403 and r.json()["code"] == "phone_sign_in_off"
    actions = [a for (a,) in db.execute(text("SELECT action FROM audit.events ORDER BY id"))]
    assert {"driver.claimed", "employee.app_claimed"} <= set(actions) and actions.count("device.bound") == 2


def test_without_phone_codes_the_office_resets_a_forgotten_password(admin_client, client, imported):
    phone_codes(admin_client, False)
    set_claim(admin_client, imported)
    assert choose(client, start(client).json()["claim_token"], "first-pass-1").status_code == 200
    emp = admin_client.get(f"/api/v1/employees/{imported['id']}").json()
    body = {"version": emp["version"], "phone": "+96550002222"}
    r = admin_client.patch(f"/api/v1/employees/{imported['id']}", json=body)
    assert r.status_code == 200, r.text  # the number the office handed him this month: contact data
    out = set_claim(admin_client, imported, password="reset-2026")  # his phone is bound: a reset, not a skip
    assert out["set"] == 1 and out["skipped"] == []
    assert own_sign_in(client, "first-pass-1", "phone-0002").json()["code"] == "claim_invalid"  # stops at once
    claim = start(client, password="reset-2026", device="phone-0002").json()
    assert claim["next"] == "password"
    assert choose(client, claim["claim_token"], "second-pass-2", device="phone-0002").status_code == 200
    assert admin_client.get(f"/api/v1/employees/{imported['id']}").json()["phone"] == "+96550002222"  # kept

    # the lock covers his own password too
    for _ in range(5):
        own_sign_in(client, "wrong-pass-0", "phone-0009")
    assert own_sign_in(client, "second-pass-2", "phone-0002").status_code == 401
    assert admin_client.get(f"/api/v1/employees/{imported['id']}/claim").json()["locked"] is True


def test_turning_phone_codes_on_or_off_midway(admin_client, client, imported):
    phone_codes(admin_client, False)
    set_claim(admin_client, imported)
    token = start(client).json()["claim_token"]
    phone_codes(admin_client, True)
    r = choose(client, token, "my-own-pass-1")
    assert r.status_code == 409 and r.json()["code"] == "sign_in_method_changed"
    phone_codes(admin_client, False)
    assert choose(client, token, "my-own-pass-1").status_code == 200
    phone_codes(admin_client, True)
    # with phone codes on again his own password opens nothing: he changes phones by code
    assert own_sign_in(client, "my-own-pass-1", "phone-0002").json()["code"] == "claim_invalid"


def test_without_phone_codes_the_app_needs_no_phone_but_a_link_still_does(admin_client, imported):
    r = admin_client.put(f"/api/v1/employees/{imported['id']}/app-access", json={"app_access": "active"})
    assert r.status_code == 422 and r.json()["code"] == "driver_phone_required"
    phone_codes(admin_client, False)
    r = admin_client.put(f"/api/v1/employees/{imported['id']}/app-access", json={"app_access": "active"})
    assert r.status_code == 200 and r.json()["app_access"] == "active", r.text
    link = f"/api/v1/employees/{imported['id']}/activation-link"
    r = admin_client.post(link, json={"channel": "whatsapp"})
    assert r.status_code == 422 and r.json()["code"] == "driver_phone_required"  # nowhere to send it
    assert admin_client.post(link, json={"channel": "manual"}).status_code == 201  # shown at the office
    r = admin_client.post("/api/v1/activation-links/bulk", json={"employee_ids": [imported["id"]]})
    assert r.status_code == 202 and r.json()["skipped"] == [{"id": imported["id"], "reason": "driver_phone_required"}]
    out = admin_client.post("/api/v1/activation-links/bulk", json={"all_unbound": True}).json()
    assert (out["queued"], out["skipped"]) == (0, [])  # "everyone" means everyone a link can reach: no noise


def test_without_phone_codes_the_review_outcome_reaches_him_in_the_app_only(admin_client, client, imported, company):
    from tests.test_onboarding import full_draft, save, submission_id

    make_vehicle(admin_client, company["id"], km=39_000, plate_number="45 678")
    phone_codes(admin_client, False)
    set_claim(admin_client, imported)
    h = bearer(choose(client, start(client).json()["claim_token"], "my-own-pass-1").json())
    save(client, h, full_draft(client, h, "45678"))
    assert client.post("/api/v1/driver/onboarding/submit", headers=h).json()["status"] == "submitted"
    r = admin_client.post(f"/api/v1/onboarding/{submission_id(admin_client)}/reject", json={"reason": "صورة غير واضحة"})
    assert r.status_code == 200, r.text
    assert messaging.provider().sent == []  # no number on file: nothing to send, and nothing breaks
    assert client.get("/api/v1/driver/onboarding", headers=h).json()["review_note"] == "صورة غير واضحة"
