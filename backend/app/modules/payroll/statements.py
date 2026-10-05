"""The platform's figures for a driver's month (BRD FR-PAY-01 inputs).

A platform that pays by valid days (or needs orders or hours) gets them from the driver: at the start of the month he
sends, from the app, screenshots of the platform's monthly summary and the figures he reads on them. The system cannot
read a screenshot (no OCR), and a screenshot is the driver's own evidence: a reviewer compares the figures with the
screenshots, and with the platform's partner report where there is one, then approves them as they are or corrected,
or rejects them with a reason (the driver sends them again). The office may also enter a month itself. The bonus, the
tips and the platform's deductions come from the platform's settlement and are entered by the office.

Payroll uses approved figures only. Once the month's payroll is approved, its statements no longer change.
"""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.daily_ops import service as daily_ops
from app.modules.files import service as files
from app.modules.fleet import service as fleet
from app.modules.identity import service as identity
from app.modules.payroll import platforms
from app.modules.payroll.models import Run, Statement, StatementFile
from app.modules.people import service as people

COUNTS = ("working_days", "valid_days", "orders", "hours")
AMOUNTS = ("bonus", "tips", "cancelled_orders", "platform_deductions", "late", "cash_shortage")


def month_start(d: date) -> date:
    return d.replace(day=1)


def prev_month(d: date) -> date:
    d = month_start(d)
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def month_end(d: date) -> date:
    d = month_start(d)
    nxt = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def locked_months(db: Session, pairs: Iterable[tuple[int, date]]) -> set[tuple[int, date]]:
    """Which (company, month) have an approved or paid payroll."""
    pairs = set(pairs)
    if not pairs:
        return set()
    rows = db.execute(
        select(Run.company_id, Run.month).where(
            Run.status != "draft",
            Run.company_id.in_({c for c, _ in pairs}),
            Run.month.in_({m for _, m in pairs}),
        )
    )
    return {(c, m) for c, m in rows} & pairs


def _check_open(db: Session, company_id: int, month: date) -> None:
    if locked_months(db, [(company_id, month)]):
        raise AppError(409, "payroll_locked")


def system_counts(db: Session, employee_ids: Iterable[int], month: date) -> dict[int, dict]:
    """What the system itself saw in the month: the days a driver worked (a daily report or a start of day in the
    app) and the orders in his approved daily reports. Shown next to the platform's figures, and used when the
    statement leaves them out."""
    ids = list(employee_ids)
    first, last = month_start(month), month_end(month)
    activity = daily_ops.month_activity(db, ids, first, last)
    started = fleet.start_days(db, ids, first, last)
    return {i: {"working_days": len(activity[i]["days"] | started[i]), "orders": activity[i]["orders"]} for i in ids}


def _brief(p) -> dict | None:
    return {"id": p.id, "code": p.code, "name": p.name} if p else None


def _out(db: Session, rows: list[Statement], *, with_system: bool = False) -> list[dict]:
    names = people.names(db, {s.employee_id for s in rows})
    users = identity.user_names(db, {s.reviewed_by for s in rows if s.reviewed_by})
    plats = platforms.all_by_id(db)
    shots: dict[int, list[str]] = {}
    if rows:
        for f in db.scalars(
            select(StatementFile)
            .where(StatementFile.statement_id.in_([s.id for s in rows]))
            .order_by(StatementFile.position)
        ):
            shots.setdefault(f.statement_id, []).append(f.sha256)
    locked = locked_months(db, {(s.company_id, s.month) for s in rows})
    system: dict[tuple[int, date], dict] = {}
    if with_system:
        for s in rows:
            system[(s.employee_id, s.month)] = system_counts(db, [s.employee_id], s.month)[s.employee_id]
    return [
        {
            "id": str(s.public_id),
            "employee": names.get(s.employee_id),
            "company_id": s.company_id,
            "platform": _brief(plats.get(s.platform_id)),
            "month": s.month,
            "status": s.status,
            "declared": s.declared,
            **{k: getattr(s, k) for k in COUNTS + AMOUNTS},
            "screenshots": shots.get(s.id, []),
            "system": system.get((s.employee_id, s.month), {}),
            "submitted_at": s.submitted_at,
            "from_driver": s.submitted_by_device is not None,
            "reviewed_at": s.reviewed_at,
            "reviewed_by": users.get(s.reviewed_by),
            "review_note": s.review_note,
            "locked": (s.company_id, s.month) in locked,
            "version": s.version,
        }
        for s in rows
    ]


