"""A registered car still waiting when the driver gets another car is closed as superseded.

Revision ID: 0044_vehicle_claims_superseded
Revises: 0043_vehicle_claims
"""

from alembic import op

revision = "0044_vehicle_claims_superseded"
down_revision = "0043_vehicle_claims"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE fleet.vehicle_claims DROP CONSTRAINT vehicle_claims_status_check;
ALTER TABLE fleet.vehicle_claims ADD CONSTRAINT vehicle_claims_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'superseded'));

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
