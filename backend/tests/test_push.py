"""Push to the driver's phone through Firebase Cloud Messaging (BRD FR-NTF-01), set up from the control panel: the
service account key signs the token request, each notice goes once to the phone that registered, in its language;
a token Firebase no longer knows is forgotten; nothing is sent until push is switched on."""

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import text

from app.modules.integrations import service as integrations
from app.modules.notifications import service as notifications
from tests.conftest import bearer, bind_device, make_driver

C = "/api/v1/integrations/connections"
APP = {
    "enabled": True,
    "app_id": "1:1234567890:android:0a1b2c3d4e5f6a7b",
    "api_key": "AIzaSyA-test-client-key-12345",
    "sender_id": "1234567890",
}
TOKEN_A, TOKEN_B, TOKEN_C = ("fcm-token-" + c * 30 for c in "abc")


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class FakeGoogle:
    """The token endpoint and FCM: checks the signed assertion, records each message, refuses dead tokens."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.account = {
            "type": "service_account",
            "project_id": "fleet-test",
            "client_email": "push@fleet-test.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
            "private_key": self.key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ).decode(),
        }
        self.sent: list[dict] = []
        self.tokens_issued = 0
        self.dead: set[str] = set()
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, text="unavailable")
        if request.url.host == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            header, claims, signature = form["assertion"].split(".")
            self.key.public_key().verify(
                _b64decode(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
            )  # raises if not signed with the account's key
            body = json.loads(_b64decode(claims))
            assert body["iss"] == self.account["client_email"] and body["scope"].endswith("firebase.messaging")
            self.tokens_issued += 1
            return httpx.Response(200, json={"access_token": f"at-{self.tokens_issued}", "expires_in": 3600})
        assert request.url.path == "/v1/projects/fleet-test/messages:send"
        assert request.headers["authorization"].startswith("Bearer at-")
        message = json.loads(request.content)["message"]
        if message["token"] in self.dead:
            return httpx.Response(
                404, json={"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}
            )
        self.sent.append(message)
        return httpx.Response(200, json={"name": "projects/fleet-test/messages/1"})


@pytest.fixture
def google(monkeypatch):
    g = FakeGoogle()
    monkeypatch.setattr(integrations, "_fcm_transport", lambda loaded: httpx.MockTransport(g.handler))
    return g


def switch_on(admin_client, google, **config) -> dict:
    r = admin_client.put(
        f"{C}/push",
        json={"version": 0, "config": APP | config, "secrets": {"service_account": json.dumps(google.account)}},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_switched_on_from_the_panel_after_google_accepts_the_key(admin_client, client, google):
    # a key that is not a service account is refused; nothing saved
    r = admin_client.put(f"{C}/push", json={"version": 0, "config": APP, "secrets": {"service_account": "not json!"}})
    assert r.status_code == 422 and r.json()["code"] == "connection_check_failed"
    assert client.get("/api/v1/driver/app-config").json()["push"] is None
    saved = switch_on(admin_client, google)
    assert saved["check_ok"] is True and saved["secrets"]["service_account"]["set"] is True
    assert google.tokens_issued == 1  # tried before saving
    assert "private_key" not in json.dumps(saved)  # write-only
    # the app gets the public values it registers with, the project from the key
    assert client.get("/api/v1/driver/app-config").json()["push"] == {
        "project_id": "fleet-test",
        "app_id": APP["app_id"],
        "api_key": APP["api_key"],
        "sender_id": APP["sender_id"],
    }
    listed = {c["kind"]: c for c in admin_client.get(C).json()}
    assert listed["push"]["status"] == {"phones": 0}


def test_each_notice_goes_once_to_the_registered_phone_in_its_language(
    admin_client, client, new_client, google, db, company
):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    other = new_client()
    d2 = make_driver(admin_client, company["id"])
    h2 = bearer(bind_device(other, d2["phone"]))
    r = admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "15"})
    assert r.status_code == 201
    assert notifications.push_pending(db) == 0 and google.sent == []  # push not on yet: it waits

    switch_on(admin_client, google)
    assert notifications.push_pending(db) == 0  # on, but no phone registered: still waiting
    r = client.post("/api/v1/driver/push-token", headers=h, json={"token": TOKEN_A, "lang": "en"})
    assert r.status_code == 204
    assert other.post("/api/v1/driver/push-token", headers=h2, json={"token": TOKEN_B}).status_code == 204
    assert notifications.push_pending(db) == 1
    (msg,) = google.sent
    assert msg["token"] == TOKEN_A
    assert msg["notification"]["title"] == "New notification" and "15.000" in msg["notification"]["body"]
    assert "receipt no." in msg["notification"]["body"]  # the language the app registered with
    assert msg["data"]["kind"] == "receipt_issued" and msg["data"]["entity_type"] == "receipt"
    assert notifications.push_pending(db) == 0  # once

    # the other driver's phone in the default language; a token Firebase forgot is dropped, not retried
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": d2["id"], "amount": "7"})
    assert notifications.push_pending(db) == 1 and google.sent[-1]["notification"]["title"] == "إشعار جديد"
    google.dead.add(TOKEN_A)
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "3"})
    assert notifications.push_pending(db) == 0
    token = text(
        "SELECT push_token FROM identity.devices WHERE revoked_at IS NULL "
        "AND employee_id = (SELECT id FROM people.employees WHERE public_id = :p)"
    )
    assert db.scalar(token, {"p": d["id"]}) is None
    # the app sends a new token: what waited goes out
    client.post("/api/v1/driver/push-token", headers=h, json={"token": TOKEN_C, "lang": "en"})
    assert notifications.push_pending(db) == 1 and google.sent[-1]["token"] == TOKEN_C
    assert {c["kind"]: c for c in admin_client.get(C).json()}["push"]["status"] == {"phones": 2}


def test_firebase_down_stops_the_pass_and_the_next_one_sends(admin_client, client, google, db, company):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    switch_on(admin_client, google)
    client.post("/api/v1/driver/push-token", headers=h, json={"token": "fcm-token-" + "d" * 30})
    for amount in ("1", "2"):
        admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": amount})
    google.down = True
    assert notifications.push_pending(db) == 0
    google.down = False
    assert notifications.push_pending(db) == 2


def test_a_phone_signed_out_or_replaced_gets_nothing(admin_client, client, google, db, company):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    switch_on(admin_client, google)
    client.post("/api/v1/driver/push-token", headers=h, json={"token": "fcm-token-" + "e" * 30})
    assert client.post("/api/v1/driver/auth/logout", headers=h).status_code == 204
    admin_client.post("/api/v1/cash/receipts", json={"driver_id": d["id"], "amount": "5"})
    assert notifications.push_pending(db) == 0 and google.sent == []
    assert client.post("/api/v1/driver/push-token", json={"token": "x" * 30}).status_code == 401
