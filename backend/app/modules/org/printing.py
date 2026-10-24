"""Print templates: the one A4 layout every report, receipt and printout of the panel is printed in, and the header of
the Excel files. A default template and, for an operating company that wants its own, an override; the identity in
the header (name, CR number, phone, address) is the company's the report belongs to, or the group's (the default
template's names, else the installation's display name) when a report spans companies.

Published as a whole set (default + overrides) with a version, as the driver status templates are: the newest is in
force, «back to the previous setting» publishes the one before again as a new version."""

import base64
import re
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.files import service as files
from app.modules.identity import service as identity
from app.modules.org.models import Company, PrintTemplateVersion

IMAGE_MAX_BYTES = 1_000_000  # a logo or a watermark: embedded in every printout
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]

HEADER_VARIABLES = ("company", "company_en", "cr_number", "license_number", "pam_file_number", "phone", "address")
FOOTER_VARIABLES = ("page", "pages", "printed_at", "printed_by", "company")
VARIABLE = re.compile(r"\{(\w+)\}")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Header(_M):
    show_logo: bool = True
    logo: Sha | None = None
    logo_position: Literal["start", "center", "end"] = "start"
    show_name_ar: bool = True
    show_name_en: bool = True
    name_ar: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""  # blank: the company's
    name_en: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    lines: list[Line] = Field(default_factory=lambda: ["س.ت: {cr_number}", "{address}", "هاتف: {phone}"], max_length=4)
    title_align: Literal["start", "center", "end"] = "center"
    show_title: bool = True
    show_filters: bool = True


class Footer(_M):
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = "صفحة {page} من {pages}"
    show_printed_at: bool = True
    show_printed_by: bool = True
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""  # above the signatures
    signatures: list[Label] = Field(default_factory=list, max_length=4)  # confirmation / signature lines


class Watermark(_M):
    mode: Literal["off", "always", "drafts"] = "off"  # drafts: only on a draft / unapproved printout
    kind: Literal["text", "image"] = "text"
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] = "مسودة"
    image: Sha | None = None
    opacity: float = Field(0.08, ge=0.02, le=0.5)
    angle: int = Field(-30, ge=-90, le=90)
    size: int = Field(96, ge=24, le=240)  # the text's size in px, an image's width in mm


class Page(_M):
    margin_top: int = Field(14, ge=5, le=40)  # mm
    margin_bottom: int = Field(16, ge=5, le=40)
    margin_start: int = Field(12, ge=5, le=40)
    margin_end: int = Field(12, ge=5, le=40)
    font_size: float = Field(10.5, ge=8, le=16)  # pt
    accent: Color = "#0A6CFF"
    text_color: Color = "#111111"
    header_rule: bool = True
    zebra: bool = False


class Template(_M):
    header: Header = Field(default_factory=Header)
    footer: Footer = Field(default_factory=Footer)
    watermark: Watermark = Field(default_factory=Watermark)
    page: Page = Field(default_factory=Page)


SAMPLE_IDENTITY = {
    "company": "شركة النموذج للتوصيل",
    "company_en": "Sample Delivery Co.",
    "cr_number": "123456",
    "license_number": "L-0001",
    "pam_file_number": "77-001",
    "phone": "+96520000000",
    "address": "الكويت — الشويخ الصناعية",
}


def default_template() -> dict:
    return Template().model_dump()


def _check_variables(t: Template) -> None:
    for i, line in enumerate(t.header.lines):
        bad = sorted(set(VARIABLE.findall(line)) - set(HEADER_VARIABLES))
        if bad:
            raise AppError(422, "print_template_variable_unknown", field=f"header.lines.{i}", variable=bad[0])
    bad = sorted(set(VARIABLE.findall(t.footer.text)) - set(FOOTER_VARIABLES))
    if bad:
        raise AppError(422, "print_template_variable_unknown", field="footer.text", variable=bad[0])


