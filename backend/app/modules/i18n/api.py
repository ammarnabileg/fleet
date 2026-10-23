import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_session
from app.modules.i18n import schemas, service
from app.modules.identity.service import Principal, require_device, require_permission

router = APIRouter(prefix="/api/v1/i18n", tags=["i18n"])
driver_router = APIRouter(prefix="/api/v1/driver", tags=["i18n"])
manage = require_permission("i18n.manage")
view_texts = require_permission("settings.view")
edit_texts = require_permission("settings.update")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---- the driver app: its languages and strings, also before sign-in


def _device_or_limited(request: Request, db: Session = Depends(get_session)) -> None:
    """A signed-in phone is not counted; before sign-in the address is (like the other public routes)."""
    if request.headers.get("authorization"):
        require_device(request, db)
    else:
        ratelimit.hit("public_texts")


@driver_router.get("/languages", response_model=list[schemas.DriverLanguageOut])
def driver_languages(db: Session = Depends(get_session)):
    return service.driver_languages(db)


@driver_router.get("/translations/manifest", dependencies=[Depends(_device_or_limited)])
def driver_translations_manifest(request: Request, db: Session = Depends(get_session)):
    """The enabled languages and their latest published bundle (version, sha256). Polled by the app after its first
    screen: an unchanged manifest answers 304 to If-None-Match."""
    body = service.manifest(db)
    etag = 'W/"' + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(body, headers=headers)


@driver_router.get("/translations/bundle/{lang}/{version}", dependencies=[Depends(_device_or_limited)])
def driver_translation_bundle(lang: str, version: int, db: Session = Depends(get_session)):
    """A published bundle, byte for byte as published (the manifest's sha256 is of these bytes). Immutable."""
    body = service.bundle_body(db, lang, version)
    return Response(
        body.encode(), media_type="application/json", headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )


