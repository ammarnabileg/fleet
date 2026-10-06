"""Pay schemes (docs/payroll-schemes.md): a platform offers schemes (per order, by batch level, base price with tier
bonuses and penalties), each driver is on one scheme per month, and a driver asks from the app to change it from the
next month, decided in the dashboard. The month's batch level, attendance marks and a missed star day are entered by
the reviewer with the month's figures; a payroll line keeps the scheme it used and how it got its earnings.

Revision ID: 0018_pay_schemes
Revises: 0017_daily_fields
"""

from alembic import op

revision = "0018_pay_schemes"
down_revision = "0017_daily_fields"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE payroll.schemes (
    id                   bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT schemes_pkey PRIMARY KEY,
    public_id            uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT schemes_public_id_key UNIQUE,
    platform_id          bigint NOT NULL CONSTRAINT schemes_platform_id_fkey REFERENCES payroll.platforms (id),
    code                 text NOT NULL CONSTRAINT schemes_code_check CHECK (code ~ '^[a-z][a-z0-9_]{1,30}$'),
    name                 jsonb NOT NULL,
    description          jsonb,
    calculator           text NOT NULL CONSTRAINT schemes_calculator_check
                             CHECK (calculator IN ('platform_rates', 'per_order', 'batch', 'tiered_target')),
    per_order            numeric(12,3) CONSTRAINT schemes_per_order_check CHECK (per_order >= 0),
    target_orders        integer NOT NULL DEFAULT 420 CONSTRAINT schemes_target_orders_check CHECK (target_orders >= 0),
    required_valid_days  smallint NOT NULL DEFAULT 28
                             CONSTRAINT schemes_required_valid_days_check CHECK (required_valid_days BETWEEN 0 AND 31),
    missing_order_rate   numeric(12,3) CONSTRAINT schemes_missing_order_rate_check CHECK (missing_order_rate >= 0),
    reduced_rate         numeric(12,3) CONSTRAINT schemes_reduced_rate_check CHECK (reduced_rate >= 0),
    bonus_when_reduced   boolean NOT NULL DEFAULT false,
    marks_when_reduced   boolean NOT NULL DEFAULT false,
    floor_at_zero        boolean NOT NULL DEFAULT true,
    company_covers       text[] NOT NULL DEFAULT '{}' CONSTRAINT schemes_company_covers_check
                             CHECK (company_covers <@ ARRAY['maintenance', 'housing', 'gas', 'sim']::text[]),
    driver_selectable    boolean NOT NULL DEFAULT true,
    is_active            boolean NOT NULL DEFAULT true,
    created_by           bigint NOT NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    version              integer NOT NULL DEFAULT 1,
    CONSTRAINT schemes_platform_id_key UNIQUE (platform_id, code),
    CONSTRAINT schemes_rates_check CHECK (
        (calculator NOT IN ('per_order', 'tiered_target') OR per_order IS NOT NULL) AND
        (calculator <> 'tiered_target' OR reduced_rate IS NOT NULL))
);

CREATE TABLE payroll.scheme_steps (
    scheme_id  bigint NOT NULL CONSTRAINT scheme_steps_scheme_id_fkey REFERENCES payroll.schemes (id) ON DELETE CASCADE,
    kind       text NOT NULL CONSTRAINT scheme_steps_kind_check
                   CHECK (kind IN ('batch_rate', 'tier_bonus', 'marks_deduction', 'marks_reduce')),
    threshold  numeric(12,3) NOT NULL CONSTRAINT scheme_steps_threshold_check CHECK (threshold >= 0),
    amount     numeric(12,3) CONSTRAINT scheme_steps_amount_check CHECK (amount >= 0),
    CONSTRAINT scheme_steps_pkey PRIMARY KEY (scheme_id, kind, threshold),
    CONSTRAINT scheme_steps_amount_kind_check CHECK ((kind = 'marks_reduce') = (amount IS NULL))
);

