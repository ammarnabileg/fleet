"""The treasury on screen is the books: money that leaves a branch treasury outside the cash ledger (an expense paid
from it, a supplier's invoice paid later from it, an advance) is a posted cash journal of kind "disbursement"
(treasury -X, disbursements +X), one per document, so the treasury balance per branch goes down with it. The
disbursements account is company-wide like adjustments. Its document already credits the treasury in the books, so
the journal itself makes no entry (app.modules.finance.posting). An expense names the branch whose treasury paid it
(older expenses keep none). Cash taken from the bank back to a treasury is a posted "bank_withdrawal" (treasury +Z,
bank -Z).

Revision ID: 0037_treasury
Revises: 0036_manual_entries
"""

from alembic import op

revision = "0037_treasury"
down_revision = "0036_manual_entries"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE cash.accounts DROP CONSTRAINT accounts_kind_check;
ALTER TABLE cash.accounts ADD CONSTRAINT accounts_kind_check
    CHECK (kind IN ('driver', 'treasury', 'bank', 'cod_clearing', 'adjustments', 'payroll_recovery', 'writeoff',
                    'opening', 'fuel', 'disbursements'));
ALTER TABLE cash.journals DROP CONSTRAINT journals_kind_check;
ALTER TABLE cash.journals ADD CONSTRAINT journals_kind_check
    CHECK (kind IN ('collection', 'adjustment', 'deposit', 'bank_deposit', 'settlement', 'writeoff', 'reversal',
                    'opening', 'fuel', 'disbursement', 'bank_withdrawal'));

-- one disbursement per document (an expense, an advance): undone only by its reversal
DROP INDEX cash.journals_one_per_source;
CREATE UNIQUE INDEX journals_one_per_source ON cash.journals (source_type, source_id, kind)
    WHERE status <> 'rejected' AND kind IN ('collection', 'deposit', 'settlement', 'opening', 'disbursement');

ALTER TABLE finance.expenses ADD COLUMN branch_id bigint
    CONSTRAINT expenses_branch_id_fkey REFERENCES org.branches (id);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
