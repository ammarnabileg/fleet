"""The languages and their published texts in a transfer file. A language is known by its code; a text by its scope
and key. Only what the drivers and the office see is exported: the texts of each language's latest published version
that differ from the shipped ones (drafts not yet published stay behind). An import saves them as reviewed and
publishes the language again (a new version the apps download)."""

import json

from sqlalchemy import select, update

from app.core.errors import AppError
from app.core.transfer import CREATED, UNCHANGED, UPDATED, ExportContext, ImportContext, Report, Section, each
from app.modules.audit import service as audit
from app.modules.i18n import store
from app.modules.i18n.models import Language, State, Translation
from app.modules.i18n.schemas import LanguageIn
from app.modules.i18n.service import _validate_fallback

FIELDS = ("name_native", "name_en", "direction", "is_active", "sort_order")


def _export(ctx: ExportContext) -> dict:
    db = ctx.db
    langs = list(db.scalars(select(Language).order_by(Language.sort_order, Language.code)))
    texts = {}
    for lang in langs:
        bundle = store.latest(db, lang.code)
        if bundle is None:
            continue
        base = store.base_texts("app", lang.code)
        app = {k: v for k, v in json.loads(bundle.body)["strings"].items() if base.get(k) != v}
        scopes = {"app": app} | {sc: dict(bundle.overrides.get(sc, {})) for sc in ("server", "status_templates")}
        scopes = {sc: dict(sorted(v.items())) for sc, v in scopes.items() if v}
        if scopes:
            texts[lang.code] = scopes
    return {
        "languages": [
            {"code": x.code, "fallback_code": x.fallback_code, "is_default": x.is_default}
            | {f: getattr(x, f) for f in FIELDS}
            for x in langs
        ],
        "texts": texts,
    }


def _apply(ctx: ImportContext, data, report: Report) -> None:
    db = ctx.db
    if not isinstance(data, dict):
        report.skip("*", "config_section_invalid")
        return
    items = data.get("languages") or []
    changed_langs: set[str] = set()

    def one(item):
        clean = LanguageIn.model_validate(
            {k: item.get(k) for k in ("code", "name_native", "name_en", "direction", "sort_order")}
        ).model_dump()
        active = bool(item.get("is_active", True)) or clean["code"] in store.REQUIRED or bool(item.get("is_default"))
        lang = db.get(Language, clean["code"], with_for_update=True)
        values = {k: clean[k] for k in ("name_native", "name_en", "direction", "sort_order")} | {"is_active": active}
        if lang is None:
            db.add(Language(code=clean["code"], is_default=False, version=1, **values))
            db.flush()
            outcome = CREATED
        else:
            if lang.is_default and not active:
                raise AppError(422, "cannot_deactivate_default")
            if all(getattr(lang, k) == v for k, v in values.items()):
                outcome = UNCHANGED
            else:
                for k, v in values.items():
                    setattr(lang, k, v)
                lang.version += 1
                outcome = UPDATED
        if item.get("is_default"):
            lang = db.get(Language, clean["code"])
            if not lang.is_default:
                db.execute(update(Language).where(Language.is_default.is_(True)).values(is_default=False))
                db.flush()
                lang.is_default, lang.is_active = True, True
                lang.version += 1
                outcome = UPDATED if outcome == UNCHANGED else outcome
        db.flush()
        if outcome != UNCHANGED:
            changed_langs.add(clean["code"])
        return outcome

    each(db, report, items, lambda i: i.get("code"), one)

    def fallback(item):  # once every language is there: a fallback may name one created above
        lang = db.get(Language, item.get("code"))
        if lang is None or lang.fallback_code == item.get("fallback_code"):
            return UNCHANGED
        _validate_fallback(db, lang.code, item.get("fallback_code"))
        lang.fallback_code = item.get("fallback_code")
        lang.version += 1
        db.flush()
        changed_langs.add(lang.code)
        return UPDATED

    sub = Report()
    each(db, sub, items, lambda i: f"{i.get('code')}:fallback", fallback)
    report.updated += sub.updated
    report.skipped += sub.skipped

    texts = data.get("texts") or {}
    for code, scopes in sorted(texts.items()) if isinstance(texts, dict) else []:
        _apply_texts(ctx, code, scopes, report, changed_langs)
    if changed_langs:
        db.execute(update(State).values(revision=State.revision + 1))
        audit.record(
            db,
            action="language.updated",
            entity_type="language",
            entity_id=",".join(sorted(changed_langs)),
            actor_user_id=ctx.actor_user_id,
            after={"import": sorted(changed_langs)},
            comment="config import",
        )


def _apply_texts(ctx: ImportContext, code: str, scopes, report: Report, changed_langs: set[str]) -> None:
    db = ctx.db
    lang = db.get(Language, code)
    if lang is None:
        report.skip(f"{code}:texts", "unknown_language", code=code)
        return
    rows = {(r.scope, r.key): r for r in db.scalars(select(Translation).where(Translation.lang == code))}
    items = [(sc, k, v) for sc, entries in (scopes or {}).items() for k, v in (entries or {}).items()]
    bundle = store.latest(db, code)
    in_force = {
        "app": json.loads(bundle.body)["strings"] if bundle else store.base_texts("app", code),
        "server": store.base_texts("server", code) | store.overrides_in_force(db, code, "server"),
        "status_templates": store.base_texts("status_templates", code)
        | store.overrides_in_force(db, code, "status_templates"),
    }
    publish = False

    def one(item):
        nonlocal publish
        scope, key, text = item
        if not isinstance(text, str):
            raise AppError(422, "config_item_invalid", field=f"{scope}:{key}", detail="text")
        store._check(scope, key, text)
        row = rows.get((scope, key))
        draft = row.text if row is not None else store.base_texts(scope, code).get(key)
        if draft == text and in_force[scope].get(key) == text:
            return UNCHANGED
        if row is None or row.text != text or row.status != "reviewed":
            store._upsert(db, scope, key, code, text, "reviewed", ctx.actor_user_id)
        publish = True
        return CREATED if row is None else UPDATED

    each(db, report, items, lambda i: f"{code}:{i[0]}:{i[1]}", one)
    if publish:
        store.publish(db, ctx.actor_user_id, code, commit=False)
        changed_langs.add(code)


SECTIONS_OUT = [
    Section(
        "languages",
        {"ar": "اللغات والترجمات المنشورة", "en": "Languages and published translations"},
        _export,
        _apply,
        order=10,
    )
]
