"""Companies, branches and settings. Imported by every module that needs a setting or a branch check."""

import time
import uuid
from collections.abc import Iterable

from fastapi import Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.core.events import emit
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.i18n import service as i18n
from app.modules.org.models import Branch, Company, Setting
from app.modules.org.schemas import APP_SCREENS, LOCKED_SCREENS, SECTIONS

SPLASH_MAX_BYTES = 2_000_000  # the app keeps it to show before the network answers

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


def section_now(db: Session, name: str) -> BaseModel:
    """A settings section read from the database now, not from the cache (a gate that must hold the moment it is
    switched)."""
    return _load(db, name)[1]


def phone_codes(db: Session) -> bool:
    """Whether a WhatsApp code verifies a driver's phone (and a driver signs in with it): see DriverSignInSettings."""
    return get_section(db, "driver_sign_in").phone_codes


def screen_shown(db: Session, key: str) -> bool:
    return key not in get_section(db, "driver_app").hidden_screens


def screen(key: str):
    """Dependency of a driver endpoint behind an app screen: refused while this client hides the screen, whatever
    the app shows (an older app, or a direct call)."""
    if key not in APP_SCREENS:
        raise ValueError(f"unknown app screen {key}")

    def check(db: Session = Depends(get_session)) -> None:
        if not screen_shown(db, key):
            raise AppError(403, "screen_off")

    return check


def app_screens() -> dict:
    return {"screens": list(APP_SCREENS), "locked": list(LOCKED_SCREENS)}


def splash_file(db: Session) -> files.FileInfo | None:
    """The splash image when one is set and usable: a JPEG or PNG the app can keep."""
    app = get_section(db, "driver_app")
    if not app.splash_enabled or not app.splash_image:
        return None
    try:
        info = files.get(db, app.splash_image)
    except AppError:
        return None
    return info if info.content_type in files.IMAGES and info.size_bytes <= SPLASH_MAX_BYTES else None


def driver_app_config(db: Session) -> dict:
    """What the app asks before and after sign-in: how the driver signs in, the screens hidden, the splash screen."""
    from app.modules.integrations import service as integrations

    app = get_section(db, "driver_app")
    image = splash_file(db)
    return {
        "phone_codes": phone_codes(db),
        "hidden_screens": app.hidden_screens,
        "splash": {"image": image.sha256, "color": app.splash_color, "seconds": app.splash_seconds} if image else None,
        "push": integrations.push_client(db),  # Firebase's public values for this app, once push is on
    }


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


# ------------------------------------------------------------------ companies (legal entities)

COMPANY_FIELDS = (
    "name",
    "trade_name",
    "cr_number",
    "license_number",
    "license_expiry",
    "pam_file_number",
    "phone",
    "address",
    "contact_name",
    "contact_phone",
    "is_active",
)


def company_ids_exist(db: Session, ids: Iterable[int]) -> bool:
    ids = set(ids)
    return db.scalar(select(func.count()).select_from(Company).where(Company.id.in_(ids))) == len(ids)


def _company_out(c: Company) -> dict:
    out = {f: getattr(c, f) for f in COMPANY_FIELDS}
    return {"id": c.id, "public_id": str(c.public_id), **out, "version": c.version}


def _scoped(q, all_companies: bool, company_ids: Iterable[int]):
    return q if all_companies else q.where(Company.id.in_(list(company_ids)))


def list_companies(db: Session, *, all_companies: bool, company_ids: Iterable[int]) -> list[dict]:
    q = _scoped(select(Company).order_by(Company.id), all_companies, company_ids)
    return [_company_out(c) for c in db.scalars(q)]


def _get_company(db: Session, public_id, *, all_companies: bool, company_ids: Iterable[int]) -> Company:
    company = db.scalar(select(Company).where(Company.public_id == public_id))
    # outside the user's scope looks exactly like "does not exist"
    if company is None or not (all_companies or company.id in set(company_ids)):
        raise AppError(404, "company_not_found")
    return company


def get_company(db: Session, public_id, **scope) -> dict:
    return _company_out(_get_company(db, public_id, **scope))


def _check_cr_number(db: Session, cr_number: str | None, own_id: int | None = None) -> None:
    if cr_number and db.scalar(select(Company.id).where(Company.cr_number == cr_number, Company.id != (own_id or 0))):
        raise AppError(409, "cr_number_taken")


