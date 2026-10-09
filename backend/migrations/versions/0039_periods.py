"""Month close: a month of the books is closed by the accountant once its check is clean (no drafts, nothing left to
enter or to reverse, nothing pending, every treasury day with movements counted and closed, every earlier month
closed). A closed month takes no entry: none is inserted or approved with its date, and no cash journal is written or
posted with a business date in it; both are refused here as well as in the service. Only the latest closed month may
be reopened, with a reason. A month without a row is open.

Writers take a shared lock on the month (finance.month_closed) and the close an exclusive one, so a close never
misses a document written while it checks.

Revision ID: 0039_periods
Revises: 0038_treasury_closings
"""

from alembic import op

revision = "0039_periods"
down_revision = "0038_treasury_closings"
branch_labels = None
depends_on = None

SQL = r"""
CREATE TABLE finance.periods (
    month          date        CONSTRAINT periods_pkey PRIMARY KEY
                               CONSTRAINT periods_month_check CHECK (extract(day FROM month) = 1),
    status         text        NOT NULL CONSTRAINT periods_status_check CHECK (status IN ('open', 'closed')),
    closed_by      bigint      CONSTRAINT periods_closed_by_fkey REFERENCES identity.users (id),
    closed_at      timestamptz,
    reopened_by    bigint      CONSTRAINT periods_reopened_by_fkey REFERENCES identity.users (id),
    reopened_at    timestamptz,
    reopen_reason  text,
    CONSTRAINT periods_closed_check CHECK (status <> 'closed' OR (closed_by IS NOT NULL AND closed_at IS NOT NULL)),
    CONSTRAINT periods_reopened_check
        CHECK ((reopened_at IS NULL) = (reopened_by IS NULL) AND (reopened_at IS NULL) = (reopen_reason IS NULL))
);

-- Whether the month of a day is closed, holding the month's shared lock until the transaction ends.
CREATE FUNCTION finance.month_closed(day date) RETURNS boolean LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock_shared(hashtextextended('finance.period:' || to_char(day, 'YYYY-MM'), 0));
    RETURN EXISTS (SELECT 1 FROM finance.periods
                   WHERE month = date_trunc('month', day)::date AND status = 'closed');
END $$;

CREATE FUNCTION finance.guard_period() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (TG_OP = 'INSERT' OR (OLD.status = 'draft' AND NEW.status = 'approved'))
       AND finance.month_closed(NEW.entry_date) THEN
        RAISE EXCEPTION 'the month of % is closed', NEW.entry_date;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER entries_period BEFORE INSERT OR UPDATE OF status ON finance.entries
    FOR EACH ROW EXECUTE FUNCTION finance.guard_period();

CREATE FUNCTION cash.guard_period() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (TG_OP = 'INSERT' OR (NEW.status = 'posted' AND OLD.status <> 'posted'))
       AND finance.month_closed(NEW.business_date) THEN
        RAISE EXCEPTION 'the month of % is closed', NEW.business_date;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER journals_period BEFORE INSERT OR UPDATE OF status ON cash.journals
    FOR EACH ROW EXECUTE FUNCTION cash.guard_period();

-- who closes the books' months in the role templates: the accountant, and management
INSERT INTO identity.role_permissions (role_id, permission)
SELECT id, 'finance.close' FROM identity.roles WHERE code IN ('accountant', 'management')
ON CONFLICT DO NOTHING;

SELECT public.fleet_apply_grants();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
