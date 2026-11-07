"""Printing: a cash receipt keeps what it was issued with (the driver's name and civil ID, his company and the plate of
the car he worked with then), so a later change of car or name does not alter an old receipt; receipts issued before
this get them from the driver and the car he held at the time. And the print templates: every publish of the A4
layout (the default and the per-company overrides, as one set), the newest in force, a rollback published again as a
new version (restored_from), as the driver status templates are.

Revision ID: 0068_print_templates
Revises: 0067_broadcast_style
"""

from alembic import op

revision = "0068_print_templates"
down_revision = "0067_broadcast_style"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE cash.receipts
    ADD COLUMN company_id   bigint,
    ADD COLUMN driver_name  jsonb,
    ADD COLUMN civil_id     text,
    ADD COLUMN plate_number text;

UPDATE cash.receipts r
   SET company_id = e.company_id, driver_name = e.name, civil_id = e.civil_id
  FROM people.employees e
 WHERE e.id = r.driver_id;

UPDATE cash.receipts r
   SET plate_number = (
       SELECT v.plate_number
         FROM fleet.custodies c JOIN fleet.vehicles v ON v.id = c.vehicle_id
        WHERE c.driver_id = r.driver_id AND c.started_at <= r.created_at
          AND (c.ended_at IS NULL OR c.ended_at > r.created_at)
        ORDER BY (c.kind = 'replacement') DESC
        LIMIT 1);

CREATE TABLE org.print_template_versions (
    version       integer     CONSTRAINT print_template_versions_pkey PRIMARY KEY
                              CONSTRAINT print_template_versions_version_check CHECK (version > 0),
    config        jsonb       NOT NULL,
    restored_from integer,
    changed       text,
    created_by    bigint,
    created_at    timestamptz NOT NULL DEFAULT now()
);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
