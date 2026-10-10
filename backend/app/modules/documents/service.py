"""Official documents of employees, vehicles and companies, with expiry dates.

A renewal adds a new current document and keeps the previous one as history. This service knows owners only by
(owner_type, owner_id, company_id): the API resolves and scope-checks the owner through its own module.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today, utcnow
from app.core.db import violated_constraint
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.documents.models import Document, DocumentType, Renewal
from app.modules.files import service as files
from app.modules.notifications import service as notifications
from app.modules.org import service as org


@dataclass(frozen=True)
class Owner:
    type: str  # employee / vehicle / company
    id: int
    public_id: str
    company_id: int
    label: dict | str  # a localized name or a plate number, for alerts


def employee_type_codes(db: Session) -> dict[str, bool]:
    """Active employee document types -> whether they need an expiry date."""
    q = select(DocumentType).where(DocumentType.is_active.is_(True), DocumentType.applies_to == "employee")
    return {t.code: t.requires_expiry for t in db.scalars(q)}


def list_types(db: Session) -> list[dict]:
    q = select(DocumentType).where(DocumentType.is_active.is_(True)).order_by(DocumentType.sort_order)
    return [
        {"code": t.code, "name": t.name, "applies_to": t.applies_to, "requires_expiry": t.requires_expiry}
        for t in db.scalars(q)
    ]


def _out(d: Document, owner_public_id: str | None = None) -> dict:
    return {
        "id": str(d.public_id),
        "type_code": d.type_code,
        "owner_type": d.owner_type,
        "owner_id": owner_public_id,
        "company_id": d.company_id,
        "number": d.number,
        "issue_date": d.issue_date,
        "expiry_date": d.expiry_date,
        "has_file": d.file_sha256 is not None,
        "has_back_file": d.file_back_sha256 is not None,
        "notes": d.notes,
        "is_current": d.is_current,
        "created_at": d.created_at,
    }


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Document.company_id.in_(list(company_ids)))


def list_for_owner(db: Session, owner: Owner, *, include_history: bool = False) -> list[dict]:
    q = select(Document).where(Document.owner_type == owner.type, Document.owner_id == owner.id)
    if not include_history:
        q = q.where(Document.is_current.is_(True))
    return [_out(d, owner.public_id) for d in db.scalars(q.order_by(Document.type_code, Document.id.desc()))]


def list_expiring(
    db: Session, *, within_days: int, all_companies: bool, company_ids: Iterable[int], limit: int = 200
) -> list[dict]:
    """Current documents expiring within `within_days` (expired ones included), soonest first."""
    q = _scoped(
        select(Document)
        .where(Document.is_current.is_(True), Document.expiry_date <= today() + timedelta(days=within_days))
        .order_by(Document.expiry_date)
        .limit(min(limit, 500)),
        all_companies,
        company_ids,
    )
    return [_out(d) | {"owner_db_id": d.owner_id} for d in db.scalars(q)]


def add(db: Session, owner: Owner, data: dict, *, actor_user_id: int, commit: bool = True) -> dict:
    """commit=False adds the document to the caller's transaction (driver self-registration approves at once)."""
    doc_type = db.get(DocumentType, data["type_code"])
    if doc_type is None or not doc_type.is_active:
        raise AppError(422, "document_type_not_found")
    if doc_type.applies_to != owner.type:
        raise AppError(422, "document_type_mismatch")
    if doc_type.requires_expiry and data.get("expiry_date") is None:
        raise AppError(422, "expiry_date_required")
    if data.get("issue_date") and data.get("expiry_date") and data["expiry_date"] < data["issue_date"]:
        raise AppError(422, "expiry_before_issue")
    for field in ("file_sha256", "file_back_sha256"):
        if data.get(field):
            files.get(db, data[field])
    previous = db.scalar(
        select(Document)
        .where(
            Document.type_code == doc_type.code,
            Document.owner_type == owner.type,
            Document.owner_id == owner.id,
            Document.is_current.is_(True),
        )
        .with_for_update()
    )
    if previous is not None:  # a renewal: the old one stays as history and its alerts close
        db.execute(update(Document).where(Document.id == previous.id).values(is_current=False))
        db.flush()
        for kind in ("document_expiring", "document_expired"):
            notifications.resolve(db, f"{kind}:{previous.id}:{previous.expiry_date}")
    doc = Document(
        type_code=doc_type.code,
        owner_type=owner.type,
        owner_id=owner.id,
        company_id=owner.company_id,
        number=data.get("number"),
        issue_date=data.get("issue_date"),
        expiry_date=data.get("expiry_date"),
        file_sha256=data.get("file_sha256"),
        file_back_sha256=data.get("file_back_sha256"),
        notes=data.get("notes"),
        created_by=actor_user_id,
    )
    db.add(doc)
    db.flush()
    db.refresh(doc)
    out = _out(doc, owner.public_id)
    audit.record(
        db,
        action="document.added",
        entity_type="document",
        entity_id=doc.public_id,
        actor_user_id=actor_user_id,
        company_id=owner.company_id,
        after=out | {"replaces": str(previous.public_id) if previous else None},
    )
    if commit:
        db.commit()
    return out


