from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.i18n import schemas, service
from app.modules.identity.service import Principal, require_permission

router = APIRouter(prefix="/api/v1/i18n", tags=["i18n"])
manage = require_permission("i18n.manage")


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
