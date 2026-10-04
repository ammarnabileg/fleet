"""Every test session gets a brand-new PostgreSQL database built by the real migrations.

TEST_ADMIN_DATABASE_URL points at a server where the user may CREATE DATABASE, e.g.
postgresql+psycopg://postgres:postgres@localhost:5432/postgres (CI) or a local socket.
"""

import os
import pathlib
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
SCHEMAS = ("org", "identity", "audit", "integrations")
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def database_url():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    name = f"fleet_test_{uuid.uuid4().hex[:10]}"
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
        c.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fleet_app') "
                "THEN CREATE ROLE fleet_app LOGIN; END IF; END $$"
            )
        )
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    os.environ.update(
        DATABASE_URL=url, SECRET_KEY="test-secret-key-not-for-production", COOKIE_SECURE="false", APP_ENV="test"
    )
    from app.core import config, db

    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    db._session_factory.cache_clear()

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    yield url
    db.get_engine().dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
def clean(database_url):
    from app.core.db import get_engine
    from app.modules.org import service as org

    tables = []
    with get_engine().begin() as c:
        for schema in SCHEMAS:
            tables += [
                f'"{schema}"."{t}"'
                for t in c.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema}
                ).scalars()
            ]
        c.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    org._cache.clear()
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
    totp = pyotp.parse_uri(secret_uri)
    import time

    return totp.at(time.time() + 30 * offset_steps)


@pytest.fixture
def org_setup(admin_client):
    """One company with two branches, A and B."""
    company = admin_client.post("/api/v1/companies", json={"name_ar": "الشركة", "name_en": "Company"}).json()
    a = admin_client.post(
        "/api/v1/branches", json={"company_public_id": company["public_id"], "name_ar": "فرع أ", "name_en": "Branch A"}
    ).json()
    b = admin_client.post(
        "/api/v1/branches", json={"company_public_id": company["public_id"], "name_ar": "فرع ب", "name_en": "Branch B"}
    ).json()
    return {"company": company, "a": a, "b": b}


def make_user(admin_client, username, *, permissions=(), branch_ids=(), all_branches=False, role=None):
    role = role or f"role_{username.lower()}"
    r = admin_client.post(
        "/api/v1/roles", json={"code": role, "name_ar": "دور", "name_en": "Role", "permissions": list(permissions)}
    )
    assert r.status_code in (201, 409), r.text
    r = admin_client.post(
        "/api/v1/users",
        json={
            "username": username,
            "full_name": f"User {username}",
            "password": PASSWORD,
            "role_codes": [role],
            "branch_ids": list(branch_ids),
            "all_branches": all_branches,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
