"""Decision D: a month's penalties never take the net below zero. What the pay could not cover is a line of the
uncollected deductions balance, recorded when the run is approved, for review: an accountant carries it to a later
month (a manual deduction, with payroll.approve and a note) or drops it with a note. Nothing is carried by itself.

Revision ID: 0047_uncollected
Revises: 0046_scheme_versions
"""

from alembic import op

revision = "0047_uncollected"
down_revision = "0046_scheme_versions"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE payroll.uncollected (
    id            bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT uncollected_pkey PRIMARY KEY,
    public_id     uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT uncollected_public_id_key UNIQUE,
    run_id        bigint NOT NULL CONSTRAINT uncollected_run_id_fkey REFERENCES payroll.runs (id),
    employee_id   bigint NOT NULL CONSTRAINT uncollected_employee_id_fkey REFERENCES people.employees (id),
    company_id    bigint NOT NULL,
    month         date NOT NULL CONSTRAINT uncollected_month_check CHECK (extract(day FROM month) = 1),
    round         integer NOT NULL DEFAULT 0,             -- the run's approval it comes from (runs.reopened then)
    amount        numeric(12,3) NOT NULL CONSTRAINT uncollected_amount_check CHECK (amount > 0),
    -- why: the month's penalties [{code, amount}] and what the month earned
    reason        jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        text NOT NULL DEFAULT 'review' CONSTRAINT uncollected_status_check
                      CHECK (status IN ('review', 'carried', 'dropped')),
    note          text,
    deduction_id  bigint CONSTRAINT uncollected_deduction_id_fkey REFERENCES payroll.deductions (id),
    decided_by    bigint,
    decided_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    version       integer NOT NULL DEFAULT 1,
    CONSTRAINT uncollected_run_id_key UNIQUE (run_id, employee_id, round),
    CONSTRAINT uncollected_decided_check CHECK ((status = 'review') = (decided_at IS NULL)),
    CONSTRAINT uncollected_note_check CHECK (status = 'review' OR note IS NOT NULL),
    CONSTRAINT uncollected_carried_check CHECK ((status = 'carried') = (deduction_id IS NOT NULL))
);
CREATE INDEX uncollected_month_idx ON payroll.uncollected (month, status);
CREATE INDEX uncollected_employee_id_idx ON payroll.uncollected (employee_id);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
