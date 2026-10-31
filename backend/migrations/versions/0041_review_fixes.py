"""Treasury phase 2 review fixes: a deduction's books date. A deduction enters the books on the Kuwait day it was
made; one approved after that day was closed (its month in the books, or for an advance its treasury day by the
count) enters them, and leaves the treasury, on the day it is approved instead: that day is kept here so its entry
and its treasury movement carry the same date.

Revision ID: 0041_review_fixes
Revises: 0040_petty_cash
"""

from alembic import op

revision = "0041_review_fixes"
down_revision = "0040_petty_cash"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE payroll.deductions ADD COLUMN books_date date;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