def validate(db: Session, data: dict) -> dict:
    """A template as stored: every field checked, unknown fields refused, variables only from the lists."""
    try:
        t = Template.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        raise AppError(422, "print_template_invalid", field=".".join(str(x) for x in err["loc"])) from None
    _check_variables(t)
    for sha in (t.header.logo, t.watermark.image):
        if sha is not None and not _is_image(db, sha):
            raise AppError(422, "print_template_image_missing")
    return t.model_dump()


# ------------------------------------------------------------------ versions


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('org.print_templates', 0))"))


def _empty() -> dict:
    return {"default": default_template(), "companies": {}}


def _normalized(config: dict) -> dict:
    """A stored set read with today's fields: a field added since it was published takes its default."""
    out = {"default": Template.model_validate(config.get("default") or {}).model_dump(), "companies": {}}
    for cid, t in (config.get("companies") or {}).items():
        out["companies"][str(cid)] = Template.model_validate(t).model_dump()
    return out


def current(db: Session) -> tuple[int, dict]:
    row = db.scalar(select(PrintTemplateVersion).order_by(PrintTemplateVersion.version.desc()).limit(1))
    return (0, _empty()) if row is None else (row.version, _normalized(row.config))


def _publish(db: Session, config: dict, *, actor_user_id: int, changed: str | None, restored_from: int | None) -> None:
    version, _ = current(db)
    db.add(
        PrintTemplateVersion(
            version=version + 1, config=config, restored_from=restored_from, changed=changed, created_by=actor_user_id
        )
    )
    audit.record(
        db,
        action="print_template.rollback" if restored_from is not None else "print_template.published",
        entity_type="print_template",
        entity_id=changed or f"v{restored_from}",
        actor_user_id=actor_user_id,
        after={"version": version + 1, "restored_from": restored_from},
    )
    db.commit()


def _check_version(db: Session, expected: int) -> dict:
    _lock(db)
    version, config = current(db)
    if version != expected:
        raise AppError(409, "print_config_changed")
    return config


def _company(db: Session, company_id: int, all_companies: bool, company_ids: Iterable[int]) -> Company:
    company = db.get(Company, company_id)
    if company is None or not (all_companies or company.id in set(company_ids)):
        raise AppError(404, "company_not_found")
    return company


def publish_default(db: Session, data: dict, *, expected_version: int, actor_user_id: int) -> dict:
    clean = validate(db, data)
    config = _check_version(db, expected_version)
    config["default"] = clean
    _publish(db, config, actor_user_id=actor_user_id, changed="default", restored_from=None)
    return manage(db)


def publish_company(
    db: Session, company_id: int, data: dict | None, *, expected_version: int, actor_user_id: int, **scope
) -> dict:
    """A company's own template; none removes it (the company prints with the default again)."""
    _company(db, company_id, **scope)
    clean = None if data is None else validate(db, data)
    config = _check_version(db, expected_version)
    if clean is None:
        config["companies"].pop(str(company_id), None)
    else:
        config["companies"][str(company_id)] = clean
    _publish(db, config, actor_user_id=actor_user_id, changed=f"company:{company_id}", restored_from=None)
    return manage(db)


def rollback(db: Session, *, expected_version: int, actor_user_id: int) -> dict:
    """«Back to the previous setting»: the set before the current one, published again as a new version; again goes
    one further back (the version the current one came from is skipped)."""
    _check_version(db, expected_version)
    if expected_version == 0:
        raise AppError(409, "print_config_no_previous")
    row = db.get(PrintTemplateVersion, expected_version)
    base = row.restored_from if row.restored_from is not None else expected_version
    if base <= 0:
        raise AppError(409, "print_config_no_previous")
    target = base - 1
    config = _empty() if target == 0 else _normalized(db.get(PrintTemplateVersion, target).config)
    _publish(db, config, actor_user_id=actor_user_id, changed=None, restored_from=target)
    return manage(db)


