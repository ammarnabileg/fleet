"""In-app alerts. Each kind has a fixed severity and a permission: only users holding that permission see the alert,
and only for the companies in their scope. Texts are translations: namespace "alerts", key = kind; the params fill
the placeholders (a param may be a localized name, picked in the reader's language)."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Text, and_, case, cast, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.i18n import service as i18n
from app.modules.notifications.models import Alert, AlertEvent, DriverNotice


@dataclass(frozen=True)
class Kind:
    severity: str
    permission: str
    params: tuple[str, ...]  # the translations may use these placeholders, and every alert must provide them


KINDS: dict[str, Kind] = {
    "device_replaced": Kind("warning", "devices.manage", ("driver", "model")),
    "otp_delivery_failed": Kind("warning", "devices.manage", ("driver",)),
    "messaging_down": Kind("critical", "devices.manage", ("state",)),
    "mock_location": Kind("critical", "tracking.live", ("driver",)),
    "signal_lost": Kind("warning", "tracking.live", ("driver", "plate", "minutes")),
    "location_permission_off": Kind("warning", "tracking.live", ("driver", "plate")),
    "gps_off": Kind("warning", "tracking.live", ("driver", "plate")),
    "tracking_stopped": Kind("warning", "tracking.live", ("driver", "plate")),
    "contact_acknowledged": Kind("info", "tracking.live", ("driver",)),
    "odometer_lower": Kind("warning", "odometer.review", ("plate", "driver", "value", "previous")),
    "odometer_higher_than_next": Kind("warning", "odometer.review", ("plate", "driver", "value", "next")),
    "odometer_daily_limit": Kind("warning", "odometer.review", ("plate", "driver", "km", "limit")),
    "odometer_off_duty": Kind("warning", "odometer.review", ("plate", "km", "from_driver", "to_driver")),
    "odometer_photo_reused": Kind("critical", "odometer.review", ("plate", "driver")),
    "emergency_custody": Kind("warning", "custody.assign", ("plate", "driver", "reason")),
    "driver_left_with_vehicle": Kind("critical", "custody.assign", ("driver", "plate")),
    "document_expiring": Kind("warning", "documents.view", ("document", "owner", "date", "days")),
    "document_expired": Kind("critical", "documents.view", ("document", "owner", "date")),
    "onboarding_submitted": Kind("info", "employees.onboarding", ("driver",)),
    "cash_balance_high": Kind("warning", "cash.view", ("driver", "balance", "limit")),
    "daily_report_overdue": Kind("warning", "daily_reports.review", ("driver", "date", "hours")),
    "daily_report_escalated": Kind("warning", "daily_reports.escalations", ("driver", "date", "hours")),
    "daily_report_missing": Kind("warning", "daily_reports.review", ("driver", "date")),
    "daily_report_change_requested": Kind("info", "daily_reports.review", ("driver", "date")),
    "vehicle_change_requested": Kind("info", "custody.assign", ("driver", "plate", "requested", "reason")),
    "vehicle_claim_requested": Kind("info", "custody.assign", ("driver", "plate", "km")),
    "document_renewal_submitted": Kind("info", "documents.manage", ("driver", "document", "date")),
    "ledger_invariant": Kind("critical", "cash.view", ("problem",)),
    "treasury_deposit_due": Kind("warning", "treasury.view", ("branch", "balance", "limit")),
    "treasury_deposit_day": Kind("info", "treasury.view", ("branch", "balance")),
    "treasury_not_closed": Kind("warning", "treasury.view", ("branch", "day")),
    "driver_left_with_cash": Kind("critical", "cash.view", ("driver", "balance")),
    "fuel_claim": Kind("info", "cash.fuel_review", ("name", "amount")),
    "maintenance_requested": Kind("info", "maintenance.approve", ("plate", "number")),
    "maintenance_emergency": Kind("warning", "maintenance.approve", ("plate", "number")),
    "maintenance_quote_pending": Kind(
        "warning", "maintenance.approve", ("plate", "number", "center", "amount", "limit")
    ),
    "maintenance_ready": Kind("info", "maintenance.view", ("plate", "number", "center")),
    "maintenance_due": Kind("info", "maintenance.view", ("plate", "title", "due")),
    "maintenance_overdue": Kind("warning", "maintenance.view", ("plate", "title", "due")),
    "maintenance_late": Kind("warning", "maintenance.view", ("plate", "number", "center", "date")),
    "maintenance_long_stay": Kind("info", "maintenance.view", ("plate", "number", "center", "date")),
    "maintenance_escalated": Kind("critical", "maintenance.approve", ("plate", "number", "center", "date", "assignee")),
    "maintenance_invoice_pending": Kind("info", "invoices.approve", ("center", "number", "total")),
    "maintenance_invoice_duplicate": Kind("warning", "invoices.approve", ("center", "number", "total")),
    "maintenance_invoice_same_file": Kind("warning", "invoices.approve", ("center", "number", "total")),
    "maintenance_invoice_differs": Kind("warning", "invoices.approve", ("center", "number", "total", "quote")),
    "accident_reported": Kind("warning", "accidents.view", ("plate", "number", "driver")),
    "accident_injuries": Kind("critical", "accidents.view", ("plate", "number", "driver")),
    "accident_estimate_submitted": Kind("info", "accidents.update", ("plate", "number", "center", "amount")),
    "accident_awaiting_police_report": Kind("warning", "accidents.view", ("plate", "number", "days")),
    "fine_no_driver": Kind("warning", "fines.manage", ("plate", "number", "at")),
    "approval_escalated": Kind("warning", "approvals.view", ("ref", "hours")),
    "payroll_objection": Kind("info", "payroll.view", ("driver", "month")),
    "leave_requested": Kind("info", "leaves.approve", ("driver", "kind", "from", "to", "days")),
    "absence_consecutive": Kind("warning", "leaves.approve", ("driver", "days", "from", "to")),
    "absence_yearly": Kind("warning", "leaves.approve", ("driver", "days", "year")),
    "absence_followup": Kind("warning", "leaves.view", ("driver", "kind", "from", "to", "days")),
}


def raise_alert(
    db: Session,
    kind: str,
    *,
    company_id: int | None,
    entity_type: str | None = None,
    entity_id=None,
    params: dict | None = None,
    dedupe_key: str | None = None,
    once: bool = False,
    refresh: bool = False,
) -> bool:
    """Adds the alert to the caller's transaction. With a dedupe_key, at most one alert per situation stays open (not
    handled); with once=True, a situation alerts only once even after it was handled; with refresh=True, the open
    alert takes the new params (a balance that keeps rising shows its current value) and notes when (updated_at).
    The text says what happened when the alert was raised; how long ago, and what is true now, the reader's screen
    works out from the times."""
    spec = KINDS[kind]
    missing = set(spec.params) - set(params or {})
    if missing:
        raise ValueError(f"alert {kind!r} needs params {sorted(missing)}")
    if once and db.scalar(select(Alert.id).where(Alert.dedupe_key == dedupe_key).limit(1)):
        return False
    stmt = insert(Alert).values(
        kind=kind,
        severity=spec.severity,
        permission=spec.permission,
        company_id=company_id,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        params=params or {},
        dedupe_key=dedupe_key,
    )
    if dedupe_key and refresh:
        stmt = stmt.on_conflict_do_update(
            index_elements=["dedupe_key"],
            index_where=Alert.resolved_at.is_(None),
            set_={
                "params": stmt.excluded.params,
                # only a change of figures is an update: the same figures again leave the time alone
                "updated_at": case((Alert.params == stmt.excluded.params, Alert.updated_at), else_=func.now()),
            },
        )
    elif dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Alert.resolved_at.is_(None))
    return db.execute(stmt.returning(Alert.id)).first() is not None


def resolve(db: Session, dedupe_key: str, *, prefix: bool = False) -> None:
    """The situation is over (e.g. the signal is back): the open alert closes itself (handled automatically)."""
    match = Alert.dedupe_key.startswith(dedupe_key, autoescape=True) if prefix else Alert.dedupe_key == dedupe_key
    _close_auto(db, match)


def resolve_entity(db: Session, entity_type: str, entity_id, kinds: Iterable[str] | None = None) -> None:
    """The record an alert is about was dealt with (a flagged reading reviewed): its open alerts close themselves."""
    match = and_(Alert.entity_type == entity_type, Alert.entity_id == str(entity_id))
    if kinds is not None:
        match = and_(match, Alert.kind.in_(list(kinds)))
    _close_auto(db, match)


def _close_auto(db: Session, match) -> None:
    db.execute(
        update(Alert).where(match, Alert.resolved_at.is_(None)).values(resolved_at=func.now(), resolution="auto")
    )


def _visible(q, *, permissions: Iterable[str], all_companies: bool, company_ids: Iterable[int]):
    q = q.where(Alert.permission.in_(list(permissions)))
    if not all_companies:
        q = q.where(or_(Alert.company_id.is_(None), Alert.company_id.in_(list(company_ids))))
    return q


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEVERITY_RANK = case({"critical": 0, "warning": 1, "info": 2}, value=Alert.severity, else_=3)


def _shown(key: str, value):
    """A date param reads as the panel shows dates (day-month-year), the right way round inside Arabic text."""
    if isinstance(value, str) and ISO_DATE.match(value):
        y, m, d = value.split("-")
        return f"⁦{d}-{m}-{y}⁩"
    return value


def _status(a: Alert) -> str:
    return "resolved" if a.resolved_at is not None else "seen" if a.acknowledged_at is not None else "new"


def _outs(db: Session, alerts: list[Alert], lang: str) -> list[dict]:
    from app.modules.identity import service as identity  # identity raises alerts: imported when used

    default = i18n.default_language(db).code
    users = identity.user_refs(
        db, {u for a in alerts for u in (a.acknowledged_by, a.resolved_by, a.assigned_to, a.escalated_by)}
    )
    out = []
    for a in alerts:
        params = {k: i18n.pick(v, lang, default) if isinstance(v, dict) else v for k, v in a.params.items()}
        out.append(
            {
                "id": str(a.public_id),
                "kind": a.kind,
                "severity": a.severity,
                "message": i18n.t(db, lang, f"alerts.{a.kind}", **{k: _shown(k, v) for k, v in params.items()}),
                "params": params,
                "company_id": a.company_id,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
                "status": _status(a),
                "acknowledged_at": a.acknowledged_at,
                "acknowledged_by": users.get(a.acknowledged_by),
                "resolved_at": a.resolved_at,
                "resolved_by": users.get(a.resolved_by),
                "resolution": a.resolution,
                "resolution_note": a.resolution_note,
                "assigned_to": users.get(a.assigned_to),
                "assigned_at": a.assigned_at,
                "escalated_at": a.escalated_at,
                "escalated_by": users.get(a.escalated_by),
            }
        )
    return out


def _kinds_matching(db: Session, lang: str, q: str) -> list[str]:
    """The kinds whose text (in the reader's language) holds the words searched: «إشارة» finds the lost signals."""
    texts = i18n.effective_catalog(db, lang).get("alerts", {})
    return [k for k, text in texts.items() if q.casefold() in PLACEHOLDER.sub(" ", text).casefold()]


PLACEHOLDER = re.compile(r"\{\w+\}")
STATUSES = ("open", "new", "seen", "resolved", "all")


def list_alerts(
    db: Session,
    *,
    permissions: Iterable[str],
    all_companies: bool,
    company_ids: Iterable[int],
    lang: str,
    status: str = "open",
    severity: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    assigned: str | None = None,
    user_id: int | None = None,
    sort: str = "newest",
    before: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    """status: open (not handled: new or seen), new (nobody has seen it), seen, resolved, all. sort: newest first, or
    the most severe first (then the newest). assigned: me, none, or a user's public id."""
    order = (Alert.created_at.desc(), Alert.id.desc())
    if sort == "severity":
        order = (SEVERITY_RANK, *order)
    query = _visible(
        select(Alert).order_by(*order).offset(offset).limit(min(limit, 200)),
        permissions=permissions,
        all_companies=all_companies,
        company_ids=company_ids,
    )
    if status == "open":
        query = query.where(Alert.resolved_at.is_(None))
    elif status == "new":
        query = query.where(Alert.resolved_at.is_(None), Alert.acknowledged_at.is_(None))
    elif status == "seen":
        query = query.where(Alert.resolved_at.is_(None), Alert.acknowledged_at.is_not(None))
    elif status == "resolved":
        query = query.where(Alert.resolved_at.is_not(None))
    if severity:
        query = query.where(Alert.severity == severity)
    if kind:
        query = query.where(Alert.kind == kind)
    if q and q.strip():
        words = q.strip()
        like = words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                cast(Alert.params, Text).ilike(f"%{like}%", escape="\\"),  # names, plates, numbers
                Alert.kind.in_(_kinds_matching(db, lang, words)),
            )
        )
    if since:
        query = query.where(Alert.created_at >= since)
    if until:
        query = query.where(Alert.created_at < until)
    if assigned == "me":
        query = query.where(Alert.assigned_to == user_id)
    elif assigned == "none":
        query = query.where(Alert.assigned_to.is_(None))
    elif assigned:
        from app.modules.identity import service as identity

        query = query.where(Alert.assigned_to == identity.user_id(db, assigned))
    if before:  # pagination by time: pass the created_at of the last alert received
        query = query.where(Alert.created_at < before)
    return _outs(db, list(db.scalars(query)), lang)


