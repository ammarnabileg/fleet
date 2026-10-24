"""A change of vehicle is "done" only when the driver took the car he asked for: approving it leaves it waiting for the
handover (approved), the custody of the requested car started for him closes it as done and links that custody;
another car handed to him, or the office closing it without the change, closes it (closed, with a note). Returning
his car no longer closes it. Requests already marked done are left as they are: the office's list shows those with no
handover of the requested car after them, to be reviewed by a person.

Revision ID: 0052_change_handover
Revises: 0051_scheme_blocks
"""

from alembic import op

revision = "0052_change_handover"
down_revision = "0051_scheme_blocks"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE fleet.vehicle_change_requests DROP CONSTRAINT vehicle_change_requests_status_check;
ALTER TABLE fleet.vehicle_change_requests ADD CONSTRAINT vehicle_change_requests_status_check
    CHECK (status IN ('pending', 'approved', 'done', 'rejected', 'closed'));
ALTER TABLE fleet.vehicle_change_requests
    ADD COLUMN approved_by bigint,
    ADD COLUMN approved_at timestamptz,
    -- the custody of the requested car that made it done
    ADD COLUMN fulfilled_custody_id bigint
        CONSTRAINT vehicle_change_requests_fulfilled_custody_id_fkey REFERENCES fleet.custodies (id);
-- one open request (waiting for a decision or for the handover) per custody
DROP INDEX fleet.vehicle_change_requests_one_pending_idx;
CREATE UNIQUE INDEX vehicle_change_requests_one_pending_idx ON fleet.vehicle_change_requests (custody_id)
    WHERE status IN ('pending', 'approved');
CREATE INDEX vehicle_change_requests_employee_open_idx ON fleet.vehicle_change_requests (employee_id)
    WHERE status IN ('pending', 'approved');

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
