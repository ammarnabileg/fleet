"""The driver's texts by language, managed from the dashboard.

Three scopes: `app` (the driver app's strings, its arb keys), `server` (the catalog texts a driver sees: errors,
notices, maintenance stages, statement lines) and `status_templates` (the live-status cards' built-in texts).

The base text of a (scope, key, language) ships with the code: the app's strings in seed/<lang>.json (ar and en are
copies of the app's arb files, the other languages the initial translations), the server texts in catalog/<lang>.json
(ar, en) or seed/<lang>.json (the others). A row in i18n.translations is an edit made from the dashboard or a base
text marked as reviewed. Arabic and English shipped texts count as reviewed; the other languages' shipped texts need a
native speaker's review.

Edits are drafts. Publishing a language makes an immutable bundle (i18n.bundles): the app's complete strings as one
JSON document with its sha256, and the dashboard's server and status-card texts in force. languages.strings_version
names the latest published version (0: none, the shipped texts); the app and the server texts only ever see published
versions. The app polls a small manifest (ETag) and downloads a bundle only when its version is newer than its copy.
"""

import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.i18n import icu
from app.modules.i18n.models import Bundle, Language, State, Translation

SEED_DIR = Path(__file__).parent / "seed"
CATALOG_DIR = Path(__file__).parent / "catalog"
SCOPES = ("app", "server", "status_templates")
REQUIRED = ("ar", "en")  # the app's own languages: always on
# the catalog namespaces whose texts reach the driver (the app shows the server's errors as they come)
DRIVER_NAMESPACES = (
    "errors",
    "messages",
    "driver_notice",
    "maintenance_status",
    "finance_source",
    "journal_kind",
    "deduction_source",
)
MAX_ITEMS = 2000
SHEET_HEADER = ["scope", "key", "en", "translation", "status"]
BUNDLE_SCHEMA = 1  # the bundle document's shape; an app refuses a schema newer than the one it reads
MIN_APP_BUILD = 1  # the oldest app build that reads these bundles


# ------------------------------------------------------------------ base texts (code)


@lru_cache
def seed(lang: str) -> dict:
    path = SEED_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@lru_cache
def catalog_file(lang: str) -> dict[str, dict[str, str]]:
    path = CATALOG_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def base_catalog(lang: str) -> dict[str, dict[str, str]]:
    """The server catalog shipped for a language: its catalog file, or its seed's server texts."""
    return catalog_file(lang) or seed(lang).get("server", {})


@lru_cache
def base_texts(scope: str, lang: str) -> dict[str, str]:
    if scope == "server":
        catalog = base_catalog(lang)
        return {f"{ns}.{k}": v for ns in DRIVER_NAMESPACES for k, v in catalog.get(ns, {}).items()}
    return dict(seed(lang).get(scope, {}))


@lru_cache
def keys(scope: str) -> tuple[str, ...]:
    """The keys of a scope: those of the English base (Arabic for any it lacks)."""
    return tuple(sorted(base_texts(scope, "en").keys() | base_texts(scope, "ar").keys()))


def reference(scope: str, key: str) -> str | None:
    """The source text a translation must match (its arguments): English, else Arabic."""
    return base_texts(scope, "en").get(key) or base_texts(scope, "ar").get(key)


def base_status(lang: str, text: str | None) -> str:
    if not text:
        return "missing"
    return "reviewed" if lang in REQUIRED else "needs_review"


# ------------------------------------------------------------------ state


def _rows(db: Session, lang: str, scope: str | None = None) -> dict[tuple[str, str], Translation]:
    q = select(Translation).where(Translation.lang == lang)
    if scope:
        q = q.where(Translation.scope == scope)
    return {(r.scope, r.key): r for r in db.scalars(q)}


def _language(db: Session, code: str, *, active_only: bool = False) -> Language:
    lang = db.get(Language, code)
    if lang is None or (active_only and not lang.is_active):
        raise AppError(404, "unknown_language", code=code)
    return lang


def _changed(db: Session, lang: Language) -> None:  # noqa: ARG001 - a draft: nothing is published
    db.execute(update(State).values(revision=State.revision + 1))  # the server catalogs' cache


def effective(db: Session, lang: str, scope: str) -> dict[str, str]:
    """The texts of a scope in a language: the dashboard's edits over the shipped base (no fallback here)."""
    out = dict(base_texts(scope, lang))
    for (_, key), row in _rows(db, lang, scope).items():
        out[key] = row.text
    allowed = set(keys(scope))
    return {k: v for k, v in out.items() if k in allowed}


