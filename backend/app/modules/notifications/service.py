"""In-app alerts. Each kind has a fixed severity and a permission: only users holding that permission see the alert,
and only for the companies in their scope. Texts are translations: namespace "alerts", key = kind; the params fill
the placeholders (a param may be a localized name, picked in the reader's language)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.i18n import service as i18n
from app.modules.notifications.models import Alert


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
    "odometer_lower": Kind("warning", "odometer.review", ("plate", "driver", "value", "previous")),
    "odometer_higher_than_next": Kind("warning", "odometer.review", ("plate", "driver", "value", "next")),
    "odometer_daily_limit": Kind("warning", "odometer.review", ("plate", "driver", "km", "limit")),
    "odometer_off_duty": Kind("warning", "odometer.review", ("plate", "km")),
    "odometer_photo_reused": Kind("critical", "odometer.review", ("plate", "driver")),
    "emergency_custody": Kind("warning", "custody.assign", ("plate", "driver", "reason")),
    "driver_left_with_vehicle": Kind("critical", "custody.assign", ("driver", "plate")),
    "document_expiring": Kind("warning", "documents.view", ("document", "owner", "date", "days")),
    "document_expired": Kind("critical", "documents.view", ("document", "owner", "date")),
    "onboarding_submitted": Kind("info", "employees.onboarding", ("driver",)),
    "cash_balance_high": Kind("warning", "cash.view", ("driver", "balance", "limit")),
    "daily_report_overdue": Kind("warning", "daily_reports.review", ("driver", "date", "hours")),
    "ledger_invariant": Kind("critical", "cash.view", ("problem",)),
    "driver_left_with_cash": Kind("critical", "cash.view", ("driver", "balance")),
    "maintenance_requested": Kind("info", "maintenance.approve", ("plate", "number")),
    "maintenance_emergency": Kind("warning", "maintenance.approve", ("plate", "number")),
    "maintenance_quote_pending": Kind(
        "warning", "maintenance.approve", ("plate", "number", "center", "amount", "limit")
    ),
    "maintenance_ready": Kind("info", "maintenance.view", ("plate", "number", "center")),
    "maintenance_invoice_pending": Kind("info", "invoices.approve", ("center", "number", "total")),
    "maintenance_invoice_duplicate": Kind("warning", "invoices.approve", ("center", "number", "total")),
    "maintenance_invoice_differs": Kind("warning", "invoices.approve", ("center", "number", "total", "quote")),
    "accident_reported": Kind("warning", "accidents.view", ("plate", "number", "driver")),
    "accident_injuries": Kind("critical", "accidents.view", ("plate", "number", "driver")),
    "accident_estimate_submitted": Kind("info", "accidents.update", ("plate", "number", "center", "amount")),
    "accident_awaiting_police_report": Kind("warning", "accidents.view", ("plate", "number", "days")),
    "fine_no_driver": Kind("warning", "fines.manage", ("plate", "number", "at")),
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
    """Adds the alert to the caller's transaction. With a dedupe_key, at most one alert per situation stays open;
    with once=True, a situation alerts only once even after someone acknowledged it; with refresh=True, the open
    alert takes the new params (a balance that keeps rising shows its current value)."""
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
            index_where=Alert.acknowledged_at.is_(None),
            set_={"params": stmt.excluded.params},
        )
    elif dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=Alert.acknowledged_at.is_(None))
    return db.execute(stmt.returning(Alert.id)).first() is not None


def resolve(db: Session, dedupe_key: str, *, prefix: bool = False) -> None:
    """The situation is over (e.g. the signal is back): the open alert closes itself."""
    match = Alert.dedupe_key.startswith(dedupe_key, autoescape=True) if prefix else Alert.dedupe_key == dedupe_key
    db.execute(update(Alert).where(match, Alert.acknowledged_at.is_(None)).values(acknowledged_at=func.now()))


def _visible(q, *, permissions: Iterable[str], all_companies: bool, company_ids: Iterable[int]):
    q = q.where(Alert.permission.in_(list(permissions)))
    if not all_companies:
        q = q.where(or_(Alert.company_id.is_(None), Alert.company_id.in_(list(company_ids))))
    return q


def _out(db: Session, a: Alert, lang: str, default: str) -> dict:
    params = {k: i18n.pick(v, lang, default) if isinstance(v, dict) else v for k, v in a.params.items()}
    return {
        "id": str(a.public_id),
        "kind": a.kind,
        "severity": a.severity,
        "message": i18n.t(db, lang, f"alerts.{a.kind}", **params),
        "params": params,
        "company_id": a.company_id,
        "entity_type": a.entity_type,
        "entity_id": a.entity_id,
        "created_at": a.created_at,
        "acknowledged_at": a.acknowledged_at,
    }


def list_alerts(
    db: Session,
    *,
    permissions: Iterable[str],
    all_companies: bool,
    company_ids: Iterable[int],
    lang: str,
    open_only: bool = True,
    kind: str | None = None,
    before: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    q = _visible(
        select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(min(limit, 200)),
        permissions=permissions,
        all_companies=all_companies,
        company_ids=company_ids,
    )
    if open_only:
        q = q.where(Alert.acknowledged_at.is_(None))
    if kind:
        q = q.where(Alert.kind == kind)
    if before:  # pagination: pass the created_at of the last alert received
        q = q.where(Alert.created_at < before)
    default = i18n.default_language(db).code
    return [_out(db, a, lang, default) for a in db.scalars(q)]


def acknowledge(
    db: Session, public_id, *, actor_user_id: int, permissions: Iterable[str], all_companies: bool, company_ids
) -> None:
    q = _visible(
        select(Alert).where(Alert.public_id == public_id),
        permissions=permissions,
        all_companies=all_companies,
        company_ids=company_ids,
    )
    alert = db.scalar(q.with_for_update())
    if alert is None:
        raise AppError(404, "alert_not_found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by = func.now(), actor_user_id
    db.commit()
