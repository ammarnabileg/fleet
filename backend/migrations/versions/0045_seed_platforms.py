"""The two delivery platforms the drivers work on, so they can be put on one from the first day: only on an install
that has no platform yet (one that already set its own keeps them as they are). Their pay rule is left at the
defaults, set from the control panel.

What each driver sends in his daily report (with the day's screenshot when the settings require it):
- keeta: whether the platform counted the day valid, nothing else;
- talabat: the day's orders and the cash collected.

What he sends in his monthly statement (the platform's month summary, with screenshots):
- keeta: valid days, orders and hours. His orders are not in his daily reports, so the month's orders (what the
  platform's pay schemes are priced on) come from the statement; the valid days there are the platform's own count
  for the month, the daily ones being the check; hours are kept for the review.
- talabat: orders, the month's total to compare with the sum of his approved daily reports.

Revision ID: 0045_seed_platforms
Revises: 0044_vehicle_claims_superseded
"""

from alembic import op

revision = "0045_seed_platforms"
down_revision = "0044_vehicle_claims_superseded"
branch_labels = None
depends_on = None

SQL = r"""
INSERT INTO payroll.platforms (code, name, is_active, daily_fields, driver_fields)
SELECT v.code, v.name::jsonb, true, v.daily_fields::text[], v.driver_fields::text[]
FROM (VALUES
    ('keeta', '{"ar": "كيتا", "en": "Keeta"}', '{valid_day}', '{valid_days,orders,hours}'),
    ('talabat', '{"ar": "طلبات", "en": "Talabat"}', '{orders,cash}', '{orders}')
) AS v (code, name, daily_fields, driver_fields)
WHERE NOT EXISTS (SELECT 1 FROM payroll.platforms);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
