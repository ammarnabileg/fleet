"""Activation links: the supervisor sends a one-time link to the driver's registered WhatsApp number; opening it
binds the phone without an OTP (first registration, or a supervisor-led phone change)."""

import re
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core import messaging
from tests.conftest import bearer, bind_device, login, make_driver, make_employee, make_user


def _link(admin_client, driver, channel="whatsapp"):
    return admin_client.post(f"/api/v1/employees/{driver['id']}/activation-link", json={"channel": channel})


def _token_sent_to(phone):
    message = next(m for m in reversed(messaging.provider().sent) if m.to == phone)
    return re.search(r"/activate#t=([A-Za-z0-9_-]+)", message.text).group(1)


def _activate(client, token, device_uid=None, model="Galaxy A15"):
    return client.post(
        "/api/v1/driver/auth/activate",
        json={"token": token, "device_uid": device_uid or uuid.uuid4().hex, "platform": "android", "model": model},
    )


def test_whatsapp_link_binds_the_phone_without_an_otp(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    r = _link(admin_client, d)
    assert r.status_code == 201
    out = r.json()
    assert out["url"] is None  # never shown to the sender
    assert out["sent_to"].startswith("+965") and out["sent_to"][-4:] == d["phone"][-4:] and "•" in out["sent_to"]
    message = messaging.provider().sent[-1]
    assert message.to == d["phone"] and "http://localhost:8080/activate#t=" in message.text and "24" in message.text
    assert d["name"]["ar"] in message.text and d["name"]["en"] in message.text  # Arabic, then English
    assert "أكمل بياناتك" in message.text and "complete your details" in message.text  # first time: registration
    assert message.text.count("/activate#t=") == 2 and len(set(re.findall(r"#t=(\S+)", message.text))) == 1
    tokens = _activate(client, _token_sent_to(d["phone"]))
    assert tokens.status_code == 200
    assert client.get("/api/v1/driver/today", headers=bearer(tokens.json())).status_code == 200
    assert not [m for m in messaging.provider().sent if "رمز" in m.text]  # no OTP was involved
    via = db.execute(text("SELECT after->>'via' FROM audit.events WHERE action = 'device.bound'")).scalar()
    assert via == "activation_link"


def test_a_link_works_once_and_a_new_one_cancels_the_old_one(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    _link(admin_client, d)
    first = _token_sent_to(d["phone"])
    _link(admin_client, d)
    second = _token_sent_to(d["phone"])
    r = _activate(client, first)
    assert r.status_code == 401 and r.json()["code"] == "activation_link_invalid"
    assert _activate(client, second).status_code == 200
    assert _activate(client, second).status_code == 401  # used


def test_an_expired_link_or_a_driver_without_access_is_refused(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    _link(admin_client, d)
    token = _token_sent_to(d["phone"])
    db.execute(text("UPDATE identity.activation_links SET expires_at = now() - interval '1 second'"))
    db.commit()
    assert _activate(client, token).status_code == 401
    _link(admin_client, d)
    token = _token_sent_to(d["phone"])
    admin_client.put(f"/api/v1/employees/{d['id']}/app-access", json={"app_access": "suspended"})
    assert _activate(client, token).status_code == 401


def test_who_can_receive_a_link(admin_client, company):
    office = make_employee(admin_client, company["id"])
    r = _link(admin_client, office)
    assert r.status_code == 422 and r.json()["code"] == "not_a_driver"
    no_app = make_driver(admin_client, company["id"], app=False)
    r = _link(admin_client, no_app)
    assert r.status_code == 422 and r.json()["code"] == "driver_app_not_active"
    r = admin_client.post(
        f"/api/v1/employees/{no_app['id']}/activation-link", json={"channel": "whatsapp", "phone": "+96599999999"}
    )
    assert r.status_code == 422  # the number is always the registered one


def test_rate_limit_per_driver(admin_client, company):
    d = make_driver(admin_client, company["id"])
    for _ in range(5):
        assert _link(admin_client, d).status_code == 201
    r = _link(admin_client, d)
    assert r.status_code == 429 and r.json()["code"] == "activation_rate_limited"


def test_manual_link_is_shown_for_the_office(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    sent_before = len(messaging.provider().sent)
    out = admin_client.post(
        f"/api/v1/employees/{d['id']}/activation-link", json={"channel": "manual", "onboarding": False}
    ).json()
    assert out["onboarding"] is False
    assert out["sent_to"] is None and out["url"].startswith("http://localhost:8080/activate#t=")
    assert len(messaging.provider().sent) == sent_before
    assert _activate(client, out["url"].split("#t=")[1]).status_code == 200


def test_activating_replaces_the_bound_phone_and_alerts(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    old = bind_device(client, d["phone"], model="Old phone")
    _link(admin_client, d)
    new = _activate(client, _token_sent_to(d["phone"]), model="New phone").json()
    assert client.get("/api/v1/driver/today", headers=bearer(old)).status_code == 401
    assert client.get("/api/v1/driver/today", headers=bearer(new)).status_code == 200
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["device_replaced"]


def test_permission_and_company_scope(admin_client, new_client, companies):
    d = make_driver(admin_client, companies["b"]["id"])
    make_user(admin_client, "devices_a", permissions=["devices.manage"], company_ids=[companies["a"]["id"]])
    make_user(admin_client, "viewer", permissions=["employees.view"])
    c = new_client()
    login(c, "devices_a")
    assert _link(c, d).status_code == 404
    c = new_client()
    login(c, "viewer")
    assert _link(c, d).status_code == 403


class FakeEvolution:
    def __init__(self, error):
        self.error = error

    def send(self, to, text_):
        raise self.error

    def connection_state(self):
        return "open"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (messaging.NotOnWhatsApp("no"), 422, "phone_not_on_whatsapp"),
        (messaging.DeliveryError("down"), 502, "message_not_delivered"),
    ],
)
def test_delivery_problems_are_told_to_the_sender_and_leave_no_usable_link(
    admin_client, company, db, monkeypatch, error, status, code
):
    d = make_driver(admin_client, company["id"])
    monkeypatch.setattr(messaging, "provider", lambda: FakeEvolution(error))
    r = _link(admin_client, d)
    assert r.status_code == status and r.json()["code"] == code
    assert db.execute(text("SELECT count(*) FROM identity.activation_links")).scalar() == 0


def test_evolution_reports_a_number_without_whatsapp():
    def handler(request):
        body = request.read().decode()
        assert '"linkPreview":false' in body.replace(" ", "")
        return httpx.Response(
            400,
            json={
                "status": 400,
                "error": "Bad Request",
                "response": {
                    "message": [{"jid": "96550001234@s.whatsapp.net", "exists": False, "number": "96550001234"}]
                },
            },
        )

    provider = messaging.EvolutionProvider("https://evo.example", "k", "fleet", transport=httpx.MockTransport(handler))
    with pytest.raises(messaging.NotOnWhatsApp):
        provider.send("+96550001234", "x")
