"""Kuwait plates are written code/number.

The import (and a few hand entries) stored 60-76505, 60 76505 or 1016684 for what the plate shows as 60/76505 and
10/16684. normalize_plate now writes every new plate as code/number; this rewrites the existing ones the same way: a
code of one or two digits and a number of up to five, separated by a dash, a space, a dot or nothing (a run of 6 or 7
digits: the last five are the number). A plate whose rewritten form another vehicle already has is left as it was.

Revision ID: 0075_kuwait_plates
Revises: 0074_email
"""

from alembic import op

revision = "0075_kuwait_plates"
down_revision = "0074_email"
branch_labels = None
depends_on = None

SQL = r"""
WITH fixed AS (
    SELECT id, CASE
        WHEN btrim(plate_number) ~ '^\d{1,2}\s*[-/.\\ ]\s*\d{1,5}$'
            THEN regexp_replace(btrim(plate_number), '^(\d{1,2})\s*[-/.\\ ]\s*(\d{1,5})$', '\1/\2')
        WHEN btrim(plate_number) ~ '^\d{6,7}$'
            THEN left(btrim(plate_number), length(btrim(plate_number)) - 5) || '/' || right(btrim(plate_number), 5)
    END AS plate
    FROM fleet.vehicles
), ranked AS (
    SELECT f.id, f.plate, row_number() OVER (PARTITION BY f.plate ORDER BY f.id) AS n
    FROM fixed f
    WHERE f.plate IS NOT NULL
      AND f.plate <> (SELECT v.plate_number FROM fleet.vehicles v WHERE v.id = f.id)
      AND NOT EXISTS (SELECT 1 FROM fleet.vehicles o WHERE o.id <> f.id
                      AND upper(regexp_replace(o.plate_number, '\s', '', 'g')) = f.plate)
)
UPDATE fleet.vehicles v SET plate_number = r.plate FROM ranked r WHERE v.id = r.id AND r.n = 1;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