def _insert(db: Session, s: Statement) -> None:
    db.add(s)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "statements_one_per_month_idx":
            raise
        raise AppError(409, "statement_exists") from None
    db.refresh(s)


# ------------------------------------------------------------------ the driver


def _open_months(db: Session, company_id: int) -> list[date]:
    """This month and the previous one, unless their payroll is approved."""
    months = [prev_month(today()), month_start(today())]
    locked = locked_months(db, [(company_id, m) for m in months])
    return [m for m in months if (company_id, m) not in locked]


def driver_view(db: Session, employee_id: int) -> dict:
    profile = people.payroll_profile(db, employee_id)
    platform = platforms.get(db, profile["platform_id"])
    rows = list(
        db.scalars(
            select(Statement)
            .where(Statement.employee_id == employee_id)
            .order_by(Statement.month.desc(), Statement.id.desc())
            .limit(12)
        )
    )
    return {
        "platform": _brief(platform),
        "driver_fields": list(platform.driver_fields) if platform else [],
        "months": _open_months(db, profile["company_id"]) if platform else [],
        "statements": [
            {
                "id": str(s.public_id),
                "month": s.month,
                "status": s.status,
                "declared": s.declared,
                "valid_days": s.valid_days,
                "orders": s.orders,
                "hours": s.hours,
                "review_note": s.review_note,
                "submitted_at": s.submitted_at,
            }
            for s in rows
        ],
    }


def driver_submit(db: Session, employee_id: int, device_id: int, data: dict) -> dict:
    profile = people.payroll_profile(db, employee_id)
    platform = platforms.get(db, profile["platform_id"])
    if platform is None:
        raise AppError(422, "no_platform")
    month = month_start(data["month"])
    if month not in (prev_month(today()), month_start(today())):
        raise AppError(422, "statement_month_invalid")
    _check_open(db, profile["company_id"], month)
    for field in platform.driver_fields:
        if data.get(field) is None:
            raise AppError(422, "field_required", field=field)
    for sha in data["screenshots"]:
        shot = files.get(db, sha)
        if shot.uploaded_by_device != device_id or shot.content_type not in files.IMAGES:
            raise AppError(422, "file_not_yours")
    declared = {k: data[k] for k in ("valid_days", "orders", "hours") if data.get(k) is not None}
    s = Statement(
        employee_id=employee_id,
        company_id=profile["company_id"],
        platform_id=platform.id,
        month=month,
        declared={k: str(v) if k == "hours" else v for k, v in declared.items()},
        valid_days=data.get("valid_days"),
        orders=data.get("orders"),
        hours=data.get("hours"),
        submitted_by_device=device_id,
    )
    _insert(db, s)
    for i, sha in enumerate(dict.fromkeys(data["screenshots"])):
        db.add(StatementFile(statement_id=s.id, sha256=sha, position=i))
    audit.record(
        db,
        action="statement.submitted",
        entity_type="statement",
        entity_id=s.public_id,
        actor_type="device",
        company_id=s.company_id,
        after={"month": month, **s.declared},
    )
    db.commit()
    return driver_view(db, employee_id)


# ------------------------------------------------------------------ the office


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Statement.company_id.in_(list(company_ids)))


def _row(db: Session, public_id, *, lock: bool = False, **scope) -> Statement:
    q = _scoped(select(Statement).where(Statement.public_id == public_id), **scope)
    s = db.scalar(q.with_for_update() if lock else q)
    if s is None:
        raise AppError(404, "statement_not_found")
    return s


def list_statements(
    db: Session,
    *,
    month: date | None = None,
    status: str | None = None,
    platform_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    **scope,
) -> list[dict]:
    q = _scoped(select(Statement), **scope)
    if month:
        q = q.where(Statement.month == month_start(month))
    if status:
        q = q.where(Statement.status == status)
    if platform_id:
        q = q.where(Statement.platform_id == platform_id)
    q = q.order_by(Statement.status != "submitted", Statement.month.desc(), Statement.submitted_at.desc())
    return _out(db, list(db.scalars(q.limit(min(limit, 500)).offset(offset))))