def get_file(
    db: Session, public_id, *, side: str = "front", all_companies: bool, company_ids: Iterable[int]
) -> files.FileInfo:
    doc = db.scalar(_scoped(select(Document).where(Document.public_id == public_id), all_companies, company_ids))
    if doc is None:
        raise AppError(404, "document_not_found")
    sha = doc.file_back_sha256 if side == "back" else doc.file_sha256
    if sha is None:
        raise AppError(404, "file_not_found")
    return files.get(db, sha)


def current_expiry(db: Session, type_code: str, owner_type: str, owner_id: int) -> tuple[bool, date | None]:
    """(a current document exists, its expiry date)."""
    row = db.execute(
        select(Document.expiry_date).where(
            Document.type_code == type_code,
            Document.owner_type == owner_type,
            Document.owner_id == owner_id,
            Document.is_current.is_(True),
        )
    ).first()
    return (False, None) if row is None else (True, row[0])


def scan_expiring(db: Session, label_of) -> int:
    """Daily: one alert per document and expiry date, "expiring" first and "expired" once the date passes.
    `label_of(owner_type, owner_id)` gives the owner's display name (resolved by the caller's modules)."""
    settings = org.get_section(db, "documents")
    horizon = max(settings.expiry_alert_days, settings.commercial_license_alert_days)
    q = select(Document).where(Document.is_current.is_(True), Document.expiry_date <= today() + timedelta(days=horizon))
    type_names = {t.code: t.name for t in db.scalars(select(DocumentType))}
    raised = 0
    for doc in db.scalars(q):
        days = (doc.expiry_date - today()).days
        limit = (
            settings.commercial_license_alert_days
            if doc.type_code == "commercial_license"
            else settings.expiry_alert_days
        )
        if days > limit:
            continue
        kind = "document_expired" if days < 0 else "document_expiring"
        if kind == "document_expired":
            notifications.resolve(db, f"document_expiring:{doc.id}:{doc.expiry_date}")
        raised += notifications.raise_alert(
            db,
            kind,
            company_id=doc.company_id,
            entity_type="document",
            entity_id=doc.public_id,
            params={
                "document": type_names[doc.type_code],
                "owner": label_of(doc.owner_type, doc.owner_id),
                "date": doc.expiry_date.isoformat(),
                "days": max(days, 0),
            },
            dedupe_key=f"{kind}:{doc.id}:{doc.expiry_date}",
        )
        if doc.owner_type == "employee":  # the driver sees his own residency or licence about to expire
            notifications.notify_driver(
                db,
                doc.owner_id,
                kind,
                params={
                    "document": type_names[doc.type_code],
                    "date": doc.expiry_date.isoformat(),
                    "days": max(days, 0),
                },
                entity_type="document",
                entity_id=doc.public_id,
                dedupe_key=f"{kind}:{doc.id}:{doc.expiry_date}",
            )
    db.commit()
    return raised


# ------------------------------------------------------------------ the driver's documents (BRD FR-APP-05)


def _renewal_out(r: Renewal, type_names: dict, names: dict | None = None) -> dict:
    return {
        "id": str(r.public_id),
        "type_code": r.type_code,
        "type_name": type_names.get(r.type_code),
        "driver": (names or {}).get(r.employee_id),
        "number": r.number,
        "expiry_date": r.expiry_date,
        "status": r.status,
        "created_at": r.created_at,
        "decided_at": r.decided_at,
        "note": r.note,
    }


def _type_names(db: Session) -> dict:
    return {t.code: t.name for t in db.scalars(select(DocumentType))}


def driver_documents(db: Session, employee_id: int) -> list[dict]:
    """The driver's current documents with their expiry and how long is left, and the renewal he sent for each
    type, if any; plus the types he has none of yet."""
    settings = org.get_section(db, "documents")
    names = _type_names(db)
    current = {
        d.type_code: d
        for d in db.scalars(
            select(Document).where(
                Document.owner_type == "employee", Document.owner_id == employee_id, Document.is_current.is_(True)
            )
        )
    }
    latest: dict[str, Renewal] = {}
    for r in db.scalars(select(Renewal).where(Renewal.employee_id == employee_id).order_by(Renewal.id)):
        latest[r.type_code] = r
    types = db.scalars(
        select(DocumentType)
        .where(DocumentType.applies_to == "employee", DocumentType.is_active.is_(True))
        .order_by(DocumentType.sort_order)
    )
    out = []
    for t in types:
        d = current.get(t.code)
        days = (d.expiry_date - today()).days if d and d.expiry_date else None
        state = (
            "missing"
            if d is None
            else "expired"
            if days is not None and days < 0
            else "expiring"
            if days is not None and days <= settings.expiry_alert_days
            else "valid"
        )
        if d is None and not t.requires_expiry:
            continue  # a contract he has none of is not his to send
        renewal = latest.get(t.code)
        out.append(
            {
                "type_code": t.code,
                "type_name": t.name,
                "number": d.number if d else None,
                "expiry_date": d.expiry_date if d else None,
                "days_left": days,
                "state": state,
                "renewable": t.requires_expiry,
                "renewal": _renewal_out(renewal, names) if renewal else None,
            }
        )
    return out


