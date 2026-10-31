"""A driver with no platform says in the app which company he works with (the first screen after he signs in): a
request the office approves (his platform set, his ID on it in the same step) or rejects with a reason; he is told
either way. While it waits, his daily report asks that platform's fields (provisionally); payroll never reads a
request, only the platform the office set."""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.notifications import service as notifications
from app.modules.payroll import schemes as pay_schemes
from app.modules.payroll.models import Platform, PlatformRequest, Scheme
from app.modules.people import service as people


def _offered(db: Session) -> list[Platform]:
    """What a driver may pick: the active platforms, the core ones first."""
    q = select(Platform).where(Platform.is_active.is_(True)).order_by(Platform.is_core.desc(), Platform.id)
    return list(db.scalars(q))


def _brief(p: Platform | None) -> dict | None:
    return {"id": p.id, "code": p.code, "name": p.name, "is_core": p.is_core} if p else None


def _scheme(s: Scheme | None) -> dict | None:
    return {"id": str(s.public_id), "code": s.code, "name": s.name} if s else None


def _out(db: Session, rows: list[PlatformRequest]) -> list[dict]:
    names = people.names(db, {r.employee_id for r in rows})
    plats = {p.id: p for p in db.scalars(select(Platform).where(Platform.id.in_({r.platform_id for r in rows})))}
    picked = {r.scheme_id for r in rows if r.scheme_id}
    chosen = {s.id: s for s in db.scalars(select(Scheme).where(Scheme.id.in_(picked)))} if picked else {}
    return [
        {
            "id": str(r.public_id),
            "employee": names.get(r.employee_id),
            "company_id": r.company_id,
            "platform": _brief(plats.get(r.platform_id)),
            "scheme": _scheme(chosen.get(r.scheme_id)),
            "status": r.status,
            "driver_note": r.driver_note,
            "admin_note": r.admin_note,
            "platform_driver_id": r.platform_driver_id,
            "created_at": r.created_at,
            "decided_at": r.decided_at,
            "version": r.version,
        }
        for r in rows
    ]


def _latest(db: Session, employee_id: int) -> PlatformRequest | None:
    return db.scalar(
        select(PlatformRequest)
        .where(PlatformRequest.employee_id == employee_id, PlatformRequest.status != "cancelled")
        .order_by(PlatformRequest.id.desc())
        .limit(1)
    )


def pending_platform(db: Session, employee_id: int) -> int | None:
    return db.scalar(
        select(PlatformRequest.platform_id).where(
            PlatformRequest.employee_id == employee_id, PlatformRequest.status == "pending"
        )
    )


def driver_view(db: Session, employee_id: int) -> dict:
    """What the app shows: his platform (set by the office), the companies he may pick, his latest request; `ask`:
    the company screen is due (no platform, nothing waiting)."""
    driver = people.ref(db, employee_id)
    latest = _latest(db, employee_id)
    mine = db.get(Platform, driver.platform_id) if driver.platform_id else None
    return {
        "platform": _brief(mine),
        "platforms": [_brief(p) for p in _offered(db)],
        "request": _out(db, [latest])[0] if latest else None,
        "ask": mine is None and (latest is None or latest.status != "pending"),
    }


def _alert_key(r: PlatformRequest) -> str:
    return f"platform_request:{r.id}"


def offered_schemes(db: Session, employee_id: int, platform_id: int) -> list[dict]:
    """The schemes a company offers its drivers, for the one who is about to pick it (he is not on it yet)."""
    people.ref(db, employee_id)
    p = db.get(Platform, platform_id)
    if p is None or not p.is_active:
        raise AppError(422, "platform_not_found")
    return pay_schemes.list_schemes(db, platform_id=p.id, offered_only=True)


