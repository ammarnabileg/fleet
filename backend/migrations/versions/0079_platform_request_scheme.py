"""The scheme a driver picks with his company in the app: kept on his request, set on him when the office approves.

Revision ID: 0079_platform_request_scheme
Revises: 0078_scheme_change_unlock
"""

from alembic import op

revision = "0079_platform_request_scheme"
down_revision = "0078_scheme_change_unlock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE payroll.platform_requests ADD COLUMN scheme_id bigint REFERENCES payroll.schemes (id);
        SELECT public.fleet_apply_grants();
        """
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only")
