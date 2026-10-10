"""Request limits by client address (BRD section 8): a guess counts only when it fails, so an office signing in all
day is never stopped while a script guessing is, right password included, once over the limit; a WhatsApp code sent
counts every time; an address listed as exempt (the office on sign-up day) is never limited; the window passes; and
uploads are counted per user or device rather than per address."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.clock import utcnow
from app.core.config import get_settings
from tests.conftest import PASSWORD, jpeg, login, make_user


@pytest.fixture
def tight(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_sign_in_per_15min", 3)
    monkeypatch.setattr(s, "rate_uploads_per_hour", 2)
    monkeypatch.setattr(s, "rate_otp_send_per_hour", 2)
    return s


def _login(client, password):
    return client.post("/api/v1/auth/login", json={"username": "admin", "password": password})


def test_failed_sign_ins_are_limited_by_address_and_right_ones_are_not(app, superuser, tight, monkeypatch):
    office = TestClient(app, client=("203.0.113.7", 50000))
    for _ in range(6):  # twice the limit: signing in is not guessing
        assert _login(office, PASSWORD).status_code == 200
    for _ in range(3):
        assert _login(office, "not the password").status_code == 401  # counted, though the request failed
    r = _login(office, PASSWORD)
    assert r.status_code == 429 and r.json()["code"] == "too_many_requests" and 1 <= r.json()["params"]["minutes"] <= 15
    # another address is not limited by this one
    assert _login(TestClient(app, client=("198.51.100.20", 50000)), PASSWORD).status_code == 200
    # the window passes
    later = utcnow() + timedelta(minutes=15)
    monkeypatch.setattr(ratelimit, "utcnow", lambda: later)
    assert _login(office, PASSWORD).status_code == 200


def test_an_exempt_network_is_never_limited(app, superuser, tight, monkeypatch):
    monkeypatch.setattr(tight, "rate_limit_exempt", "10.20.0.0/16, 192.0.2.1")
    for address in ("10.20.3.4", "192.0.2.1"):
        c = TestClient(app, client=(address, 50000))
        for _ in range(5):
            assert _login(c, "not the password").status_code in (401, 423)  # the account lock still applies
    c = TestClient(app, client=("10.21.0.1", 50000))  # outside the network
    for _ in range(3):
        _login(c, "not the password")
    assert _login(c, PASSWORD).status_code == 429


def test_uploads_are_counted_per_user_not_per_address(app, superuser, admin_client, tight):
    def up(client):
        return client.post("/api/v1/files", files={"file": ("p.jpg", jpeg(), "application/octet-stream")})

    assert [up(admin_client).status_code for _ in range(3)] == [201, 201, 429]
    make_user(admin_client, "clerk", permissions=["documents.manage"])
    clerk = TestClient(app)  # the same address as the admin
    login(clerk, "clerk")
    assert up(clerk).status_code == 201


def test_every_code_sent_counts(app, tight):
    phone = TestClient(app, client=("203.0.113.9", 50000))
    body = {"phone": "+96550000001", "device_uid": "device-1"}
    codes = [phone.post("/api/v1/driver/auth/otp", json=body).status_code for _ in range(3)]
    assert codes[2] == 429 and 429 not in codes[:2]  # sent or refused by the switch, each one counts
