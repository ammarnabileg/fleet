"""A stored file may have a copy on the server's disk, in the R2 bucket, or both.

files.files.storage said where a file's bytes were (one place). It becomes two flags: on_disk (a copy on the disk of
the server that wrote or fetched it) and in_r2 (a copy in the bucket, which every server sharing this database
reads). The office chooses in the control panel where new files go: the disk, R2, or both; a background job copies
the files each way the choice asks, and a file is read from wherever a copy is.

The existing rows: a file recorded on the disk is on the disk; a file recorded in R2 is in R2 (its disk copy, if the
operator kept it, is found again by the next copy to the disk without downloading it).

Revision ID: 0072_file_copies
Revises: 0071_platforms_hub
"""

from alembic import op

revision = "0072_file_copies"
down_revision = "0071_platforms_hub"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE files.files
    ADD COLUMN on_disk boolean NOT NULL DEFAULT true,
    ADD COLUMN in_r2   boolean NOT NULL DEFAULT false;
UPDATE files.files SET on_disk = (storage = 'local'), in_r2 = (storage = 'r2');
DROP INDEX files.files_storage_idx;
ALTER TABLE files.files DROP COLUMN storage;
ALTER TABLE files.files ADD CONSTRAINT files_copy_check CHECK (on_disk OR in_r2);
-- what the background copies still have to do
CREATE INDEX files_to_r2_idx ON files.files (sha256) WHERE on_disk AND NOT in_r2;
CREATE INDEX files_to_disk_idx ON files.files (sha256) WHERE in_r2 AND NOT on_disk;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