def ask(
    db: Session, employee_id: int, *, device_id: int, platform_id: int, note: str | None, scheme_public_id=None
) -> dict:
    driver = people.ref(db, employee_id)
    if not driver.is_driver:
        raise AppError(422, "not_a_driver")
    if driver.platform_id:
        raise AppError(409, "platform_already_set")
    p = db.get(Platform, platform_id)
    if p is None or not p.is_active:
        raise AppError(422, "platform_not_found")
    scheme = None
    if scheme_public_id is not None:
        scheme = db.scalar(select(Scheme).where(Scheme.public_id == scheme_public_id))
        if scheme is None or not (scheme.is_active and scheme.driver_selectable and scheme.platform_id == p.id):
            raise AppError(422, "scheme_not_available")
    r = PlatformRequest(
        employee_id=employee_id,
        company_id=driver.company_id,
        platform_id=p.id,
        scheme_id=scheme.id if scheme else None,
        driver_note=(note or "").strip() or None,
        submitted_by_device=device_id,
    )
    db.add(r)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != "platform_requests_employee_id_idx":
            raise
        raise AppError(409, "platform_request_pending") from None
    db.refresh(r)
    notifications.raise_alert(
        db,
        "platform_request",
        company_id=r.company_id,
        entity_type="platform_request",
        entity_id=r.public_id,
        params={"driver": driver.name, "platform": p.name},
        dedupe_key=_alert_key(r),
    )
    audit.record(
        db,
        action="platform_request.submitted",
        entity_type="platform_request",
        entity_id=r.public_id,
        actor_type="device",
        company_id=r.company_id,
        after={"platform": p.code, "scheme": scheme.code if scheme else None},
    )
    db.commit()
    return driver_view(db, employee_id)


def _decide(db: Session, r: PlatformRequest, **values) -> None:
    """Conditional on pending: decided (or cancelled) once; whoever comes second is told so."""
    done = db.execute(
        update(PlatformRequest)
        .where(PlatformRequest.id == r.id, PlatformRequest.status == "pending")
        .values(version=PlatformRequest.version + 1, **values)
    ).rowcount
    if not done:
        raise AppError(409, "platform_request_decided")
    notifications.resolve(db, _alert_key(r))


def cancel(db: Session, employee_id: int, public_id) -> dict:
    r = db.scalar(
        select(PlatformRequest).where(
            PlatformRequest.public_id == public_id, PlatformRequest.employee_id == employee_id
        )
    )
    if r is None:
        raise AppError(404, "platform_request_not_found")
    _decide(db, r, status="cancelled")
    audit.record(
        db,
        action="platform_request.cancelled",
        entity_type="platform_request",
        entity_id=r.public_id,
        actor_type="device",
        company_id=r.company_id,
    )
    db.commit()
    return driver_view(db, employee_id)


def _scoped(q, all_companies: bool, company_ids):
    return q if all_companies else q.where(PlatformRequest.company_id.in_(list(company_ids)))


def list_requests(
    db: Session,
    *,
    status: str | None,
    platform_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    all_companies: bool,
    company_ids,
) -> list[dict]:
    q = select(PlatformRequest).order_by(PlatformRequest.created_at.desc(), PlatformRequest.id.desc())
    if status:
        q = q.where(PlatformRequest.status == status)
    if platform_id:
        q = q.where(PlatformRequest.platform_id == platform_id)
    return _out(db, list(db.scalars(_scoped(q, all_companies, company_ids).limit(limit).offset(offset))))


def counts(db: Session, *, all_companies: bool, company_ids) -> dict:
    """Pending requests: in all, and by the platform asked for."""
    q = select(PlatformRequest.platform_id, func.count()).where(PlatformRequest.status == "pending")
    by = dict(db.execute(_scoped(q, all_companies, company_ids).group_by(PlatformRequest.platform_id)).all())
    return {"pending": sum(by.values()), "by_platform": {str(k): v for k, v in by.items()}}


def _get(db: Session, public_id, *, version: int | None, all_companies: bool, company_ids) -> PlatformRequest:
    r = db.scalar(_scoped(select(PlatformRequest).where(PlatformRequest.public_id == public_id), all_companies,
                          company_ids))  # fmt: skip
    if r is None:
        raise AppError(404, "platform_request_not_found")
    if r.status != "pending":
        raise AppError(409, "platform_request_decided")
    if version is not None and r.version != version:
        raise AppError(409, "version_conflict")
    return r


def approve(
    db: Session,
    public_id,
    *,
    version: int | None,
    platform_id: int | None,
    platform_driver_id: str | None,
    actor_user_id: int,
    **scope,
) -> dict:
    """His platform set (the one he asked for, or the one the office corrects it to) with his ID on it when given."""
    r = _get(db, public_id, version=version, **scope)
    p = db.get(Platform, platform_id or r.platform_id)
    if p is None or not p.is_active:
        raise AppError(422, "platform_not_found")
    driver = people.ref(db, r.employee_id)
    if driver.platform_id:
        raise AppError(409, "platform_already_set")
    _decide(
        db, r, status="approved", platform_id=p.id, decided_by=actor_user_id, decided_at=utcnow(),
        platform_driver_id=(platform_driver_id or "").strip() or None,
    )  # fmt: skip
    people.put_on_platform(
        db,
        driver.public_id,
        platform_id=p.id,
        platform_driver_id=platform_driver_id,
        actor_user_id=actor_user_id,
        commit=False,
        **scope,
    )
    # the scheme he picked with it, from the first month still open, when it is still offered on that company
    scheme = db.get(Scheme, r.scheme_id) if r.scheme_id else None
    if scheme is not None and scheme.is_active and scheme.platform_id == p.id:
        pay_schemes.set_first(db, people.ref(db, r.employee_id), scheme, actor_user_id=actor_user_id)
    audit.record(
        db,
        action="platform_request.approved",
        entity_type="platform_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"platform": p.code, "platform_driver_id": (platform_driver_id or "").strip() or None},
    )
    notifications.notify_driver(
        db, r.employee_id, "platform_request_approved", params={"platform": p.name},
        entity_type="platform_request", entity_id=r.public_id,
    )  # fmt: skip
    db.commit()
    db.refresh(r)
    return _out(db, [r])[0]


