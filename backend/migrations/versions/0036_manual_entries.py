"""Entries the accountant writes himself: a manual entry (free lines, balanced) and the opening balances of the books
(dated the day before the books start, the difference to the opening balances account). Neither has a document, so
the source check lets them through without one, like a reversal. A manual or opening line may name the employee it is
with (the account statement's party). An old system's entry imported from Excel is a manual entry whose reference
keeps its old number ("OLD-<n>"), imported once.

Revision ID: 0036_manual_entries
Revises: 0035_fuel_claims
"""

from alembic import op

revision = "0036_manual_entries"
down_revision = "0035_fuel_claims"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE finance.entries DROP CONSTRAINT entries_source_kind_check;
ALTER TABLE finance.entries ADD CONSTRAINT entries_source_kind_check
    CHECK (source_kind IN ('cash_journal', 'expense', 'expense_payment', 'maintenance_invoice', 'invoice_payment',
                           'payroll_run', 'payroll_payment', 'deduction', 'fine_payment', 'reversal', 'manual',
                           'opening'));
ALTER TABLE finance.entries DROP CONSTRAINT entries_source_check;
ALTER TABLE finance.entries ADD CONSTRAINT entries_source_check
    CHECK (source_kind IN ('reversal', 'manual', 'opening') OR source_id IS NOT NULL);

-- an old system's entry number is imported once (while its entry stands)
CREATE UNIQUE INDEX entries_old_ref ON finance.entries (source_ref)
    WHERE source_kind = 'manual' AND source_ref LIKE 'OLD-%' AND reversed_by_id IS NULL;

ALTER TABLE finance.entry_lines ADD COLUMN employee_id bigint
    CONSTRAINT entry_lines_employee_id_fkey REFERENCES people.employees (id);
CREATE INDEX entry_lines_employee_id_idx ON finance.entry_lines (employee_id) WHERE employee_id IS NOT NULL;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