def summary(
    db: Session,
    *,
    permissions: Iterable[str],
    all_companies: bool,
    company_ids: Iterable[int],
    lang: str,
    user_id: int | None = None,
) -> dict:
    """What the panel polls every few seconds: the open alerts by severity (not capped), how many nobody has seen yet
    (the bell), how many are assigned to this user, and the newest one, so it can say what arrived. Small queries on
    the open-alerts index."""
    scope = {"permissions": list(permissions), "all_companies": all_companies, "company_ids": list(company_ids)}
    open_ = Alert.resolved_at.is_(None)
    counts = dict(
        db.execute(_visible(select(Alert.severity, func.count()).where(open_).group_by(Alert.severity), **scope)).all()
    )
    new, mine = db.execute(
        _visible(
            select(
                func.count().filter(Alert.acknowledged_at.is_(None)),
                func.count().filter(Alert.assigned_to == user_id) if user_id is not None else literal(0),
            ).where(open_),
            **scope,
        )
    ).one()
    latest = db.scalar(_visible(select(Alert).where(open_).order_by(Alert.id.desc()).limit(1), **scope))
    return {
        "open": sum(counts.values()),
        **{s: counts.get(s, 0) for s in ("critical", "warning", "info")},
        "new": new,
        "mine": mine,
        "latest": _outs(db, [latest], lang)[0] if latest else None,
    }


