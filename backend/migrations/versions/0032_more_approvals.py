"""Approval workflows reach two more money decisions (BRD FR-WFL-02, FR-CSH-09): a manual correction of a driver's
cash balance and a deduction the office enters itself. With a workflow and a step for the amount, each waits as
pending until its last step approves it; refused, it keeps the reason. Without one, both apply at once as before.

Revision ID: 0032_more_approvals
Revises: 0031_off_duty_permission
"""

from alembic import op

revision = "0032_more_approvals"
down_revision = "0031_off_duty_permission"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE approvals.workflows DROP CONSTRAINT workflows_process_check;
ALTER TABLE approvals.workflows ADD CONSTRAINT workflows_process_check
    CHECK (process IN ('daily_report', 'maintenance_request', 'maintenance_quote', 'maintenance_invoice',
                       'accident_estimate', 'expense', 'payroll_run', 'cash_adjustment', 'manual_deduction'));

-- a manual deduction waits for its workflow (pending) and may be refused (rejected, with the reason in cancel_reason)
ALTER TABLE payroll.deductions DROP CONSTRAINT deductions_status_check;
ALTER TABLE payroll.deductions ADD CONSTRAINT deductions_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled'));
ALTER TABLE payroll.deductions DROP CONSTRAINT deductions_cancelled_check;
ALTER TABLE payroll.deductions ADD CONSTRAINT deductions_cancelled_check
    CHECK (status NOT IN ('cancelled', 'rejected') OR cancel_reason IS NOT NULL);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
