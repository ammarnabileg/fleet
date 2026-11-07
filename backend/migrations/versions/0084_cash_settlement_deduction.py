"""A cash receipt keeps the id the panel gave it, so a double click or a resent request records it once.

What an ending driver still owes in cash, recovered through payroll: his settlement now makes a deduction of its
own kind ("cash"), taken from his final pay, and its posting clears the payroll recovery account the settlement
filled (before, nothing deducted it: his pay stayed whole and the account kept the debit).

Revision ID: 0084_cash_settlement_deduction
Revises: 0083_factory_reset
"""

from alembic import op

revision = "0084_cash_settlement_deduction"
down_revision = "0083_factory_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE payroll.deductions DROP CONSTRAINT deductions_source_type_check;
ALTER TABLE payroll.deductions ADD CONSTRAINT deductions_source_type_check
    CHECK (source_type IN ('accident', 'fine', 'advance', 'sim', 'other', 'cash'));
ALTER TABLE cash.receipts ADD COLUMN client_ref uuid CONSTRAINT receipts_client_ref_key UNIQUE;
""")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
