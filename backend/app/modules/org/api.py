import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, get_principal, require_permission
from app.modules.org import schemas, service

router = APIRouter(prefix="/api/v1", tags=["org"])


@router.get("/branding", response_model=schemas.BrandingOut)
def branding(db: Session = Depends(get_session)):
    """Public: the sign-in page shows the installation's name before anyone signs in."""
    b = service.get_section(db, "branding")
    return schemas.BrandingOut(display_name=b.display_name, primary_color=b.primary_color)


@router.get("/settings", response_model=dict[str, schemas.SettingOut])
def get_settings(_: Principal = Depends(require_permission("settings.view")), db: Session = Depends(get_session)):
    return {
        name: schemas.SettingOut(version=v, value=m.model_dump(mode="json"))
        for name, (v, m) in service.all_sections(db).items()
    }


@router.put("/settings/{section}", response_model=schemas.SettingOut)
def put_settings(
    section: str,
    body: schemas.SettingIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    version, value = service.update_section(
        db, section, body.value, expected_version=body.version, actor_user_id=principal.user_id
    )
    return schemas.SettingOut(version=version, value=value.model_dump(mode="json"))


# ---- companies: the legal entities employees and vehicles belong to


@router.get("/companies/options", response_model=list[schemas.CompanyOption])
def company_options(principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    """Names only, for the company drop-downs of other screens."""
    return service.list_companies(db, **principal.scope)


@router.get("/companies", response_model=list[schemas.CompanyOut])
def list_companies(
    principal: Principal = Depends(require_permission("companies.view")), db: Session = Depends(get_session)
):
    return service.list_companies(db, **principal.scope)


@router.get("/companies/{public_id}", response_model=schemas.CompanyOut)
def get_company(
    public_id: uuid.UUID,
    principal: Principal = Depends(require_permission("companies.view")),
    db: Session = Depends(get_session),
):
    return service.get_company(db, public_id, **principal.scope)


@router.post("/companies", response_model=schemas.CompanyOut, status_code=201)
def create_company(
    body: schemas.CompanyIn,
    principal: Principal = Depends(require_permission("companies.create")),
    db: Session = Depends(get_session),
):
    return service.create_company(
        db, body.model_dump(), all_companies=principal.sees_all_companies, actor_user_id=principal.user_id
    )


@router.patch("/companies/{public_id}", response_model=schemas.CompanyOut)
def update_company(
    public_id: uuid.UUID,
    body: schemas.CompanyUpdateIn,
    principal: Principal = Depends(require_permission("companies.update")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_company(
        db, public_id, version=version, changes=changes, actor_user_id=principal.user_id, **principal.scope
    )


# ---- branches: operational locations, visible to everyone signed in


@router.get("/branches", response_model=list[schemas.BranchOut])
def list_branches(_: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return service.list_branches(db)


@router.post("/branches", response_model=schemas.BranchOut, status_code=201)
def create_branch(
    body: schemas.BranchIn,
    principal: Principal = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_session),
):
    return service.create_branch(db, name=body.name, actor_user_id=principal.user_id)


@router.patch("/branches/{public_id}", response_model=schemas.BranchOut)
def update_branch(
    public_id: uuid.UUID,
    body: schemas.BranchUpdateIn,
    principal: Principal = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_branch(db, public_id, version=version, changes=changes, actor_user_id=principal.user_id)
