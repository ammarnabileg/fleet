"""Fuel economy: the litres of a driver's fuel claim (from the app, or the accountant reading the receipt) and the
odometer of a fuel expense's car. With the odometer and the litres of consecutive fills of a car, the fuel per 100 km
and the cost per km are computed, only where the readings go forward and the litres are known.

Revision ID: 0061_fuel_economy
Revises: 0060_maintenance_plans
"""

from alembic import op

revision = "0061_fuel_economy"
down_revision = "0060_maintenance_plans"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE cash.fuel_claims ADD COLUMN litres numeric(8,2)
    CONSTRAINT fuel_claims_litres_check CHECK (litres > 0 AND litres <= 500);
CREATE INDEX fuel_claims_vehicle_id_idx ON cash.fuel_claims (vehicle_id, paid_at);
ALTER TABLE finance.expenses ADD COLUMN odometer_km integer
    CONSTRAINT expenses_odometer_km_check CHECK (odometer_km >= 0);
"""


def upgrade() -> None:
    op.execute(SQL)
    op.execute("SELECT public.fleet_apply_grants();")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
