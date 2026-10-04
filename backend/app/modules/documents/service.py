"""Official documents of employees, vehicles and companies, with expiry dates.

A renewal adds a new current document and keeps the previous one as history. This service knows owners only by
(owner_type, owner_id, company_id): the API resolves and scope-checks the owner through its own module.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.documents.models import Document, DocumentType
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
    db.commit()
    return raised