def latest(db: Session, code: str) -> Bundle | None:
    lang = db.get(Language, code)
    return db.get(Bundle, (code, lang.strings_version)) if lang and lang.strings_version else None


def overrides_in_force(db: Session, code: str, scope: str) -> dict[str, str]:
    """The dashboard's texts the drivers get: those of the latest published bundle; before the language's first
    publish, the texts saved from the old settings screen before drafts existed (migration 0063)."""
    bundle = latest(db, code)
    if bundle is not None:
        return dict(bundle.overrides.get(scope, {}))
    since = db.scalar(select(State.drafts_since))
    return {key: row.text for (_, key), row in _rows(db, code, scope).items() if row.updated_at < since}


def server_rows(db: Session, lang: str) -> dict[str, dict[str, str]]:
    """The server texts in force of a language as a catalog layer (namespace -> key -> text)."""
    out: dict[str, dict[str, str]] = {}
    for key, text in overrides_in_force(db, lang, "server").items():
        ns, _, k = key.partition(".")
        out.setdefault(ns, {})[k] = text
    return out


def table(
    db: Session, code: str, *, scope: str | None = None, status: str | None = None, query: str | None = None
) -> list[dict]:
    """The dashboard's table: every key with its English and Arabic text, the translation and its status."""
    _language(db, code)
    if scope and scope not in SCOPES:
        raise AppError(422, "validation_error")
    rows = _rows(db, code)
    edited_ar, edited_en = (_rows(db, "ar"), _rows(db, "en")) if code not in REQUIRED else ({}, {})
    out = []
    for sc in SCOPES:
        if scope and sc != scope:
            continue
        base, en, ar = base_texts(sc, code), base_texts(sc, "en"), base_texts(sc, "ar")
        for key in keys(sc):
            row = rows.get((sc, key))
            text = row.text if row else base.get(key)
            st = row.status if row else base_status(code, text)
            if status and st != status:
                continue
            en_text = (rows if code == "en" else edited_en).get((sc, key))
            ar_text = (rows if code == "ar" else edited_ar).get((sc, key))
            item = {
                "scope": sc,
                "key": key,
                "en": en_text.text if en_text else en.get(key, ""),
                "ar": ar_text.text if ar_text else ar.get(key, ""),
                "text": text or "",
                "base": base.get(key),
                "status": st,
                "edited": row is not None and row.text != base.get(key),
                "updated_at": row.updated_at if row else None,
            }
            if query and query.lower() not in f"{sc}.{key} {item['en']} {item['ar']} {item['text']}".lower():
                continue
            out.append(item)
    return out


def progress(db: Session, code: str) -> dict:
    counts = {"reviewed": 0, "needs_review": 0, "machine": 0, "missing": 0}
    for item in table(db, code):
        counts[item["status"]] += 1
    total = sum(counts.values())
    return counts | {"total": total, "percent": round(100 * counts["reviewed"] / total) if total else 100}


# ------------------------------------------------------------------ editing


def _check(scope: str, key: str, text: str) -> None:
    if scope not in SCOPES or key not in keys(scope):
        raise AppError(422, "unknown_translation_key", key=f"{scope}:{key}")
    problem = icu.check(text, reference(scope, key))
    if problem:
        raise AppError(422, "invalid_translation", key=key, reason=problem)


def _upsert(db: Session, scope: str, key: str, lang: str, text: str, status: str, actor: int | None) -> None:
    stmt = insert(Translation).values(scope=scope, key=key, lang=lang, text=text, status=status, updated_by=actor)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["scope", "key", "lang"],
            set_={
                "text": stmt.excluded.text,
                "status": status,
                "updated_by": actor,
                "updated_at": stmt.excluded.updated_at,
            },
        )
    )