def _get(db: Session, public_id, *, permissions, all_companies: bool, company_ids, lock: bool = False) -> Alert:
    q = _visible(
        select(Alert).where(Alert.public_id == public_id),
        permissions=permissions,
        all_companies=all_companies,
        company_ids=company_ids,
    )
    alert = db.scalar(q.with_for_update() if lock else q)
    if alert is None:
        raise AppError(404, "alert_not_found")
    return alert


def _log(db: Session, alert: Alert, action: str, actor_user_id: int, *, target: int | None = None, note=None):
    from app.modules.audit import service as audit

    db.add(AlertEvent(alert_id=alert.id, action=action, actor_user_id=actor_user_id, target_user_id=target, note=note))
    audit.record(
        db,
        action=f"alert.{action}",
        entity_type="alert",
        entity_id=alert.public_id,
        actor_user_id=actor_user_id,
        company_id=alert.company_id,
        after={"kind": alert.kind, "note": note} | ({"user_id": target} if target is not None else {}),
    )


def acknowledge(
    db: Session, public_id, *, actor_user_id: int, permissions: Iterable[str], all_companies: bool, company_ids
) -> None:
    """Seen: someone looked at it. It stays open until its cause is gone or someone records how it was handled."""
    alert = _get(
        db, public_id, permissions=permissions, all_companies=all_companies, company_ids=company_ids, lock=True
    )
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by = func.now(), actor_user_id
        _log(db, alert, "acknowledged", actor_user_id)
    db.commit()


