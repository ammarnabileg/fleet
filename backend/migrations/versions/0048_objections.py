"""A driver objects to his payslip from the app (the whole of it or one line), with his reason and a photo or PDF if he
has one; the office answers in the dashboard. An objection never edits the approved run: a settlement is a separate
manual deduction (or adjustment) for a later month, linked from the objection.

Revision ID: 0048_objections
Revises: 0047_uncollected
"""

from alembic import op

revision = "0048_objections"
down_revision = "0047_uncollected"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE payroll.objections (
    id                   bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT objections_pkey PRIMARY KEY,
    public_id            uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT objections_public_id_key UNIQUE,
    -- the payslip: the driver's line in an approved run (lines are rebuilt when a reopened run is recomputed)
    run_id               bigint NOT NULL CONSTRAINT objections_run_id_fkey REFERENCES payroll.runs (id),
    employee_id          bigint NOT NULL CONSTRAINT objections_employee_id_fkey REFERENCES people.employees (id),
    company_id           bigint NOT NULL,
    month                date NOT NULL CONSTRAINT objections_month_check CHECK (extract(day FROM month) = 1),
    item_code            text,               -- a line of the payslip (orders_pay, missing_target, deduction:<id>...); none: all of it
    item_amount          numeric(12,3),      -- what the payslip said for it when he objected
    reason               text NOT NULL CONSTRAINT objections_reason_check CHECK (length(btrim(reason)) > 0),
    attachment_sha256    text CONSTRAINT objections_attachment_sha256_fkey REFERENCES files.files (sha256),
    status               text NOT NULL DEFAULT 'open' CONSTRAINT objections_status_check
                             CHECK (status IN ('open', 'in_review', 'accepted', 'rejected', 'closed')),
    response             text,
    action_taken         text,
    deduction_id         bigint CONSTRAINT objections_deduction_id_fkey REFERENCES payroll.deductions (id),
    handled_by           bigint,
    handled_at           timestamptz,
    client_ref           uuid NOT NULL CONSTRAINT objections_client_ref_key UNIQUE,
    submitted_by_device  bigint,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    version              integer NOT NULL DEFAULT 1,
    CONSTRAINT objections_answered_check CHECK (status NOT IN ('accepted', 'rejected') OR response IS NOT NULL)
);
CREATE INDEX objections_status_idx ON payroll.objections (status, created_at);
CREATE INDEX objections_employee_id_idx ON payroll.objections (employee_id, created_at);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
