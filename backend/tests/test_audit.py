import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.conftest import APP_ROLE_PASSWORD, login, make_user


def test_audit_trail_is_append_only(admin_client, db):
    assert db.execute(text("SELECT count(*) FROM audit.events")).scalar() > 0
    for sql in ("UPDATE audit.events SET action = 'x'", "DELETE FROM audit.events"):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
        db.rollback()


def test_audit_view_is_company_scoped(admin_client, new_client, companies):
    a, b = companies["a"], companies["b"]
    for company in (a, b):
        admin_client.patch(f"/api/v1/companies/{company['public_id']}", json={"version": 1, "phone": "22000000"})
    make_user(admin_client, "auditor_a", permissions=["audit.view"], company_ids=[a["id"]])
    c = new_client()
    login(c, "auditor_a")
    events = c.get("/api/v1/audit", params={"entity_type": "company"}).json()
    assert events and {e["company_id"] for e in events} == {a["id"]}
    everything = admin_client.get("/api/v1/audit", params={"action": "company"}).json()
    assert {e["company_id"] for e in everything} == {a["id"], b["id"]}


def test_application_role_has_least_privilege(database_url, admin_client):
    eng = create_engine(make_url(database_url["url"]).set(username="fleet_app", password=APP_ROLE_PASSWORD))
    with eng.connect() as c:
        assert c.execute(text("SHOW statement_timeout")).scalar() == "30s"
        c.execute(text("INSERT INTO audit.events (actor_type, action, entity_type) VALUES ('system', 't', 't')"))
        c.commit()
        assert c.execute(text("SELECT count(*) FROM i18n.languages")).scalar() == 2  # later schemas are granted too
        with pytest.raises(DBAPIError, match="permission denied"):
            c.execute(text("UPDATE audit.events SET action = 'x'"))
        c.rollback()
        with pytest.raises(DBAPIError, match="permission denied"):
            c.execute(text("TRUNCATE audit.events"))
    eng.dispose()
