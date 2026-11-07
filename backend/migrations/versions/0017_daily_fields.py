"""What the driver sends in his daily report is the platform's to say: orders and cash for one, orders and whether
the day counted (a valid day, from the platform app's day summary) for another. Payroll builds the month from the
approved daily reports, so a platform that reports valid days daily needs no monthly statement.

Revision ID: 0017_daily_fields
Revises: 0016_phone_codes_switch
"""

from alembic import op

revision = "0017_daily_fields"
down_revision = "0016_phone_codes_switch"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE payroll.platforms
    ADD COLUMN daily_fields text[] NOT NULL DEFAULT '{orders,cash}',
    ADD CONSTRAINT platforms_daily_fields_check CHECK (daily_fields <@ ARRAY['orders', 'cash', 'valid_day']::text[]);

ALTER TABLE daily_ops.reports ADD COLUMN valid_day boolean;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
