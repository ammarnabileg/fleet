"""A driver may start his day again after ending it: the business day holds several work sessions, each with its
own start and end reading and its own daily report, and the day's figures are their sum. One open session at a time
is kept by the service, under the vehicle's lock (a start while the day is open, or an end when it is already
ended, is refused); one live report per session by the index.

Revision ID: 0033_day_sessions
Revises: 0032_more_approvals
"""

from alembic import op

revision = "0033_day_sessions"
down_revision = "0032_more_approvals"
branch_labels = None
depends_on = None

SQL = r"""
DROP INDEX fleet.odometer_readings_start_day_idx;

ALTER TABLE daily_ops.reports ADD COLUMN session smallint NOT NULL DEFAULT 1
    CONSTRAINT reports_session_check CHECK (session >= 1);
DROP INDEX daily_ops.reports_one_per_day_idx;
-- one live report per driver, day and work session (the second session's report adds to the first)
CREATE UNIQUE INDEX reports_one_per_session_idx ON daily_ops.reports (employee_id, business_date, session)
    WHERE status <> 'rejected';

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
