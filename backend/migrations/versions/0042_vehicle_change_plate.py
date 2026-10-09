"""A change of vehicle names the other car: the plate the driver typed and the vehicle it matched. Requests made
before keep an empty plate and no vehicle; their open alerts get an empty requested plate to show.

Revision ID: 0042_vehicle_change_plate
Revises: 0041_review_fixes
"""

from alembic import op

revision = "0042_vehicle_change_plate"
down_revision = "0041_review_fixes"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE fleet.vehicle_change_requests
    ADD COLUMN requested_plate text NOT NULL DEFAULT '',
    ADD COLUMN requested_vehicle_id bigint
        CONSTRAINT vehicle_change_requests_requested_vehicle_id_fkey REFERENCES fleet.vehicles (id);
ALTER TABLE fleet.vehicle_change_requests ALTER COLUMN requested_plate DROP DEFAULT;

UPDATE notifications.alerts SET params = params || '{"requested": "—"}'::jsonb
 WHERE kind = 'vehicle_change_requested' AND NOT params ? 'requested';

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
