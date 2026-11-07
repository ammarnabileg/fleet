"""A driver asks the office first to change his pay scheme (no scheme named): once approved he picks one himself,
from next month.

Revision ID: 0078_scheme_change_unlock
Revises: 0077_default_schemes
"""

from alembic import op

revision = "0078_scheme_change_unlock"
down_revision = "0077_default_schemes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE payroll.scheme_change_requests ALTER COLUMN requested_scheme_id DROP NOT NULL;
        ALTER TABLE payroll.scheme_change_requests ADD COLUMN picked_at timestamptz;
        ALTER TABLE payroll.scheme_change_requests DROP CONSTRAINT IF EXISTS scheme_change_requests_change_check;
        ALTER TABLE payroll.scheme_change_requests ADD CONSTRAINT scheme_change_requests_change_check
            CHECK (requested_scheme_id IS NULL OR requested_scheme_id IS DISTINCT FROM current_scheme_id);
        ALTER TABLE payroll.scheme_change_requests ADD CONSTRAINT scheme_change_requests_picked_check
            CHECK (picked_at IS NULL OR (status = 'approved' AND requested_scheme_id IS NOT NULL));
        SELECT public.fleet_apply_grants();
        """
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only")
