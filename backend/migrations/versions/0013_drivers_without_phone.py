"""A driver may be recorded before his phone is known (an imported list of civil IDs and professions); he gets no
app access until a phone is added, since the phone is how the app signs him in.

Revision ID: 0013_drivers_without_phone
Revises: 0012_connections
"""

from alembic import op

revision = "0013_drivers_without_phone"
down_revision = "0012_connections"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE people.employees DROP CONSTRAINT employees_driver_phone_check;
ALTER TABLE people.employees ADD CONSTRAINT employees_driver_phone_check
    CHECK (NOT is_driver OR phone IS NOT NULL OR app_access = 'none');
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
