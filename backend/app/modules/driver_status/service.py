"""The driver's live status, computed on the server as separate states (never one status field):

- shift: working / off_duty, from the start and end of his work day (the same rule as the live map);
- vehicle: available / maintenance / breakdown / none. No request marks a car "not drivable", so a car with an open
  accident (its status "accident") is the breakdown; a car at a center (or marked in maintenance) is maintenance;
- tracking: active / stale / off, from the last point that really reached the server for his custody, against the
  signal loss setting; off when there is nothing to track (no custody, the car at a center);
- alerts, several at once: custody_settlement (his cash over the alert limit of the cash settings), contact_request
  (open requests of the office), document_missing (a document missing or expired), location_problem (the phone's
  last health report: permission, GPS, the tracking service; or the points stopped coming).

Each alert takes its priority, expiry and visibility from the published templates (see templates.py).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import live
from app.core.clock import KUWAIT, utcnow
from app.core.clock import today as clock_today
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.cash import service as cash
from app.modules.daily_ops import service as daily_ops
from app.modules.documents import service as documents
from app.modules.driver_status import templates as tpl
from app.modules.driver_status.models import ConfigVersion, ContactRequest
from app.modules.fleet import service as fleet
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.maintenance import service as maintenance
from app.modules.notifications import service as notifications
from app.modules.org import service as org
from app.modules.people import service as people
from app.modules.tracking import service as tracking

# ------------------------------------------------------------------ templates and versions


def current(db: Session) -> tuple[int, dict]:
    """The config in force: (version, {code: template}). Version 0 is the built-in set, before any publish. A code
    added to the app after the last publish takes its built-in template."""
    row = db.scalar(select(ConfigVersion).order_by(ConfigVersion.version.desc()).limit(1))
    if row is None:
        return 0, {k: dict(v) for k, v in tpl.DEFAULTS.items()}
    return row.version, {k: dict(row.templates.get(k) or v) for k, v in tpl.DEFAULTS.items()}


def _localized(db: Session, code: str, template: dict, langs) -> dict:
    """The template with its built-in texts in the drivers' other languages (French, Hindi, ...), from the dashboard's
    translations, while the office has not rewritten them (Arabic and English are the template's own)."""
    out = dict(template)
    for field in ("name", "title", "subtitle"):
        value = dict(out.get(field) or {})
        for lang in langs:
            if lang in ("ar", "en") or value.get(lang):
                continue
            text_ = i18n.status_text(db, lang, f"{code}.{field}", value.get("en", ""))
            if text_:
                value[lang] = text_
        out[field] = value
    return out


def _config_out(version: int, templates: dict, company_id: int | None = None, db: Session | None = None) -> dict:
    # a driver gets what applies to him: a template off for him is not there, and his app uses its built-in card
    langs = [lang.code for lang in i18n.list_languages(db)] if db is not None else []
    items = [
        {"code": c} | (_localized(db, c, t, langs) if db is not None else t)
        for c, t in templates.items()
        if company_id is None or tpl.applies(t, company_id)
    ]
    return {"version": version, "min_app_template_version": tpl.ENGINE_VERSION, "templates": items}


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('driver_status.config', 0))"))


def _publish(
    db: Session, templates: dict, *, actor_user_id: int, changed: str | None, restored_from: int | None
) -> int:
    version, _ = current(db)
    db.add(
        ConfigVersion(
            version=version + 1,
            templates=templates,
            restored_from=restored_from,
            changed=changed,
            created_by=actor_user_id,
        )
    )
    audit.record(
        db,
        action="driver_status.rollback" if restored_from is not None else "driver_status.published",
        entity_type="status_template",
        entity_id=changed or f"v{restored_from}",
        actor_user_id=actor_user_id,
        after={"version": version + 1, "restored_from": restored_from, "template": templates.get(changed or "")},
    )
    db.commit()
    return version + 1


def _scope_companies(db: Session, all_companies: bool, company_ids: Iterable[int]) -> set[int]:
    return tracking.company_scope(db, all_companies, company_ids)


