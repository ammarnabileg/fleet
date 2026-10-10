"""A pay scheme's terms change by version, each from a month: a run uses the version of its own month, so a change
never reaches a month already paid. Every existing scheme gets its terms of today as version 1, from its creation month
or the earliest month a driver was put on it or a run used it; a payroll line keeps the version it was paid on.

Revision ID: 0045_scheme_versions
Revises: 0044_vehicle_claims_superseded
"""

from alembic import op

revision = "0045_scheme_versions"
down_revision = "0044_vehicle_claims_superseded"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE payroll.scheme_versions (
    id                   bigint GENERATED ALWAYS AS IDENTITY CONSTRAINT scheme_versions_pkey PRIMARY KEY,
    scheme_id            bigint NOT NULL CONSTRAINT scheme_versions_scheme_id_fkey
                             REFERENCES payroll.schemes (id) ON DELETE CASCADE,
    version_no           integer NOT NULL CONSTRAINT scheme_versions_version_no_check CHECK (version_no >= 1),
    effective_month      date NOT NULL
                             CONSTRAINT scheme_versions_effective_month_check CHECK (extract(day FROM effective_month) = 1),
    per_order            numeric(12,3) CONSTRAINT scheme_versions_per_order_check CHECK (per_order >= 0),
    target_orders        integer NOT NULL CONSTRAINT scheme_versions_target_orders_check CHECK (target_orders >= 0),
    required_valid_days  smallint NOT NULL
                             CONSTRAINT scheme_versions_required_valid_days_check CHECK (required_valid_days BETWEEN 0 AND 31),
    missing_order_rate   numeric(12,3) CONSTRAINT scheme_versions_missing_order_rate_check CHECK (missing_order_rate >= 0),
    reduced_rate         numeric(12,3) CONSTRAINT scheme_versions_reduced_rate_check CHECK (reduced_rate >= 0),
    bonus_when_reduced   boolean NOT NULL,
    marks_when_reduced   boolean NOT NULL,
    floor_at_zero        boolean NOT NULL,
    company_covers       text[] NOT NULL DEFAULT '{}' CONSTRAINT scheme_versions_company_covers_check
                             CHECK (company_covers <@ ARRAY['maintenance', 'housing', 'gas', 'sim']::text[]),
    -- the list-shaped rules of this version: [{kind, threshold, amount}], amounts as text (fils, exact)
    steps                jsonb NOT NULL DEFAULT '[]'::jsonb,
    note                 text,
    created_by           bigint,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT scheme_versions_scheme_id_key UNIQUE (scheme_id, version_no),
    CONSTRAINT scheme_versions_month_key UNIQUE (scheme_id, effective_month)
);

ALTER TABLE payroll.lines ADD COLUMN scheme_version integer;

INSERT INTO payroll.scheme_versions (
    scheme_id, version_no, effective_month, per_order, target_orders, required_valid_days, missing_order_rate,
    reduced_rate, bonus_when_reduced, marks_when_reduced, floor_at_zero, company_covers, steps, created_by, created_at)
SELECT s.id, 1,
       LEAST(
           date_trunc('month', s.created_at AT TIME ZONE 'Asia/Kuwait')::date,
           COALESCE((SELECT min(r.month) FROM payroll.lines l JOIN payroll.runs r ON r.id = l.run_id
                     WHERE l.scheme_id = s.id), 'infinity'::date),
           COALESCE((SELECT min(d.valid_from) FROM payroll.driver_schemes d WHERE d.scheme_id = s.id), 'infinity'::date)),
       s.per_order, s.target_orders, s.required_valid_days, s.missing_order_rate, s.reduced_rate,
       s.bonus_when_reduced, s.marks_when_reduced, s.floor_at_zero, s.company_covers,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('kind', st.kind, 'threshold', st.threshold::text,
                                                     'amount', st.amount::text) ORDER BY st.kind, st.threshold)
                 FROM payroll.scheme_steps st WHERE st.scheme_id = s.id), '[]'::jsonb),
       s.created_by, s.created_at
FROM payroll.schemes s;

UPDATE payroll.lines SET scheme_version = 1 WHERE scheme_id IS NOT NULL;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
