"""Sign-in codes go out over WhatsApp (Evolution API). A delivery failure never changes the answer to the phone,
and the supervisors are told when the channel is down."""

import json

import httpx
import pytest

from app.core import messaging
from app.core.config import get_settings
from tests.conftest import login, make_driver, make_user


def evolution(handler):
    return messaging.EvolutionProvider(
        "https://evo.example/", "secret-key", "fleet otp", transport=httpx.MockTransport(handler)
    )


def test_evolution_send_text_request():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(201, json={"key": {"id": "ABC"}, "status": "PENDING"})

    evolution(handler).send("+96550001234", "رمز الدخول: 123456")
    (r,) = seen
    assert r.method == "POST" and str(r.url) == "https://evo.example/message/sendText/fleet%20otp"
    assert r.headers["apikey"] == "secret-key"
    assert json.loads(r.read()) == {"number": "96550001234", "text": "رمز الدخول: 123456", "linkPreview": False}


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(400, json={"response": {"message": ["not on WhatsApp"]}}),
        lambda request: httpx.Response(401),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused")),
    ],
)
def test_evolution_failures_become_delivery_errors(handler):
    with pytest.raises(messaging.DeliveryError):
        evolution(handler).send("+96550001234", "x")


def test_evolution_connection_state():
    def handler(request):
        assert request.url.raw_path == b"/instance/connectionState/fleet%20otp"
        return httpx.Response(200, json={"instance": {"instanceName": "fleet otp", "state": "close"}})

    assert evolution(handler).connection_state() == "close"


class Broken:
    def __init__(self, state="close"):
        self.state = state

    def send(self, to, text):
        raise messaging.DeliveryError("evolution api answered 500")

    def connection_state(self):
        if self.state == "unreachable":
            raise messaging.DeliveryError("down")
        return self.state


def test_a_failed_delivery_gives_the_same_answer_and_alerts(admin_client, client, new_client, company, monkeypatch):
    d = make_driver(admin_client, company["id"])
    monkeypatch.setattr(messaging, "provider", lambda: Broken())
    r = client.post("/api/v1/driver/auth/otp", json={"phone": d["phone"], "device_uid": "device-0001"})
    assert (r.status_code, r.json()) == (202, {"status": "sent"})
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
    assert [a["kind"] for a in alerts] == ["otp_delivery_failed"] and "WhatsApp" in alerts[0]["message"]
    make_user(admin_client, "map_only", permissions=["tracking.live"])
    c = new_client()
    login(c, "map_only")
    assert c.get("/api/v1/alerts").json() == []


def test_channel_down_alerts_and_closes_itself(admin_client, db, monkeypatch):
    from app.modules.identity import service as identity

    for state in ("close", "unreachable"):
        monkeypatch.setattr(messaging, "provider", lambda state=state: Broken(state))
        assert identity.check_messaging_channel(db) == state
    alerts = admin_client.get("/api/v1/alerts").json()
    assert [a["kind"] for a in alerts] == ["messaging_down"]  # one open alert while it stays down
    monkeypatch.setattr(messaging, "provider", lambda: Broken("open"))
    assert identity.check_messaging_channel(db) == "open"
    assert admin_client.get("/api/v1/alerts").json() == []


def test_production_refuses_a_missing_or_unsafe_configuration(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="must not be used in production"):
        messaging.LogProvider()
    monkeypatch.setattr(settings, "messaging_provider", "whatsapp")
    messaging.provider.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="EVOLUTION_API_URL"):
            messaging.provider()
        monkeypatch.setattr(settings, "evolution_api_url", "https://evo.example")
        monkeypatch.setattr(settings, "evolution_api_key", "k")
        monkeypatch.setattr(settings, "evolution_instance", "fleet")
        assert isinstance(messaging.provider(), messaging.EvolutionProvider)
    finally:
        messaging.provider.cache_clear()