def publish(db: Session, code: str, data: dict, *, expected_version: int, actor_user_id: int, **scope) -> dict:
    """Validates one template and publishes the whole set with it as the next version."""
    try:
        clean = tpl.validate(code, data, _scope_companies(db, **scope))
    except tpl.TemplateError as e:
        raise AppError(422, e.code, **e.params) from None
    _lock(db)
    version, templates = current(db)
    if version != expected_version:
        raise AppError(409, "status_config_changed")
    templates[code] = clean
    _publish(db, templates, actor_user_id=actor_user_id, changed=code, restored_from=None)
    _broadcast(db, _scope_companies(db, True, ()), {"config": True})
    return manage(db)


def rollback(db: Session, *, expected_version: int, actor_user_id: int) -> dict:
    """«Back to the previous setting»: the set in force before the current one is published again as a new version.
    Again after that goes one further back (the version the current one came from is skipped)."""
    _lock(db)
    version, _ = current(db)
    if version != expected_version:
        raise AppError(409, "status_config_changed")
    if version == 0:
        raise AppError(409, "status_config_no_previous")
    row = db.get(ConfigVersion, version)
    base = row.restored_from if row.restored_from is not None else version
    if base <= 0:
        raise AppError(409, "status_config_no_previous")
    target = base - 1
    templates = (
        {k: dict(v) for k, v in tpl.DEFAULTS.items()} if target == 0 else dict(db.get(ConfigVersion, target).templates)
    )
    _publish(db, templates, actor_user_id=actor_user_id, changed=None, restored_from=target)
    _broadcast(db, _scope_companies(db, True, ()), {"config": True})
    return manage(db)


def manage(db: Session) -> dict:
    """The panel's templates page: what is in force, the lists the app supports, and the publish history."""
    version, templates = current(db)
    rows = list(db.scalars(select(ConfigVersion).order_by(ConfigVersion.version.desc()).limit(30)))
    users = identity.user_refs(db, {r.created_by for r in rows})
    return {
        "config_version": version,
        "templates": [{"code": code} | t for code, t in templates.items()],
        "options": {
            "kinds": list(tpl.KINDS),
            "icons": list(tpl.ICONS),
            "actions": list(tpl.ACTIONS),
            "variables": list(tpl.VARIABLES),
            "visibility": list(tpl.VISIBILITY),
            "audiences": list(tpl.AUDIENCES),
            "palette": list(tpl.PALETTE),
            "max_actions": tpl.MAX_ACTIONS,
            "samples": tpl.SAMPLES,
        },
        "can_rollback": version > 0 and ((rows[0].restored_from if rows[0].restored_from is not None else version) > 0),
        "history": [
            {
                "version": r.version,
                "changed": r.changed,
                "restored_from": r.restored_from,
                "created_at": r.created_at,
                "created_by": users.get(r.created_by),
            }
            for r in rows
        ],
    }


def preview(db: Session, code: str, data: dict, lang: str, values: dict | None = None) -> dict:
    """The card as the app draws it, with sample values (or the given ones): validated the same as a publish."""
    try:
        clean = tpl.validate(code, data, None)
    except tpl.TemplateError as e:
        raise AppError(422, e.code, **e.params) from None
    return tpl.render(clean, tpl.SAMPLES | (values or {}), lang) | {"priority": clean["priority"]}


# ------------------------------------------------------------------ the states


def _kw(t: datetime | None) -> str | None:
    return t.astimezone(KUWAIT).strftime("%H:%M") if t else None


