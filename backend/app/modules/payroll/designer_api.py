"""The rules designer's calls: a platform's input fields, the month review (values, exceptions, imports), the rule
catalog and templates, and trying a block list on sample figures."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.files import service as files
from app.modules.identity.service import Principal, require_permission
from app.modules.payroll import designer_schemas as schemas
from app.modules.payroll import forms, month_import
from app.modules.payroll import month as months

router = APIRouter(prefix="/api/v1/payroll", tags=["payroll rules"])


# ------------------------------------------------------------------ a platform's fields


@router.get("/platforms/{platform_id}/fields")
def platform_fields(
    platform_id: int, _: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return forms.get(db, platform_id)


@router.put("/platforms/{platform_id}/fields")
def set_platform_fields(
    platform_id: int,
    body: schemas.FieldsIn,
    principal: Principal = Depends(require_permission("settings.update")),
    db: Session = Depends(get_session),
):
    data = body.model_dump(mode="json")
    version = data.pop("version")
    return forms.save(db, platform_id, data, version=version, actor_user_id=principal.user_id)


# ------------------------------------------------------------------ the month review


@router.get("/month-review")
def month_review(
    platform_id: int,
    month: date,
    principal: Principal = Depends(require_permission("payroll.view")),
    db: Session = Depends(get_session),
):
    return months.review(db, platform_id=platform_id, month=month, **principal.scope)


@router.put("/month-review/{employee_id}")
def set_month_values(
    employee_id: uuid.UUID,
    body: schemas.MonthValuesIn,
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    return months.set_values(
        db, employee_id, month=body.month, data=body.model_dump(), actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/month-exceptions", status_code=201)
def add_exception(
    body: schemas.ExceptionIn,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    data = body.model_dump(mode="json")
    return months.add_exception(
        db, body.employee_id, month=body.month, data=data, actor_user_id=principal.user_id, **principal.scope
    )


@router.post("/month-exceptions/{public_id}/cancel")
def cancel_exception(
    public_id: uuid.UUID,
    body: schemas.CancelIn,
    principal: Principal = Depends(require_permission("payroll.approve")),
    db: Session = Depends(get_session),
):
    return months.cancel_exception(db, public_id, note=body.note, actor_user_id=principal.user_id, **principal.scope)


# ------------------------------------------------------------------ the month from Excel

Format = Literal["partner_batches", "generic"]


@router.post("/month-imports/check")
def check_import(
    file: UploadFile,
    platform_id: int = Form(...),
    month_: date = Form(..., alias="month"),
    format: Format = Form("partner_batches"),
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    """What the file would change, before anything is applied."""
    data = files.read_upload(file)
    return month_import.check(db, platform_id=platform_id, month_=month_, fmt=format, data=data, **principal.scope)


@router.post("/month-imports", status_code=201)
def apply_import(
    file: UploadFile,
    platform_id: int = Form(...),
    month_: date = Form(..., alias="month"),
    format: Format = Form("partner_batches"),
    principal: Principal = Depends(require_permission("payroll.prepare")),
    db: Session = Depends(get_session),
):
    data = files.read_upload(file)
    return month_import.apply(
        db,
        platform_id=platform_id,
        month_=month_,
        fmt=format,
        data=data,
        file_name=file.filename,
        actor_user_id=principal.user_id,
        **principal.scope,
    )


@router.get("/month-imports/template")
def import_template(
    platform_id: int, _: Principal = Depends(require_permission("payroll.view")), db: Session = Depends(get_session)
):
    return Response(
        month_import.template(db, platform_id),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="month-template-{platform_id}.xlsx"'},
    )