def resolve_by_user(
    db: Session,
    public_id,
    *,
    note: str,
    actor_user_id: int,
    permissions: Iterable[str],
    all_companies: bool,
    company_ids,
) -> None:
    """Handled: what was done, in a word. Seen too, when nobody had acknowledged it yet."""
    alert = _get(
        db, public_id, permissions=permissions, all_companies=all_companies, company_ids=company_ids, lock=True
    )
    if alert.resolved_at is not None:
        raise AppError(409, "alert_resolved")
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by = func.now(), actor_user_id
    alert.resolved_at, alert.resolved_by, alert.resolution, alert.resolution_note = (
        func.now(),
        actor_user_id,
        "manual",
        note,
    )
    _log(db, alert, "resolved", actor_user_id, note=note)
    db.commit()


def handlers(db: Session, public_id, *, permissions: Iterable[str], all_companies: bool, company_ids) -> list[dict]:
    """Who may handle the alert: the active users who would see it themselves (its permission, its company)."""
    from app.modules.identity import service as identity

    alert = _get(db, public_id, permissions=permissions, all_companies=all_companies, company_ids=company_ids)
    return list(identity.users_who_can(db, alert.permission, alert.company_id).values())


def assign(
    db: Session,
    public_id,
    *,
    user_public_id,
    note: str | None,
    escalate: bool,
    actor_user_id: int,
    permissions: Iterable[str],
    all_companies: bool,
    company_ids,
) -> None:
    """Gives the open alert to someone who can see it (or to nobody). Escalating gives it to another, with the reason,
    and marks it escalated; it is also seen, by the one who escalated it."""
    from app.modules.identity import service as identity

    alert = _get(
        db, public_id, permissions=permissions, all_companies=all_companies, company_ids=company_ids, lock=True
    )
    if alert.resolved_at is not None:
        raise AppError(409, "alert_resolved")
    target = None
    if user_public_id is not None:
        target = identity.user_id(db, user_public_id)
        if target not in identity.users_who_can(db, alert.permission, alert.company_id):
            raise AppError(422, "alert_handler_cannot_see")
    elif escalate:
        raise AppError(422, "alert_handler_required")
    if escalate:
        if target == actor_user_id:
            raise AppError(422, "alert_escalate_to_self")
        alert.escalated_at, alert.escalated_by = func.now(), actor_user_id
        if alert.acknowledged_at is None:
            alert.acknowledged_at, alert.acknowledged_by = func.now(), actor_user_id
    elif target == alert.assigned_to:
        db.commit()
        return
    alert.assigned_to, alert.assigned_at = target, (func.now() if target is not None else None)
    action = "escalated" if escalate else "assigned" if target is not None else "unassigned"
    _log(db, alert, action, actor_user_id, target=target, note=note)
    db.commit()


