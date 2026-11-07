"""Push to the driver's phone (BRD FR-NTF-01): the Firebase token of the device he signed in on, and the language the
app was in when it registered it (a push is written in it).

Revision ID: 0025_push_tokens
Revises: 0024_driver_notices
"""

from alembic import op

revision = "0025_push_tokens"
down_revision = "0024_driver_notices"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE identity.devices
    ADD COLUMN push_token    text,
    ADD COLUMN push_lang     text,
    ADD COLUMN push_token_at timestamptz;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