CREATE TABLE payroll.scheme_change_requests (
    id                   bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT scheme_change_requests_pkey PRIMARY KEY,
    public_id            uuid NOT NULL DEFAULT gen_random_uuid() CONSTRAINT scheme_change_requests_public_id_key UNIQUE,
    employee_id          bigint NOT NULL CONSTRAINT scheme_change_requests_employee_id_fkey
                             REFERENCES people.employees (id),
    company_id           bigint NOT NULL,
    current_scheme_id    bigint CONSTRAINT scheme_change_requests_current_scheme_id_fkey REFERENCES payroll.schemes (id),
    requested_scheme_id  bigint NOT NULL CONSTRAINT scheme_change_requests_requested_scheme_id_fkey
                             REFERENCES payroll.schemes (id),
    effective_month      date NOT NULL,
    status               text NOT NULL DEFAULT 'pending' CONSTRAINT scheme_change_requests_status_check
                             CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    driver_note          text,
    admin_note           text,
    submitted_by_device  bigint,
    decided_by           bigint,
    decided_at           timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    version              integer NOT NULL DEFAULT 1,
    CONSTRAINT scheme_change_requests_month_check CHECK (extract(day FROM effective_month) = 1),
    CONSTRAINT scheme_change_requests_change_check CHECK (requested_scheme_id IS DISTINCT FROM current_scheme_id),
    CONSTRAINT scheme_change_requests_decided_check
        CHECK ((status IN ('approved', 'rejected')) = (decided_at IS NOT NULL))
);
CREATE UNIQUE INDEX scheme_change_requests_employee_id_idx
    ON payroll.scheme_change_requests (employee_id) WHERE status = 'pending';
CREATE INDEX scheme_change_requests_status_idx ON payroll.scheme_change_requests (status, created_at);

CREATE TABLE payroll.driver_schemes (
    id           bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT driver_schemes_pkey PRIMARY KEY,
    employee_id  bigint NOT NULL CONSTRAINT driver_schemes_employee_id_fkey REFERENCES people.employees (id),
    scheme_id    bigint NOT NULL CONSTRAINT driver_schemes_scheme_id_fkey REFERENCES payroll.schemes (id),
    valid_from   date NOT NULL,
    valid_to     date,
    source       text NOT NULL CONSTRAINT driver_schemes_source_check
                     CHECK (source IN ('office', 'registration', 'request', 'import')),
    request_id   bigint CONSTRAINT driver_schemes_request_id_fkey REFERENCES payroll.scheme_change_requests (id),
    set_by       bigint,
    set_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT driver_schemes_month_check CHECK (
        extract(day FROM valid_from) = 1
        AND (valid_to IS NULL OR (extract(day FROM valid_to) = 1 AND valid_to > valid_from))),
    CONSTRAINT driver_schemes_overlap EXCLUDE USING gist
        (employee_id WITH =, daterange(valid_from, valid_to) WITH &&)
);
CREATE INDEX driver_schemes_scheme_id_idx ON payroll.driver_schemes (scheme_id);

ALTER TABLE payroll.statements
    ADD COLUMN batch_level       smallint CONSTRAINT statements_batch_level_check CHECK (batch_level BETWEEN 1 AND 20),
    ADD COLUMN attendance_marks  smallint CONSTRAINT statements_attendance_marks_check CHECK (attendance_marks >= 0),
    ADD COLUMN star_day_failed   boolean;

ALTER TABLE payroll.lines
    ADD COLUMN scheme_id  bigint CONSTRAINT lines_scheme_id_fkey REFERENCES payroll.schemes (id),
    ADD COLUMN breakdown  jsonb NOT NULL DEFAULT '[]'::jsonb;

-- HR prepares payroll, so it keeps who is on which scheme and decides the drivers' requests
INSERT INTO identity.role_permissions (role_id, permission)
SELECT r.id, 'payroll.schemes' FROM identity.roles r WHERE r.code = 'hr'
ON CONFLICT DO NOTHING;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