def counts(db: Session, **scope) -> dict:
    """Statements waiting for review (the menu's count)."""
    q = _scoped(select(Statement.id).where(Statement.status == "submitted"), **scope)
    return {"submitted": len(db.scalars(q).all())}


def detail(db: Session, public_id, **scope) -> dict:
    return _out(db, [_row(db, public_id, **scope)], with_system=True)[0]


def screenshot(db: Session, public_id, sha256: str, **scope) -> files.FileInfo:
    s = _row(db, public_id, **scope)
    found = db.get(StatementFile, (s.id, sha256))
    if found is None:
        raise AppError(404, "file_not_found")
    return files.get(db, sha256)


def office_create(db: Session, data: dict, *, actor_user_id: int, **scope) -> dict:
    employee = people.ref_by_public_id(db, data["employee_id"], **scope)
    profile = people.payroll_profile(db, employee.id)
    month = month_start(data["month"])
    if month > month_start(today()):
        raise AppError(422, "statement_month_invalid")
    _check_open(db, profile["company_id"], month)
    figures = {k: data.get(k) for k in COUNTS} | {k: data[k] for k in AMOUNTS}
    s = Statement(
        employee_id=employee.id,
        company_id=profile["company_id"],
        platform_id=profile["platform_id"],
        month=month,
        status="approved",
        submitted_by_user=actor_user_id,
        reviewed_by=actor_user_id,
        reviewed_at=utcnow(),
        review_note=data.get("note"),
        **figures,
    )
    _insert(db, s)
    audit.record(
        db,
        action="statement.entered",
        entity_type="statement",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        after={"month": month, **figures},
    )
    db.commit()
    return detail(db, s.public_id, **scope)


def approve(db: Session, public_id, data: dict, *, actor_user_id: int, **scope) -> dict:
    """Approves the figures as entered by the reviewer (the driver's own unless corrected). An approved statement can
    be corrected again until the month's payroll is approved."""
    s = _row(db, public_id, lock=True, **scope)
    if s.status == "rejected":
        raise AppError(409, "statement_rejected")
    _check_open(db, s.company_id, s.month)
    before = {k: getattr(s, k) for k in COUNTS + AMOUNTS}
    for k in COUNTS + AMOUNTS:
        setattr(s, k, data.get(k))
    s.status, s.reviewed_by, s.reviewed_at, s.review_note = "approved", actor_user_id, utcnow(), data.get("note")
    s.version += 1
    audit.record(
        db,
        action="statement.approved",
        entity_type="statement",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        before=before,
        after={k: getattr(s, k) for k in COUNTS + AMOUNTS} | {"declared": s.declared},
    )
    db.commit()
    return detail(db, s.public_id, **scope)


def reject(db: Session, public_id, *, reason: str, actor_user_id: int, **scope) -> dict:
    s = _row(db, public_id, lock=True, **scope)
    if s.status != "submitted":
        raise AppError(409, "statement_not_submitted")
    _check_open(db, s.company_id, s.month)
    s.status, s.reviewed_by, s.reviewed_at, s.review_note = "rejected", actor_user_id, utcnow(), reason
    s.version += 1
    audit.record(
        db,
        action="statement.rejected",
        entity_type="statement",
        entity_id=s.public_id,
        actor_user_id=actor_user_id,
        company_id=s.company_id,
        after={"reason": reason},
    )
    db.commit()
    return detail(db, s.public_id, **scope)


# ------------------------------------------------------------------ for the payroll run


def for_month(db: Session, employee_ids: Iterable[int], month: date) -> dict[int, Statement]:
    """Each employee's live statement for the month (approved or still waiting for review)."""
    ids = list(employee_ids)
    if not ids:
        return {}
    q = select(Statement).where(
        Statement.employee_id.in_(ids), Statement.month == month_start(month), Statement.status != "rejected"
    )
    return {s.employee_id: s for s in db.scalars(q)}


def employees_with_statements(db: Session, company_id: int, month: date) -> list[int]:
    q = select(Statement.employee_id).where(
        Statement.company_id == company_id, Statement.month == month_start(month), Statement.status != "rejected"
    )
    return list(db.scalars(q))
