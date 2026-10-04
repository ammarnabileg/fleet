"""Companies, branches and settings. Imported by every module that needs a setting or a branch check."""

import time
import uuid
from collections.abc import Iterable

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.org.models import Branch, Company, Setting
from app.modules.org.schemas import SECTIONS

CACHE_SECONDS = 60
_cache: dict[str, tuple[float, int, BaseModel]] = {}
SETTINGS_NAMESPACE = uuid.UUID("6f1c3b52-6a0e-4d7e-9a43-6d3c1c2b8e10")


# ------------------------------------------------------------------ settings


def _section_model(name: str) -> type[BaseModel]:
    model = SECTIONS.get(name)
    if model is None:
        raise AppError(404, "unknown_settings_section", name)
    return model


def _load(db: Session, name: str) -> tuple[int, BaseModel]:
    model = _section_model(name)
    row = db.get(Setting, name)
    return (0, model()) if row is None else (row.version, model.model_validate(row.value))


def get_section(db: Session, name: str) -> BaseModel:
    """Effective value of a settings section (cached for up to 60 seconds per process)."""
    hit = _cache.get(name)
    if hit and hit[0] > time.monotonic():
        return hit[2]
    version, value = _load(db, name)
    _cache[name] = (time.monotonic() + CACHE_SECONDS, version, value)
    return value


def all_sections(db: Session) -> dict[str, tuple[int, BaseModel]]:
    return {name: _load(db, name) for name in SECTIONS}


def update_section(
    db: Session, name: str, value: dict, *, expected_version: int, actor_user_id: int | None
) -> tuple[int, BaseModel]:
    model = _section_model(name)
    try:
        new = model.model_validate(value)
    except ValidationError as exc:
        raise AppError(
            422, "invalid_settings", "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        ) from None
    row = db.get(Setting, name, with_for_update=True)
    current_version = 0 if row is None else row.version
    if current_version != expected_version:
        raise AppError(409, "version_conflict")
    before = model() if row is None else model.model_validate(row.value)
    stored = new.model_dump(mode="json")
    if row is None:
        row = Setting(key=name, value=stored, version=1, updated_by=actor_user_id)
        db.add(row)
    else:
        row.value, row.version, row.updated_by, row.updated_at = stored, row.version + 1, actor_user_id, func.now()
    db.flush()
    audit.record(
        db,
        action="settings.changed",
        entity_type="settings",
        entity_id=name,
        actor_user_id=actor_user_id,
        before=before.model_dump(mode="json"),
        after=stored,
    )
    emit(db, "settings.changed", uuid.uuid5(SETTINGS_NAMESPACE, name), {"section": name, "version": row.version})
    db.commit()
    _cache.pop(name, None)
    return row.version, new


# ------------------------------------------------------------------ companies & branches


def branch_ids_exist(db: Session, ids: Iterable[int]) -> bool:
    ids = set(ids)
    return db.scalar(select(func.count()).select_from(Branch).where(Branch.id.in_(ids))) == len(ids)


def _branch_out(branch: Branch, company_public_id: uuid.UUID) -> dict:
    return {
        "id": branch.id,
        "public_id": str(branch.public_id),
        "company_public_id": str(company_public_id),
        "name_ar": branch.name_ar,
        "name_en": branch.name_en,
        "is_active": branch.is_active,
        "version": branch.version,
    }


def list_companies(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.name_en)))


def create_company(db: Session, *, name_ar: str, name_en: str, actor_user_id: int) -> Company:
    company = Company(name_ar=name_ar, name_en=name_en)
    db.add(company)
    db.flush()
    db.refresh(company)
    audit.record(
        db,
        action="company.created",
        entity_type="company",
        entity_id=company.public_id,
        actor_user_id=actor_user_id,
        after={"name_ar": name_ar, "name_en": name_en},
    )
    db.commit()
    return company


def list_branches(db: Session, *, all_branches: bool, branch_ids: Iterable[int]) -> list[dict]:
    q = select(Branch, Company.public_id).join(Company, Company.id == Branch.company_id).order_by(Branch.name_en)
    if not all_branches:
        q = q.where(Branch.id.in_(list(branch_ids)))
    return [_branch_out(b, cid) for b, cid in db.execute(q)]


def _get_branch(
    db: Session, public_id: str, *, all_branches: bool, branch_ids: Iterable[int]
) -> tuple[Branch, uuid.UUID]:
    row = db.execute(
        select(Branch, Company.public_id)
        .join(Company, Company.id == Branch.company_id)
        .where(Branch.public_id == public_id)
    ).first()
    # outside the user's scope looks exactly like "does not exist"
    if row is None or not (all_branches or row[0].id in set(branch_ids)):
        raise AppError(404, "branch_not_found")
    return row[0], row[1]


def get_branch(db: Session, public_id: str, *, all_branches: bool, branch_ids: Iterable[int]) -> dict:
    return _branch_out(*_get_branch(db, public_id, all_branches=all_branches, branch_ids=branch_ids))


def create_branch(db: Session, *, company_public_id: str, name_ar: str, name_en: str, actor_user_id: int) -> dict:
    company = db.scalar(select(Company).where(Company.public_id == company_public_id))
    if company is None:
        raise AppError(422, "unknown_company")
    branch = Branch(company_id=company.id, name_ar=name_ar, name_en=name_en)
    db.add(branch)
    db.flush()
    db.refresh(branch)
    out = _branch_out(branch, company.public_id)
    audit.record(
        db,
        action="branch.created",
        entity_type="branch",
        entity_id=branch.public_id,
        actor_user_id=actor_user_id,
        branch_id=branch.id,
        after=out,
    )
    db.commit()
    return out


def update_branch(
    db: Session,
    public_id: str,
    *,
    version: int,
    changes: dict,
    all_branches: bool,
    branch_ids: Iterable[int],
    actor_user_id: int,
) -> dict:
    branch, company_public_id = _get_branch(db, public_id, all_branches=all_branches, branch_ids=branch_ids)
    if branch.version != version:
        raise AppError(409, "version_conflict")
    before = _branch_out(branch, company_public_id)
    for field in ("name_ar", "name_en", "is_active"):
        if field in changes:
            setattr(branch, field, changes[field])
    branch.version += 1
    db.flush()
    after = _branch_out(branch, company_public_id)
    audit.record(
        db,
        action="branch.updated",
        entity_type="branch",
        entity_id=branch.public_id,
        actor_user_id=actor_user_id,
        branch_id=branch.id,
        before=before,
        after=after,
    )
    db.commit()
    return after