def detail(db: Session, public_id, *, lang: str, permissions: Iterable[str], all_companies: bool, company_ids) -> dict:
    """The alert and what people did with it, oldest first."""
    from app.modules.identity import service as identity

    alert = _get(db, public_id, permissions=permissions, all_companies=all_companies, company_ids=company_ids)
    events = list(db.scalars(select(AlertEvent).where(AlertEvent.alert_id == alert.id).order_by(AlertEvent.id)))
    users = identity.user_refs(db, {u for e in events for u in (e.actor_user_id, e.target_user_id)})
    return _outs(db, [alert], lang)[0] | {
        "events": [
            {
                "action": e.action,
                "at": e.at,
                "by": users.get(e.actor_user_id),
                "user": users.get(e.target_user_id),
                "note": e.note,
            }
            for e in events
        ]
    }


# ------------------------------------------------------------------ what the driver is told (FR-NTF-01/02)

DRIVER_KINDS: dict[str, tuple[str, ...]] = {  # kind: the params its text uses
    "receipt_issued": ("number", "amount"),
    "receipt_reversed": ("number", "amount", "reason"),
    "report_corrected": ("date", "reported", "approved", "reason"),
    "report_rejected": ("date", "reason"),
    "maintenance_approved": ("number",),
    "maintenance_rejected": ("number", "reason"),
    "maintenance_ready": ("number", "center"),
    "accident_no_liability": ("number",),
    "accident_charged": ("number", "amount", "installments"),
    "fine_charged": ("number", "amount", "installments"),
    "deduction_added": ("reason", "amount", "installments"),
    "payslip_ready": ("month",),
    "report_missing": ("date",),
    "report_returned": ("date", "reason"),
    "report_change_approved": ("date",),
    "report_change_rejected": ("date", "reason"),
    "vehicle_change_approved": ("plate", "requested"),
    "vehicle_change_done": ("plate",),
    "vehicle_change_rejected": ("plate", "reason"),
    "vehicle_change_closed": ("plate", "reason"),
    "vehicle_handed_over": ("plate",),
    "vehicle_returned": ("plate",),
    "vehicle_taken": ("plate",),
    "vehicle_swapped": ("from", "to"),
    "vehicle_claim_approved": ("plate",),
    "vehicle_claim_rejected": ("plate", "reason"),
    "vehicle_claim_superseded": ("plate",),
    "document_renewal_approved": ("document",),
    "document_renewal_rejected": ("document", "reason"),
    "document_expiring": ("document", "date", "days"),
    "document_expired": ("document", "date"),
    "scheme_request_approved": ("scheme", "month"),
    "scheme_request_rejected": ("scheme", "reason"),
    "fuel_approved": ("amount",),
    "fuel_rejected": ("reason",),
    "objection_updated": ("month", "status", "response"),
    "leave_approved": ("kind", "from", "to"),
    "leave_rejected": ("kind", "from", "to", "reason"),
}


