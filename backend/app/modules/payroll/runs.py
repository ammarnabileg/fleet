"""The monthly payroll (BRD FR-PAY-01..06): one run per company and month, one line per employee at work.

A line, in the order the salary sheet shows it (for a driver on a pay scheme, the scheme's calculator gives the
earnings and its penalties instead of the platform's rates and invalid days: docs/payroll-schemes.md):

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

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.errors import AppError
from app.core.events import emit
from app.modules.approvals import service as approvals
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.payroll import calculators, platforms, schemes, statements
from app.modules.payroll.calculators import Month, Rules
from app.modules.payroll.columns import BY_CODE, COLUMNS
from app.modules.payroll.models import Deduction, Line, LineDeduction, Platform, Run, Scheme, Statement
from app.modules.payroll.service import month_cap, schedule
from app.modules.people import service as people

FILS = Decimal("0.001")
ZERO = Decimal(0)
BLOCKING = (
    "statement_missing",
    "statement_pending",
    "daily_pending",
    "scheme_missing",
    "figures_missing",
    "net_negative",
)
SCHEME_CELLS = ("orders_pay", "tier_bonus", "missing_target", "marks_deduction", "uncovered_penalty")
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
    breakdown: list[dict] = field(default_factory=list)  # the scheme's items: what the payslip explains


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
    scheme_name: dict | None = None,
    rules: Rules | None = None,
    needs_scheme: bool = False,
    absence_rule: str = "none",
) -> Computed:
    """One salary line. Pure: everything it needs is passed in. With `rules` (the driver's scheme this month) the
    scheme's calculator gives the earnings and the penalties; `needs_scheme`: his platform has schemes, so a driver
    on none is flagged rather than paid on the platform's rates."""
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

    on_scheme = rules is not None and rules.calculator != "platform_rates"
    month = Month(
        orders=orders or 0,
        valid_days=valid_days,
        batch_level=approved.batch_level if approved else None,
        attendance_marks=approved.attendance_marks if approved else None,
        star_day_failed=approved.star_day_failed if approved else None,
    )
    scheme_cells = dict.fromkeys(SCHEME_CELLS, ZERO)
    breakdown: list[dict] = []
    penalties = ZERO
    lacking = calculators.missing(calculators.CALCULATORS[rules.calculator], month) if on_scheme else []

    gross = basic if pay_basic and not on_scheme else ZERO  # a scheme is the whole of the platform's pay
    if on_scheme and not lacking:
        result = calculators.run(rules, month)
        gross += result.pay
        penalties = result.penalties
        for item in result.items:
            scheme_cells[item.code] = scheme_cells.get(item.code, ZERO) + abs(item.amount)
            breakdown.append({"code": item.code, "amount": str(item.amount), "why": item.why})
    elif platform and not on_scheme:
        gross += money(platform.per_order * (orders or 0))
        gross += money(platform.per_hour * (hours or 0))
        gross += money(platform.per_valid_day * (valid_days or 0))
    gross += items["bonus"] + items["tips"]

    invalid = ZERO
    if platform and not on_scheme and platform.invalid_days != "none" and valid_days is not None:
        days = max(0, working_days - valid_days)
        rate = (
            money(basic / platform.day_divisor)
            if platform.invalid_days == "daily_wage"
            else money(platform.invalid_day_amount)
        )
        invalid = money(days * rate)
    # absence and unpaid leave: a day's wage each when the settings say so, for pay made of the basic salary
    absent = system.get("absence_days", 0) + system.get("unpaid_leave_days", 0)
    absence = ZERO
    if absence_rule == "daily_wage" and absent and pay_basic and not on_scheme:
        absence = money(absent * money(basic / (platform.day_divisor if platform else 30)))
    month_items = sum((items[k] for k in MONTH_ITEMS), ZERO)
    earned = gross - invalid - absence - penalties
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
    deductions = invalid + absence + penalties + month_items + installments
    net = gross - deductions

    flags = []
    if system.get("pending_reports"):  # their orders, valid days and cash count only once reviewed
        flags.append("daily_pending")
    if needs_statement and statement is None:
        flags.append("statement_missing")
    elif needs_statement and approved is None:
        flags.append("statement_pending")
    if needs_scheme and rules is None:
        flags.append("scheme_missing")
    if lacking:
        flags.append("figures_missing")  # the reviewer enters them from the platform's report
    if earned - month_items < 0:
        flags.append("net_negative")
    if pay_basic and not basic and not on_scheme:
        flags.append("no_basic_salary")
    if profile["payment_method"] != "cash" and not profile["iban"]:
        flags.append("no_iban")
    if profile["is_driver"] and platform is None:
        flags.append("no_platform")
    if carried:
        flags.append("carried")
    if system.get("unclassified_days"):
        flags.append("days_unclassified")  # HR has days to mark: an absence among them is not deducted yet

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
        "absence_days": system.get("absence_days", 0),
        "leave_days": system.get("leave_days", 0),
        "scheme": (scheme_name or {}).get(name_lang) or next(iter((scheme_name or {}).values()), None),
        "batch_level": month.batch_level,
        "attendance_marks": month.attendance_marks,
        **scheme_cells,
        "bonus": items["bonus"],
        "tips": items["tips"],
        "gross": gross,
        "invalid_days_deduction": invalid,
        "absence_deduction": absence,
        **{k: items[k] for k in MONTH_ITEMS},
        **taken,
        "carried": carried,
        "net": net,
        "blank": None,
    }
    for code, value in cells.items():  # every amount with its three decimals, as the sheet shows it
        if value is not None and BY_CODE[code].kind == "money":
            cells[code] = money(value)
    return Computed(cells, money(gross), money(deductions), money(net), flags, dues, breakdown)


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
    # their advances locked first: an advance cancelled at the same moment (payroll.service.cancel, which locks it
    # too) is then either cancelled before this run reads it, or refused because this run took part of it
    db.execute(
        select(Deduction.id)
        .where(
            Deduction.employee_id.in_(ids or [0]), Deduction.source_type == "advance", Deduction.status == "approved"
        )
        .order_by(Deduction.id)
        .with_for_update()
    )
    dues = dues_for(db, ids, month)
    plats = platforms.all_by_id(db)
    assigned = schemes.for_month(db, ids, month)
    rules = schemes.rules_for(db, {s.id: s for s in assigned.values()})
    with_schemes = schemes.platforms_with_schemes(db)
    lang = i18n.default_language(db).code
    absence_rule = org.get_section(db, "payroll").absence_deduction
    totals = {"lines": 0, "gross": ZERO, "deductions": ZERO, "net": ZERO, "blocking": 0, "by_platform": {}}
    for p in profiles:
        platform = plats.get(p["platform_id"])
        st = found.get(p["id"])
        scheme = assigned.get(p["id"])
        if scheme is not None and scheme.platform_id != p["platform_id"]:
            scheme = None  # he moved platform: his old platform's scheme does not apply
        c = compute(
            p,
            platform,
            st,
            system[p["id"]],
            dues[p["id"]],
            cap_percent=run.cap_percent,
            cap_base=run.cap_base,
            name_lang=lang,
            scheme_name=scheme.name if scheme else None,
            rules=rules.get(scheme.id) if scheme else None,
            needs_scheme=bool(p["is_driver"] and p["platform_id"] in with_schemes),
            absence_rule=absence_rule,
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
            scheme_id=scheme.id if scheme else None,
            breakdown=c.breakdown,
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
                "breakdown": line.breakdown,
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
    approvals.submitted(db, "payroll_run", **_approval(run), actor_user_id=actor_user_id)
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
    approvals.submitted(db, "payroll_run", **_approval(run), actor_user_id=actor_user_id, note="recomputed")
    db.commit()
    return detail(db, public_id, **scope)


def _approval(run: Run) -> dict:
    return {
        "document_id": run.id,
        "document_key": run.public_id,
        "document_ref": f"PAY-{run.month:%Y-%m}",
        "company_id": run.company_id,
        "amount": Decimal(run.totals["net"]),
    }


def _open_month(db: Session, run: Run) -> None:
    """A run enters the books at its month's end: refused (period_closed) when that month of the books is closed."""
    from app.modules.finance import service as finance

    finance.check_open_month(db, _month_end(run.month))


def approve(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "draft":
        raise AppError(409, "run_not_draft")
    _open_month(db, run)
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
    if not approvals.gate(db, "payroll_run", **_approval(run), actor_user_id=actor_user_id):
        db.commit()  # this step recorded; the run waits for the next one
        return detail(db, public_id, **scope)
    run.status, run.approved_by, run.approved_at = "approved", actor_user_id, utcnow()
    run.version += 1
    employees = set(db.scalars(select(Line.employee_id).where(Line.run_id == run.id)))
    for employee_id in people.driver_ids(db, employees):  # the payslip is in the app now
        notifications.notify_driver(
            db,
            employee_id,
            "payslip_ready",
            params={"month": run.month.strftime("%m-%Y")},
            entity_type="payroll_run",
            entity_id=run.public_id,
            dedupe_key=f"payslip:{run.id}:{run.reopened}",
        )
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


def send_back(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    """Refused at a step of its approval workflow: it stays a draft, to be corrected and approved again."""
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "draft":
        raise AppError(409, "run_not_draft")
    approvals.gate(db, "payroll_run", **_approval(run), actor_user_id=actor_user_id, approve=False, reason=reason)
    audit.record(
        db,
        action="payroll.sent_back",
        entity_type="payroll_run",
        entity_id=run.public_id,
        actor_user_id=actor_user_id,
        company_id=run.company_id,
        after={"month": run.month, "reason": reason},
    )
    db.commit()
    return detail(db, public_id, **scope)


def reopen(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    run = _run(db, public_id, lock=True, **scope)
    if run.status != "approved":
        raise AppError(409, "run_not_approved")
    _open_month(db, run)  # its entry stands in a closed month
    if db.scalar(select(Run.id).where(Run.company_id == run.company_id, Run.month > run.month, Run.status != "draft")):
        raise AppError(409, "later_run_approved")
    run.status, run.approved_by, run.approved_at = "draft", None, None
    run.reopened += 1
    run.version += 1
    approvals.submitted(db, "payroll_run", **_approval(run), actor_user_id=actor_user_id)  # to be approved again
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


def sheet_columns(platform: Platform | None, labels: dict, cells: Iterable[dict] = ()) -> list[dict]:
    """The platform's sheet as the client set it, or every column. An absence deduction taken from any of the lines
    (`cells`) is shown even when the client's sheet has no column for it, just before the net: no line's net may be
    lower than its sheet adds up to without saying why."""
    if not (platform and platform.columns):
        return [{"code": c, "header": labels.get(c, c)} for c in DEFAULT_COLUMNS]
    cols = list(platform.columns)
    codes = {c["code"] for c in cols}
    if "absence_deduction" in codes or not any(Decimal(str(x.get("absence_deduction") or 0)) for x in cells):
        return cols
    extra = [{"code": k, "header": labels.get(k, k)} for k in ("absence_days", "absence_deduction") if k not in codes]
    at = next((i for i, c in enumerate(cols) if c["code"] == "net"), len(cols))
    return cols[:at] + extra + cols[at:]


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
    ids = {line.scheme_id for line, _ in rows if line.scheme_id}
    names = dict(db.execute(select(Scheme.id, Scheme.name).where(Scheme.id.in_(ids))).all()) if ids else {}
    out = []
    for line, run in rows:
        platform = plats.get(line.platform_id)
        cols = [
            c
            for c in sheet_columns(platform, labels, [line.cells])
            if c["code"] not in IDENTITY and c["code"] in BY_CODE
        ]
        out.append(
            {
                "month": run.month,
                "status": run.status,
                "platform": {"id": platform.id, "code": platform.code, "name": platform.name} if platform else None,
                "rows": [{"code": c["code"], "header": c["header"], "value": line.cells.get(c["code"])} for c in cols],
                # how his scheme computed the month, item by item with its reason (none on the platform's own rule)
                "scheme": {"name": names[line.scheme_id]} if line.scheme_id in names else None,
                "breakdown": line.breakdown or [],
                "gross": line.gross,
                "deductions": line.deductions,
                "net": line.net,
            }
        )
    return out


def run_for_export(db: Session, public_id, **scope) -> tuple[Run, list[Line]]:
    run = _run(db, public_id, **scope)
    return run, list(db.scalars(select(Line).where(Line.run_id == run.id).order_by(Line.id)))


# ------------------------------------------------------------------ for finance


def _month_end(month: date) -> date:
    nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def runs_for_posting(db: Session, first: date, last: date) -> dict[str, list[dict]]:
    """Approved runs whose month ends first..last (the month's salaries, net and installments taken), and runs paid
    on Kuwait days first..last: finance enters each once. A run reopened since is no longer listed."""
    approved = list(db.scalars(select(Run).where(Run.status.in_(("approved", "paid")), Run.month <= last)))
    approved = [r for r in approved if first <= _month_end(r.month) <= last]
    paid_on = func.date(func.timezone("Asia/Kuwait", Run.paid_at))
    paid = db.execute(select(Run, paid_on).where(Run.status == "paid", paid_on.between(first, last))).all()
    ids = {r.id for r in approved} | {r.id for r, _ in paid}
    net: dict[int, Decimal] = defaultdict(lambda: ZERO)
    taken: dict[int, Decimal] = defaultdict(lambda: ZERO)
    drivers_cost: dict[int, Decimal] = defaultdict(lambda: ZERO)  # what the drivers' salaries cost, net + installments
    if ids:
        lines = db.execute(
            select(Line.run_id, Line.employee_id, Line.net, func.coalesce(func.sum(LineDeduction.deducted), 0))
            .outerjoin(LineDeduction, LineDeduction.line_id == Line.id)
            .where(Line.run_id.in_(ids))
            .group_by(Line.id)
        ).all()
        drivers = people.driver_ids(db, {employee_id for _, employee_id, _, _ in lines})
        for run_id, employee_id, line_net, line_taken in lines:
            net[run_id] += line_net
            taken[run_id] += line_taken
            if employee_id in drivers:
                drivers_cost[run_id] += line_net + line_taken

    def out(r: Run, day: date) -> dict:
        return {
            "id": r.id,
            "company_id": r.company_id,
            "month": r.month,
            "date": day,
            "net": net[r.id],
            "installments": taken[r.id],
            "drivers": drivers_cost[r.id],
            "payment_ref": r.payment_ref,
        }

    return {"approved": [out(r, _month_end(r.month)) for r in approved], "paid": [out(r, d) for r, d in paid]}


def deductions_for_posting(db: Session, first: date, last: date) -> list[dict]:
    """Deductions made on Kuwait days first..last, for what the employee owes: the total while it stands, what was
    taken in approved payroll if it was cancelled since (nothing more will be)."""
    # the day it was made, or the day it was approved when that day was closed already (books_date)
    made_on = func.coalesce(Deduction.books_date, func.date(func.timezone("Asia/Kuwait", Deduction.created_at)))
    rows = db.execute(select(Deduction, made_on).where(made_on.between(first, last))).all()
    cancelled = [d.id for d, _ in rows if d.status == "cancelled"]
    taken: dict[int, Decimal] = {}
    if cancelled:
        taken = dict(
            db.execute(
                select(LineDeduction.deduction_id, func.sum(LineDeduction.deducted))
                .join(Line, Line.id == LineDeduction.line_id)
                .join(Run, Run.id == Line.run_id)
                .where(LineDeduction.deduction_id.in_(cancelled), Run.status.in_(("approved", "paid")))
                .group_by(LineDeduction.deduction_id)
            ).all()
        )
    return [
        {
            "id": d.id,
            "employee_id": d.employee_id,
            "company_id": d.company_id,
            "source_type": d.source_type,
            "reason": d.reason,
            "amount": d.total if d.status == "approved" else (taken.get(d.id) or ZERO),
            "date": day,
        }
        for d, day in rows
    ]
