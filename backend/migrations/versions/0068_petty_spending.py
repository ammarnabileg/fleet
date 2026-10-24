"""A petty cash holder records what he spent from his custody in the driver app: the amount, the expense type, the
invoice's camera photo and date, the vendor if he wants. The office approves it (a finance expense paid from his
custody: his petty balance goes down by the existing posting) or rejects it with a reason. Expense types say whether
they may be spent from a custody (`petty`), and the app gets a screen "petty" an office may hide.

Revision ID: 0068_petty_spending
Revises: 0067_broadcast_style
"""

from alembic import op

revision = "0068_petty_spending"
down_revision = "0067_broadcast_style"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE finance.expense_types ADD COLUMN petty boolean NOT NULL DEFAULT false;
UPDATE finance.expense_types SET petty = true WHERE code IN ('fuel', 'repairs', 'office', 'other');

CREATE TABLE cash.petty_expenses (
    id              bigint        GENERATED ALWAYS AS IDENTITY CONSTRAINT petty_expenses_pkey PRIMARY KEY,
    public_id       uuid          NOT NULL DEFAULT gen_random_uuid() CONSTRAINT petty_expenses_public_id_key UNIQUE,
    employee_id     bigint        NOT NULL CONSTRAINT petty_expenses_employee_id_fkey REFERENCES people.employees (id),
    company_id      bigint        NOT NULL CONSTRAINT petty_expenses_company_id_fkey REFERENCES org.companies (id),
    branch_id       bigint        NOT NULL CONSTRAINT petty_expenses_branch_id_fkey REFERENCES org.branches (id),
    client_ref      uuid          NOT NULL CONSTRAINT petty_expenses_client_ref_key UNIQUE,
    type_id         bigint        NOT NULL CONSTRAINT petty_expenses_type_id_fkey REFERENCES finance.expense_types (id),
    amount          numeric(12,3) NOT NULL CONSTRAINT petty_expenses_amount_check CHECK (amount > 0),
    invoice_date    date          NOT NULL,
    vendor          text          CONSTRAINT petty_expenses_vendor_check CHECK (char_length(vendor) <= 200),
    note            text          CONSTRAINT petty_expenses_note_check CHECK (char_length(note) <= 500),
    invoice_sha256  text          NOT NULL CONSTRAINT petty_expenses_invoice_sha256_fkey REFERENCES files.files (sha256)
                                  CONSTRAINT petty_expenses_invoice_sha256_key UNIQUE,
    status          text          NOT NULL DEFAULT 'pending'
                                  CONSTRAINT petty_expenses_status_check
                                  CHECK (status IN ('pending', 'in_review', 'approved', 'rejected', 'cancelled')),
    decision_note   text,
    decided_by      bigint        CONSTRAINT petty_expenses_decided_by_fkey REFERENCES identity.users (id),
    decided_at      timestamptz,
    expense_id      bigint        CONSTRAINT petty_expenses_expense_id_fkey REFERENCES finance.expenses (id)
                                  CONSTRAINT petty_expenses_expense_id_key UNIQUE,
    created_at      timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT petty_expenses_decision_check
        CHECK ((status IN ('pending', 'cancelled')) = (decided_at IS NULL)
               AND (status NOT IN ('in_review', 'approved') OR expense_id IS NOT NULL)
               AND (status <> 'rejected' OR decision_note IS NOT NULL))
);
CREATE INDEX petty_expenses_employee_id_idx ON cash.petty_expenses (employee_id, created_at);
CREATE INDEX petty_expenses_status_idx ON cash.petty_expenses (status, created_at);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
