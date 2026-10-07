import json
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import sheets
from app.core.clock import KUWAIT
from app.core.db import get_session
from app.modules.audit import service
from app.modules.audit.schemas import AuditEventOut, AuditUserOut
from app.modules.i18n import service as i18n
from app.modules.identity import service as identity
from app.modules.identity.service import Principal, require_permission
from app.modules.org import service as org

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNS = ("occurred_at", "actor", "action", "entity_type", "entity_id", "company", "ip", "before", "after")


def _filters(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    principal: Principal = Depends(require_permission("audit.view")),
    db: Session = Depends(get_session),
) -> dict:
    """By record type, record, action, who acted and Kuwait days (BRD FR-AUD-03), within the user's companies."""
    return {
        **principal.scope,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "actor_user_id": identity.user_id(db, actor_id) if actor_id else None,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("", response_model=list[AuditEventOut])
def list_audit(
    filters: dict = Depends(_filters),
    before_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_session),
):
    events = service.list_events(db, before_id=before_id, limit=limit, **filters)
    names = identity.user_names(db, (e.actor_user_id for e in events))
    return [
        AuditEventOut.model_validate(e).model_copy(update={"actor_name": names.get(e.actor_user_id)}) for e in events
    ]


@router.get("/users", response_model=list[AuditUserOut])
def audit_users(_: Principal = Depends(require_permission("audit.view")), db: Session = Depends(get_session)):
    return identity.user_options(db)


@router.get("/export")
def export_audit(
    filters: dict = Depends(_filters),
    format: Literal["xlsx", "csv"] = "xlsx",
    accept_language: str | None = Header(None),
    principal: Principal = Depends(require_permission("audit.export")),
    db: Session = Depends(get_session),
):
    """The matching events as Excel in the user's language, or CSV with the column keys for other systems."""
    events = service.export_events(db, **filters)
    lang = i18n.negotiate(db, principal.locale, accept_language)
    names = identity.user_names(db, (e.actor_user_id for e in events))
    companies = {c["id"]: c["name"] for c in org.list_companies(db, all_companies=True, company_ids=())}
    default = i18n.default_language(db).code

    def text(key: str, fallback: str) -> str:
        value = i18n.t(db, lang, key)
        return fallback if value == key else value

    def company(cid):
        name = companies.get(cid)
        return "" if not name else name.get(lang) or name.get(default) or next(iter(name.values()), "")

    def actor(e) -> str:
        if e.actor_user_id:
            return names.get(e.actor_user_id, f"#{e.actor_user_id}")
        return text(f"audit_actor.{e.actor_type}", e.actor_type)

    def as_json(value) -> str:
        return "" if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)

    rows = [
        [
            e.occurred_at.astimezone(KUWAIT).strftime("%Y-%m-%d %H:%M:%S"),
            actor(e),
            e.action,
            e.entity_type if format == "csv" else text(f"audit_entity.{e.entity_type}", e.entity_type),
            e.entity_id or "",
            company(e.company_id) if e.company_id else "",
            e.ip or "",
            as_json(e.before),
            as_json(e.after),
        ]
        for e in events
    ]
    if format == "csv":
        body, media = sheets.to_csv(list(COLUMNS), rows), "text/csv; charset=utf-8"
    else:
        header = [text(f"audit_column.{c}", c) for c in COLUMNS]
        body = sheets.to_xlsx(text("audit_column.title", "audit"), header, rows, rtl=lang == "ar", text_columns=(4, 6))
        media = XLSX
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="audit.{format}"'})
