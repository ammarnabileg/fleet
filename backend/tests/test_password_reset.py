"""An office user who forgot the password sets a new one with a code sent to the phone on the account (BRD FR-USR-03):
the page tells nobody which usernames exist, a code serves once and only three tries, the new password signs every
session out, and an account with two-step verification needs the authenticator's code too."""

from sqlalchemy import text

from app.core import messaging
from tests.conftest import PASSWORD, login, make_user, otp_code, totp_code

R = "/api/v1/auth/password-reset"
NEW = "a-brand-new-password-42"


def with_phone(admin_client, username: str, phone: str) -> dict:
    make_user(admin_client, username, permissions=["vehicles.view"])
    [u] = [u for u in admin_client.get("/api/v1/users").json() if u["username"] == username]
    r = admin_client.patch(f"/api/v1/users/{u['public_id']}", json={"version": u["version"], "phone": phone})
    assert r.status_code == 200, r.text
    return u


def sent_to(phone: str) -> list[str]:
    return [m.text for m in messaging.provider().sent if m.to == phone]


def test_a_code_on_the_phone_sets_a_new_password_once(admin_client, client, new_client):
    phone = "+96550001111"
    with_phone(admin_client, "forgetful", phone)
    signed_in = new_client()
    login(signed_in, "forgetful")

    r = client.post(R, json={"username": "  Forgetful "})  # as typed on the page
    assert r.status_code == 202
    [message] = sent_to(phone)
    assert "{" not in message and "10" in message
    code = otp_code(phone)

    r = client.post(f"{R}/confirm", json={"username": "forgetful", "code": code, "new_password": "short"})
    assert r.status_code == 422 and r.json()["code"] == "password_too_short"  # costs no try
    r = client.post(f"{R}/confirm", json={"username": "forgetful", "code": code, "new_password": NEW})
    assert r.status_code == 204, r.text
    assert signed_in.get("/api/v1/auth/me").status_code == 401  # signed out everywhere
    login(new_client(), "forgetful", NEW)
    assert client.post("/api/v1/auth/login", json={"username": "forgetful", "password": PASSWORD}).status_code == 401
    r = client.post(f"{R}/confirm", json={"username": "forgetful", "code": code, "new_password": NEW + "x"})
    assert r.status_code == 401 and r.json()["code"] == "otp_invalid"  # the code served once

    events = [e["action"] for e in admin_client.get("/api/v1/audit", params={"entity_type": "user"}).json()]
    assert "user.password_reset_by_code" in events and "auth.password_reset_requested" in events


def test_the_same_answer_for_any_username_and_nothing_sent(admin_client, client):
    make_user(admin_client, "no_phone_user", permissions=["vehicles.view"])
    before = len(messaging.provider().sent)
    for name in ("nobody_here", "no_phone_user"):
        r = client.post(R, json={"username": name})
        assert r.status_code == 202 and r.content in (b"", b"null")
        r = client.post(f"{R}/confirm", json={"username": name, "code": "123456", "new_password": NEW})
        assert r.status_code == 401 and r.json()["code"] == "otp_invalid"
    assert len(messaging.provider().sent) == before


def test_three_tries_then_locked_and_requests_limited(admin_client, client):
    phone = "+96550002222"
    with_phone(admin_client, "guesser", phone)
    client.post(R, json={"username": "guesser"})
    code = otp_code(phone)
    wrong = "000000" if code != "000000" else "111111"
    for expected in (401, 401, 429):
        r = client.post(f"{R}/confirm", json={"username": "guesser", "code": wrong, "new_password": NEW})
        assert r.status_code == expected
    r = client.post(f"{R}/confirm", json={"username": "guesser", "code": code, "new_password": NEW})
    assert r.status_code == 429 and r.json()["code"] == "otp_locked"  # the right code is too late

    client.post(R, json={"username": "guesser"})
    client.post(R, json={"username": "guesser"})
    r = client.post(R, json={"username": "guesser"})  # a fourth in fifteen minutes
    assert r.status_code == 429 and r.json()["code"] == "otp_rate_limited"
    for _ in range(3):
        client.post(R, json={"username": "ghost_user"})
    assert client.post(R, json={"username": "ghost_user"}).status_code == 429  # unknown names are limited alike


def test_an_expired_or_disabled_account_gets_no_new_password(admin_client, client, db):
    phone = "+96550003333"
    u = with_phone(admin_client, "slowpoke", phone)
    client.post(R, json={"username": "slowpoke"})
    code = otp_code(phone)
    db.execute(text("UPDATE identity.password_reset_codes SET expires_at = now() - interval '1 second'"))
    db.commit()
    r = client.post(f"{R}/confirm", json={"username": "slowpoke", "code": code, "new_password": NEW})
    assert r.status_code == 401

    client.post(R, json={"username": "slowpoke"})
    code = otp_code(phone)
    u = next(x for x in admin_client.get("/api/v1/users").json() if x["username"] == "slowpoke")
    r = admin_client.patch(f"/api/v1/users/{u['public_id']}", json={"version": u["version"], "is_active": False})
    assert r.status_code == 200, r.text
    r = client.post(f"{R}/confirm", json={"username": "slowpoke", "code": code, "new_password": NEW})
    assert r.status_code == 401
    before = len(sent_to(phone))
    assert client.post(R, json={"username": "slowpoke"}).status_code == 202
    assert len(sent_to(phone)) == before  # a disabled account is sent no code


def test_two_step_accounts_need_the_authenticator_too_and_a_lock_is_lifted(admin_client, client, new_client):
    phone = "+96550004444"
    with_phone(admin_client, "careful", phone)
    own = new_client()
    login(own, "careful")
    uri = own.post("/api/v1/auth/mfa/setup").json()["otpauth_uri"]
    assert own.post("/api/v1/auth/mfa/enable", json={"code": totp_code(uri)}).status_code == 204
    for _ in range(5):  # locked out by wrong passwords
        new_client().post("/api/v1/auth/login", json={"username": "careful", "password": "wrong-password"})
    assert (
        new_client().post("/api/v1/auth/login", json={"username": "careful", "password": PASSWORD}).status_code == 423
    )

    client.post(R, json={"username": "careful"})
    code = otp_code(phone)
    r = client.post(f"{R}/confirm", json={"username": "careful", "code": code, "new_password": NEW})
    assert r.status_code == 401 and r.json()["code"] == "mfa_code_invalid"  # WhatsApp alone is not enough
    r = client.post(
        f"{R}/confirm",
        json={"username": "careful", "code": code, "new_password": NEW, "mfa_code": totp_code(uri, offset_steps=1)},
    )
    assert r.status_code == 204, r.text
    r = new_client().post("/api/v1/auth/login", json={"username": "careful", "password": NEW})
    assert r.status_code == 200 and r.json()["mfa_required"] is True  # unlocked, and still two steps
