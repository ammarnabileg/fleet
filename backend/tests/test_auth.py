from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import PASSWORD, login, make_user, totp_code


def test_login_me_and_logout_with_csrf(client, superuser):
    csrf = login(client, superuser)
    me = client.get("/api/v1/auth/me").json()
    assert me["username"] == "admin" and me["is_superuser"] and me["csrf_token"] == csrf
    r = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_is_httponly_and_samesite(client, superuser):
    r = client.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_unknown_user_and_wrong_password_look_the_same(client, superuser, db):
    a = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever-password"})
    b = client.post("/api/v1/auth/login", json={"username": superuser, "password": "wrong-password"})
    assert a.status_code == b.status_code == 401
    assert a.json()["code"] == b.json()["code"] == "invalid_credentials"
    assert db.execute(text("SELECT count(*) FROM audit.events WHERE action = 'auth.login_failed'")).scalar() == 2


def test_lockout_after_five_failures(client, superuser, db):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": superuser, "password": "wrong-password"})
    r = client.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD})
    assert r.status_code == 423 and r.json()["code"] == "account_locked"
    assert db.execute(text("SELECT count(*) FROM audit.events WHERE action = 'auth.locked'")).scalar() == 1
    db.execute(text("UPDATE identity.users SET locked_until = now() - interval '1 minute'"))
    db.commit()
    login(client, superuser)


def test_mfa_enrolment_login_rotation_and_replay(client, new_client, superuser):
    login(client, superuser)
    uri = client.post("/api/v1/auth/mfa/setup").json()["otpauth_uri"]
    assert client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}).status_code == 422
    assert client.post("/api/v1/auth/mfa/enable", json={"code": totp_code(uri)}).status_code == 204

    second = new_client()
    r = second.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD})
    assert r.json() == {"mfa_required": True, "csrf_token": None}
    pending_cookie = second.cookies.get("fleet_session")
    assert second.get("/api/v1/auth/me").status_code == 401  # password alone is not enough
    assert second.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code == 401
    code = totp_code(uri, offset_steps=1)  # the enrolment already used this step
    r = second.post("/api/v1/auth/mfa/verify", json={"code": code})
    assert r.status_code == 200 and r.json()["csrf_token"]
    assert second.cookies.get("fleet_session") != pending_cookie  # new session id after MFA
    assert second.get("/api/v1/auth/me").status_code == 200

    third = new_client()
    third.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD})
    r = third.post("/api/v1/auth/mfa/verify", json={"code": code})
    assert r.status_code == 401 and r.json()["code"] == "invalid_code"  # the same code cannot be used twice


def test_idle_session_expires(client, superuser, db):
    login(client, superuser)
    db.execute(text("UPDATE identity.sessions SET last_seen_at = now() - interval '3 hours'"))
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_change_signs_out_other_sessions(client, new_client, superuser, admin_client):
    other = new_client()
    login(other, superuser)
    r = admin_client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert r.status_code == 422 and r.json()["code"] == "password_too_short"
    r = admin_client.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "a-much-longer-password"}
    )
    assert r.status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401
    assert admin_client.get("/api/v1/auth/me").status_code == 200


def test_deactivating_a_user_ends_their_sessions(admin_client, new_client):
    user = make_user(admin_client, "clerk", all_branches=True)
    c = new_client()
    login(c, "clerk")
    r = admin_client.patch(f"/api/v1/users/{user['public_id']}", json={"version": user["version"], "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.post("/api/v1/auth/login", json={"username": "clerk", "password": PASSWORD}).status_code == 401


def test_pending_mfa_session_expires_after_five_minutes(client, superuser, db):
    login(client, superuser)
    uri = client.post("/api/v1/auth/mfa/setup").json()["otpauth_uri"]
    client.post("/api/v1/auth/mfa/enable", json={"code": totp_code(uri)})
    fresh = client.__class__(client.app)
    fresh.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD})
    db.execute(
        text("UPDATE identity.sessions SET created_at = :t WHERE mfa_passed = false"),
        {"t": datetime.now(UTC) - timedelta(minutes=6)},
    )
    db.commit()
    r = fresh.post("/api/v1/auth/mfa/verify", json={"code": totp_code(uri, offset_steps=1)})
    assert r.status_code == 401 and r.json()["code"] == "not_authenticated"