def reject(db: Session, public_id, *, version: int | None, note: str, actor_user_id: int, **scope) -> dict:
    r = _get(db, public_id, version=version, **scope)
    _decide(db, r, status="rejected", admin_note=note, decided_by=actor_user_id, decided_at=utcnow())
    p = db.get(Platform, r.platform_id)
    audit.record(
        db,
        action="platform_request.rejected",
        entity_type="platform_request",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"note": note},
    )
    notifications.notify_driver(
        db, r.employee_id, "platform_request_rejected", params={"platform": p.name, "reason": note},
        entity_type="platform_request", entity_id=r.public_id,
    )  # fmt: skip
    db.commit()
    db.refresh(r)
    return _out(db, [r])[0]


# ------------------------------------------------------------------ chosen with the registration


def registration_options(db: Session, employee_id: int) -> dict:
    """What the registration's last step offers: his company when the office already set it (he picks only a scheme),
    else the companies he may pick; and every scheme they offer, each with its company."""
    driver = people.ref(db, employee_id)
    mine = db.get(Platform, driver.platform_id) if driver.platform_id else None
    plats = [mine] if mine else _offered(db)
    return {
        "platform": _brief(mine),
        "platforms": [_brief(p) for p in plats],
        "schemes": [s for p in plats for s in pay_schemes.list_schemes(db, platform_id=p.id, offered_only=True)],
    }


def check_registration_choice(db: Session, employee_id: int, platform_id: int | None, scheme_public_id) -> list[str]:
    """What is missing or no longer offered in the registration's company and scheme (both are required)."""
    driver = people.ref(db, employee_id)
    pid = driver.platform_id or platform_id
    missing = []
    p = db.get(Platform, pid) if pid else None
    if p is None or not p.is_active:
        missing.append("platform")
    scheme = db.scalar(select(Scheme).where(Scheme.public_id == scheme_public_id)) if scheme_public_id else None
    if scheme is None or not (scheme.is_active and scheme.driver_selectable) or (p and scheme.platform_id != p.id):
        missing.append("scheme")
    return missing


def apply_registration_choice(
    db: Session, employee_id: int, platform_id: int | None, scheme_public_id, *, actor_user_id: int, **scope
) -> None:
    """In the caller's transaction, at the registration's approval: his company (unless the office set one), then his
    scheme from the first month still open, when it is still offered on that company."""
    driver = people.ref(db, employee_id)
    if not driver.platform_id and platform_id:
        p = db.get(Platform, platform_id)
        if p is None or not p.is_active:
            raise AppError(422, "platform_not_found")
        people.put_on_platform(
            db, driver.public_id, platform_id=p.id, platform_driver_id=None, actor_user_id=actor_user_id,
            commit=False, **scope,
        )  # fmt: skip
        driver = people.ref(db, employee_id)
    scheme = db.scalar(select(Scheme).where(Scheme.public_id == scheme_public_id)) if scheme_public_id else None
    if scheme is not None and scheme.is_active and scheme.platform_id == driver.platform_id:
        pay_schemes.set_first(db, driver, scheme, actor_user_id=actor_user_id)


def registration_choice_names(db: Session, employee_id: int, platform_id: int | None, scheme_public_id) -> dict:
    """For the reviewer: the company (his own when the office set it) and the scheme the registration names."""
    driver = people.ref(db, employee_id)
    p = db.get(Platform, driver.platform_id or platform_id) if (driver.platform_id or platform_id) else None
    scheme = db.scalar(select(Scheme).where(Scheme.public_id == scheme_public_id)) if scheme_public_id else None
    return {"platform": _brief(p), "scheme": _scheme(scheme), "platform_set_by_office": bool(driver.platform_id)}