def save(db: Session, actor_user_id: int | None, code: str, items: list[dict], *, action="translations.edited") -> dict:
    """Saves texts (each validated as an ICU message with the source's arguments); `reviewed` marks them reviewed."""
    lang = _language(db, code)
    if len(items) > MAX_ITEMS:
        raise AppError(422, "validation_error")
    current = _rows(db, code)
    for item in items:
        _check(item["scope"], item["key"], item["text"])
    changes = []
    for item in items:
        sc, key, text = item["scope"], item["key"], item["text"]
        status = "reviewed" if item.get("reviewed") else "needs_review"
        row = current.get((sc, key))
        before = row.text if row else base_texts(sc, code).get(key)
        _upsert(db, sc, key, code, text, status, actor_user_id)
        changes.append({"key": f"{sc}:{key}", "before": before, "after": text, "status": status})
    _changed(db, lang)
    audit.record(
        db, action=action, entity_type="language", entity_id=code, actor_user_id=actor_user_id,
        after={"count": len(changes), "changes": changes[:50]},
    )  # fmt: skip
    db.commit()
    return {"saved": len(changes), "version": lang.strings_version}


def review(db: Session, actor_user_id: int, code: str, items: list[dict]) -> dict:
    """Marks texts as reviewed as they are (a shipped text gets its row)."""
    lang = _language(db, code)
    if len(items) > MAX_ITEMS:
        raise AppError(422, "validation_error")
    current = _rows(db, code)
    done = []
    for item in items:
        sc, key = item["scope"], item["key"]
        if sc not in SCOPES or key not in keys(sc):
            raise AppError(422, "unknown_translation_key", key=f"{sc}:{key}")
        row = current.get((sc, key))
        if row is not None:
            if row.status != "reviewed":
                row.status, row.updated_by = "reviewed", actor_user_id
                done.append(f"{sc}:{key}")
            continue
        text = base_texts(sc, code).get(key)
        if text and code not in REQUIRED:
            _upsert(db, sc, key, code, text, "reviewed", actor_user_id)
            done.append(f"{sc}:{key}")
    if done:
        _changed(db, lang)
        audit.record(
            db, action="translations.reviewed", entity_type="language", entity_id=code,
            actor_user_id=actor_user_id, after={"count": len(done), "keys": done[:50]},
        )  # fmt: skip
    db.commit()
    return {"reviewed": len(done), "version": lang.strings_version}


def revert(db: Session, actor_user_id: int, code: str, scope: str, key: str) -> dict:
    """Back to the shipped text (its status as shipped)."""
    lang = _language(db, code)
    row = db.get(Translation, (scope, key, code))
    if row is None:
        raise AppError(404, "unknown_translation_key", key=f"{scope}:{key}")
    before = row.text
    db.delete(row)
    _changed(db, lang)
    audit.record(
        db, action="translations.reverted", entity_type="language", entity_id=code, actor_user_id=actor_user_id,
        before={"key": f"{scope}:{key}", "text": before},
    )  # fmt: skip
    db.commit()
    return {"version": lang.strings_version}


# ------------------------------------------------------------------ Excel round trip


def export_xlsx(db: Session, code: str) -> bytes:
    from app.core.sheets import to_xlsx

    rows = [[r["scope"], r["key"], r["en"], r["text"], r["status"]] for r in table(db, code)]
    return to_xlsx(f"translations-{code}", SHEET_HEADER, rows, rtl=False, text_columns=range(5))


def import_xlsx(db: Session, actor_user_id: int, code: str, data: bytes, *, reviewed: bool = False) -> dict:
    """The sheet exported above, translated offline: rows whose translation changed are saved (all or none)."""
    import zipfile

    import openpyxl

    _language(db, code)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    rows = list(wb.worksheets[0].iter_rows(values_only=True)) if wb.worksheets else []
    if not rows:
        raise AppError(422, "translation_sheet_invalid")
    header = [str(c or "").strip().lower() for c in rows[0]]
    try:
        at = {name: header.index(name) for name in ("scope", "key", "translation")}
    except ValueError:
        raise AppError(422, "translation_sheet_invalid") from None
    current = {(r["scope"], r["key"]): r["text"] for r in table(db, code)}
    items, problems = [], []
    for n, row in enumerate(rows[1:], start=2):
        cells = [("" if c is None else str(c)) for c in row] + [""] * len(header)
        sc, key, text = cells[at["scope"]].strip(), cells[at["key"]].strip(), cells[at["translation"]]
        if not sc and not key:
            continue
        if not text.strip() or current.get((sc, key)) == text:
            continue
        try:
            _check(sc, key, text)
        except AppError as e:
            problems.append({"row": n, "key": key, "code": e.code, **e.params})
            continue
        items.append({"scope": sc, "key": key, "text": text, "reviewed": reviewed})
    if problems:
        raise AppError(422, "translation_import_invalid", count=len(problems), rows=problems[:50])
    if not items:
        return {"saved": 0, "version": _language(db, code).strings_version}
    return save(db, actor_user_id, code, items, action="translations.imported")


