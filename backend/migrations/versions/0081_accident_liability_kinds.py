"""Who pays for an accident, four ways instead of three: the insurance company (a cheque to repair the vehicle, chased
every day until it is received), the company (the repair stays its own expense, no deduction), the driver (the
deduction, in full or by a percentage) and an amicable settlement (the other party pays cash to an employee; recorded,
not booked, and no police report needed). "No liability" becomes the company's and "shared" the driver's with its
percentage.

Revision ID: 0081_accident_liability_kinds
Revises: 0080_keeta_per_order_scheme
"""

from alembic import op

revision = "0081_accident_liability_kinds"
down_revision = "0080_keeta_per_order_scheme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE accidents.accidents
    DROP CONSTRAINT accidents_liability_check,
    DROP CONSTRAINT accidents_outcome_check,
    ADD COLUMN insurer             text,
    ADD COLUMN insurance_claim_no  text,
    ADD COLUMN cheque_no           text,
    ADD COLUMN cheque_amount       numeric(12, 3),
    ADD COLUMN cheque_received_on  date,
    ADD COLUMN cheque_recorded_by  bigint,
    ADD COLUMN cheque_recorded_at  timestamptz,
    ADD COLUMN settlement_amount   numeric(12, 3),
    ADD COLUMN settlement_employee_id bigint CONSTRAINT accidents_settlement_employee_id_fkey
        REFERENCES people.employees (id);

UPDATE accidents.accidents SET liability = 'company' WHERE liability = 'none';
UPDATE accidents.accidents SET liability = 'driver' WHERE liability = 'shared';

ALTER TABLE accidents.accidents
    ADD CONSTRAINT accidents_liability_check
        CHECK (liability IN ('insurance', 'company', 'driver', 'settlement')),
    ADD CONSTRAINT accidents_outcome_check
        CHECK (liability IS NULL OR liability = 'settlement' OR police_report_sha256 IS NOT NULL),
    ADD CONSTRAINT accidents_insurance_check
        CHECK (liability IS DISTINCT FROM 'insurance' OR insurer IS NOT NULL),
    ADD CONSTRAINT accidents_cheque_check
        CHECK ((cheque_received_on IS NULL) = (cheque_amount IS NULL) AND (cheque_amount IS NULL OR cheque_amount > 0)),
    ADD CONSTRAINT accidents_settlement_check
        CHECK (liability IS DISTINCT FROM 'settlement'
               OR (settlement_amount > 0 AND settlement_employee_id IS NOT NULL));
""")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
