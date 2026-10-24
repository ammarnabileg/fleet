"""The driver app's update flow: where a release came from (uploaded, or imported from the repository's GitHub
releases by the panel or the hourly job, then without a user), and one row of state for what was last written to
Firebase Remote Config and last read from GitHub, shown in the panel with the reason of a failure.

Revision ID: 0070_app_update_flow
Revises: 0069_petty_spending
"""

from alembic import op

revision = "0070_app_update_flow"
down_revision = "0069_petty_spending"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE org.app_releases
    ADD COLUMN origin text NOT NULL DEFAULT 'upload'
        CONSTRAINT app_releases_origin_check CHECK (origin IN ('upload', 'github')),
    ADD COLUMN github_tag text,
    ALTER COLUMN created_by DROP NOT NULL;

CREATE TABLE org.app_update_state (
    id                  smallint    NOT NULL DEFAULT 1 CONSTRAINT app_update_state_pkey PRIMARY KEY
                                    CONSTRAINT app_update_state_id_check CHECK (id = 1),
    remote_state        text        NOT NULL DEFAULT 'never'
                                    CONSTRAINT app_update_state_remote_state_check
                                    CHECK (remote_state IN ('never', 'published', 'failed', 'not_configured')),
    remote_error        text,
    remote_values       jsonb,
    remote_at           timestamptz,
    github_state        text        NOT NULL DEFAULT 'never'
                                    CONSTRAINT app_update_state_github_state_check
                                    CHECK (github_state IN ('never', 'imported', 'up_to_date', 'failed')),
    github_error        text,
    github_release      text,
    github_at           timestamptz
);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
