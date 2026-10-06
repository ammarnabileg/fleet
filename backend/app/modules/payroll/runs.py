"""The monthly payroll (BRD FR-PAY-01..06): one run per company and month, one line per employee at work.

A line, in the order the salary sheet shows it:

    earnings    = basic salary (when the platform's rule pays it) + orders x rate + hours x rate + valid days x rate
                  + bonus + tips
    invalid     = (days worked - valid days) x the day's rate (the basic salary / divisor, or a fixed amount), for a
                  platform that pays by valid days; days worked come from the statement or, without one, from the
                  system (days with a daily report or a start of day in the app)
    month items = cancelled orders + the platform's deductions + late + cash shortage (from the statement)
    installments: the approved deductions (accidents, traffic fines, advances, SIM cards, other) due this month: their
                  monthly plan plus what earlier months could not take, oldest first, up to the cap. The cap is the
                  share of the month's salary in the settings (FR-PAY-03, BR-16: no default, payroll does not run
                  without it), of the basic salary or of the salary earned this month (earnings - invalid), and never
                  more than what is left after the month's items, so the net is never negative (FR-PAY-04). What a
                  month cannot take moves to the next one.
    net         = earnings - invalid - month items - installments taken

A draft is recomputed at will; approving recomputes it once more, refuses lines that are not ready (a statement
missing or waiting for review, a negative net) and locks the run and the month's statements. What each deduction
took in approved months is what the next months build on. Reopening is for the latest approved month only.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.org import service as org
from app.modules.payroll import platforms, statements
from app.modules.payroll.columns import BY_CODE, COLUMNS
from app.modules.payroll.models import Deduction, Line, LineDeduction, Platform, Run, Statement
from app.modules.payroll.service import month_cap, schedule
from app.modules.people import service as people

FILS = Decimal("0.001")
ZERO = Decimal(0)
BLOCKING = ("statement_missing", "statement_pending", "daily_pending", "net_negative")
# installment deductions by source -> the salary-sheet column they fill
SOURCE_COLUMN = {
    "accident": "car_repair",
    "fine": "traffic_fines",
    "advance": "advance",
    "sim": "sim",
    "other": "other_deductions",
}
MONTH_ITEMS = ("cancelled_orders", "platform_deductions", "late", "cash_shortage")
IDENTITY = ("platform_driver_id", "name", "job_title", "civil_id", "iban", "bank_name", "payment_method", "blank")
DEFAULT_COLUMNS = [c.code for c in COLUMNS if c.code != "blank"]


def money(v) -> Decimal:
    return Decimal(v or 0).quantize(FILS, rounding=ROUND_HALF_UP)


@dataclass
class Due:
    deduction: Deduction
    due: Decimal  # this month's plan plus what earlier months could not take
    deducted: Decimal = ZERO


@dataclass
class Computed:
    cells: dict
    gross: Decimal
    deductions: Decimal
    net: Decimal
    flags: list[str] = field(default_factory=list)
    dues: list[Due] = field(default_factory=list)


def compute(
    profile: dict,
    platform: Platform | None,
    statement,
    system: dict,
    dues: list[Due],
    *,
    cap_percent: Decimal,
    cap_base: str,
    name_lang: str,
) -> Computed:
    """One salary line. Pure: everything it needs is passed in."""
    approved = statement if statement is not None and statement.status == "approved" else None
    basic = money(profile["basic_salary"])
    pay_basic = platform.pay_basic if platform else True
    daily_valid = bool(platform and "valid_day" in platform.daily_fields)  # the driver sends it in each daily report
    needs_statement = bool(
        platform and (platform.driver_fields or (platform.invalid_days != "none" and not daily_valid))
    )

    working_days = approved.working_days if approved and approved.working_days is not None else system["working_days"]
    orders = approved.orders if approved and approved.orders is not None else system["orders"]
    hours = approved.hours if approved else None
    valid_days = approved.valid_days if approved else None
    if valid_days is None and daily_valid:
        valid_days = system["valid_days"]
    items = {k: money(getattr(approved, k)) if approved else ZERO for k in ("bonus", "tips", *MONTH_ITEMS)}

    gross = basic if pay_basic else ZERO
    if platform:
        gross += money(platform.per_order * (orders or 0))
        gross += money(platform.per_hour * (hours or 0))
        gross += money(platform.per_valid_day * (valid_days or 0))
    gross += items["bonus"] + items["tips"]

    invalid = ZERO
    if platform and platform.invalid_days != "none" and valid_days is not None:
        days = max(0, working_days - valid_days)
        rate = (
            money(basic / platform.day_divisor)
            if platform.invalid_days == "daily_wage"
            else money(platform.invalid_day_amount)
        )
        invalid = money(days * rate)
    month_items = sum((items[k] for k in MONTH_ITEMS), ZERO)
    earned = gross - invalid
    room = max(ZERO, earned - month_items)
    allowed = min(month_cap(basic if cap_base == "basic" else max(earned, ZERO), cap_percent), room)
    for d in sorted(dues, key=lambda x: (x.deduction.start_month, x.deduction.id)):
        d.deducted = min(d.due, allowed)
        allowed -= d.deducted
    taken = {code: ZERO for code in SOURCE_COLUMN.values()}
    for d in dues:
        taken[SOURCE_COLUMN[d.deduction.source_type]] += d.deducted
    installments = sum(taken.values(), ZERO)
    carried = sum((d.due - d.deducted for d in dues), ZERO)
    deductions = invalid + month_items + installments
    net = gross - deductions

    flags = []
    if system.get("pending_reports"):  # their orders, valid days and cash count only once reviewed
        flags.append("daily_pending")
    if needs_statement and statement is None:
        flags.append("statement_missing")
    elif needs_statement and approved is None:
        flags.append("statement_pending")
    if earned - month_items < 0:
        flags.append("net_negative")
    if pay_basic and not basic:
        flags.append("no_basic_salary")
    if profile["payment_method"] != "cash" and not profile["iban"]:
        flags.append("no_iban")
    if profile["is_driver"] and platform is None:
        flags.append("no_platform")
    if carried:
        flags.append("carried")

    name = profile["name"].get(name_lang) or next(iter(profile["name"].values()), "")
    cells = {
        "platform_driver_id": profile["platform_driver_id"],
        "name": name,
        "job_title": profile["job_title"],
        "civil_id": profile["civil_id"],
        "iban": profile["iban"],
        "bank_name": profile["bank_name"],
        "payment_method": profile["payment_method"],
        "basic": basic,
        "hours": hours,
        "orders": orders,
        "working_days": working_days,
        "valid_days": valid_days,
        "bonus": items["bonus"],
        "tips": items["tips"],
        "gross": gross,
        "invalid_days_deduction": invalid,
        **{k: items[k] for k in MONTH_ITEMS},
        **taken,
        "carried": carried,
        "net": net,
        "blank": None,
    }
    for code, value in cells.items():  # every amount with its three decimals, as the sheet shows it
        if value is not None and BY_CODE[code].kind == "money":
            cells[code] = money(value)
    return Computed(cells, money(gross), money(deductions), money(net), flags, dues)


def _json(cells: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in cells.items()}


# ------------------------------------------------------------------ deductions due in a month


def dues_for(db: Session, employee_ids: Iterable[int], month: date) -> dict[int, list[Due]]:
    """Each employee's live deductions with what they ask of `month`: the plan up to this month, less what approved
    months took (so a capped month's remainder comes back), never more than what is left of the total."""
    ids = list(employee_ids)
    out: dict[int, list[Due]] = {i: [] for i in ids}
    if not ids:
        return out
    rows = list(
        db.scalars(
            select(Deduction).where(
                Deduction.employee_id.in_(ids), Deduction.status == "approved", Deduction.start_month <= month
            )
        )
    )
    taken = dict(
        db.execute(
            select(LineDeduction.deduction_id, func.sum(LineDeduction.deducted))
            .join(Line, Line.id == LineDeduction.line_id)
            .join(Run, Run.id == Line.run_id)
            .where(
                Run.status != "draft", Run.month < month, LineDeduction.deduction_id.in_([d.id for d in rows] or [0])
            )
            .group_by(LineDeduction.deduction_id)
        ).all()
    )
    for d in rows:
        before = Decimal(taken.get(d.id) or 0)
        planned = sum(
            (s["amount"] for s in schedule(d.total, d.installments, d.start_month) if s["month"] <= month), ZERO
        )
        due = max(ZERO, planned - before)  # the plan sums to the total, so this never exceeds what is left
        if due:
            out[d.employee_id].append(Due(d, due))
    return out


# ------------------------------------------------------------------ the run


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Run.company_id.in_(list(company_ids)))