def _duration(since: datetime, now: datetime) -> str:
    minutes = max(0, int((now - since).total_seconds() // 60))
    return f"{minutes // 60}:{minutes % 60:02d}"


def _shift(db: Session, employee_id: int, custody) -> dict:
    """day_ended: off duty after ending today's day (not before starting it); orders_today: what his reports of today
    counted, once one did."""
    if custody is None:
        return {"state": "off_duty", "started_at": None, "sessions_today": 0, "day_ended": False, "orders_today": None}
    working = custody.id in fleet.on_duty_now(db, [custody.id])
    today = fleet.driver_today(db, employee_id)
    return {
        "state": "working" if working else "off_duty",
        "started_at": today.get("day_started_at") if working else None,
        "sessions_today": today.get("sessions", 0),
        "day_ended": not working and bool(today.get("end_day_done")),
        "orders_today": daily_ops.orders_on(db, employee_id, clock_today()),
    }


def _vehicle(db: Session, employee_id: int, custody, lang: str) -> dict:
    if custody is None:
        return {"state": "none", "plate_number": None, "stage": None, "center": None}
    v = fleet.vehicles(db, [custody.vehicle_id])[custody.vehicle_id]
    at_center = bool(fleet.in_maintenance(db, [custody.id])) or v.status == "maintenance"
    state = "breakdown" if v.status == "accident" else "maintenance" if at_center else "available"
    stage = center = None
    if state == "maintenance":
        latest = next(iter(maintenance.for_driver(db, employee_id, limit=1)), None)
        if latest is not None:
            stage = i18n.t(db, lang, f"maintenance_status.{latest['status']}")
            center = (latest.get("center") or {}).get("name")
    return {"state": state, "plate_number": v.plate_number, "stage": stage, "center": center}


def _tracking(db: Session, custody) -> dict:
    required = custody is not None and not fleet.in_maintenance(db, [custody.id])
    last = tracking.last_fix_at(db, custody.vehicle_id, custody.id) if custody is not None else None
    if not required:
        state = "off"
    else:
        reference = last or custody.started_at
        state = "active" if last is not None and utcnow() - reference <= tracking.signal_loss_after(db) else "stale"
    return {"state": state, "required": required, "last_update": last}


HEALTH_PROBLEMS = (
    # "while in use" still tracks through the foreground service: only a real refusal is a problem by itself
    ("permission_denied", lambda s: s.get("location_permission") == "denied"),
    ("gps_off", lambda s: s.get("gps_enabled") is False),
    ("service_stopped", lambda s: s.get("tracking_service_running") is False),
)


def _health(db: Session, employee_id: int, device_id: int | None) -> dict | None:
    ids = [device_id] if device_id is not None else sorted(identity.device_ids_of(db, employee_id), reverse=True)
    for i in ids:
        s = identity.device_status(db, i)
        if s is not None:
            return s
    return None


def _open_requests(db: Session, employee_ids: Iterable[int]) -> list[ContactRequest]:
    ids = list(employee_ids)
    if not ids:
        return []
    return list(
        db.scalars(
            select(ContactRequest)
            .where(ContactRequest.employee_id.in_(ids), ContactRequest.status == "open")
            .order_by(ContactRequest.id.desc())
        )
    )


def _visible(t: dict, shift: dict, vehicle: dict) -> bool:
    return {
        "always": True,
        "working": shift["state"] == "working",
        "off_duty": shift["state"] == "off_duty",
        "has_vehicle": vehicle["state"] != "none",
    }[t["visibility"]]


def compute(
    db: Session,
    employee: people.EmployeeRef,
    *,
    lang: str,
    device_id: int | None = None,
    now: datetime | None = None,
) -> dict:
    """The driver's states and alerts now, the alerts most important first."""
    now = now or utcnow()
    default = i18n.default_language(db).code
    version, templates = current(db)
    custody = fleet.open_custody_for_driver(db, employee.id)
    shift = _shift(db, employee.id, custody)
    vehicle = _vehicle(db, employee.id, custody, lang)
    track = _tracking(db, custody)
    raw: list[tuple[str, str, dict, dict, datetime | None]] = []  # code, id, values, data, created_at

    limit = org.get_section(db, "cash").driver_balance_alert
    balance = cash.driver_balance(db, employee.id).total
    if limit > 0 and balance > limit:
        raw.append(("custody_settlement", "custody_settlement", {"amount": f"{balance:.3f}", "due": None}, {}, None))

    users: dict[int, dict | None] = {}
    for r in _open_requests(db, [employee.id]):
        if r.created_by not in users:
            users[r.created_by] = identity.user_contact(db, r.created_by)
        who = users[r.created_by] or {}
        raw.append(
            (
                "contact_request",
                f"contact:{r.public_id}",
                {"supervisor": who.get("name")},
                {
                    "request_id": str(r.public_id),
                    "message": r.message,
                    "reason": r.reason,
                    "phone": who.get("phone"),
                },
                r.created_at,
            )
        )

    for d in documents.driver_documents(db, employee.id):
        if d["state"] in ("missing", "expired"):
            name = i18n.pick(d["type_name"], lang, default) if isinstance(d["type_name"], dict) else d["type_name"]
            raw.append(
                (
                    "document_missing",
                    f"document:{d['type_code']}",
                    {"document": name, "due": d["expiry_date"].isoformat() if d["expiry_date"] else None},
                    {"state": d["state"], "type_code": d["type_code"]},
                    None,
                )
            )

    if track["required"]:
        health = _health(db, employee.id, device_id) or {}
        reasons = [name for name, failing in HEALTH_PROBLEMS if failing(health)]
        if track["state"] == "stale":
            reasons.append("stale")
            if health.get("location_permission") == "while_in_use":
                reasons.append("permission_limited")  # the points stopped: "always" is the likely fix
        if reasons:
            raw.append(
                (
                    "location_problem",
                    "location_problem",
                    {"last_update": _kw(track["last_update"])},
                    {"reasons": reasons, "last_update": track["last_update"]},
                    None,
                )
            )

    alerts = []
    for code, alert_id, values, data, created_at in raw:
        t = templates[code]
        if not tpl.applies(t, employee.company_id) or not _visible(t, shift, vehicle):
            continue
        expires_at = created_at + timedelta(minutes=t["ttl_minutes"]) if created_at and t["ttl_minutes"] else None
        if expires_at is not None and expires_at <= now:
            continue  # expired: the card goes back to the base state (the office still sees the request open)
        shown = tpl.render(_localized(db, code, t, [lang]), values, lang)
        alerts.append(
            {
                "id": alert_id,
                "code": code,
                "kind": t["kind"],
                "priority": t["priority"],
                "created_at": created_at,
                "expires_at": expires_at,
                "values": {k: v for k, v in values.items() if v is not None},
                "data": data,
                "title": shown["title"],
                "subtitle": shown["subtitle"],
                "actions": shown["actions"],
            }
        )
    alerts.sort(key=lambda a: (-a["priority"], a["id"]))
    if shift["started_at"] is not None:
        shift["duration"] = _duration(shift["started_at"], now)
    return {
        "config_version": version,
        "min_app_template_version": tpl.ENGINE_VERSION,
        "generated_at": now,
        "shift": shift,
        "vehicle": vehicle,
        "tracking": track,
        "alerts": alerts,
    }


def for_driver(db: Session, device: identity.DevicePrincipal, *, lang: str, config_version: int | None) -> dict:
    """GET /driver/live-status: the states, and the templates when the app's cached version is not the current one
    (an older app that sends none gets them too, and simply ignores what it does not read)."""
    employee = people.ref(db, device.employee_id)
    out = compute(db, employee, lang=lang, device_id=device.device_id)
    if config_version != out["config_version"]:
        version, templates = current(db)
        out["config"] = _config_out(version, templates, employee.company_id, db)
    else:
        out["config"] = None
    return out


def drivers(db: Session, *, lang: str, all_companies: bool, company_ids: Iterable[int]) -> list[dict]:
    """The panel's «drivers' status»: each driver holding a car, or with an open contact request, in the user's
    companies."""
    scope = _scope_companies(db, all_companies, company_ids)
    ids = {c.driver_id for c in fleet.open_custodies(db) if c.company_id in scope}
    ids |= set(
        db.scalars(
            select(ContactRequest.employee_id).where(
                ContactRequest.status == "open", ContactRequest.company_id.in_(scope)
            )
        )
    )
    out = []
    names = people.names(db, ids)
    for employee_id in ids:
        e = people.ref(db, employee_id)
        if e is None or e.company_id not in scope:
            continue
        state = compute(db, e, lang=lang)
        out.append({"driver": names[employee_id], "company_id": e.company_id} | state)
    out.sort(key=lambda r: (-(r["alerts"][0]["priority"] if r["alerts"] else -1), str(r["driver"]["name"])))
    return out


# ------------------------------------------------------------------ contact requests


def _broadcast(db: Session, company_ids: Iterable[int], data: dict) -> None:
    for c in company_ids:
        live.broker().publish(c, {"event": "driver_status", "data": data})


def _request_out(db: Session, rows: list[ContactRequest]) -> list[dict]:
    names = people.names(db, {r.employee_id for r in rows})
    users = identity.user_refs(db, {u for r in rows for u in (r.created_by, r.closed_by)})
    return [
        {
            "id": str(r.public_id),
            "driver": names.get(r.employee_id),
            "company_id": r.company_id,
            "message": r.message,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at,
            "created_by": users.get(r.created_by),
            "acknowledged_at": r.acknowledged_at,
            "closed_at": r.closed_at,
            "closed_by": users.get(r.closed_by),
        }
        for r in rows
    ]


def create_request(
    db: Session, *, driver_public_id, message: str, reason: str | None, actor_user_id: int, **scope
) -> dict:
    driver = people.ref_by_public_id(db, driver_public_id, **scope)
    if not driver.is_driver:
        raise AppError(422, "contact_not_a_driver")
    r = ContactRequest(
        employee_id=driver.id,
        company_id=driver.company_id,
        created_by=actor_user_id,
        message=message,
        reason=reason,
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        action="contact_request.created",
        entity_type="contact_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=driver.company_id,
        after={"driver": driver.name, "message": message, "reason": reason},
    )
    db.commit()
    _broadcast(db, [driver.company_id], {"contact_request": str(r.public_id), "status": "open"})
    return _request_out(db, [r])[0]


def _scoped_request(db: Session, public_id, *, all_companies: bool, company_ids, lock: bool = False) -> ContactRequest:
    q = select(ContactRequest).where(ContactRequest.public_id == public_id)
    if not all_companies:
        q = q.where(ContactRequest.company_id.in_(list(company_ids)))
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise AppError(404, "contact_request_not_found")
    return r


def list_requests(db: Session, *, status: str = "open", all_companies: bool, company_ids, limit: int = 100) -> list:
    q = select(ContactRequest).order_by(ContactRequest.id.desc()).limit(min(limit, 200))
    if not all_companies:
        q = q.where(ContactRequest.company_id.in_(list(company_ids)))
    if status == "active":
        q = q.where(ContactRequest.status.in_(("open", "acknowledged")))
    elif status != "all":
        q = q.where(ContactRequest.status == status)
    return _request_out(db, list(db.scalars(q)))


def close_request(db: Session, public_id, *, actor_user_id: int, **scope) -> dict:
    r = _scoped_request(db, public_id, lock=True, **scope)
    if r.status != "closed":
        r.status, r.closed_at, r.closed_by = "closed", func.now(), actor_user_id
        audit.record(
            db,
            action="contact_request.closed",
            entity_type="contact_request",
            entity_id=r.public_id,
            actor_user_id=actor_user_id,
            company_id=r.company_id,
        )
        notifications.resolve(db, f"contact_acknowledged:{r.id}")
        db.commit()
        db.refresh(r)
        _broadcast(db, [r.company_id], {"contact_request": str(r.public_id), "status": "closed"})
    return _request_out(db, [r])[0]


def acknowledge(db: Session, device: identity.DevicePrincipal, public_id, *, client_ref: uuid.UUID) -> dict:
    """The driver tapped «Done» (or called): idempotent. The same request acknowledged again (a retry whose answer was
    lost, or another tap) answers the same; a request the office closed meanwhile is closed, nothing to do."""
    r = db.scalar(
        select(ContactRequest)
        .where(ContactRequest.public_id == public_id, ContactRequest.employee_id == device.employee_id)
        .with_for_update()
    )
    if r is None:
        raise AppError(404, "contact_request_not_found")
    if r.status == "open":
        r.status, r.acknowledged_at, r.ack_client_ref = "acknowledged", func.now(), client_ref
        audit.record(
            db,
            action="contact_request.acknowledged",
            entity_type="contact_request",
            entity_id=r.public_id,
            actor_type="device",
            company_id=r.company_id,
        )
        notifications.raise_alert(
            db,
            "contact_acknowledged",
            company_id=r.company_id,
            entity_type="employee",
            entity_id=device.employee_public_id,
            params={"driver": device.name},
            dedupe_key=f"contact_acknowledged:{r.id}",
        )
        db.commit()
        db.refresh(r)
        _broadcast(db, [r.company_id], {"contact_request": str(r.public_id), "status": "acknowledged"})
    return {"id": str(r.public_id), "status": r.status, "acknowledged_at": r.acknowledged_at}
