"""Month close: a month of the books checked (what still has to be done in it, each with what to do), then closed by
the accountant once the check is clean. A closed month takes no entry and no cash journal dated in it (refused here
and by the database); only the latest closed month reopens, with a reason. A month without a row is open."""

from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.finance.models import Entry, Expense, Period
from app.modules.identity import service as identity

PROBLEMS = (
    "month_not_over",
    "earlier_month_open",
    "draft_entries",
    "stale_entries",
    "documents_not_entered",
    "pending_expenses",
    "pending_fuel_claims",
    "pending_daily_reports",
    "pending_deductions",
    "draft_payroll_runs",
    "treasury_days_open",
)


def parse_month(raw: str) -> date:
    """ "2026-09" -> 2026-09-01; 422 otherwise."""
    try:
        year, month = raw.split("-")
        if len(year) != 4 or len(month) != 2:
            raise ValueError
        return date(int(year), int(month), 1)
    except ValueError:
        raise AppError(422, "invalid_month") from None


def month_end(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _label(month: date) -> str:
    return f"{month:%Y-%m}"


def is_closed(db: Session, day: date) -> bool:
    """Whether the month of `day` is closed, holding the month's shared lock until the transaction ends: a close
    (which takes it exclusively) then never runs between this check and what the caller writes."""
    return bool(db.scalar(text("SELECT finance.month_closed(:d)"), {"d": day}))


def check_open(db: Session, day: date) -> None:
    """409 period_closed when the month of `day` is closed (see is_closed)."""
    if is_closed(db, day):
        raise AppError(409, "period_closed", month=_label(day.replace(day=1)))


def _lock(db: Session, month: date) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"finance.period:{_label(month)}"})


def _out(db: Session, p: Period | None, month: date, latest: date | None) -> dict:
    users = identity.user_names(db, {p.closed_by, p.reopened_by} if p else set())
    closed = p is not None and p.status == "closed"
    return {
        "month": _label(month),
        "status": "closed" if closed else "open",
        "closed_by": users.get(p.closed_by) if closed else None,
        "closed_at": p.closed_at if closed else None,
        "reopened_by": users.get(p.reopened_by) if p else None,
        "reopened_at": p.reopened_at if p else None,
        "reopen_reason": p.reopen_reason if p else None,
        "reopenable": closed and month == latest,
    }


def _latest_closed(db: Session) -> date | None:
    return db.scalar(select(func.max(Period.month)).where(Period.status == "closed"))


def list_periods(db: Session, first: date, last: date) -> list[dict]:
    """The months first..last, newest first, with their status."""
    if last < first:
        raise AppError(422, "invalid_range")
    rows = {p.month: p for p in db.scalars(select(Period).where(Period.month.between(first, last)))}
    latest = _latest_closed(db)
    out, m = [], last
    while m >= first and len(out) < 120:
        out.append(_out(db, rows.get(m), m, latest))
        m = (m - timedelta(days=1)).replace(day=1)
    return out


def problems(db: Session, month: date) -> list[dict]:
    """What stands between the month and its close, each {code, params}: the month not over yet, an earlier month
    still open, drafts, entries whose document changed, documents not entered yet, documents still waiting for a
    decision (expenses, fuel claims, daily reports, deductions, payroll runs), treasury days with movements not
    counted and closed (per branch)."""
    from app.modules.cash import service as cash
    from app.modules.daily_ops import service as daily_ops
    from app.modules.finance import service as finance
    from app.modules.payroll import service as payroll

    first, last = month, month_end(month)
    out: list[dict] = []

    def add(code: str, **params) -> None:
        assert code in PROBLEMS, code
        out.append({"code": code, "params": params})

    if last >= today():
        add("month_not_over", end=last.isoformat())
    earliest = db.scalar(select(func.min(Entry.entry_date)))
    if earliest is not None:
        closed = set(db.scalars(select(Period.month).where(Period.status == "closed", Period.month < first)))
        m = earliest.replace(day=1)
        while m < first:
            if m not in closed:
                add("earlier_month_open", month=_label(m))
                break
            m = (m + timedelta(days=32)).replace(day=1)
    drafts = db.scalar(
        select(func.count()).select_from(Entry).where(Entry.status == "draft", Entry.entry_date.between(first, last))
    )
    if drafts:
        add("draft_entries", count=drafts)
    start = finance.books(db).books_start_date
    lo = max(first, start) if start else first  # documents before the books start are in the opening balances
    if lo <= last:
        missing, stale = finance.compare(db, lo, last)
        if stale:
            add("stale_entries", count=len(stale))
        if missing:
            add("documents_not_entered", count=len(missing))
    expenses = db.scalar(
        select(func.count())
        .select_from(Expense)
        .where(Expense.status == "pending", Expense.expense_date.between(first, last))
    )
    if expenses:
        add("pending_expenses", count=expenses)
    fuel = cash.pending_fuel_claims(db, first, last)
    if fuel:
        add("pending_fuel_claims", count=fuel)
    reports = daily_ops.pending_between(db, first, last)
    if reports:
        add("pending_daily_reports", count=reports)
    waiting = payroll.pending_for_close(db, first, last)
    if waiting["deductions"]:
        add("pending_deductions", count=waiting["deductions"])
    if waiting["runs"]:
        add("draft_payroll_runs", count=waiting["runs"])
    for b in cash.unclosed_days(db, first, last):
        add(
            "treasury_days_open",
            branch=b["branch"]["name"],
            count=len(b["days"]),
            first=b["days"][0].isoformat(),
        )
    return out


def check(db: Session, month: date) -> dict:
    p = db.get(Period, month)
    return {
        "month": _label(month),
        "status": p.status if p else "open",
        "problems": problems(db, month),
    }


def close(db: Session, month: date, *, actor_user_id: int) -> dict:
    """Closed only with a clean check (422 period_not_ready with the problems otherwise), under the month's exclusive
    lock: no document of the month is being written while it checks."""
    _lock(db, month)
    p = db.get(Period, month, with_for_update=True)
    if p is not None and p.status == "closed":
        raise AppError(409, "period_closed", month=_label(month))
    found = problems(db, month)
    if found:
        raise AppError(422, "period_not_ready", month=_label(month), count=len(found), problems=found)
    if p is None:
        p = Period(month=month, status="closed")
        db.add(p)
    p.status, p.closed_by, p.closed_at = "closed", actor_user_id, utcnow()
    db.flush()
    audit.record(
        db,
        action="finance.period.closed",
        entity_type="period",
        entity_id=_label(month),
        actor_user_id=actor_user_id,
        after={"month": _label(month)},
    )
    db.commit()
    return _out(db, p, month, month)


def reopen(db: Session, month: date, *, reason: str, actor_user_id: int) -> dict:
    """Only the latest closed month reopens (the ones before it stay closed), with the reason."""
    _lock(db, month)
    p = db.get(Period, month, with_for_update=True)
    if p is None or p.status != "closed" or month != _latest_closed(db):
        raise AppError(409, "period_not_latest")
    p.status, p.reopened_by, p.reopened_at, p.reopen_reason = "open", actor_user_id, utcnow(), reason
    db.flush()
    audit.record(
        db,
        action="finance.period.reopened",
        entity_type="period",
        entity_id=_label(month),
        actor_user_id=actor_user_id,
        after={"month": _label(month), "reason": reason},
    )
    db.commit()
    return _out(db, p, month, _latest_closed(db))
