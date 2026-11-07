"""i18n: languages and translation overrides. Base catalogs (ar, en) ship with the code.

Revision ID: 0002_i18n
Revises: 0001_foundation
"""

from alembic import op

revision = "0002_i18n"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

SQL = r"""
CREATE SCHEMA i18n;

CREATE TABLE i18n.languages (
    code           text        CONSTRAINT languages_pkey PRIMARY KEY
                               CONSTRAINT languages_code_check CHECK (code ~ '^[a-z]{2,3}(-[A-Z]{2})?$'),
    name_native    text        NOT NULL,
    name_en        text        NOT NULL,
    direction      text        NOT NULL CONSTRAINT languages_direction_check CHECK (direction IN ('rtl', 'ltr')),
    fallback_code  text        CONSTRAINT languages_fallback_code_fkey REFERENCES i18n.languages (code),
    is_default     boolean     NOT NULL DEFAULT false,
    is_active      boolean     NOT NULL DEFAULT true,
    sort_order     integer     NOT NULL DEFAULT 100,
    created_at     timestamptz NOT NULL DEFAULT now(),
    version        integer     NOT NULL DEFAULT 1,
    CONSTRAINT languages_default_active_check CHECK (NOT (is_default AND NOT is_active)),
    CONSTRAINT languages_fallback_check CHECK (fallback_code IS DISTINCT FROM code)
);
CREATE UNIQUE INDEX languages_is_default_idx ON i18n.languages (is_default) WHERE is_default;

-- Edits made from the settings screen, and whole languages added without a deploy.
-- Effective text = base catalog (code) <- overrides (here), with the language's fallback chain.
CREATE TABLE i18n.overrides (
    lang        text        NOT NULL CONSTRAINT overrides_lang_fkey REFERENCES i18n.languages (code),
    namespace   text        NOT NULL,
    key         text        NOT NULL,
    value       text        NOT NULL,
    updated_by  bigint,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT overrides_pkey PRIMARY KEY (lang, namespace, key)
);

-- Bumped on every change; clients cache catalogs by this number (ETag).
CREATE TABLE i18n.state (
    singleton  boolean NOT NULL DEFAULT true CONSTRAINT state_pkey PRIMARY KEY CONSTRAINT state_singleton_check CHECK (singleton),
    revision   bigint  NOT NULL DEFAULT 1
);
INSERT INTO i18n.state DEFAULT VALUES;

INSERT INTO i18n.languages (code, name_native, name_en, direction, is_default, sort_order) VALUES
    ('ar', 'العربية', 'Arabic', 'rtl', true, 1),
    ('en', 'English', 'English', 'ltr', false, 2);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