def create_company(db: Session, data: dict, *, all_companies: bool, actor_user_id: int) -> dict:
    if not all_companies:  # a company-limited user would not even see what they created
        raise AppError(403, "company_out_of_scope")
    data = {
        **data,
        "name": i18n.validate_localized(db, data["name"]),
        "trade_name": i18n.validate_localized(db, data.get("trade_name"), required=False),
    }
    _check_cr_number(db, data.get("cr_number"))
    company = Company(**data)
    db.add(company)
    db.flush()
    db.refresh(company)
    out = _company_out(company)
    audit.record(
        db,
        action="company.created",
        entity_type="company",
        entity_id=company.public_id,
        actor_user_id=actor_user_id,
        company_id=company.id,
        after=out,
    )
    db.commit()
    return out


def update_company(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int, **scope) -> dict:
    company = _get_company(db, public_id, **scope)
    if company.version != version:
        raise AppError(409, "version_conflict")
    before = _company_out(company)
    if "name" in changes:
        changes["name"] = i18n.validate_localized(db, changes["name"])
    if "trade_name" in changes:
        changes["trade_name"] = i18n.validate_localized(db, changes["trade_name"], required=False)
    if "cr_number" in changes:
        _check_cr_number(db, changes["cr_number"], company.id)
    for field in COMPANY_FIELDS:
        if field in changes:
            setattr(company, field, changes[field])
    company.version += 1
    company.updated_at = func.now()
    db.flush()
    db.refresh(company)
    after = _company_out(company)
    audit.record(
        db,
        action="company.updated",
        entity_type="company",
        entity_id=company.public_id,
        actor_user_id=actor_user_id,
        company_id=company.id,
        before=before,
        after=after,
    )
    db.commit()
    return after


# ------------------------------------------------------------------ branches (operational, no access scope)


def _branch_out(b: Branch) -> dict:
    return {
        "id": b.id,
        "public_id": str(b.public_id),
        "name": b.name,
        "is_default": b.is_default,
        "is_active": b.is_active,
        "version": b.version,
    }


def list_branches(db: Session) -> list[dict]:
    return [_branch_out(b) for b in db.scalars(select(Branch).order_by(Branch.is_default.desc(), Branch.id))]


def _same(label: str, names: dict | None) -> bool:
    label = " ".join(label.split()).casefold()
    return bool(names) and label in {" ".join(v.split()).casefold() for v in names.values()}


def company_id_by_name(db: Session, label: str) -> int | None:
    """Imported files carry names: matched against the name and trade name in any language, or the CR number."""
    for c in db.scalars(select(Company)):
        if _same(label, c.name) or _same(label, c.trade_name) or (c.cr_number and label.strip() == c.cr_number):
            return c.id
    return None


def branch_id_by_name(db: Session, label: str) -> int | None:
    return next((b.id for b in db.scalars(select(Branch)) if _same(label, b.name)), None)


def default_branch_id(db: Session) -> int:
    return db.scalar(select(Branch.id).where(Branch.is_default.is_(True)))


def create_branch(db: Session, *, name: dict, actor_user_id: int) -> dict:
    branch = Branch(name=i18n.validate_localized(db, name), is_default=False)
    db.add(branch)
    db.flush()
    db.refresh(branch)
    out = _branch_out(branch)
    audit.record(
        db,
        action="branch.created",
        entity_type="branch",
        entity_id=branch.public_id,
        actor_user_id=actor_user_id,
        after=out,
    )
    db.commit()
    return out


def update_branch(db: Session, public_id, *, version: int, changes: dict, actor_user_id: int) -> dict:
    branch = db.scalar(select(Branch).where(Branch.public_id == public_id))
    if branch is None:
        raise AppError(404, "branch_not_found")
    if branch.version != version:
        raise AppError(409, "version_conflict")
    before = _branch_out(branch)
    if "name" in changes:
        branch.name = i18n.validate_localized(db, changes["name"])
    if changes.get("is_default") and not branch.is_default:
        db.execute(update(Branch).where(Branch.is_default.is_(True)).values(is_default=False))
        db.flush()
        branch.is_default, branch.is_active = True, True
    if "is_active" in changes and not branch.is_default:
        branch.is_active = changes["is_active"]
    branch.version += 1
    db.flush()
    after = _branch_out(branch)
    audit.record(
        db,
        action="branch.updated",
        entity_type="branch",
        entity_id=branch.public_id,
        actor_user_id=actor_user_id,
        before=before,
        after=after,
    )
    db.commit()
    return after


def labels(db: Session, company_id: int, branch_id: int | None) -> tuple[dict | None, dict | None]:
    """The company's and branch's names (as shown to the driver in his profile)."""
    company = db.get(Company, company_id)
    branch = db.get(Branch, branch_id) if branch_id else None
    return (company.name if company else None, branch.name if branch else None)
