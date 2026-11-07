import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_session
from app.core.errors import AppError
from app.modules.app_updates import service as app_updates
from app.modules.files import service as files
from app.modules.identity.service import Principal, require_permission
from app.modules.org import site

router = APIRouter(prefix="/api/v1", tags=["site"])

Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class ContactIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    phone: Line = ""
    email: Line = ""
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=3000)]
    website: str = ""  # a field people never see: a bot that fills it is thanked and ignored


class StatusIn(BaseModel):
    status: Literal["new", "read", "done"]


# ------------------------------------------------------------------ public: the site on the main domain


@router.get("/site")
def content(db: Session = Depends(get_session)):
    """Public: what the company's site shows, in every language, and whether the app can be downloaded."""
    return site.public_content(db, download=app_updates.download_info(db)["release"] is not None)


@router.get("/site/logo/{sha256}")
def logo(sha256: str, db: Session = Depends(get_session)):
    return files.response(db, site.logo(db, sha256), headers={"Cache-Control": "public, max-age=86400"})


@router.post("/site/contact", status_code=204)
def contact(body: ContactIn, request: Request, db: Session = Depends(get_session)):
    """Public, limited per address: a message from the contact form, for the office."""
    ratelimit.hit("contact")
    if body.website:
        return None
    if not (body.phone or body.email):
        raise AppError(422, "contact_needed")
    lang = request.headers.get("accept-language", "").split(",")[0].split("-")[0].strip()[:5] or None
    site.send_message(db, name=body.name, phone=body.phone, email=body.email, message=body.message, lang=lang)
    return None


# ------------------------------------------------------------------ the panel


@router.get("/site/messages")
def messages(
    status: Literal["new", "read", "done"] | None = None,
    _: Principal = Depends(require_permission("settings.view")),
    db: Session = Depends(get_session),
):
    return {"items": site.list_messages(db, status), "counts": site.counts(db)}


@router.post("/site/messages/{public_id}/status")
def set_status(
    public_id: uuid.UUID,
    body: StatusIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return site.set_status(db, public_id, body.status, actor_user_id=principal.user_id)
