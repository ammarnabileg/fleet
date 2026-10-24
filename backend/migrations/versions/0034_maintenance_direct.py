"""A maintenance request sent by the driver straight to the center he picked (settings: direct_to_center) keeps
that on the request itself: the center's shortcuts (no quote needed, the invoice before "ready") and the driver's own
pickup follow the request, not the switch as it stands later.

Revision ID: 0034_maintenance_direct
Revises: 0033_day_sessions
"""

from alembic import op

revision = "0034_maintenance_direct"
down_revision = "0033_day_sessions"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE maintenance.requests ADD COLUMN direct boolean NOT NULL DEFAULT false;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
