import uuid

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import get_session
from app.modules.app_updates import schemas, service
from app.modules.files import service as files
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1", tags=["app updates"])


@router.get("/app-releases", response_model=schemas.OverviewOut)
def overview(principal: Principal = Depends(require_permission("settings.view")), db: Session = Depends(get_session)):
    """The driver app's releases, how many phones run each, and the drivers still on an older one."""
    return service.overview(db, all_companies=principal.sees_all_companies, company_ids=principal.company_ids)


@router.post("/app-releases", response_model=schemas.ReleaseOut, status_code=201)
def upload(
    file: UploadFile,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    """An APK as the CI built it: a draft until published. Its package and versionCode are read from the file."""
    ratelimit.hit("upload", f"user:{principal.user_id}")
    data = files.read_upload(file, get_settings().max_apk_mb)
    return service.upload(db, data, notes=None, actor_user_id=principal.user_id)


@router.patch("/app-releases/{public_id}", response_model=schemas.ReleaseOut)
def update(
    public_id: uuid.UUID,
    body: schemas.ReleaseUpdateIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.update(db, public_id, body.model_dump(exclude_unset=True), actor_user_id=principal.user_id)


@router.post("/app-releases/{public_id}/publish", response_model=schemas.ReleaseOut)
def publish(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.set_status(db, public_id, "published", actor_user_id=principal.user_id)


@router.post("/app-releases/{public_id}/unpublish", response_model=schemas.ReleaseOut)
def unpublish(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    return service.set_status(db, public_id, "draft", actor_user_id=principal.user_id)


@router.delete("/app-releases/{public_id}", status_code=204)
def delete(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    service.delete_draft(db, public_id, actor_user_id=principal.user_id)
    return Response(status_code=204)


@router.get("/app-releases/{public_id}/file")
def download(
    public_id: uuid.UUID,
    _: Principal = Depends(require_permission("settings.view")),
    db: Session = Depends(get_session),
):
    row, info = service.file_of(db, public_id)
    return files.response(db, info, filename=f"driver-app-{row.version_code}.apk")


# ------------------------------------------------------------------ the app: before sign-in too (the sign-in screen
# updates an app too old to sign in), limited per address like the other public driver endpoints


@router.get("/driver/app-update", response_model=schemas.UpdateCheckOut)
def check(
    request: Request,
    version_code: int = Query(..., ge=0, le=2_100_000_000),
    lang: str | None = Query(None, max_length=10),
    db: Session = Depends(get_session),
):
    ratelimit.hit("app_update")
    lang = lang or request.headers.get("accept-language", "").split(",")[0].split("-")[0].strip() or None
    return service.check(db, version_code, lang)


@router.get("/driver/app-update/{version_code}.apk")
def driver_download(version_code: int, db: Session = Depends(get_session)):
    """A published release's APK. From the server's disk a Range request gets its part, so a cut download resumes."""
    ratelimit.hit("app_update")
    info = service.published_file(db, version_code)
    return files.response(
        db, info, filename=f"driver-app-{version_code}.apk", headers={"Cache-Control": "private, max-age=86400"}
    )
