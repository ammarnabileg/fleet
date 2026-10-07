"""Movement outside the work day is the driver's own time (BRD FR-TRK-09): seeing it on the route and the live map
takes its own permission, tracking.off_duty. The management role template holds it; others are given it by choice.

Revision ID: 0031_off_duty_permission
Revises: 0030_password_reset_codes
"""

from alembic import op

revision = "0031_off_duty_permission"
down_revision = "0030_password_reset_codes"
branch_labels = None
depends_on = None

SQL = r"""
INSERT INTO identity.role_permissions (role_id, permission)
SELECT id, 'tracking.off_duty' FROM identity.roles WHERE code = 'management'
ON CONFLICT DO NOTHING;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
