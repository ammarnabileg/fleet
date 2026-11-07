"""The system back to new before going live: the system administrator only, with their password and the phrase; the
business's records emptied and the set-up kept, in one transaction. The success is checked inside a transaction that
is rolled back (the suite's database is shared)."""

from sqlalchemy import text

from tests.conftest import PASSWORD, login, make_driver, make_user, make_vehicle

R = "/api/v1/system/factory-reset"
PHRASE = "امسح كل البيانات"


def test_only_the_system_administrator_with_the_password_and_the_phrase(admin_client, new_client):
    make_user(admin_client, "reset_nobody", permissions=["settings.view"])
    c = new_client()
    login(c, "reset_nobody")
    r = c.post(R, json={"password": PASSWORD, "confirm": PHRASE})
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    r = admin_client.post(R, json={"password": "wrong", "confirm": PHRASE})
    assert r.status_code == 403 and r.json()["code"] == "invalid_credentials"
    r = admin_client.post(R, json={"password": PASSWORD, "confirm": "امسح"})
    assert r.status_code == 422 and r.json()["code"] == "reset_phrase_mismatch"


def test_the_records_go_the_set_up_stays_and_only_the_administrator_remains(admin_client, db, company):
    from app.modules.org import service as org

    make_user(admin_client, "reset_clerk", permissions=["employees.view"])
    make_driver(admin_client, company["id"])
    make_vehicle(admin_client, company["id"])

    def count(table, where="true"):
        return db.execute(text(f"SELECT count(*) FROM {table} WHERE {where}")).scalar()  # noqa: S608 - fixed names

    kept = ("org.companies", "org.branches", "payroll.platforms", "payroll.schemes", "identity.roles",
            "finance.accounts", "documents.document_types")  # fmt: skip
    kept_before = {t: count(t) for t in kept}
    audit_before = count("audit.events")
    admin = db.execute(text("SELECT id, public_id FROM identity.users WHERE username = 'admin'")).one()
    commit = db.commit
    db.commit = db.flush  # checked, then rolled back
    try:
        org.factory_reset(db, actor_user_id=admin.id, actor_public_id=admin.public_id)  # as the application role
        for t in ("people.employees", "fleet.vehicles", "fleet.custodies", "tracking.positions", "cash.journals",
                  "finance.entries", "payroll.deductions", "accidents.accidents", "maintenance.centers",
                  "accidents.insurers", "notifications.alerts", "identity.devices"):  # fmt: skip
            assert count(t) == 0, t
        assert {t: count(t) for t in kept_before} == kept_before
        assert db.execute(text("SELECT username FROM identity.users")).scalars().all() == ["admin"]
        assert count("cash.accounts", "kind IN ('driver', 'petty')") == 0
        assert count("audit.events") == audit_before + 1
        assert count("audit.events", "action = 'system.factory_reset'") >= 1
    finally:
        db.commit = commit
        db.rollback()
    assert count("people.employees") > 0  # rolled back: the suite goes on
