"""The system back to new, for its owner before going live: one database function the app may call as a whole and
nothing else. It empties what the business recorded (drivers, vehicles, custody, positions, cash and the books' entries,
payroll runs, deductions, accidents, fines, maintenance and its centers, insurers, documents, alerts, devices and every
office user but the one asking) and keeps what the system is set up with: the companies and branches with their
settings, the platforms with their pay schemes, the roles, the chart of accounts and expense types, the document types,
employment statuses, leave types, approval workflows, translations, app releases and the audit log (which records the
reset). The numbering starts again. All in one transaction: anything refused and nothing is emptied.

It truncates, so the guards on posted journals and entries (which refuse a DELETE) do not stand in its way: that is
why it is a SECURITY DEFINER function of the migration owner, and why the app gets EXECUTE on it and not TRUNCATE.

Revision ID: 0083_factory_reset
Revises: 0082_accident_insurers
"""

from alembic import op

revision = "0083_factory_reset"
down_revision = "0082_accident_insurers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION public.fleet_factory_reset(keep_user bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM identity.users WHERE id = keep_user AND is_superuser) THEN
        RAISE EXCEPTION 'factory reset: user % is not a superuser', keep_user;
    END IF;
    TRUNCATE
        accidents.accident_events, accidents.accident_photos, accidents.accidents, accidents.insurers,
        approvals.decisions, approvals.delegations, approvals.steps, approvals.requests,
        attendance.day_marks, attendance.leaves,
        cash.fuel_claims, cash.journal_lines, cash.journals, cash.petty_expenses, cash.receipts,
        cash.treasury_closings,
        daily_ops.report_changes, daily_ops.reports,
        documents.renewals, documents.documents,
        finance.entry_lines, finance.entries, finance.expense_files, finance.expenses, finance.periods,
        fines.fines,
        fleet.custody_photos, fleet.odometer_readings, fleet.vehicle_change_requests, fleet.vehicle_claims,
        fleet.custodies, fleet.vehicles,
        identity.activation_links, identity.claim_attempts, identity.device_status, identity.device_tokens,
        identity.driver_claims, identity.link_queue, identity.otp_challenges, identity.password_reset_codes,
        identity.rate_hits, identity.devices,
        integrations.deliveries, integrations.email_outbox, integrations.message_log, integrations.outbox,
        integrations.processed_events,
        maintenance.invoice_items, maintenance.invoices, maintenance.quotes, maintenance.replacements,
        maintenance.request_events, maintenance.request_photos, maintenance.requests, maintenance.schedules,
        maintenance.center_users, maintenance.centers,
        notifications.alert_events, notifications.alerts, notifications.broadcast_deliveries,
        notifications.broadcasts, notifications.contact_requests, notifications.driver_notices,
        onboarding.submissions,
        org.site_messages,
        payroll.line_deductions, payroll.lines, payroll.statement_files, payroll.statements, payroll.runs,
        payroll.deductions, payroll.driver_schemes, payroll.month_exceptions, payroll.month_imports,
        payroll.month_values, payroll.objections, payroll.platform_requests, payroll.rider_id_months,
        payroll.scheme_change_requests, payroll.uncollected,
        tracking.last_positions, tracking.mock_events, tracking.positions, tracking.rejected_points
    RESTART IDENTITY;
    -- the drivers' and petty cash holders' accounts went with them; the branch treasuries and the books' accounts stay
    DELETE FROM cash.accounts WHERE kind IN ('driver', 'petty');
    TRUNCATE people.status_history, people.external_refs;
    DELETE FROM people.employees;
    -- every office user but the one asking
    DELETE FROM identity.sessions WHERE user_id <> keep_user;
    DELETE FROM identity.user_roles WHERE user_id <> keep_user;
    DELETE FROM identity.user_companies WHERE user_id <> keep_user;
    DELETE FROM identity.users WHERE id <> keep_user;
    ALTER SEQUENCE accidents.accident_number_seq RESTART;
    ALTER SEQUENCE fines.fine_number_seq RESTART;
    ALTER SEQUENCE maintenance.request_number_seq RESTART;
    ALTER SEQUENCE finance.entry_number_seq RESTART;
    ALTER SEQUENCE finance.expense_number_seq RESTART;
END $$;
REVOKE ALL ON FUNCTION public.fleet_factory_reset(bigint) FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fleet_app') THEN
        GRANT EXECUTE ON FUNCTION public.fleet_factory_reset(bigint) TO fleet_app;
    END IF;
END $$;
SELECT public.fleet_apply_grants();
""")


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations")
