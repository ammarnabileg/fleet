"""A platform's own input fields, set in the dashboard: what the driver fills in the app each day (the built-in
orders, cash and valid day, and any field the office adds) and what the office enters or imports each month (batch
rows, marks, star day, lateness, tasks by type, any number). The month's values per driver, the imports they came
from (re-importing the same month replaces, never adds), the approved exceptions of a driver's month, and a price
per order agreed with one driver on his scheme.

Revision ID: 0050_platform_fields
Revises: 0049_payroll_gate
"""

from alembic import op

revision = "0050_platform_fields"
down_revision = "0049_payroll_gate"
branch_labels = None
depends_on = None

SQL = r"""
-- the fields, as lists in the order the app and the month review show them: [{key, label, type, builtin, required,
-- help, options}]; a platform without a row asks what its daily_fields say, as before
CREATE TABLE payroll.platform_forms (
    platform_id  bigint CONSTRAINT platform_forms_pkey PRIMARY KEY
                     CONSTRAINT platform_forms_platform_id_fkey REFERENCES payroll.platforms (id) ON DELETE CASCADE,
    daily        jsonb NOT NULL DEFAULT '[]'::jsonb,
    monthly      jsonb NOT NULL DEFAULT '[]'::jsonb,
    screenshot   boolean,  -- the daily screenshot for this platform; NULL: the global setting
    version      integer NOT NULL DEFAULT 1,
    updated_by   bigint,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- what the driver sent in the platform's own daily fields, by key
ALTER TABLE daily_ops.reports ADD COLUMN extra jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE payroll.month_imports (
    id           bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT month_imports_pkey PRIMARY KEY,
    public_id    uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT month_imports_public_id_key UNIQUE,
    platform_id  bigint NOT NULL CONSTRAINT month_imports_platform_id_fkey REFERENCES payroll.platforms (id),
    month        date NOT NULL CONSTRAINT month_imports_month_check CHECK (extract(day FROM month) = 1),
    format       text NOT NULL CONSTRAINT month_imports_format_check CHECK (format IN ('partner_batches', 'generic')),
    file_sha256  text NOT NULL,
    file_name    text,
    summary      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by   bigint NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- one row per driver, month, field and sub-key (the batch number, the task type): the key an import replaces on
CREATE TABLE payroll.month_values (
    id           bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT month_values_pkey PRIMARY KEY,
    employee_id  bigint NOT NULL CONSTRAINT month_values_employee_id_fkey REFERENCES people.employees (id),
    company_id   bigint NOT NULL,
    platform_id  bigint NOT NULL CONSTRAINT month_values_platform_id_fkey REFERENCES payroll.platforms (id),
    month        date NOT NULL CONSTRAINT month_values_month_check CHECK (extract(day FROM month) = 1),
    key          text NOT NULL CONSTRAINT month_values_key_check CHECK (key ~ '^[a-z][a-z0-9_]{0,39}$'),
    sub          text NOT NULL DEFAULT '',
    value        numeric(12,3) NOT NULL,
    source       text NOT NULL CONSTRAINT month_values_source_check CHECK (source IN ('manual', 'import')),
    import_id    bigint CONSTRAINT month_values_import_id_fkey REFERENCES payroll.month_imports (id),
    set_by       bigint,
    set_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT month_values_platform_id_key UNIQUE (platform_id, month, employee_id, key, sub)
);
CREATE INDEX month_values_month_idx ON payroll.month_values (month, employee_id);

CREATE TABLE payroll.month_exceptions (
    id           bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT month_exceptions_pkey PRIMARY KEY,
    public_id    uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT month_exceptions_public_id_key UNIQUE,
    employee_id  bigint NOT NULL CONSTRAINT month_exceptions_employee_id_fkey REFERENCES people.employees (id),
    company_id   bigint NOT NULL,
    month        date NOT NULL CONSTRAINT month_exceptions_month_check CHECK (extract(day FROM month) = 1),
    kind         text NOT NULL CONSTRAINT month_exceptions_kind_check
                     CHECK (kind IN ('accepted_excuse', 'company_error', 'exception_day')),
    days         smallint NOT NULL DEFAULT 0 CONSTRAINT month_exceptions_days_check CHECK (days BETWEEN 0 AND 31),
    corrections  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- company_error: {field: corrected value}
    note         text NOT NULL CONSTRAINT month_exceptions_note_check CHECK (length(btrim(note)) >= 3),
    approved_by  bigint NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    cancelled_by bigint,
    cancelled_at timestamptz,
    cancel_note  text,
    CONSTRAINT month_exceptions_cancelled_check CHECK ((cancelled_at IS NULL) = (cancelled_by IS NULL))
);
CREATE INDEX month_exceptions_month_idx ON payroll.month_exceptions (month, employee_id);

ALTER TABLE payroll.driver_schemes ADD COLUMN personal_rate numeric(12,3)
    CONSTRAINT driver_schemes_personal_rate_check CHECK (personal_rate >= 0);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
