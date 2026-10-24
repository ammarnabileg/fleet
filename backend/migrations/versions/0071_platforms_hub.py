"""The contracted delivery platforms as a section of their own:

- the two core platforms (keeta, talabat) are built in: seeded when missing (an install that set its own platforms
  gets them added beside its own), marked core, never deleted; others are added and removed as before;
- each platform keeps the column mapping of its last monthly Excel import (the headers chosen for each field), so the
  next file pre-selects it;
- a batch row of a driver's month may carry its period (the platform sets the batch week by week): the same batch
  twice in a month is two rows, each with its own dates (sub: «batch@period start»);
- a driver with no platform picks his company in the app: a request the office approves (his platform set, and his
  ID on it) or rejects with a reason. Until approved nothing of payroll reads it.

Revision ID: 0071_platforms_hub
Revises: 0069_petty_spending
"""

from alembic import op

revision = "0071_platforms_hub"
down_revision = "0069_petty_spending"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE payroll.platforms ADD COLUMN is_core boolean NOT NULL DEFAULT false;
ALTER TABLE payroll.platforms ADD COLUMN import_mapping jsonb;

INSERT INTO payroll.platforms (code, name, is_active, daily_fields, driver_fields)
SELECT v.code, v.name::jsonb, true, v.daily_fields::text[], v.driver_fields::text[]
FROM (VALUES
    ('keeta', '{"ar": "كيتا", "en": "Keeta"}', '{valid_day}', '{valid_days,orders,hours}'),
    ('talabat', '{"ar": "طلبات", "en": "Talabat"}', '{orders,cash}', '{orders}')
) AS v (code, name, daily_fields, driver_fields)
WHERE NOT EXISTS (SELECT 1 FROM payroll.platforms p WHERE p.code = v.code);
UPDATE payroll.platforms SET is_core = true WHERE code IN ('keeta', 'talabat');

ALTER TABLE payroll.month_values ADD COLUMN period_start date;
ALTER TABLE payroll.month_values ADD COLUMN period_end date;
ALTER TABLE payroll.month_values ADD CONSTRAINT month_values_period_check
    CHECK ((period_start IS NULL) = (period_end IS NULL) AND (period_end IS NULL OR period_end >= period_start));

ALTER TABLE payroll.month_imports DROP CONSTRAINT month_imports_format_check;
ALTER TABLE payroll.month_imports ADD CONSTRAINT month_imports_format_check
    CHECK (format IN ('partner_batches', 'generic', 'mapped'));

CREATE TABLE payroll.platform_requests (
    id                  bigint      GENERATED ALWAYS AS IDENTITY CONSTRAINT platform_requests_pkey PRIMARY KEY,
    public_id           uuid        NOT NULL DEFAULT gen_random_uuid() CONSTRAINT platform_requests_public_id_key UNIQUE,
    employee_id         bigint      NOT NULL CONSTRAINT platform_requests_employee_id_fkey REFERENCES people.employees (id),
    company_id          bigint      NOT NULL,
    platform_id         bigint      NOT NULL CONSTRAINT platform_requests_platform_id_fkey REFERENCES payroll.platforms (id),
    status              text        NOT NULL DEFAULT 'pending'
                                    CONSTRAINT platform_requests_status_check
                                    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    driver_note         text        CONSTRAINT platform_requests_driver_note_check CHECK (char_length(driver_note) <= 500),
    admin_note          text,
    platform_driver_id  text,
    submitted_by_device bigint,
    decided_by          bigint,
    decided_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    version             integer     NOT NULL DEFAULT 1,
    CONSTRAINT platform_requests_decided_check CHECK ((status IN ('approved', 'rejected')) = (decided_at IS NOT NULL)),
    CONSTRAINT platform_requests_rejected_check CHECK (status <> 'rejected' OR admin_note IS NOT NULL)
);
CREATE UNIQUE INDEX platform_requests_employee_id_idx ON payroll.platform_requests (employee_id)
    WHERE status = 'pending';
CREATE INDEX platform_requests_status_idx ON payroll.platform_requests (status, created_at);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