def submit_renewal(
    db: Session, *, employee_id: int, company_id: int, device_id: int, driver_name: dict, data: dict
) -> dict:
    """The renewed document from the driver's phone: the photo or scan from this phone, the new expiry date."""
    doc_type = db.get(DocumentType, data["type_code"])
    if doc_type is None or not doc_type.is_active or doc_type.applies_to != "employee" or not doc_type.requires_expiry:
        raise AppError(422, "document_type_not_found")
    if data["expiry_date"] <= today():
        raise AppError(422, "expiry_in_past")
    f = files.get(db, data["file_sha256"])
    if f.uploaded_by_device != device_id:
        raise AppError(422, "file_not_yours")
    renewal = Renewal(
        employee_id=employee_id,
        company_id=company_id,
        type_code=doc_type.code,
        number=data.get("number"),
        expiry_date=data["expiry_date"],
        file_sha256=data["file_sha256"],
        created_by_device=device_id,
    )
    try:
        with db.begin_nested():
            db.add(renewal)
            db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == "renewals_one_pending_idx":
            raise AppError(409, "renewal_exists") from None
        raise
    notifications.raise_alert(
        db,
        "document_renewal_submitted",
        company_id=company_id,
        entity_type="document_renewal",
        entity_id=renewal.public_id,
        params={"driver": driver_name, "document": doc_type.name, "date": renewal.expiry_date.isoformat()},
        dedupe_key=f"document_renewal:{renewal.id}",
    )
    audit.record(
        db,
        action="document.renewal_submitted",
        entity_type="document_renewal",
        entity_id=renewal.public_id,
        actor_type="device",
        company_id=company_id,
        after={"type": doc_type.code, "number": renewal.number, "expiry_date": renewal.expiry_date},
    )
    db.commit()
    return _renewal_out(renewal, _type_names(db))


def _renewal(db: Session, public_id, *, lock: bool = False, all_companies: bool, company_ids) -> Renewal:
    q = select(Renewal).where(Renewal.public_id == public_id)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None or not (all_companies or r.company_id in set(company_ids)):
        raise AppError(404, "renewal_not_found")
    return r


def list_renewals(db: Session, *, status: str | None, names_of, all_companies: bool, company_ids) -> list[dict]:
    q = select(Renewal).order_by(Renewal.created_at)
    if status:
        q = q.where(Renewal.status == status)
    if not all_companies:
        q = q.where(Renewal.company_id.in_(list(company_ids)))
    rows = list(db.scalars(q.limit(500)))
    names = names_of({r.employee_id for r in rows})
    type_names = _type_names(db)
    return [_renewal_out(r, type_names, names) for r in rows]


def renewal_employee_id(db: Session, public_id, **scope) -> int:
    return _renewal(db, public_id, **scope).employee_id


def renewal_file(db: Session, public_id, **scope) -> files.FileInfo:
    return files.get(db, _renewal(db, public_id, **scope).file_sha256)


def decide_renewal(
    db: Session, public_id, *, approve: bool, note: str | None, owner: Owner | None, actor_user_id: int, **scope
) -> dict:
    """Checked against the photo: approved, it becomes the driver's current document (the old one kept as history,
    its expiry alerts closed); refused, the driver reads why."""
    r = _renewal(db, public_id, lock=True, **scope)
    if r.status != "pending":
        raise AppError(409, "renewal_decided")
    if not approve and not note:
        raise AppError(422, "reason_required")
    type_names = _type_names(db)
    if approve:
        doc = add(
            db,
            owner,
            {"type_code": r.type_code, "number": r.number, "expiry_date": r.expiry_date, "file_sha256": r.file_sha256},
            actor_user_id=actor_user_id,
            commit=False,
        )
        r.document_id = db.scalar(select(Document.id).where(Document.public_id == doc["id"]))
    r.status = "approved" if approve else "rejected"
    r.decided_by, r.decided_at, r.note = actor_user_id, utcnow(), note
    notifications.resolve(db, f"document_renewal:{r.id}")
    params = {"document": type_names[r.type_code]} | ({} if approve else {"reason": note})
    notifications.notify_driver(
        db,
        r.employee_id,
        "document_renewal_approved" if approve else "document_renewal_rejected",
        params=params,
    )
    audit.record(
        db,
        action="document.renewal_approved" if approve else "document.renewal_rejected",
        entity_type="document_renewal",
        entity_id=r.public_id,
        actor_user_id=actor_user_id,
        company_id=r.company_id,
        after={"note": note},
    )
    db.commit()
    return _renewal_out(r, type_names)
