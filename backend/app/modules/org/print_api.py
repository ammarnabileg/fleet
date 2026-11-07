"""The print templates (Settings → print templates) and the layout every printout of the panel is printed in."""

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import Principal, get_principal, require_permission
from app.modules.org import printing

router = APIRouter(prefix="/api/v1", tags=["printing"])


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: dict | None  # none (a company only): the company prints with the default again
    config_version: int


class RollbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: int


@router.get("/print-templates")
def manage(_: Principal = Depends(require_permission("settings.view")), db: Session = Depends(get_session)):
    return printing.manage(db)


@router.put("/print-templates/default")
def publish_default(
    body: PublishIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return printing.publish_default(
        db, body.template or {}, expected_version=body.config_version, actor_user_id=principal.user_id
    )


@router.put("/print-templates/companies/{company_id}")
def publish_company(
    company_id: int,
    body: PublishIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return printing.publish_company(
        db,
        company_id,
        body.template,
        expected_version=body.config_version,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.post("/print-templates/rollback")
def rollback(
    body: RollbackIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return printing.rollback(db, expected_version=body.config_version, actor_user_id=principal.user_id)


@router.post("/print-templates/images", status_code=201)
def upload_image(
    file: UploadFile,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    """A logo or a watermark image: a JPEG or a PNG of at most 1 MB."""
    return printing.store_image(db, files.read_upload(file, max_mb=2), actor_user_id=principal.user_id)


@router.get("/print-templates/images/{sha256}")
def image(sha256: str, _: Principal = Depends(require_permission("settings.view")), db: Session = Depends(get_session)):
    return files.response(db, printing.image(db, sha256))


@router.get("/print/layout")
def layout(
    company_id: int | None = None, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)
):
    """Any signed-in office user who can print something (a cashier's receipt, a report): the template in force for
    that company, its header's identity and its images. No company: the group's identity."""
    return printing.layout(db, company_id, **principal.scope)
