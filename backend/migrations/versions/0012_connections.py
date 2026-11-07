"""External services set up from the control panel, and where each stored file lives.

integrations.connections holds one row per external service (file storage, WhatsApp): its settings in plain
JSON, and its secrets (an API key, a secret access key) encrypted with the installation's key. Secrets are never
returned by the API; the panel only shows whether one is set and its last characters.

files.files.storage records where a file's bytes are: the server's disk ('local') or the R2 bucket ('r2'). A file
stays readable wherever it was written, so switching storage never breaks old records.

Revision ID: 0012_connections
Revises: 0011_fines
"""

from alembic import op

revision = "0012_connections"
down_revision = "0011_fines"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE integrations.connections (
    kind         text        CONSTRAINT connections_pkey PRIMARY KEY
                             CONSTRAINT connections_kind_check CHECK (kind ~ '^[a-z][a-z0-9_]{1,30}$'),
    config       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    secrets      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    version      integer     NOT NULL DEFAULT 1,
    updated_by   bigint,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    checked_at   timestamptz,
    check_ok     boolean,
    check_error  text
);

ALTER TABLE files.files ADD COLUMN storage text NOT NULL DEFAULT 'local'
    CONSTRAINT files_storage_check CHECK (storage IN ('local', 'r2'));
CREATE INDEX files_storage_idx ON files.files (storage);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