def _run(db: Session, public_id, *, lock: bool = False, **scope) -> Run:
    q = _scoped(select(Run).where(Run.public_id == public_id), **scope)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise AppError(404, "run_not_found")
    return r


def _fill(db: Session, run: Run) -> None:
    """(Re)computes every line of a draft run."""
    from app.modules.i18n import service as i18n

    db.execute(delete(Line).where(Line.run_id == run.id))
    month = run.month
    # employees at work, and one who left during the month but whose month the platform reported
    reported = statements.employees_with_statements(db, run.company_id, month)
    profiles = people.payroll_profiles(db, company_id=run.company_id, employee_ids=reported)
    ids = [p["id"] for p in profiles]
    found = statements.for_month(db, ids, month)
    system = statements.system_counts(db, ids, month)
    dues = dues_for(db, ids, month)
    plats = platforms.all_by_id(db)
    lang = i18n.default_language(db).code
    totals = {"lines": 0, "gross": ZERO, "deductions": ZERO, "net": ZERO, "blocking": 0, "by_platform": {}}
    for p in profiles:
        platform = plats.get(p["platform_id"])
        st = found.get(p["id"])
        c = compute(
            p,
            platform,
            st,
            system[p["id"]],
            dues[p["id"]],
            cap_percent=run.cap_percent,
            cap_base=run.cap_base,
            name_lang=lang,
        )
        line = Line(
            run_id=run.id,
            employee_id=p["id"],
            platform_id=p["platform_id"],
            statement_id=st.id if st is not None else None,
            cells=_json(c.cells),
            gross=c.gross,
            deductions=c.deductions,
            net=c.net,
            flags=c.flags,
        )
        db.add(line)
        db.flush()
        for d in c.dues:
            db.add(LineDeduction(line_id=line.id, deduction_id=d.deduction.id, due=d.due, deducted=d.deducted))
        totals["lines"] += 1
        totals["gross"] += c.gross
        totals["deductions"] += c.deductions
        totals["net"] += c.net
        totals["blocking"] += any(f in BLOCKING for f in c.flags)
        key = str(p["platform_id"] or "")
        totals["by_platform"][key] = totals["by_platform"].get(key, 0) + 1
    run.totals = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()}
    db.flush()


