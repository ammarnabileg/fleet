"""Indexes for what grows every day (measured on a synthetic fleet of 600 vehicles with a year of history): the
odometer readings listed newest first and the ones waiting for review, a driver's readings by business day (his day in
the app, attendance, payroll), the drivers who started a given day (the dashboard, missing reports), and the daily
reports of a day or a range for every driver (the dashboard, the daily summary).

Revision ID: 0053_data_indexes
Revises: 0052_change_handover
"""

from alembic import op

revision = "0053_data_indexes"
down_revision = "0052_change_handover"
branch_labels = None
depends_on = None

SQL = r"""
CREATE INDEX odometer_readings_recorded_at_idx ON fleet.odometer_readings (recorded_at, id);
CREATE INDEX odometer_readings_pending_idx ON fleet.odometer_readings (recorded_at) WHERE review_status = 'pending';
CREATE INDEX odometer_readings_driver_id_idx ON fleet.odometer_readings (driver_id, business_date);
CREATE INDEX odometer_readings_start_day_idx ON fleet.odometer_readings (business_date) WHERE kind = 'start_day';
CREATE INDEX reports_business_date_idx ON daily_ops.reports (business_date);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
