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


def test_existing_schemes_become_their_version_1(database_url, admin_engine):
    """Migration 0046: a scheme set up before versions keeps its terms as version 1, from its creation month or the
    earliest month a driver was put on it."""
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
        command.upgrade(cfg, "0044_vehicle_claims_superseded")
        engine = create_engine(_url(name))
        with engine.begin() as c:
            platform = c.scalar(
                text("INSERT INTO payroll.platforms (code, name) VALUES ('kx', :n) RETURNING id"),
                {"n": '{"ar": "ك", "en": "k"}'},
            )
            scheme = c.scalar(
                text(
                    "INSERT INTO payroll.schemes (platform_id, code, name, calculator, per_order, missing_order_rate, "
                    "reduced_rate, company_covers, created_by, created_at) VALUES "
                    """(:p, 'standard', '{"ar": "س", "en": "s"}', 'tiered_target', 0.350, 0.350, 0.200, '{gas}', 1, """
                    "'2026-03-31 22:30:00+00') RETURNING id"
                ),
                {"p": platform},
            )
            c.execute(
                text(
                    "INSERT INTO payroll.scheme_steps (scheme_id, kind, threshold, amount) VALUES "
                    "(:s, 'tier_bonus', 450, 50), (:s, 'marks_reduce', 5, NULL)"
                ),
                {"s": scheme},
            )
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT version_no, effective_month, per_order, missing_order_rate, reduced_rate, company_covers, "
                    "bonus_when_reduced, floor_at_zero, steps FROM payroll.scheme_versions WHERE scheme_id = :s"
                ),
                {"s": scheme},
            ).all()
        engine.dispose()
        assert len(row) == 1
        no, month, per_order, missing, reduced, covers, bonus, floor, steps = row[0]
        assert (no, str(month)) == (1, "2026-04-01")  # 31 March 22:30 UTC is already April in Kuwait
        assert (str(per_order), str(missing), str(reduced), covers, bonus, floor) == (
            "0.350",
            "0.350",
            "0.200",
            ["gas"],
            False,
            True,
        )
        assert steps == [
            {"kind": "marks_reduce", "threshold": "5.000", "amount": None},
            {"kind": "tier_bonus", "threshold": "450.000", "amount": "50.000"},
        ]
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_existing_installs_start_with_the_payroll_gate_closed(database_url, admin_engine):
    """Migration 0049: an install that already has payroll settings gets live_approval_enabled false, the rest kept."""
    import json
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
        command.upgrade(cfg, "0048_objections")
        engine = create_engine(_url(name))
        with engine.begin() as c:
            c.execute(
                text("INSERT INTO org.settings (key, value) VALUES ('payroll', :v)"),
                {"v": json.dumps({"max_deduction_percent": "50.00", "deduction_cap_base": "basic"})},
            )
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            value = c.scalar(text("SELECT value FROM org.settings WHERE key = 'payroll'"))
        engine.dispose()
        assert value == {
            "max_deduction_percent": "50.00",
            "deduction_cap_base": "basic",
            "live_approval_enabled": False,
        }
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
