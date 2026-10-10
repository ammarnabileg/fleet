"""Pay schemes as rule blocks: a scheme version holds an ordered list of blocks (the rules designer); the four old
calculators stay for the versions that used them. Every existing scheme gets its terms written as blocks, giving the
same money, as its next version from the first month no approved payroll paid on it (its latest version itself when
none did); a payroll line keeps how the blocks reasoned (trace).

Revision ID: 0051_scheme_blocks
Revises: 0050_platform_fields
"""

import json
from datetime import timedelta
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0051_scheme_blocks"
down_revision = "0050_platform_fields"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE payroll.schemes DROP CONSTRAINT schemes_calculator_check;
ALTER TABLE payroll.schemes ADD CONSTRAINT schemes_calculator_check
    CHECK (calculator IN ('platform_rates', 'per_order', 'batch', 'tiered_target', 'blocks'));
-- the version's rules as ordered blocks; NULL: the scheme's calculator with the version's numbers
ALTER TABLE payroll.scheme_versions ADD COLUMN blocks jsonb;
-- what each block did or did not do, and why (the payslip's full calculation)
ALTER TABLE payroll.lines ADD COLUMN trace jsonb NOT NULL DEFAULT '[]'::jsonb;
"""


def _m(v) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.001")))


def _block(type_, params, condition=None, group=None):
    return {"type": type_, "params": params, "condition": condition or [], "on_exception": "none", "group": group,
            "label": None}  # fmt: skip


def blocks_of(calc: str, v: dict) -> list[dict]:
    """The same as app/modules/payroll/rules/convert.py at this revision: kept here so the migration never changes."""
    steps: dict[str, list] = {}
    for st in sorted(v["steps"] or [], key=lambda x: Decimal(str(x["threshold"]))):
        steps.setdefault(st["kind"], []).append(st)
    missing = []
    if v["missing_order_rate"]:
        missing = [_block("missing_orders", {"source": "orders", "target": v["target_orders"],
                                             "rate": _m(v["missing_order_rate"])})]  # fmt: skip
    if calc == "per_order":
        return [_block("per_order", {"rate": _m(v["per_order"]), "source": "orders"}), *missing]
    if calc == "batch":
        rates = [
            {"batch": int(Decimal(str(s["threshold"]))), "rate": _m(s["amount"])} for s in steps.get("batch_rate", [])
        ]
        return [_block("batch_rate", {"rates": rates, "personal_rate": False}), *missing]
    if calc == "tiered_target":
        reduced = {"rate": _m(v["reduced_rate"]), "mode": "replace"}
        out = [
            _block("per_order", {"rate": _m(v["per_order"]), "source": "orders"}),
            _block("price_change", reduced, [{"fact": "star_day_failed", "op": "is_true"}], "reduced"),
        ]
        if steps.get("marks_reduce"):
            at = int(Decimal(str(steps["marks_reduce"][0]["threshold"])))
            out.append(_block("price_change", dict(reduced), [{"fact": "marks", "op": "gte", "value": at}], "reduced"))
        not_reduced = [{"fact": "price_changed", "op": "is_false"}]
        tiers = [
            {"from": int(Decimal(str(s["threshold"]))), "amount": _m(s["amount"])} for s in steps.get("tier_bonus", [])
        ]
        if tiers:
            out.append(_block("tier_bonus", {"source": "orders", "mode": "highest", "tiers": tiers},
                              [] if v["bonus_when_reduced"] else not_reduced))  # fmt: skip
        out += missing
        table = [
            {"from": int(Decimal(str(s["threshold"]))), "amount": _m(s["amount"])}
            for s in steps.get("marks_deduction", [])
        ]
        if table:
            out.append(_block("attendance_marks", {"mode": "table", "table": table},
                              [] if v["marks_when_reduced"] else not_reduced))  # fmt: skip
        return out
    return []  # platform_rates: the platform's own rule, as before


def upgrade() -> None:
    op.execute(SQL)
    bind = op.get_bind()
    schemes = bind.execute(
        sa.text("SELECT id, calculator FROM payroll.schemes WHERE calculator <> 'platform_rates'")
    ).all()
    for scheme_id, calc in schemes:
        latest = (
            bind.execute(
                sa.text(
                    "SELECT * FROM payroll.scheme_versions WHERE scheme_id = :s ORDER BY effective_month DESC LIMIT 1"
                ),
                {"s": scheme_id},
            )
            .mappings()
            .first()
        )
        if latest is None:
            continue
        blocks = blocks_of(calc, dict(latest))
        if not blocks:
            continue
        paid = bind.execute(
            sa.text(
                "SELECT max(r.month) FROM payroll.lines l JOIN payroll.runs r ON r.id = l.run_id "
                "WHERE l.scheme_id = :s AND r.status <> 'draft'"
            ),  # fmt: skip
            {"s": scheme_id},
        ).scalar()
        target = latest["effective_month"]
        if paid is not None and paid >= target:
            target = (paid.replace(day=28) + timedelta(days=4)).replace(day=1)  # the month after the last one paid
        if target == latest["effective_month"]:  # never paid on: the latest version is written as blocks
            bind.execute(sa.text("UPDATE payroll.scheme_versions SET blocks = CAST(:b AS jsonb) WHERE id = :id"),
                         {"b": json.dumps(blocks), "id": latest["id"]})  # fmt: skip
            continue
        bind.execute(
            sa.text(
                "INSERT INTO payroll.scheme_versions (scheme_id, version_no, effective_month, per_order, target_orders,"
                " required_valid_days, missing_order_rate, reduced_rate, bonus_when_reduced, marks_when_reduced,"
                " floor_at_zero, company_covers, steps, note, created_by, blocks)"
                " SELECT scheme_id, version_no + 1, :m, per_order, target_orders, required_valid_days, missing_order_rate,"
                " reduced_rate, bonus_when_reduced, marks_when_reduced, floor_at_zero, company_covers, steps,"
                " 'rules designer: the same terms as blocks', created_by, CAST(:b AS jsonb)"
                " FROM payroll.scheme_versions WHERE id = :id"
            ),
            {"m": target, "b": json.dumps(blocks), "id": latest["id"]},
        )
    op.execute("SELECT public.fleet_apply_grants();")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
