"""The audit record names the device the action came from and its comment (BRD FR-AUD-01): the browser or the
driver app (with the phone model), and the reason or note given with the action. And a bank deposit keeps the photo
of the bank's receipt (FR-CSH-07).

Revision ID: 0029_audit_device_comment
Revises: 0028_driver_requests
"""

from alembic import op

revision = "0029_audit_device_comment"
down_revision = "0028_driver_requests"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE audit.events ADD COLUMN device text;
ALTER TABLE audit.events ADD COLUMN comment text;
ALTER TABLE cash.journals ADD COLUMN attachment_sha256 text
    CONSTRAINT journals_attachment_sha256_fkey REFERENCES files.files (sha256);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
