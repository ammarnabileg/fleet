"""Petty cash custody: an employee holding cash for small expenses has a cash account of kind "petty" (one per
employee, on his branch). The accountant funds it from a branch treasury (journal "petty_fund": petty +X, treasury
-X) and takes back what is left (journal "petty_return": treasury +X, petty -X); in the books Dr / Cr the new role
petty_cash, on account 1115 «العهد النقدية» where the chart has that code free. An expense may be paid from a holder's
custody (payment_method "petty"): approved, it is a disbursement journal out of the petty account (made no entry: the
expense's own entry credits petty_cash), reversed when the expense is cancelled.

Revision ID: 0040_petty_cash
Revises: 0039_periods
"""

from alembic import op

revision = "0040_petty_cash"
down_revision = "0039_periods"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE cash.accounts ADD COLUMN employee_id bigint
    CONSTRAINT accounts_employee_id_fkey REFERENCES people.employees (id);
ALTER TABLE cash.accounts DROP CONSTRAINT accounts_kind_check;
ALTER TABLE cash.accounts ADD CONSTRAINT accounts_kind_check
    CHECK (kind IN ('driver', 'treasury', 'bank', 'cod_clearing', 'adjustments', 'payroll_recovery', 'writeoff',
                    'opening', 'fuel', 'disbursements', 'petty'));
ALTER TABLE cash.accounts ADD CONSTRAINT accounts_petty_check CHECK ((kind = 'petty') = (employee_id IS NOT NULL));
-- several holders on one branch: the holder is part of the account's key
ALTER TABLE cash.accounts DROP CONSTRAINT accounts_kind_key;
ALTER TABLE cash.accounts ADD CONSTRAINT accounts_kind_key
    UNIQUE NULLS NOT DISTINCT (kind, driver_id, branch_id, employee_id);
CREATE UNIQUE INDEX accounts_one_petty ON cash.accounts (employee_id) WHERE kind = 'petty';

ALTER TABLE cash.journals DROP CONSTRAINT journals_kind_check;
ALTER TABLE cash.journals ADD CONSTRAINT journals_kind_check
    CHECK (kind IN ('collection', 'adjustment', 'deposit', 'bank_deposit', 'settlement', 'writeoff', 'reversal',
                    'opening', 'fuel', 'disbursement', 'bank_withdrawal', 'count_diff', 'petty_fund', 'petty_return'));

ALTER TABLE finance.expenses DROP CONSTRAINT expenses_payment_method_check;
ALTER TABLE finance.expenses ADD CONSTRAINT expenses_payment_method_check
    CHECK (payment_method IN ('treasury', 'bank', 'payable', 'petty'));
ALTER TABLE finance.expenses ADD COLUMN petty_employee_id bigint
    CONSTRAINT expenses_petty_employee_id_fkey REFERENCES people.employees (id);
ALTER TABLE finance.expenses ADD CONSTRAINT expenses_petty_check
    CHECK ((payment_method = 'petty') = (petty_employee_id IS NOT NULL));

-- the custody in the books: 1115 where the code is free (a chart that has its own 1115 maps the role by hand)
WITH made AS (
    INSERT INTO finance.accounts (code, name, type)
    VALUES ('1115', '{"ar": "العهد النقدية", "en": "Petty cash custody"}'::jsonb, 'asset')
    ON CONFLICT (code) DO NOTHING
    RETURNING id
)
INSERT INTO finance.account_roles (role, account_id)
SELECT 'petty_cash', id FROM made
ON CONFLICT (role) DO NOTHING;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
