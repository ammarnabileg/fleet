"""Driver languages: French, Swahili, Hindi and Filipino beside Arabic and English, and one translation store for the
driver's texts managed from the dashboard.

i18n.translations holds a text per (scope, key, language): `app` (the driver app's strings), `server` (the catalog
texts the driver sees: errors, notices, ...) and `status_templates` (the live-status cards). The texts shipped with
the code (the app's arb files, the catalogs, the seed files of the new languages) stay the base; a row here is an edit
made from the dashboard (a draft), or a base text marked as reviewed. Drafts reach the drivers when the language is
published: i18n.bundles keeps each published version (immutable, with its checksum) and languages.strings_version
names the latest. The old overrides (server texts edited from the settings screen) move here as reviewed `server`
rows: they stay in force until the language is first published (rows older than state.drafts_since).

Revision ID: 0063_driver_languages
Revises: 0062_driver_live_status
"""

from alembic import op

revision = "0063_driver_languages"
down_revision = "0062_driver_live_status"
branch_labels = None
depends_on = None

SQL = r"""
-- the latest published bundle of the language (0: none yet, the texts shipped with the code and the app)
ALTER TABLE i18n.languages ADD COLUMN strings_version bigint NOT NULL DEFAULT 0;

INSERT INTO i18n.languages (code, name_native, name_en, direction, fallback_code, is_default, sort_order) VALUES
    ('fr', 'Français', 'French', 'ltr', 'en', false, 3),
    ('sw', 'Kiswahili', 'Swahili', 'ltr', 'en', false, 4),
    ('hi', 'हिन्दी', 'Hindi', 'ltr', 'en', false, 5),
    ('fil', 'Filipino', 'Filipino', 'ltr', 'en', false, 6)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE i18n.translations (
    scope       text        NOT NULL
                            CONSTRAINT translations_scope_check CHECK (scope IN ('app', 'server', 'status_templates')),
    key         text        NOT NULL,
    lang        text        NOT NULL CONSTRAINT translations_lang_fkey REFERENCES i18n.languages (code),
    text        text        NOT NULL,
    status      text        NOT NULL DEFAULT 'needs_review'
                            CONSTRAINT translations_status_check CHECK (status IN ('machine', 'needs_review', 'reviewed')),
    updated_by  bigint,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT translations_pkey PRIMARY KEY (scope, key, lang)
);
CREATE INDEX translations_lang_idx ON i18n.translations (lang, scope);

INSERT INTO i18n.translations (scope, key, lang, text, status, updated_by, updated_at)
SELECT 'server', namespace || '.' || key, lang, value, 'reviewed', updated_by, updated_at FROM i18n.overrides;
DROP TABLE i18n.overrides;
-- texts saved before this migration applied at once; from now on an edit is a draft until published
ALTER TABLE i18n.state ADD COLUMN drafts_since timestamptz NOT NULL DEFAULT now();

-- Published bundles: immutable snapshots of a language's texts. `body` is the exact JSON document the app downloads
-- (its sha256 is in the manifest); `overrides` holds the dashboard's server and status-template texts in force.
CREATE TABLE i18n.bundles (
    lang        text        NOT NULL CONSTRAINT bundles_lang_fkey REFERENCES i18n.languages (code),
    version     bigint      NOT NULL CONSTRAINT bundles_version_check CHECK (version > 0),
    body        text        NOT NULL,
    sha256      text        NOT NULL,
    overrides   jsonb       NOT NULL,
    created_by  bigint,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bundles_pkey PRIMARY KEY (lang, version)
);

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.get_bind().connection.driver_connection.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
