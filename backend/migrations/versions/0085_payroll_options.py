"""Payroll options the client decides in the settings: the installments' cap may also be a share of the net (what the
month leaves after its own charges); the run keeps that choice as it keeps the others.

Revision ID: 0085_payroll_options
Revises: 0084_cash_settlement_deduction
"""

from alembic import op

revision = "0085_payroll_options"
down_revision = "0084_cash_settlement_deduction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE payroll.runs DROP CONSTRAINT runs_cap_base_check;
ALTER TABLE payroll.runs ADD CONSTRAINT runs_cap_base_check CHECK (cap_base IN ('basic', 'gross', 'net'));
""")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
