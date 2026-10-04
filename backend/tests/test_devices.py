"""UAT-16: a new device needs an OTP, revokes the previous one and alerts the supervisor; tokens rotate; access
stops the moment it should."""

import uuid
from datetime import timedelta

from sqlalchemy import text

from app.core import sms
from tests.conftest import bearer, bind_device, login, make_driver, make_employee, make_user, otp_code


def _request(client, phone, device_uid="device-0001"):
    return client.post("/api/v1/driver/auth/otp", json={"phone": phone, "device_uid": device_uid})


def _verify(client, phone, code, device_uid="device-0001"):
    return client.post("/api/v1/driver/auth/verify", json={"phone": phone, "device_uid": device_uid, "code": code})


def test_the_otp_request_reveals_nothing(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    not_allowed = make_driver(admin_client, company["id"], app=False)  # a driver without app access
    office = make_employee(admin_client, company["id"], phone="+96569990000")
    for phone in (d["phone"], not_allowed["phone"], office["phone"], "+96560000001"):
        r = _request(client, phone)
        assert (r.status_code, r.json()) == (202, {"status": "sent"})
    assert [m.to for m in sms.provider().sent] == [d["phone"]]
    assert "{" not in sms.provider().sent[0].text
    assert _verify(client, "+96560000001", "123456").json()["code"] == "otp_invalid"


def test_rate_limit_and_three_attempts(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    for _ in range(3):
        assert _request(client, d["phone"]).status_code == 202
    r = _request(client, d["phone"])
    assert r.status_code == 429 and r.json()["code"] == "otp_rate_limited"
    assert _request(client, "+96560000002").status_code == 202  # per phone
    code = otp_code(d["phone"])
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    assert _verify(client, d["phone"], wrong).json()["code"] == "otp_invalid"
    assert _verify(client, d["phone"], wrong).json()["code"] == "otp_invalid"
    r = _verify(client, d["phone"], wrong)
    assert r.status_code == 429 and r.json()["code"] == "otp_locked"
    r = _verify(client, d["phone"], code)  # even the right code, once locked
    assert r.status_code == 429


def test_expired_code_and_wrong_device(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    _request(client, d["phone"], "device-aaaa")
    code = otp_code(d["phone"])
    assert _verify(client, d["phone"], code, "device-bbbb").json()["code"] == "otp_invalid"
    db.execute(text("UPDATE identity.otp_challenges SET expires_at = now() - interval '1 second'"))
    db.commit()
    assert _verify(client, d["phone"], code, "device-aaaa").json()["code"] == "otp_invalid"


def test_uat16_new_device_replaces_the_old_one_and_alerts_the_supervisor(admin_client, client, new_client, company, db):
    d = make_driver(admin_client, company["id"])
    bind_device(client, d["phone"], device_uid="phone-aaaa", model="Old phone")
    first = bind_device(client, d["phone"], device_uid="phone-aaaa", model="Old phone")  # same phone again
    assert client.get("/api/v1/driver/today", headers=bearer(first)).status_code == 200
    assert admin_client.get("/api/v1/alerts").json() == []  # a first binding, or the same phone, is normal
    second = bind_device(client, d["phone"], device_uid="phone-bbbb", model="New phone")
    assert client.get("/api/v1/driver/today", headers=bearer(first)).status_code == 401
    assert client.get("/api/v1/driver/today", headers=bearer(second)).status_code == 200
    r = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "ar"}).json()
    assert [a["kind"] for a in alerts] == ["device_replaced"] and "New phone" in alerts[0]["message"]
    make_user(admin_client, "dispatcher", permissions=["tracking.live"])
    c = new_client()
    login(c, "dispatcher")
    assert c.get("/api/v1/alerts").json() == []  # devices.manage only
    devices = admin_client.get(f"/api/v1/employees/{d['id']}/devices").json()
    assert [(x["model"], x["revoked_reason"]) for x in devices][:2] == [("New phone", None), ("Old phone", "replaced")]
    events = db.execute(text("SELECT count(*) FROM integrations.outbox WHERE event_type = 'driver.device_bound'"))
    assert events.scalar() == 3


def test_refresh_rotates_and_a_reused_token_revokes_the_family(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    t1 = bind_device(client, d["phone"])
    t2 = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t1["refresh_token"]}).json()
    assert t2["refresh_token"] != t1["refresh_token"]
    assert client.get("/api/v1/driver/today", headers=bearer(t1)).status_code == 401  # rotated away
    assert client.get("/api/v1/driver/today", headers=bearer(t2)).status_code == 200
    # an immediate retry of the same rotation (lost answer) still works ...
    t3 = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    assert t3.status_code == 200
    t3 = t3.json()
    assert client.get("/api/v1/driver/today", headers=bearer(t2)).status_code == 401
    # ... but an old token used later is theft: the whole family is revoked
    db.execute(
        text(
            "UPDATE identity.device_tokens SET revoked_at = revoked_at - interval '5 minutes' "
            "WHERE revoked_at IS NOT NULL"
        )
    )
    db.commit()
    r = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t2["refresh_token"]})
    assert r.status_code == 401 and r.json()["code"] == "token_reused"
    assert client.get("/api/v1/driver/today", headers=bearer(t3)).status_code == 401
    assert client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t3["refresh_token"]}).status_code == 401


