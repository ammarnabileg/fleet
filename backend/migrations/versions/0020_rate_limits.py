"""Request limits by client address (BRD section 8: a limit on requests and OTP attempts).

One row per (what is limited, from where, window): every API worker counts in the same row, so the limit holds with
four workers as with one. Rows older than a day are swept by the requests themselves.

Revision ID: 0020_rate_limits
Revises: 0019_attendance
"""

from alembic import op

revision = "0020_rate_limits"
down_revision = "0019_attendance"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE identity.rate_hits (
    bucket        text        NOT NULL,
    key           text        NOT NULL,
    window_start  timestamptz NOT NULL,
    hits          integer     NOT NULL,
    CONSTRAINT rate_hits_pkey PRIMARY KEY (bucket, key, window_start)
);
CREATE INDEX rate_hits_window_start_idx ON identity.rate_hits (window_start);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