@driver_router.get("/translations", dependencies=[Depends(_device_or_limited)])
def driver_translations(
    lang: Annotated[str, Query(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")],
    version: Annotated[int | None, Query(ge=0)] = None,
    db: Session = Depends(get_session),
):
    """{lang, version, dir, strings} of the app's texts, or {lang, version, dir, unchanged: true} when the app's copy
    is the current version. Only text: the app checks each string again and keeps its own on any doubt."""
    return service.for_driver(db, lang, version)


# ---- the dashboard: languages and the drivers' translations (settings.view to see, settings.update to edit)


@router.get("/translations/languages")
def translation_languages(_: Principal = Depends(view_texts), db: Session = Depends(get_session)):
    return service.admin_languages(db)


@router.patch("/translations/languages/{code}")
def toggle_language(
    code: str,
    body: schemas.LanguageToggleIn,
    principal: Principal = Depends(edit_texts),
    db: Session = Depends(get_session),
):
    return service.update_language(
        db, principal.user_id, code, version=body.version, changes={"is_active": body.is_active}
    )


@router.get("/translations/{lang}", response_model=list[schemas.TranslationRowOut])
def translation_rows(
    lang: str,
    scope: Literal["app", "server", "status_templates"] | None = None,
    status: Literal["needs_review", "reviewed", "machine", "missing"] | None = None,
    q: str | None = None,
    _: Principal = Depends(view_texts),
    db: Session = Depends(get_session),
):
    return service.table(db, lang, scope=scope, status=status, query=q)


@router.put("/translations/{lang}")
def save_translations(
    lang: str,
    body: schemas.TranslationsIn,
    principal: Principal = Depends(edit_texts),
    db: Session = Depends(get_session),
):
    return service.save(db, principal.user_id, lang, [i.model_dump() for i in body.items])


@router.post("/translations/{lang}/review")
def review_translations(
    lang: str, body: schemas.ReviewIn, principal: Principal = Depends(edit_texts), db: Session = Depends(get_session)
):
    return service.review(db, principal.user_id, lang, [i.model_dump() for i in body.items])


@router.delete("/translations/{lang}/{scope}/{key}")
def revert_translation(
    lang: str, scope: str, key: str, principal: Principal = Depends(edit_texts), db: Session = Depends(get_session)
):
    return service.revert(db, principal.user_id, lang, scope, key)


@router.post("/translations/{lang}/publish")
def publish_translations(lang: str, principal: Principal = Depends(edit_texts), db: Session = Depends(get_session)):
    """The drafts become a new published version of the language: the next manifest the apps fetch names it."""
    return service.publish(db, principal.user_id, lang)


@router.get("/translations/{lang}/export")
def export_translations(lang: str, _: Principal = Depends(view_texts), db: Session = Depends(get_session)):
    body = service.export_xlsx(db, lang)
    return Response(
        body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="translations-{lang}.xlsx"'}
    )


@router.post("/translations/{lang}/import")
def import_translations(
    lang: str,
    file: UploadFile,
    reviewed: bool = False,
    principal: Principal = Depends(edit_texts),
    db: Session = Depends(get_session),
):
    data = file.file.read(5 * 1024 * 1024 + 1)
    return service.import_xlsx(db, principal.user_id, lang, data, reviewed=reviewed)


# ---- public: the sign-in page needs its texts before anyone signs in


@router.get("/languages", response_model=list[schemas.LanguageOut])
def languages(db: Session = Depends(get_session)):
    return service.list_languages(db)


@router.get("/catalog/{lang}", response_model=schemas.CatalogOut)
def catalog(
    lang: str,
    request: Request,
    response: Response,
    ns: str | None = Query(None, description="a,b,c"),
    db: Session = Depends(get_session),
):
    language = service.get_language(db, lang)
    namespaces = sorted({n.strip() for n in ns.split(",") if n.strip()}) if ns else None
    rev = service.revision(db)
    etag = f'W/"{lang}-{rev}-{",".join(namespaces or ["*"])}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"
    return schemas.CatalogOut(
        lang=lang, direction=language.direction, revision=rev, messages=service.catalog_for(db, lang, namespaces)
    )


# ---- administration


@router.get("/admin/languages", response_model=list[schemas.LanguageAdminOut])
def all_languages(_: Principal = Depends(manage), db: Session = Depends(get_session)):
    return service.list_languages(db, active_only=False)


@router.post("/admin/languages", response_model=schemas.LanguageAdminOut, status_code=201)
def add_language(body: schemas.LanguageIn, principal: Principal = Depends(manage), db: Session = Depends(get_session)):
    return service.add_language(db, principal.user_id, **body.model_dump())


@router.patch("/admin/languages/{code}", response_model=schemas.LanguageAdminOut)
def update_language(
    code: str,
    body: schemas.LanguageUpdateIn,
    principal: Principal = Depends(manage),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_language(db, principal.user_id, code, version=version, changes=changes)


@router.get("/admin/entries/{lang}", response_model=list[schemas.EntryOut])
def entries(
    lang: str,
    namespace: str | None = None,
    missing: bool = False,
    q: str | None = None,
    _: Principal = Depends(manage),
    db: Session = Depends(get_session),
):
    return service.entries(db, lang, namespace=namespace, missing_only=missing, query=q)


@router.put("/admin/overrides/{lang}")
def save_overrides(
    lang: str, body: schemas.OverridesIn, principal: Principal = Depends(manage), db: Session = Depends(get_session)
):
    saved = service.save_overrides(db, principal.user_id, lang, [i.model_dump() for i in body.items])
    return {"saved": saved, "revision": service.revision(db)}


@router.delete("/admin/overrides/{lang}/{namespace}/{key}", status_code=204)
def delete_override(
    lang: str, namespace: str, key: str, principal: Principal = Depends(manage), db: Session = Depends(get_session)
):
    service.delete_override(db, principal.user_id, lang, namespace, key)


@router.get("/admin/export/{lang}")
def export(lang: str, _: Principal = Depends(manage), db: Session = Depends(get_session)):
    return service.effective_catalog(db, lang, active_only=False)  # also while a new language is still inactive


@router.post("/admin/import/{lang}")
def import_catalog(
    lang: str,
    body: dict[str, dict[str, str]],
    principal: Principal = Depends(manage),
    db: Session = Depends(get_session),
):
    return {"saved": service.import_catalog(db, principal.user_id, lang, body), "revision": service.revision(db)}