def test_access_stops_at_once_on_suspension_and_unbinding(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    t = bind_device(client, d["phone"])
    admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "suspended"})
    r = client.get("/api/v1/driver/today", headers=bearer(t))
    assert r.status_code == 403 and r.json()["code"] == "driver_access_disabled"
    assert client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "active"})
    t = bind_device(client, d["phone"])
    device = admin_client.get(f"/api/v1/employees/{d['id']}/devices").json()[0]
    assert admin_client.post(f"/api/v1/devices/{device['id']}/revoke").status_code == 204
    assert client.get("/api/v1/driver/today", headers=bearer(t)).status_code == 401
    assert admin_client.post(f"/api/v1/devices/{uuid.uuid4()}/revoke").status_code == 404


def test_logout_and_bad_tokens(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    t = bind_device(client, d["phone"])
    assert client.post("/api/v1/driver/auth/logout", headers=bearer(t)).status_code == 204
    assert client.get("/api/v1/driver/today", headers=bearer(t)).status_code == 401
    r = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r.status_code == 401  # a logout is final, even within the retry grace
    t = bind_device(client, d["phone"])
    rotated = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t["refresh_token"]}).json()
    client.post("/api/v1/driver/auth/logout", headers=bearer(rotated))
    r = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r.status_code == 401  # nor can an older token of the family come back
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": f"Basic {t['access_token']}"}):
        assert client.get("/api/v1/driver/today", headers=headers).json()["code"] == "device_not_authenticated"
    # an office session is not a device token, and a device token is not an office session
    assert admin_client.get("/api/v1/driver/today").status_code == 401


def test_devices_admin_is_scoped(admin_client, new_client, companies):
    d = make_driver(admin_client, companies["b"]["id"])
    make_user(admin_client, "devices_a", permissions=["devices.manage"], company_ids=[companies["a"]["id"]])
    c = new_client()
    login(c, "devices_a")
    assert c.get(f"/api/v1/employees/{d['id']}/devices").status_code == 404
    r = c.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "suspended"})
    assert r.status_code == 404


def test_access_token_expires(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    t = bind_device(client, d["phone"])
    db.execute(text("UPDATE identity.device_tokens SET expires_at = now() - interval '1 second' WHERE kind = 'access'"))
    db.commit()
    assert client.get("/api/v1/driver/today", headers=bearer(t)).status_code == 401
    t2 = client.post("/api/v1/driver/auth/refresh", json={"refresh_token": t["refresh_token"]}).json()
    assert client.get("/api/v1/driver/today", headers=bearer(t2)).status_code == 200
    assert timedelta(seconds=t2["expires_in"]) == timedelta(minutes=15)
