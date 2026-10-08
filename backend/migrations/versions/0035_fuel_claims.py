"""Fuel a driver paid from the cash he holds: claimed from the app with a camera photo of the receipt, reviewed by the
accountant (who may correct the amount). Only when his pay scheme puts fuel on the company does an approval lower the
cash he holds: a posted cash journal of kind "fuel" (driver -X, fuel +X), entered in the books as Dr fuel expense
(5120) / Cr drivers' cash (1130). A driver with a company fuel card (people.employees.fuel_card) claims nothing: his
card is topped up as one lump expense.

Revision ID: 0035_fuel_claims
Revises: 0034_maintenance_direct
"""

from alembic import op

revision = "0035_fuel_claims"
down_revision = "0034_maintenance_direct"
branch_labels = None
depends_on = None

SQL = r"""
ALTER TABLE people.employees ADD COLUMN fuel_card boolean NOT NULL DEFAULT false;

ALTER TABLE cash.accounts DROP CONSTRAINT accounts_kind_check;
ALTER TABLE cash.accounts ADD CONSTRAINT accounts_kind_check
    CHECK (kind IN ('driver', 'treasury', 'bank', 'cod_clearing', 'adjustments', 'payroll_recovery', 'writeoff',
                    'opening', 'fuel'));
ALTER TABLE cash.journals DROP CONSTRAINT journals_kind_check;
ALTER TABLE cash.journals ADD CONSTRAINT journals_kind_check
    CHECK (kind IN ('collection', 'adjustment', 'deposit', 'bank_deposit', 'settlement', 'writeoff', 'reversal',
                    'opening', 'fuel'));
DROP INDEX cash.journals_one_per_source;
CREATE UNIQUE INDEX journals_one_per_source ON cash.journals (source_type, source_id, kind)
    WHERE status <> 'rejected' AND kind IN ('collection', 'deposit', 'settlement', 'opening', 'fuel');

CREATE TABLE cash.fuel_claims (
    id              bigint        GENERATED ALWAYS AS IDENTITY CONSTRAINT fuel_claims_pkey PRIMARY KEY,
    public_id       uuid          NOT NULL DEFAULT gen_random_uuid() CONSTRAINT fuel_claims_public_id_key UNIQUE,
    employee_id     bigint        NOT NULL CONSTRAINT fuel_claims_employee_id_fkey REFERENCES people.employees (id),
    company_id      bigint        NOT NULL CONSTRAINT fuel_claims_company_id_fkey REFERENCES org.companies (id),
    branch_id       bigint        NOT NULL CONSTRAINT fuel_claims_branch_id_fkey REFERENCES org.branches (id),
    vehicle_id      bigint        NOT NULL CONSTRAINT fuel_claims_vehicle_id_fkey REFERENCES fleet.vehicles (id),
    client_ref      uuid          NOT NULL CONSTRAINT fuel_claims_client_ref_key UNIQUE,
    paid_at         timestamptz   NOT NULL,
    amount          numeric(12,3) NOT NULL CONSTRAINT fuel_claims_amount_check CHECK (amount > 0),
    odometer_km     integer       CONSTRAINT fuel_claims_odometer_km_check CHECK (odometer_km >= 0),
    receipt_sha256  text          NOT NULL CONSTRAINT fuel_claims_receipt_sha256_fkey REFERENCES files.files (sha256)
                                  CONSTRAINT fuel_claims_receipt_sha256_key UNIQUE,
    notes           text          CONSTRAINT fuel_claims_notes_check CHECK (char_length(notes) <= 500),
    status          text          NOT NULL DEFAULT 'pending'
                                  CONSTRAINT fuel_claims_status_check CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_amount numeric(12,3) CONSTRAINT fuel_claims_approved_amount_check CHECK (approved_amount > 0),
    decision_note   text,
    decided_by      bigint        CONSTRAINT fuel_claims_decided_by_fkey REFERENCES identity.users (id),
    decided_at      timestamptz,
    journal_id      bigint        CONSTRAINT fuel_claims_journal_id_fkey REFERENCES cash.journals (id),
    created_at      timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT fuel_claims_decision_check
        CHECK ((status = 'pending') = (decided_at IS NULL) AND (status <> 'approved' OR approved_amount IS NOT NULL)
               AND (status <> 'rejected' OR decision_note IS NOT NULL))
);
CREATE INDEX fuel_claims_employee_id_idx ON cash.fuel_claims (employee_id, paid_at);
CREATE INDEX fuel_claims_status_idx ON cash.fuel_claims (status, created_at);
CREATE INDEX fuel_claims_created_at_idx ON cash.fuel_claims (created_at);

-- the fuel a driver paid on the company's behalf, on the chart's fuel account where the chart in use has it
INSERT INTO finance.account_roles (role, account_id)
SELECT 'fuel_expense', id FROM finance.accounts WHERE code = '5120'
ON CONFLICT (role) DO NOTHING;

INSERT INTO identity.role_permissions (role_id, permission)
SELECT id, 'cash.fuel_review' FROM identity.roles WHERE code IN ('accountant', 'management')
ON CONFLICT DO NOTHING;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