def _settings(db: Session) -> tuple[Decimal, str]:
    s = org.get_section(db, "payroll")
    if s.max_deduction_percent is None:
        raise AppError(409, "payroll_cap_not_set")
    return s.max_deduction_percent, s.deduction_cap_base


def _out(db: Session, r: Run, *, lines: bool = False) -> dict:
    users = identity.user_names(db, {u for u in (r.prepared_by, r.approved_by, r.paid_by) if u})
    out = {
        "id": str(r.public_id),
        "company_id": r.company_id,
        "month": r.month,
        "status": r.status,
        "cap_percent": r.cap_percent,
        "cap_base": r.cap_base,
        "totals": r.totals,
        "prepared_at": r.prepared_at,
        "prepared_by": users.get(r.prepared_by),
        "approved_at": r.approved_at,
        "approved_by": users.get(r.approved_by),
        "paid_at": r.paid_at,
        "paid_by": users.get(r.paid_by),
        "payment_ref": r.payment_ref,
        "reopened": r.reopened,
        "blocking": int((r.totals or {}).get("blocking", 0)),
        "version": r.version,
    }
    if lines:
        rows = list(db.scalars(select(Line).where(Line.run_id == r.id).order_by(Line.id)))
        names = people.names(db, {line.employee_id for line in rows})
        wanted = [x.statement_id for x in rows if x.statement_id] or [0]
        sts = {s.id: str(s.public_id) for s in db.scalars(select(Statement).where(Statement.id.in_(wanted)))}
        out["lines"] = [
            {
                "employee": names.get(line.employee_id) or {},
                "platform_id": line.platform_id,
                "cells": line.cells,
                "gross": line.gross,
                "deductions": line.deductions,
                "net": line.net,
                "flags": list(line.flags),
                "statement_id": sts.get(line.statement_id),
            }
            for line in rows
        ]
    return out


def list_runs(db: Session, *, company_id: int | None = None, **scope) -> list[dict]:
    q = _scoped(select(Run), **scope)
    if company_id:
        q = q.where(Run.company_id == company_id)
    return [_out(db, r) for r in db.scalars(q.order_by(Run.month.desc(), Run.company_id))]


def detail(db: Session, public_id, **scope) -> dict:
    return _out(db, _run(db, public_id, **scope), lines=True)


def prepare(db: Session, *, company_id: int, month: date, actor_user_id: int, all_companies: bool, company_ids) -> dict:
    if not org.company_ids_exist(db, [company_id]):
        raise AppError(422, "company_not_found")
    if not (all_companies or company_id in set(company_ids)):
        raise AppError(403, "company_out_of_scope")
    month = statements.month_start(month)
    if month > statements.month_start(today()):
        raise AppError(422, "run_month_in_future")
    percent, base = _settings(db)
    if db.scalar(select(Run.id).where(Run.company_id == company_id, Run.month == month)):
        raise AppError(409, "run_exists")
    run = Run(company_id=company_id, month=month, cap_percent=percent, cap_base=base, prepared_by=actor_user_id)
    db.add(run)
    db.flush()
    _fill(db, run)
    audit.record(
        db,
        action="payroll.prepared",
        entity_type="payroll_run",
        entity_id=run.public_id,
        actor_user_id=actor_user_id,
        company_id=company_id,
        after={"month": month, **run.totals},
    )
    db.commit()
    return detail(db, run.public_id, all_companies=all_companies, company_ids=company_ids)


