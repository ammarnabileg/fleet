"""Leave types and absence requests (طلب التغيب).

Leave kinds become data: attendance.leave_types holds each type's rules (paid tiers, limits, service needed, once per
service, attachment, gender, calendar or working days), seeded with defaults read from the Kuwait private-sector
labour law (Law No. 6 of 2010): «قيم افتراضية حسب قانون العمل — راجعها مع الموارد البشرية/المستشار القانوني». Every
value is editable from the dashboard. A leave keeps the days it counts and its paid/unpaid split (computed when it is
made and again when approved), where it came from (the office, or the driver's app with a client_ref so a resend is
recognised), and the follow-up: the date the office's follow-up alert counts from (entered, the day of the request by
default) and when the office followed it up. Employees get an optional gender, for the types of one gender.

Revision ID: 0064_leave_types
Revises: 0063_driver_languages
"""

from alembic import op

revision = "0064_leave_types"
down_revision = "0063_driver_languages"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE attendance.leave_types (
    code                 text        CONSTRAINT leave_types_pkey PRIMARY KEY
                                     CONSTRAINT leave_types_code_check CHECK (code ~ '^[a-z][a-z0-9_]{1,30}$'),
    name                 jsonb       NOT NULL,
    legal_ref            text,
    tiers                jsonb       NOT NULL,
    tier_period          text        NOT NULL DEFAULT 'occurrence'
                                     CONSTRAINT leave_types_tier_period_check
                                     CHECK (tier_period IN ('occurrence', 'service_year')),
    max_per_occurrence   integer     CONSTRAINT leave_types_max_per_occurrence_check CHECK (max_per_occurrence > 0),
    max_per_year         integer     CONSTRAINT leave_types_max_per_year_check CHECK (max_per_year > 0),
    max_per_service      integer     CONSTRAINT leave_types_max_per_service_check CHECK (max_per_service > 0),
    min_service_months   integer     NOT NULL DEFAULT 0
                                     CONSTRAINT leave_types_min_service_months_check CHECK (min_service_months >= 0),
    once_per_service     boolean     NOT NULL DEFAULT false,
    requires_attachment  boolean     NOT NULL DEFAULT false,
    eligible_gender      text        CONSTRAINT leave_types_eligible_gender_check
                                     CHECK (eligible_gender IN ('male', 'female')),
    counts               text        NOT NULL DEFAULT 'calendar'
                                     CONSTRAINT leave_types_counts_check CHECK (counts IN ('calendar', 'working')),
    accrues              boolean     NOT NULL DEFAULT false,
    office_may_pay       boolean     NOT NULL DEFAULT false,
    driver_may_request   boolean     NOT NULL DEFAULT true,
    active               boolean     NOT NULL DEFAULT true,
    sort_order           integer     NOT NULL DEFAULT 0,
    version              integer     NOT NULL DEFAULT 1,
    updated_by           bigint,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

INSERT INTO attendance.leave_types (code, name, legal_ref, tiers, tier_period, max_per_occurrence, max_per_year,
    max_per_service, min_service_months, once_per_service, requires_attachment, eligible_gender, accrues,
    office_may_pay, sort_order) VALUES
('annual', '{"ar": "سنوية", "en": "Annual leave", "fr": "Congé annuel", "sw": "Likizo ya mwaka", "hi": "वार्षिक अवकाश", "fil": "Taunang bakasyon"}',
    'Art. 70', '[{"days": null, "pay_percent": 100}]', 'occurrence', NULL, 30, NULL, 9, false, false, NULL, true, false, 1),
('sick', '{"ar": "مرضية", "en": "Sick leave", "fr": "Congé maladie", "sw": "Likizo ya ugonjwa", "hi": "बीमारी अवकाश", "fil": "Bakasyon dahil sa sakit"}',
    'Art. 69', '[{"days": 15, "pay_percent": 100}, {"days": 10, "pay_percent": 75}, {"days": 10, "pay_percent": 50}, {"days": 10, "pay_percent": 25}, {"days": 30, "pay_percent": 0}]',
    'service_year', NULL, 75, NULL, 0, false, true, NULL, false, false, 2),
('maternity', '{"ar": "أمومة", "en": "Maternity leave", "fr": "Congé de maternité", "sw": "Likizo ya uzazi", "hi": "मातृत्व अवकाश", "fil": "Bakasyon sa panganganak"}',
    'Art. 24', '[{"days": 70, "pay_percent": 100}, {"days": 120, "pay_percent": 0}]', 'occurrence', 190, NULL, NULL, 0, false, false, 'female', false, false, 3),
('hajj', '{"ar": "حج", "en": "Hajj leave", "fr": "Congé de Hajj", "sw": "Likizo ya Hija", "hi": "हज अवकाश", "fil": "Bakasyon para sa Hajj"}',
    'Art. 75', '[{"days": 21, "pay_percent": 100}]', 'occurrence', 21, NULL, 21, 24, true, false, NULL, false, false, 4),
('bereavement', '{"ar": "وفاة قريب", "en": "Bereavement leave", "fr": "Congé de deuil", "sw": "Likizo ya msiba", "hi": "शोक अवकाश", "fil": "Bakasyon sa pagluluksa"}',
    'Art. 76', '[{"days": 3, "pay_percent": 100}]', 'occurrence', 3, NULL, NULL, 0, false, false, NULL, false, false, 5),
('iddah_muslim', '{"ar": "عدة (أرملة مسلمة)", "en": "Iddah leave (Muslim widow)", "fr": "Congé de viduité (veuve musulmane)", "sw": "Likizo ya eda (mjane Mwislamu)", "hi": "इद्दत अवकाश (मुस्लिम विधवा)", "fil": "Bakasyon ng iddah (balong Muslim)"}',
    'Art. 76', '[{"days": 130, "pay_percent": 100}]', 'occurrence', 130, NULL, NULL, 0, false, false, 'female', false, false, 6),
('iddah_other', '{"ar": "عدة (أرملة غير مسلمة)", "en": "Iddah leave (non-Muslim widow)", "fr": "Congé de viduité (veuve non musulmane)", "sw": "Likizo ya eda (mjane asiye Mwislamu)", "hi": "इद्दत अवकाश (गैर-मुस्लिम विधवा)", "fil": "Bakasyon ng iddah (balong hindi Muslim)"}',
    'Art. 76', '[{"days": 21, "pay_percent": 100}]', 'occurrence', 21, NULL, NULL, 0, false, false, 'female', false, false, 7),
('unpaid', '{"ar": "بدون راتب", "en": "Unpaid leave", "fr": "Congé sans solde", "sw": "Likizo bila malipo", "hi": "अवैतनिक अवकाश", "fil": "Bakasyon na walang bayad"}',
    NULL, '[{"days": null, "pay_percent": 0}]', 'occurrence', NULL, NULL, NULL, 0, false, false, NULL, false, false, 8),
('emergency', '{"ar": "طارئة", "en": "Emergency leave", "fr": "Congé d''urgence", "sw": "Likizo ya dharura", "hi": "आपातकालीन अवकाश", "fil": "Emergency na bakasyon"}',
    NULL, '[{"days": null, "pay_percent": 0}]', 'occurrence', NULL, NULL, NULL, 0, false, false, NULL, false, true, 9),
('other', '{"ar": "أخرى", "en": "Other", "fr": "Autre", "sw": "Nyingine", "hi": "अन्य", "fil": "Iba pa"}',
    NULL, '[{"days": null, "pay_percent": 0}]', 'occurrence', NULL, NULL, NULL, 0, false, false, NULL, false, true, 10);

ALTER TABLE attendance.leaves DROP CONSTRAINT leaves_kind_check;
ALTER TABLE attendance.leaves
    ADD CONSTRAINT leaves_kind_fkey FOREIGN KEY (kind) REFERENCES attendance.leave_types (code),
    ALTER COLUMN created_by DROP NOT NULL,
    ADD COLUMN counted_days integer NOT NULL DEFAULT 0,
    ADD COLUMN split jsonb NOT NULL DEFAULT '[]',
    ADD COLUMN paid_override boolean NOT NULL DEFAULT false,
    ADD COLUMN rules_overridden boolean NOT NULL DEFAULT false,
    ADD COLUMN source text NOT NULL DEFAULT 'office' CONSTRAINT leaves_source_check CHECK (source IN ('office', 'driver')),
    ADD COLUMN client_ref uuid CONSTRAINT leaves_client_ref_key UNIQUE,
    ADD COLUMN created_by_device bigint,
    ADD COLUMN followup_from date,
    ADD COLUMN followed_up_at timestamptz,
    ADD COLUMN followed_up_by bigint,
    ADD CONSTRAINT leaves_creator_check CHECK (created_by IS NOT NULL OR created_by_device IS NOT NULL);

-- the leaves made before: every day counted; only the unpaid ones unpaid (emergency and other were paid, and stay so)
UPDATE attendance.leaves SET
    counted_days = date_to - date_from + 1,
    split = jsonb_build_array(jsonb_build_object('days', date_to - date_from + 1,
                                                 'pay_percent', CASE WHEN kind = 'unpaid' THEN 0 ELSE 100 END)),
    paid_override = kind IN ('emergency', 'other'),
    followup_from = (created_at AT TIME ZONE 'Asia/Kuwait')::date;
ALTER TABLE attendance.leaves ALTER COLUMN followup_from SET NOT NULL;
-- the open requests the follow-up scan looks at
CREATE INDEX leaves_followup_idx ON attendance.leaves (followup_from) WHERE status IN ('pending', 'approved')
    AND followed_up_at IS NULL;

ALTER TABLE people.employees ADD COLUMN gender text
    CONSTRAINT employees_gender_check CHECK (gender IN ('male', 'female'));

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
