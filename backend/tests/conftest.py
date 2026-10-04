"""Tests run against a real PostgreSQL. The migrations run once into a template database; every test then gets
a fresh copy of it, seed data included (languages, role templates, main branch). The application connects as the
least-privilege fleet_app role, as in production, so a missing grant fails the tests.

TEST_ADMIN_DATABASE_URL points at a server where the user may CREATE DATABASE, e.g.
postgresql+psycopg://postgres:postgres@localhost:5432/postgres (CI) or a local socket.
"""

import os
import pathlib
import re
import time
import uuid

import pyotp
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres")
PASSWORD = "correct-horse-battery"
APP_ROLE_PASSWORD = "fleet-app-test-only"


def _url(name: str, *, app_role: bool = False) -> str:
    url = make_url(ADMIN_URL).set(database=name)
    if app_role:
        url = url.set(username="fleet_app", password=APP_ROLE_PASSWORD)
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_engine():
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def database_url(admin_engine, tmp_path_factory):
    suffix = uuid.uuid4().hex[:10]
    template, live = f"fleet_tpl_{suffix}", f"fleet_test_{suffix}"
    with admin_engine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{template}"'))
        c.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fleet_app') "
                "THEN CREATE ROLE fleet_app LOGIN; END IF; END $$"
            )
        )
        c.execute(text(f"ALTER ROLE fleet_app LOGIN PASSWORD '{APP_ROLE_PASSWORD}'"))  # CI connects over TCP
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _url(template).replace("%", "%%"))
    command.upgrade(cfg, "head")

    os.environ.update(
        DATABASE_URL=_url(live, app_role=True),
        SECRET_KEY="test-secret-key-not-for-production",
        COOKIE_SECURE="false",
        APP_ENV="test",
        FILES_DIR=str(tmp_path_factory.mktemp("files")),
    )
    from app.core import config, db

    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    db._session_factory.cache_clear()
    yield {"url": _url(live), "app_url": _url(live, app_role=True), "template": template, "live": live}
    db.get_engine().dispose()
    with admin_engine.connect() as c:
        for name in (live, template):
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(autouse=True)
def fresh_database(database_url, admin_engine):
    from app.core import messaging
    from app.core.db import get_engine
    from app.modules.i18n import service as i18n
    from app.modules.integrations import service as integrations
    from app.modules.org import service as org
    from app.modules.tracking import service as tracking

    get_engine().dispose()
    with admin_engine.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{database_url["live"]}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{database_url["live"]}" TEMPLATE "{database_url["template"]}"'))
    org._cache.clear()
    integrations._cache.clear()
    integrations._built.clear()
    i18n._effective_cache.clear()
    tracking._partitions.clear()
    messaging.provider().sent.clear()
    yield


@pytest.fixture
def db(database_url):
    """A session as the application role."""
    from app.core.db import new_session

    with new_session() as session:
        yield session


@pytest.fixture
def owner_db(database_url):
    """A session as the schema owner, for checks the application role may not do."""
    engine = create_engine(database_url["url"])
    with engine.connect() as c:
        yield c
    engine.dispose()


@pytest.fixture
def app(database_url):
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def new_client(app):
    return lambda: TestClient(app)


@pytest.fixture
def superuser(db):
    from app.modules.identity import service

    service.bootstrap_superuser(db, username="admin", full_name="System Administrator", password=PASSWORD)
    return "admin"


def login(client: TestClient, username: str, password: str = PASSWORD) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["mfa_required"] is False
    csrf = r.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    return csrf


@pytest.fixture
def admin_client(client, superuser):
    login(client, superuser)
    return client


def totp_code(secret_uri: str, offset_steps: int = 0) -> str:
    return pyotp.parse_uri(secret_uri).at(time.time() + 30 * offset_steps)


def name(ar: str, en: str) -> dict:
    return {"ar": ar, "en": en}


@pytest.fixture
def companies(admin_client):
    """Two legal entities, A and B."""
    a = admin_client.post("/api/v1/companies", json={"name": name("شركة أ", "Company A"), "cr_number": "CR-1"})
    b = admin_client.post("/api/v1/companies", json={"name": name("شركة ب", "Company B"), "cr_number": "CR-2"})
    assert a.status_code == b.status_code == 201, (a.text, b.text)
    return {"a": a.json(), "b": b.json()}


def make_user(admin_client, username, *, permissions=(), company_ids=None, role=None):
    """company_ids=None means all companies."""
    role = role or f"role_{username.lower()}"
    r = admin_client.post(
        "/api/v1/roles", json={"code": role, "name": name("دور", "Role"), "permissions": list(permissions)}
    )
    assert r.status_code in (201, 409), r.text
    r = admin_client.post(
        "/api/v1/users",
        json={
            "username": username,
            "full_name": f"User {username}",
            "password": PASSWORD,
            "role_codes": [role],
            "all_companies": company_ids is None,
            "company_ids": list(company_ids or []),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ M1 helpers


def jpeg() -> bytes:
    """A distinct image every call: a reused photo is flagged."""
    return b"\xff\xd8\xff\xe0" + os.urandom(64)


def upload(client, data: bytes | None = None, *, path="/api/v1/files", name="photo.jpg") -> str:
    r = client.post(path, files={"file": (name, data or jpeg(), "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


_counter = iter(range(10_000, 99_999))


def make_employee(admin_client, company_id, *, driver=False, phone=None, **extra) -> dict:
    n = next(_counter)
    body = {
        "employee_number": f"E{n}",
        "name": name(f"موظف {n}", f"Employee {n}"),
        "company_id": company_id,
        "is_driver": driver,
        "phone": phone or (f"+9655{n:07d}" if driver else None),
        **extra,
    }
    r = admin_client.post("/api/v1/employees", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def make_driver(admin_client, company_id, *, app=True, **extra) -> dict:
    driver = make_employee(admin_client, company_id, driver=True, **extra)
    if app:
        r = admin_client.put(f"/api/v1/employees/{driver['id']}/app-access", json={"app_access": "active"})
        assert r.status_code == 200, r.text
        driver = r.json()
    return driver


def make_vehicle(admin_client, company_id, *, km=10_000, **extra) -> dict:
    n = next(_counter)
    r = admin_client.post(
        "/api/v1/vehicles", json={"plate_number": f"{n}", "company_id": company_id, "last_odometer_km": km, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def hand_over(admin_client, vehicle, driver, *, km=None, **extra) -> dict:
    body = {
        "vehicle_id": vehicle["id"],
        "driver_id": driver["id"],
        "odometer_km": km if km is not None else vehicle["last_odometer_km"] or 0,
        "photo_sha256": upload(admin_client),
        **extra,
    }
    r = admin_client.post("/api/v1/custodies", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def otp_code(phone: str) -> str:
    from app.core import messaging

    text_ = next(m.text for m in reversed(messaging.provider().sent) if m.to == phone)
    return re.search(r"\b(\d{6})\b", text_).group(1)


def bind_device(client, phone: str, device_uid: str | None = None, model="Pixel 8") -> dict:
    device_uid = device_uid or uuid.uuid4().hex
    r = client.post("/api/v1/driver/auth/otp", json={"phone": phone, "device_uid": device_uid})
    assert r.status_code == 202, r.text
    r = client.post(
        "/api/v1/driver/auth/verify",
        json={"phone": phone, "device_uid": device_uid, "code": otp_code(phone), "platform": "android", "model": model},
    )
    assert r.status_code == 200, r.text
    return r.json()


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def company(companies):
    return companies["a"]