def recompute(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "draft":
        raise AppError(409, "run_not_draft")
    run.cap_percent, run.cap_base = _settings(db)
    run.prepared_by, run.prepared_at = actor_user_id, utcnow()
    run.version += 1
    _fill(db, run)
    db.commit()
    return detail(db, public_id, **scope)


def approve(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "draft":
        raise AppError(409, "run_not_draft")
    earlier = db.scalar(
        select(Run.month).where(Run.company_id == run.company_id, Run.month < run.month, Run.status == "draft")
    )
    if earlier:
        raise AppError(409, "earlier_run_draft", month=earlier.isoformat()[:7])
    if db.scalar(select(Run.id).where(Run.company_id == run.company_id, Run.month > run.month, Run.status != "draft")):
        raise AppError(409, "later_run_approved")
    run.cap_percent, run.cap_base = _settings(db)
    _fill(db, run)  # what is approved is what the data says now
    blocking = int(run.totals["blocking"])
    if blocking:
        db.commit()  # the recomputed lines show what blocks
        raise AppError(409, "run_has_blocking", count=blocking)
    run.status, run.approved_by, run.approved_at = "approved", actor_user_id, utcnow()
    run.version += 1
    audit.record(
        db,
        action="payroll.approved",
        entity_type="payroll_run",
        entity_id=run.public_id,
        actor_user_id=actor_user_id,
        company_id=run.company_id,
        after={"month": run.month, **run.totals},
    )
    emit(
        db,
        "payroll.run.approved",
        run.public_id,
        {
            "run_id": str(run.public_id),
            "company_id": run.company_id,
            "month": run.month.isoformat(),
            "net": run.totals["net"],
        },
    )
    db.commit()
    return detail(db, public_id, **scope)


def reopen(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "approved":
        raise AppError(409, "run_not_approved")
    if db.scalar(select(Run.id).where(Run.company_id == run.company_id, Run.month > run.month, Run.status != "draft")):
        raise AppError(409, "later_run_approved")
    run.status, run.approved_by, run.approved_at = "draft", None, None
    run.reopened += 1
    run.version += 1
    audit.record(
        db,
        action="payroll.reopened",
        entity_type="payroll_run",
        entity_id=run.public_id,
        actor_user_id=actor_user_id,
        company_id=run.company_id,
        after={"month": run.month, "reason": reason},
    )
    db.commit()
    return detail(db, public_id, **scope)


def mark_paid(db: Session, public_id, *, payment_ref: str | None, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "approved":
        raise AppError(409, "run_not_approved")
    run.status, run.paid_by, run.paid_at, run.payment_ref = "paid", actor_user_id, utcnow(), payment_ref
    run.version += 1
    audit.record(
        db,
        action="payroll.paid",
        entity_type="payroll_run",
        entity_id=run.public_id,
        actor_user_id=actor_user_id,
        company_id=run.company_id,
        after={"month": run.month, "payment_ref": payment_ref, "net": run.totals["net"]},
    )
    emit(db, "payroll.run.paid", run.public_id, {"run_id": str(run.public_id), "month": run.month.isoformat()})
    db.commit()
    return detail(db, public_id, **scope)


# ------------------------------------------------------------------ the driver's payslips


def sheet_columns(platform: Platform | None, labels: dict) -> list[dict]:
    if platform and platform.columns:
        return platform.columns
    return [{"code": c, "header": labels.get(c, c)} for c in DEFAULT_COLUMNS]


def payslips(db: Session, employee_id: int) -> list[dict]:
    from app.modules.i18n import service as i18n

    labels = i18n.base_catalog(i18n.default_language(db).code).get("payroll_column", {})
    rows = db.execute(
        select(Line, Run)
        .join(Run, Run.id == Line.run_id)
        .where(Line.employee_id == employee_id, Run.status != "draft")
        .order_by(Run.month.desc())
        .limit(12)
    ).all()
    plats = platforms.all_by_id(db)
    out = []
    for line, run in rows:
        platform = plats.get(line.platform_id)
        cols = [c for c in sheet_columns(platform, labels) if c["code"] not in IDENTITY and c["code"] in BY_CODE]
        out.append(
            {
                "month": run.month,
                "status": run.status,
                "platform": {"id": platform.id, "code": platform.code, "name": platform.name} if platform else None,
                "rows": [{"code": c["code"], "header": c["header"], "value": line.cells.get(c["code"])} for c in cols],
                "gross": line.gross,
                "deductions": line.deductions,
                "net": line.net,
            }
        )
    return out


def run_for_export(db: Session, public_id, **scope) -> tuple[Run, list[Line]]:
    run = _run(db, public_id, **scope)
    return run, list(db.scalars(select(Line).where(Line.run_id == run.id).order_by(Line.id)))
