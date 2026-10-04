"""Tests run against a real PostgreSQL. The migrations run once into a template database; every test then gets
a fresh copy of it, seed data included (languages, role templates, main branch).

TEST_ADMIN_DATABASE_URL points at a server where the user may CREATE DATABASE, e.g.
postgresql+psycopg://postgres:postgres@localhost:5432/postgres (CI) or a local socket.
"""

import os
import pathlib
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


def _url(name: str) -> str:
    return make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_engine():
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def database_url(admin_engine):
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
        DATABASE_URL=_url(live), SECRET_KEY="test-secret-key-not-for-production", COOKIE_SECURE="false", APP_ENV="test"
    )
    from app.core import config, db

    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    db._session_factory.cache_clear()
    yield {"url": _url(live), "template": template, "live": live}
    db.get_engine().dispose()
    with admin_engine.connect() as c:
        for name in (live, template):
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(autouse=True)
def fresh_database(database_url, admin_engine):
    from app.core.db import get_engine
    from app.modules.i18n import service as i18n
    from app.modules.org import service as org

    get_engine().dispose()
    with admin_engine.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{database_url["live"]}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{database_url["live"]}" TEMPLATE "{database_url["template"]}"'))
    org._cache.clear()
    i18n._effective_cache.clear()
    yield


@pytest.fixture
def db(database_url):
    from app.core.db import new_session

    with new_session() as session:
        yield session


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