def manage(db: Session) -> dict:
    """The designer page: what is in force, the variables, a sample identity, and the publish history."""
    version, config = current(db)
    rows = list(db.scalars(select(PrintTemplateVersion).order_by(PrintTemplateVersion.version.desc()).limit(30)))
    users = identity.user_refs(db, {r.created_by for r in rows})
    return {
        "config_version": version,
        "default": config["default"],
        "companies": config["companies"],
        "options": {
            "header_variables": list(HEADER_VARIABLES),
            "footer_variables": list(FOOTER_VARIABLES),
            "image_max_bytes": IMAGE_MAX_BYTES,
            "sample": SAMPLE_IDENTITY,
        },
        "history": [
            {
                "version": r.version,
                "changed": r.changed,
                "restored_from": r.restored_from,
                "by": users.get(r.created_by),
                "at": r.created_at,
            }
            for r in rows
        ],
    }


# ------------------------------------------------------------------ images


def _is_image(db: Session, sha: str) -> bool:
    try:
        return files.get(db, sha).content_type in files.IMAGES
    except AppError:
        return False


def store_image(db: Session, data: bytes, *, actor_user_id: int) -> dict:
    if len(data) > IMAGE_MAX_BYTES:
        raise AppError(413, "file_too_large", max_mb=1)
    info = files.store(db, data, source="upload", uploaded_by_user=actor_user_id, images_only=True)
    db.commit()
    return {"sha256": info.sha256, "content_type": info.content_type}


def image(db: Session, sha: str) -> files.FileInfo:
    info = files.get(db, sha)
    if info.content_type not in files.IMAGES:
        raise AppError(404, "file_not_found")
    return info


def _data_uri(db: Session, sha: str | None) -> str | None:
    if not sha:
        return None
    try:
        info = image(db, sha)
        return f"data:{info.content_type};base64," + base64.b64encode(files.read(db, info)).decode("ascii")
    except AppError:
        return None  # a missing image prints nothing rather than failing the printout


# ------------------------------------------------------------------ resolution


def _group_names(db: Session, t: dict) -> tuple[str, str]:
    from app.modules.org import service as org

    display = org.get_section(db, "branding").display_name
    return t["header"]["name_ar"] or display, t["header"]["name_en"] or display


def identity_of(db: Session, company: Company | None, template: dict) -> dict:
    """The header's values: the company's, or the group's when the printout spans companies."""
    if company is None:
        ar, en = _group_names(db, template)
        blank = {k: "" for k in HEADER_VARIABLES}
        return blank | {"company": ar, "company_en": en}
    names = company.name or {}
    ar = names.get("ar") or next(iter(names.values()), "")
    return {
        "company": template["header"]["name_ar"] or ar,
        "company_en": template["header"]["name_en"] or names.get("en") or ar,
        "cr_number": company.cr_number or "",
        "license_number": company.license_number or "",
        "pam_file_number": company.pam_file_number or "",
        "phone": company.phone or "",
        "address": company.address or "",
    }


def template_for(config: dict, company_id: int | None) -> dict:
    return (config["companies"].get(str(company_id)) if company_id else None) or config["default"]


def layout(db: Session, company_id: int | None, *, all_companies: bool, company_ids: Iterable[int]) -> dict:
    """What a printout needs: the template in force for that company (its override, else the default), the identity
    for its header, and its images inline (they print without another request)."""
    version, config = current(db)
    company = _company(db, company_id, all_companies, company_ids) if company_id else None
    t = template_for(config, company_id)
    return {
        "config_version": version,
        "company_id": company_id,
        "template": t,
        "identity": identity_of(db, company, t),
        "images": {"logo": _data_uri(db, t["header"]["logo"]), "watermark": _data_uri(db, t["watermark"]["image"])},
    }


def fill(text_: str, values: dict) -> str:
    """Variables replaced; an empty value leaves nothing (and a line left with only its label is dropped by the
    printout)."""
    return VARIABLE.sub(lambda m: str(values.get(m.group(1), "")), text_)
