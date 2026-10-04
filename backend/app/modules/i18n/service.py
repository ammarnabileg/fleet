"""Languages and translations.

Effective text for a language = base catalog shipped with the code (catalog/<lang>.json) overlaid with the
overrides saved from the settings screen, following the language's fallback chain down to the default
language. A new language (e.g. Urdu for drivers) can be added and translated without a deploy.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n.models import Language, Override, State

CATALOG_DIR = Path(__file__).parent / "catalog"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
MAX_CHAIN = 5

_effective_cache: dict[tuple[str, int], dict[str, dict[str, str]]] = {}


# ------------------------------------------------------------------ base catalogs (code)


@lru_cache
def base_catalog(lang: str) -> dict[str, dict[str, str]]:
    path = CATALOG_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@lru_cache
def base_keys() -> frozenset[tuple[str, str]]:
    """Every key the application knows. Translators can change texts, not invent keys."""
    keys: set[tuple[str, str]] = set()
    for path in CATALOG_DIR.glob("*.json"):
        for ns, entries in base_catalog(path.stem).items():
            keys.update((ns, k) for k in entries)
    return frozenset(keys)


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


# ------------------------------------------------------------------ languages


def revision(db: Session) -> int:
    return db.scalar(select(State.revision))


def _bump(db: Session) -> None:
    db.execute(update(State).values(revision=State.revision + 1))


def list_languages(db: Session, *, active_only: bool = True) -> list[Language]:
    q = select(Language).order_by(Language.sort_order, Language.code)
    if active_only:
        q = q.where(Language.is_active.is_(True))
    return list(db.scalars(q))


def default_language(db: Session) -> Language:
    return db.scalar(select(Language).where(Language.is_default.is_(True)))


def get_language(db: Session, code: str, *, active_only: bool = True) -> Language:
    lang = db.get(Language, code)
    if lang is None or (active_only and not lang.is_active):
        raise AppError(404, "unknown_language", code=code)
    return lang


def _chain(db: Session, lang: Language) -> list[str]:
    """[lang, its fallback, its fallback's fallback, ..., default]: highest priority first."""
    chain, current = [lang.code], lang
    while current.fallback_code and len(chain) < MAX_CHAIN and current.fallback_code not in chain:
        current = db.get(Language, current.fallback_code)
        chain.append(current.code)
    default = default_language(db).code
    if default not in chain:
        chain.append(default)
    return chain


def _validate_fallback(db: Session, code: str, fallback: str | None) -> None:
    if fallback is None:
        return
    seen, current = {code}, fallback
    while current:
        if current in seen:
            raise AppError(422, "invalid_fallback")
        lang = db.get(Language, current)
        if lang is None or not lang.is_active:
            raise AppError(422, "invalid_fallback")
        seen.add(current)
        current = lang.fallback_code


def _language_snapshot(lang: Language) -> dict:
    return {
        "code": lang.code,
        "name_native": lang.name_native,
        "name_en": lang.name_en,
        "direction": lang.direction,
        "fallback_code": lang.fallback_code,
        "is_default": lang.is_default,
        "is_active": lang.is_active,
        "sort_order": lang.sort_order,
        "version": lang.version,
    }


def add_language(
    db: Session,
    actor_user_id: int,
    *,
    code: str,
    name_native: str,
    name_en: str,
    direction: str,
    fallback_code: str | None,
    sort_order: int,
) -> dict:
    if db.get(Language, code):
        raise AppError(409, "language_exists")
    _validate_fallback(db, code, fallback_code)
    lang = Language(
        code=code,
        name_native=name_native,
        name_en=name_en,
        direction=direction,
        fallback_code=fallback_code,
        sort_order=sort_order,
        is_active=True,
        is_default=False,
        version=1,
    )
    db.add(lang)
    db.flush()
    snapshot = _language_snapshot(lang)
    audit.record(
        db, action="language.added", entity_type="language", entity_id=code, actor_user_id=actor_user_id, after=snapshot
    )
    _bump(db)
    db.commit()
    return snapshot


def update_language(db: Session, actor_user_id: int, code: str, *, version: int, changes: dict) -> dict:
    lang = get_language(db, code, active_only=False)
    if lang.version != version:
        raise AppError(409, "version_conflict")
    before = _language_snapshot(lang)
    if changes.get("is_active") is False and (lang.is_default or changes.get("is_default")):
        raise AppError(422, "cannot_deactivate_default")
    if changes.get("is_default") is False and lang.is_default:
        raise AppError(422, "cannot_deactivate_default")  # choose another language as default instead
    if "fallback_code" in changes:
        _validate_fallback(db, code, changes["fallback_code"])
    if changes.get("is_default") and not lang.is_default:
        db.execute(update(Language).where(Language.is_default.is_(True)).values(is_default=False))
        db.flush()
        lang.is_active = True
    for field in ("name_native", "name_en", "direction", "fallback_code", "is_active", "is_default", "sort_order"):
        if field in changes:
            setattr(lang, field, changes[field])
    lang.version += 1
    db.flush()
    after = _language_snapshot(lang)
    audit.record(
        db,
        action="language.updated",
        entity_type="language",
        entity_id=code,
        actor_user_id=actor_user_id,
        before=before,
        after=after,
    )
    _bump(db)
    db.commit()
    return after


# ------------------------------------------------------------------ catalogs


def _overrides(db: Session, lang: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for o in db.scalars(select(Override).where(Override.lang == lang)):
        out.setdefault(o.namespace, {})[o.key] = o.value
    return out


def effective_catalog(db: Session, code: str, *, active_only: bool = True) -> dict[str, dict[str, str]]:
    lang = get_language(db, code, active_only=active_only)
    key = (code, revision(db))
    if key not in _effective_cache:
        merged: dict[str, dict[str, str]] = {}
        for layer_code in reversed(_chain(db, lang)):  # lowest priority first
            for layer in (base_catalog(layer_code), _overrides(db, layer_code)):
                for ns, entries in layer.items():
                    merged.setdefault(ns, {}).update(entries)
        if len(_effective_cache) > 100:
            _effective_cache.clear()
        _effective_cache[key] = merged
    return _effective_cache[key]


def catalog_for(db: Session, code: str, namespaces: list[str] | None) -> dict[str, dict[str, str]]:
    catalog = effective_catalog(db, code)
    return {ns: catalog.get(ns, {}) for ns in namespaces} if namespaces else catalog


def t(db: Session, code: str, key: str, /, **params) -> str:
    """Server-side text (notifications, reports): key is "namespace.key"; unknown params stay as {name}."""
    ns, _, k = key.partition(".")
    text = effective_catalog(db, code).get(ns, {}).get(k, key)
    return PLACEHOLDER.sub(lambda m: str(params.get(m.group(1), m.group(0))), text)


def negotiate(db: Session, user_locale: str | None, accept_language: str | None) -> str:
    active = {lang.code for lang in list_languages(db)}
    if user_locale in active:
        return user_locale
    for part in sorted((accept_language or "").split(","), key=_q, reverse=True):
        tag = part.split(";")[0].strip()
        for candidate in (tag, tag.split("-")[0].lower()):
            if candidate in active:
                return candidate
    return default_language(db).code


def _q(part: str) -> float:
    for param in part.split(";")[1:]:
        name, _, value = param.strip().partition("=")
        if name == "q":
            try:
                return float(value)
            except ValueError:
                return 0.0
    return 1.0


# ------------------------------------------------------------------ editing translations


def entries(
    db: Session, code: str, *, namespace: str | None = None, missing_only: bool = False, query: str | None = None
) -> list[dict]:
    lang = get_language(db, code, active_only=False)
    default = default_language(db).code
    base, overrides = base_catalog(lang.code), _overrides(db, lang.code)
    default_effective = effective_catalog(db, default)
    rows = []
    for ns, key in sorted(base_keys()):
        if namespace and ns != namespace:
            continue
        own = overrides.get(ns, {}).get(key) or base.get(ns, {}).get(key)
        if missing_only and own:
            continue
        reference = default_effective.get(ns, {}).get(key, "")
        if query and query.lower() not in f"{ns}.{key} {reference} {own or ''}".lower():
            continue
        rows.append(
            {
                "namespace": ns,
                "key": key,
                "reference": reference,
                "base": base.get(ns, {}).get(key),
                "override": overrides.get(ns, {}).get(key),
            }
        )
    return rows


def _reference_placeholders(ns: str, key: str) -> set[str]:
    found: set[str] = set()
    for path in CATALOG_DIR.glob("*.json"):
        text = base_catalog(path.stem).get(ns, {}).get(key)
        if text:
            found |= placeholders(text)
    return found


def save_overrides(db: Session, actor_user_id: int, code: str, items: list[dict]) -> int:
    get_language(db, code, active_only=False)
    for item in items:
        ns, key, value = item["namespace"], item["key"], item["value"]
        if (ns, key) not in base_keys():
            raise AppError(422, "unknown_translation_key", key=f"{ns}.{key}")
        expected = _reference_placeholders(ns, key)
        if placeholders(value) != expected:
            raise AppError(
                422,
                "placeholder_mismatch",
                key=f"{ns}.{key}",
                placeholders=", ".join(f"{{{p}}}" for p in sorted(expected)) or "-",
            )
    for item in items:
        stmt = insert(Override).values(
            lang=code, namespace=item["namespace"], key=item["key"], value=item["value"], updated_by=actor_user_id
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["lang", "namespace", "key"],
                set_={
                    "value": stmt.excluded.value,
                    "updated_by": actor_user_id,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
    audit.record(
        db,
        action="translations.saved",
        entity_type="language",
        entity_id=code,
        actor_user_id=actor_user_id,
        after={"count": len(items), "keys": [f"{i['namespace']}.{i['key']}" for i in items[:50]]},
    )
    _bump(db)
    db.commit()
    return len(items)


def delete_override(db: Session, actor_user_id: int, code: str, namespace: str, key: str) -> None:
    row = db.get(Override, (code, namespace, key))
    if row is None:
        raise AppError(404, "unknown_translation_key", key=f"{namespace}.{key}")
    before = row.value
    db.delete(row)
    audit.record(
        db,
        action="translations.reverted",
        entity_type="language",
        entity_id=code,
        actor_user_id=actor_user_id,
        before={"key": f"{namespace}.{key}", "value": before},
    )
    _bump(db)
    db.commit()


def import_catalog(db: Session, actor_user_id: int, code: str, catalog: dict[str, dict[str, str]]) -> int:
    items = [{"namespace": ns, "key": k, "value": v} for ns, entries_ in catalog.items() for k, v in entries_.items()]
    return save_overrides(db, actor_user_id, code, items) if items else 0


# ------------------------------------------------------------------ localized names (master data)


def validate_localized(db: Session, value: dict[str, str] | None, *, required: bool = True) -> dict[str, str] | None:
    """Keys must be active languages and the default language must be present."""
    if value is None and not required:
        return None
    value = value or {}
    active = {lang.code for lang in list_languages(db)}
    unknown = sorted(set(value) - active)
    if unknown:
        raise AppError(422, "unknown_language", code=", ".join(unknown))
    default = default_language(db).code
    if not value.get(default):
        raise AppError(422, "default_language_required", code=default)
    return dict(value)


def pick(value: dict[str, str] | None, code: str, default: str) -> str:
    """The text of a localized name for display: requested language, then default, then any."""
    if not value:
        return ""
    return value.get(code) or value.get(default) or next(iter(value.values()))
