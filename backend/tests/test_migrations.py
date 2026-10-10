import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.models  # noqa: F401
from app.core.db import Base, get_engine, include_name


def test_models_match_the_migrated_schema(database_url):
    with get_engine().connect() as c:
        ctx = MigrationContext.configure(
            c, opts={"include_schemas": True, "include_name": include_name, "compare_type": True}
        )
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff


@pytest.mark.parametrize("in_use", ["accountant_account", "entry"])
def test_a_chart_in_use_is_kept_and_the_drivers_salaries_start_on_its_salaries_account(
    database_url, admin_engine, in_use
):
    """Migration 0023 replaces only the untouched placeholder chart: once the accountant added an account, or anything
    was entered, theirs stays, and the new role points where the salaries already go."""
    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from tests.conftest import BACKEND, _url

    name = f"fleet_mig_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        cfg.set_main_option("sqlalchemy.url", _url(name).replace("%", "%%"))
        command.upgrade(cfg, "0022_approvals")
        engine = create_engine(_url(name))
        with engine.begin() as c:
            if in_use == "accountant_account":
                c.execute(
                    text(
                        "INSERT INTO finance.accounts (code, name, type) "
                        """VALUES ('7001', '{"ar": "س", "en": "x"}', 'expense')"""
                    )
                )
            else:  # a draft entry on the placeholder chart: fuel paid from the treasury
                entry = c.scalar(
                    text(
                        "INSERT INTO finance.entries (entry_date, source_kind, source_id, source_ref, description) "
                        "VALUES (current_date, 'expense', 1, 'EXP-1', 'fuel') RETURNING id"
                    )
                )
                c.execute(
                    text(
                        "INSERT INTO finance.entry_lines (entry_id, line_no, account_id, debit, credit) "
                        "SELECT :e, 1, id, 5, 0 FROM finance.accounts WHERE code = '5104' UNION ALL "
                        "SELECT :e, 2, id, 0, 5 FROM finance.accounts WHERE code = '1101'"
                    ),
                    {"e": entry},
                )
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            codes = set(c.scalars(text("SELECT code FROM finance.accounts")))
            roles = dict(c.execute(text("SELECT role, account_id FROM finance.account_roles")).all())
        engine.dispose()
        assert {"1101", "5101"} <= codes and "5110" not in codes
        assert roles["driver_salaries_expense"] == roles["salaries_expense"]
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_the_platforms_are_seeded_only_on_an_install_without_any(database_url, admin_engine, db):
    """Migration 0045: a fresh install gets the two platforms, once; an install that already set its own platforms
    keeps them and gets nothing added."""
    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from tests.conftest import BACKEND, _url

    seeded = db.execute(text("SELECT code, daily_fields, driver_fields FROM payroll.platforms ORDER BY id")).all()
    assert [tuple(r) for r in seeded] == [
        ("keeta", ["valid_day"], ["valid_days", "orders", "hours"]),
        ("talabat", ["orders", "cash"], ["orders"]),
    ]

    name = f"fleet_mig_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        cfg.set_main_option("sqlalchemy.url", _url(name).replace("%", "%%"))
        command.upgrade(cfg, "0044_vehicle_claims_superseded")
        engine = create_engine(_url(name))
        with engine.begin() as c:
            assert c.scalar(text("SELECT count(*) FROM payroll.platforms")) == 0
            c.execute(text("""INSERT INTO payroll.platforms (code, name) VALUES ('own', '{"ar": "س", "en": "x"}')"""))
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            codes = list(c.scalars(text("SELECT code FROM payroll.platforms")))
        engine.dispose()
        assert codes == ["own"]
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