def notify_driver(
    db: Session,
    employee_id: int,
    kind: str,
    *,
    params: dict | None = None,
    entity_type: str | None = None,
    entity_id=None,
    dedupe_key: str | None = None,
) -> bool:
    """Adds a notice for the driver to the caller's transaction (once per dedupe_key). A param may be a localized name,
    picked in the driver's language when read."""
    missing = set(DRIVER_KINDS[kind]) - set(params or {})
    if missing:
        raise ValueError(f"driver notice {kind!r} needs params {sorted(missing)}")
    stmt = insert(DriverNotice).values(
        employee_id=employee_id,
        kind=kind,
        params={k: (str(v) if v is not None and not isinstance(v, dict) else v) for k, v in (params or {}).items()},
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        dedupe_key=dedupe_key,
    )
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["employee_id", "dedupe_key"], index_where=DriverNotice.dedupe_key.is_not(None)
        )
    return db.execute(stmt.returning(DriverNotice.id)).first() is not None


def notice_text(db: Session, n: DriverNotice, lang: str, default: str) -> str:
    params = {k: i18n.pick(v, lang, default) if isinstance(v, dict) else v for k, v in n.params.items()}
    return i18n.t(db, lang, f"driver_notice.{n.kind}", **params)


def driver_notices(db: Session, employee_id: int, *, lang: str, limit: int = 50) -> dict:
    """The driver's latest notices, newest first, and how many are unread."""
    rows = db.scalars(
        select(DriverNotice)
        .where(DriverNotice.employee_id == employee_id)
        .order_by(DriverNotice.id.desc())
        .limit(min(limit, 200))
    )
    default = i18n.default_language(db).code
    unread = db.scalar(
        select(func.count()).where(DriverNotice.employee_id == employee_id, DriverNotice.read_at.is_(None))
    )
    return {
        "unread": unread,
        "items": [
            {
                "id": str(n.public_id),
                "kind": n.kind,
                "message": notice_text(db, n, lang, default),
                "entity_type": n.entity_type,
                "entity_id": n.entity_id,
                "created_at": n.created_at,
                "read": n.read_at is not None,
            }
            for n in rows
        ],
    }


