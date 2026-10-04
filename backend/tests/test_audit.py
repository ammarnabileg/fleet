import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.conftest import login, make_user


def test_audit_trail_is_append_only(admin_client, db):
    assert db.execute(text("SELECT count(*) FROM audit.events")).scalar() > 0
    for sql in ("UPDATE audit.events SET action = 'x'", "DELETE FROM audit.events"):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
        db.rollback()


def test_audit_view_is_branch_scoped(admin_client, new_client, org_setup):
    a, b = org_setup["a"], org_setup["b"]
    for branch in (a, b):
        admin_client.patch(f"/api/v1/branches/{branch['public_id']}", json={"version": 1, "name_en": "Renamed"})
    make_user(admin_client, "auditor_a", permissions=["audit.view"], branch_ids=[a["id"]])
    c = new_client()
    login(c, "auditor_a")
    events = c.get("/api/v1/audit", params={"entity_type": "branch"}).json()
    assert events and {e["branch_id"] for e in events} == {a["id"]}
    everything = admin_client.get("/api/v1/audit", params={"action": "branch"}).json()
    assert {e["branch_id"] for e in everything} == {a["id"], b["id"]}


def test_application_role_has_least_privilege(database_url, admin_client):
    url = make_url(database_url).set(username="fleet_app", password=None)
    eng = create_engine(url)
    with eng.connect() as c:
        assert c.execute(text("SHOW statement_timeout")).scalar() == "30s"
        c.execute(text("INSERT INTO audit.events (actor_type, action, entity_type) VALUES ('system', 't', 't')"))
        c.commit()
        with pytest.raises(DBAPIError, match="permission denied"):
            c.execute(text("UPDATE audit.events SET action = 'x'"))
        c.rollback()
        with pytest.raises(DBAPIError, match="permission denied"):
            c.execute(text("TRUNCATE audit.events"))
    eng.dispose()
