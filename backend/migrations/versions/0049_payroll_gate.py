"""The reconciliation gate: no payroll run is approved until one month was compared with a previous month's sheet of
the client. The payroll settings get live_approval_enabled, false for every install, existing ones included (the
client asked that nothing real is approved before the test); only the owner turns it on.

Revision ID: 0049_payroll_gate
Revises: 0048_objections
"""

from alembic import op

revision = "0049_payroll_gate"
down_revision = "0048_objections"
branch_labels = None
depends_on = None

SQL = r"""
UPDATE org.settings SET value = value || '{"live_approval_enabled": false}'::jsonb, version = version + 1,
       updated_at = now()
 WHERE key = 'payroll';

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
