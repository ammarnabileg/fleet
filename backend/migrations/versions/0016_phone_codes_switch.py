"""Phone codes become a client setting (driver_sign_in.phone_codes). Without them a driver signs in with his civil ID
and his own password: chosen at his first sign-in (with the office's initial password), stored as a hash beside it,
and covered by the same lock. A driver may then have the app with no phone on file, so the database no longer
requires one; the rule stays in the service while phone codes are on.

Revision ID: 0016_phone_codes_switch
Revises: 0015_driver_claims
"""

from alembic import op

revision = "0016_phone_codes_switch"
down_revision = "0015_driver_claims"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE identity.driver_claims
    ADD COLUMN own_password_hash   text,
    ADD COLUMN own_password_set_at timestamptz,
    ADD CONSTRAINT driver_claims_own_password_check
        CHECK ((own_password_hash IS NULL) = (own_password_set_at IS NULL));

ALTER TABLE people.employees DROP CONSTRAINT employees_driver_phone_check;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