def mark_read(db: Session, employee_id: int, ids: Iterable | None) -> int:
    """The given notices, or all of them, read."""
    q = update(DriverNotice).where(DriverNotice.employee_id == employee_id, DriverNotice.read_at.is_(None))
    if ids is not None:
        q = q.where(DriverNotice.public_id.in_(list(ids)))
    n = db.execute(q.values(read_at=func.now())).rowcount
    db.commit()
    return n


PUSH_WINDOW_HOURS = 48  # older notices stay in the app's list only: a backlog is not pushed once push is switched on


def push_summary(db: Session) -> dict:
    """For the integrations page: notices waiting to be pushed (within the window: tried again every pass), and of
    the notices pushed in the last 7 days how many the driver has opened in the app (the only proof it reached him)."""
    from datetime import timedelta

    from app.core.clock import utcnow

    now = utcnow()
    waiting = db.scalar(
        select(func.count()).where(
            DriverNotice.pushed_at.is_(None), DriverNotice.created_at > now - timedelta(hours=PUSH_WINDOW_HOURS)
        )
    )
    pushed = db.execute(
        select(func.count(), func.count(DriverNotice.read_at)).where(DriverNotice.pushed_at >= now - timedelta(days=7))
    ).one()
    return {"waiting": waiting or 0, "pushed_7d": pushed[0], "read_7d": pushed[1], "window_hours": PUSH_WINDOW_HOURS}


def notices_read(db: Session, public_ids) -> dict[str, bool]:
    ids = [i for i in public_ids if i]
    if not ids:
        return {}
    q = select(DriverNotice.public_id, DriverNotice.read_at).where(DriverNotice.public_id.in_(ids))
    return {str(p): r is not None for p, r in db.execute(q)}


def push_pending(db: Session, *, limit: int = 200) -> int:
    """Pushes the notices not pushed yet to the drivers' phones (beat, every half minute). Nothing until push is set up
    in the control panel; a phone that has not registered yet keeps its notices waiting (within the window); a token
    Firebase no longer knows is forgotten. A failure of Firebase itself stops the pass: the next one tries again."""
    import logging
    from datetime import timedelta

    from app.core import push
    from app.core.clock import utcnow
    from app.modules.identity import service as identity
    from app.modules.integrations import service as integrations

    sender = integrations.pusher(db)
    if sender is None:
        return 0
    rows = list(
        db.scalars(
            select(DriverNotice)
            .where(
                DriverNotice.pushed_at.is_(None),
                DriverNotice.created_at > utcnow() - timedelta(hours=PUSH_WINDOW_HOURS),
            )
            .order_by(DriverNotice.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    targets = identity.push_targets(db, {n.employee_id for n in rows})
    default = i18n.default_language(db).code
    sent = 0
    for n in rows:
        target = targets.get(n.employee_id)
        if target is None:
            continue  # not registered (yet): it waits
        device_id, token, lang = target
        lang = i18n.usable(db, lang) if lang else default
        try:
            sender.send(
                token,
                title=i18n.t(db, lang, "messages.notice_title"),
                body=notice_text(db, n, lang, default),
                data={"id": str(n.public_id), "kind": n.kind, "entity_type": n.entity_type or "",
                      "entity_id": n.entity_id or ""},
            )  # fmt: skip
        except push.InvalidToken:
            identity.forget_push_token(db, device_id)
            gone = "the phone's token is no longer valid (app removed or reinstalled)"
            integrations.log_push(db, status="failed", notice_id=str(n.public_id), device_id=device_id, error=gone)
            targets.pop(n.employee_id, None)
            continue
        except push.PushError as exc:
            logging.getLogger("fleet.push").warning("push stopped: %s", exc)
            integrations.log_push(db, status="failed", notice_id=str(n.public_id), device_id=device_id, error=str(exc))
            break
        n.pushed_at = func.now()
        integrations.log_push(db, status="accepted", notice_id=str(n.public_id), device_id=device_id)
        sent += 1
    db.commit()
    return sent