# ------------------------------------------------------------------ publishing


def _body(code: str, version: int, direction: str, strings: dict[str, str]) -> str:
    doc = {
        "schema": BUNDLE_SCHEMA,
        "min_app_build": MIN_APP_BUILD,
        "lang": code,
        "version": version,
        "dir": direction,
        "strings": dict(sorted(strings.items())),
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def publish(db: Session, actor_user_id: int | None, code: str, *, commit: bool = True) -> dict:
    """A new immutable version of the language: its complete app strings (each checked again) and its server and
    status-card texts. Refused while any text is not a valid message."""
    lang = _language(db, code)
    strings = effective(db, code, "app")
    for key, text in strings.items():
        problem = icu.check(text, reference("app", key))
        if problem:
            raise AppError(422, "invalid_translation", key=key, reason=problem)
    version = lang.strings_version + 1
    body = _body(code, version, lang.direction, strings)
    rows = _rows(db, code)
    overrides = {sc: {k: r.text for (s_, k), r in rows.items() if s_ == sc} for sc in ("server", "status_templates")}
    sha = hashlib.sha256(body.encode()).hexdigest()
    db.add(Bundle(lang=code, version=version, body=body, sha256=sha, overrides=overrides, created_by=actor_user_id))
    lang.strings_version = version
    db.flush()
    audit.record(
        db, action="translations.published", entity_type="language", entity_id=code, actor_user_id=actor_user_id,
        after={"version": version, "sha256": sha, "strings": len(strings)},
    )  # fmt: skip
    db.execute(update(State).values(revision=State.revision + 1))
    if commit:
        db.commit()
    return {"version": version, "sha256": sha}


def unpublished(db: Session, code: str) -> int:
    """How many texts changed since the language's last publish (drafts the drivers do not see yet)."""
    bundle = latest(db, code)
    since = bundle.created_at if bundle else None
    return sum(1 for r in _rows(db, code).values() if since is None or r.updated_at > since)


# ------------------------------------------------------------------ for the app


def manifest(db: Session) -> dict:
    """The enabled languages with their latest published version and its checksum: small, polled by the app."""
    out = []
    for lang in db.scalars(select(Language).where(Language.is_active.is_(True)).order_by(Language.sort_order)):
        bundle = db.get(Bundle, (lang.code, lang.strings_version)) if lang.strings_version else None
        out.append(
            {
                "code": lang.code,
                "name_native": lang.name_native,
                "name_en": lang.name_en,
                "dir": lang.direction,
                "version": lang.strings_version,
                "sha256": bundle.sha256 if bundle else None,
            }
        )
    return {"schema": BUNDLE_SCHEMA, "min_app_build": MIN_APP_BUILD, "languages": out}


def bundle_body(db: Session, code: str, version: int) -> str:
    _language(db, code, active_only=True)
    bundle = db.get(Bundle, (code, version))
    if bundle is None:
        raise AppError(404, "not_found")
    return bundle.body


def for_driver(db: Session, code: str, version: int | None) -> dict:
    """GET /driver/translations: the latest published bundle of a language, or {unchanged: true} when the app's copy
    is that version. Before any publish: version 0, the shipped strings."""
    lang = _language(db, code, active_only=True)
    out = {"lang": lang.code, "version": lang.strings_version, "dir": lang.direction}
    if version is not None and version == lang.strings_version:
        return out | {"unchanged": True}
    bundle = latest(db, code)
    if bundle is not None:
        doc = json.loads(bundle.body)
        return out | {"schema": doc["schema"], "sha256": bundle.sha256, "strings": doc["strings"]}
    return out | {"schema": BUNDLE_SCHEMA, "strings": base_texts("app", code)}


@lru_cache(maxsize=64)
def _status_cache(lang: str, revision: int) -> dict:  # noqa: ARG001 - the revision is the cache key
    return {}


def status_text(db: Session, lang: str, key: str, en_text: str, revision: int) -> str | None:
    """A live-status template text in a new language: the translation of the built-in text, when the office has not
    rewritten it (its English is still the built-in one)."""
    if base_texts("status_templates", "en").get(key) != en_text:
        return None
    cache = _status_cache(lang, revision)
    if "texts" not in cache:
        cache["texts"] = base_texts("status_templates", lang) | overrides_in_force(db, lang, "status_templates")
    return cache["texts"].get(key)
