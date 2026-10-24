"""The office's own roles and their permissions in a transfer file, by code. The system's role templates come with
every installation and are not exported; neither are the users (people, with passwords)."""

import re

from sqlalchemy import delete, select

from app.core.errors import AppError
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each, same
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.identity.models import Role, RolePermission, User
from app.modules.identity.schemas import CODE
from app.modules.identity.service import ALL_PERMISSIONS


def _perms(db, role: Role) -> list[str]:
    return sorted(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id)))


def _export(ctx: ExportContext) -> list[dict]:
    rows = ctx.db.scalars(select(Role).where(Role.is_system.is_(False)).order_by(Role.code))
    return [{"code": r.code, "name": r.name, "permissions": _perms(ctx.db, r)} for r in rows]


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db

    def one(item):
        code = item["code"]
        if not isinstance(code, str) or not re.match(CODE, code):
            raise AppError(422, "config_item_invalid", field="code", detail=str(code))
        name = i18n.validate_localized(db, item["name"])
        wanted = set(item.get("permissions") or [])
        unknown = sorted(wanted - ALL_PERMISSIONS)
        if unknown:  # a permission of a newer installation: left out, said in the report
            report.warn(code, "config_permissions_unknown", codes=", ".join(unknown))
        wanted = sorted(wanted & ALL_PERMISSIONS)
        role = db.scalar(select(Role).where(Role.code == code).with_for_update())
        if role is not None and (role.is_system or role.all_permissions):
            raise AppError(403, "system_role")
        if role is None:
            role = Role(code=code, name=name, all_permissions=False)
            db.add(role)
            db.flush()
            db.add_all([RolePermission(role_id=role.id, permission=p) for p in wanted])
            outcome = CREATED
        else:
            if same(role.name, name) and _perms(db, role) == wanted:
                return UNCHANGED
            role.name = name
            db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            db.add_all([RolePermission(role_id=role.id, permission=p) for p in wanted])
            role.version += 1
            outcome = UPDATED
        db.flush()
        audit.record(
            db,
            action="role.created" if outcome == CREATED else "role.updated",
            entity_type="role",
            entity_id=code,
            actor_user_id=ctx.actor_user_id,
            after={"code": code, "name": name, "permissions": wanted},
            comment="config import",
        )
        return outcome

    each(db, report, data, lambda i: i.get("code"), one)


def usernames(db, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    return dict(db.execute(select(User.id, User.username).where(User.id.in_(ids)))) if ids else {}


def user_id_by_username(db, username: str) -> int:
    from sqlalchemy import func

    found = db.scalar(select(User.id).where(func.lower(User.username) == str(username).lower()))
    if found is None:
        raise AppError(422, "config_user_missing", username=username)
    return found


SECTIONS_OUT = [
    Section("roles", {"ar": "الأدوار والصلاحيات", "en": "Roles and permissions"}, _export, _apply, order=30)
]
