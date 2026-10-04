import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.identity.service import Principal, get_principal, require_permission
from app.modules.org import schemas, service

router = APIRouter(prefix="/api/v1", tags=["org"])


def _scope(p: Principal) -> dict:
    return {"all_branches": p.sees_all_branches, "branch_ids": p.branch_ids}


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
    principal: Principal = Depends(require_permission("settings.manage")),
    db: Session = Depends(get_session),
):
    version, value = service.update_section(
        db, section, body.value, expected_version=body.version, actor_user_id=principal.user_id
    )
    return schemas.SettingOut(version=version, value=value.model_dump(mode="json"))


@router.get("/companies", response_model=list[schemas.CompanyOut])
def list_companies(_: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return [
        schemas.CompanyOut(public_id=str(c.public_id), name_ar=c.name_ar, name_en=c.name_en, is_active=c.is_active)
        for c in service.list_companies(db)
    ]


@router.post("/companies", response_model=schemas.CompanyOut, status_code=201)
def create_company(
    body: schemas.CompanyIn,
    principal: Principal = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_session),
):
    c = service.create_company(db, name_ar=body.name_ar, name_en=body.name_en, actor_user_id=principal.user_id)
    return schemas.CompanyOut(public_id=str(c.public_id), name_ar=c.name_ar, name_en=c.name_en, is_active=c.is_active)


@router.get("/branches", response_model=list[schemas.BranchOut])
def list_branches(principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return service.list_branches(db, **_scope(principal))


@router.get("/branches/{public_id}", response_model=schemas.BranchOut)
def get_branch(public_id: uuid.UUID, principal: Principal = Depends(get_principal), db: Session = Depends(get_session)):
    return service.get_branch(db, public_id, **_scope(principal))


@router.post("/branches", response_model=schemas.BranchOut, status_code=201)
def create_branch(
    body: schemas.BranchIn,
    principal: Principal = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_session),
):
    return service.create_branch(db, **body.model_dump(), actor_user_id=principal.user_id)


@router.patch("/branches/{public_id}", response_model=schemas.BranchOut)
def update_branch(
    public_id: uuid.UUID,
    body: schemas.BranchUpdateIn,
    principal: Principal = Depends(require_permission("branches.manage")),
    db: Session = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    version = changes.pop("version")
    return service.update_branch(
        db, public_id, version=version, changes=changes, actor_user_id=principal.user_id, **_scope(principal)
    )
