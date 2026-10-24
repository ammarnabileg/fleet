"""Moving the configuration from one installation to another (a test server to production) as one JSON file.

Each module that owns configuration describes it in its own `transfer.py` as one or more Sections: what it exports
(plain JSON with natural keys — codes, names, CR numbers — never database ids) and how it applies a section of a
file to this database. app.modules.config_transfer gathers the sections, writes and reads the file, and runs an
import in one transaction (a dry run is the same import rolled back).

An import merges: what is missing is created, what exists (by its natural key) is updated, what the file does not
mention is never deleted. An item that cannot be applied (a reference missing here, invalid values) is skipped with
its reason; the rest of the section still applies.
"""

import base64
import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError

CREATED, UPDATED, UNCHANGED = "created", "updated", "unchanged"


@dataclass
class Report:
    """What an import did (or, in a dry run, would do) to one section."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: list[dict] = field(default_factory=list)  # [{item, code, params}]
    warnings: list[dict] = field(default_factory=list)

    def count(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)

    def skip(self, item: str, code: str, **params) -> None:
        self.skipped.append({"item": item, "code": code, "params": _plain(params)})

    def warn(self, item: str, code: str, **params) -> None:
        self.warnings.append({"item": item, "code": code, "params": _plain(params)})

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated)

    def out(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


@dataclass
class ExportContext:
    """Collects the files the exported sections refer to (logos, watermarks, the splash image: embedded in the file
    as base64) and, only when asked for, the secrets (encrypted with the user's passphrase by the caller)."""

    db: Session
    include_secrets: bool = False
    files: dict[str, dict] = field(default_factory=dict)
    secrets: dict[str, dict] = field(default_factory=dict)

    def add_file(self, sha256: str | None) -> str | None:
        from app.modules.files import service as files

        if not sha256 or sha256 in self.files:
            return sha256
        try:
            info = files.get(self.db, sha256)
            data = files.read(self.db, info)
        except AppError:
            return None  # a file gone from storage: the reference is dropped rather than exported dangling
        self.files[sha256] = {"content_type": info.content_type, "data": base64.b64encode(data).decode()}
        return sha256

    def put_secrets(self, section: str, values: dict) -> None:
        if self.include_secrets and values:
            self.secrets[section] = values


@dataclass
class ImportContext:
    db: Session
    actor_user_id: int | None
    files: dict[str, dict] = field(default_factory=dict)
    secrets: dict[str, dict] | None = None  # decrypted with the passphrase: None when the file has none or none given
    _stored: dict[str, bool] = field(default_factory=dict)
    after_commit: list[Callable[[], None]] = field(default_factory=list)

    def file(self, sha256: str | None) -> bool:
        """Makes sure a file the section refers to is stored here: already there, or written from the file's
        embedded copy (checked against its sha256). False when it is in neither place."""
        from app.modules.files import service as files

        if not sha256:
            return False
        if sha256 in self._stored:
            return self._stored[sha256]
        ok = True
        try:
            files.get(self.db, sha256)
        except AppError:
            entry = self.files.get(sha256) or {}
            try:
                data = base64.b64decode(entry.get("data") or "", validate=True)
            except ValueError:
                data = b""
            ok = bool(data) and hashlib.sha256(data).hexdigest() == sha256
            if ok:
                files.store(self.db, data, source="upload", uploaded_by_user=self.actor_user_id, images_only=True)
        self._stored[sha256] = ok
        return ok

    def section_secrets(self, key: str) -> dict | None:
        return None if self.secrets is None else self.secrets.get(key)


@dataclass(frozen=True)
class Section:
    key: str
    label: dict  # {"ar": ..., "en": ...}
    export: Callable[[ExportContext], Any]
    apply: Callable[[ImportContext, Any, Report], None]
    order: int = 100  # applied in this order: what others refer to first
    has_secrets: bool = False


def each(db: Session, report: Report, items: Any, label: Callable[[Any], str], fn: Callable[[Any], str]) -> None:
    """Applies fn to every item in its own savepoint: an item that fails is skipped with its reason (the error's
    code), the others still apply. fn returns CREATED, UPDATED or UNCHANGED."""
    if not isinstance(items, list):
        report.skip("*", "config_section_invalid")
        return
    for item in items:
        try:
            name = str(label(item))[:120]
        except Exception:  # noqa: BLE001 - a malformed item still gets a line in the report
            name = "?"
        try:
            with db.begin_nested():
                outcome = fn(item)
            report.count(outcome)
        except AppError as exc:
            report.skip(name, exc.code, **exc.params)
        except ValidationError as exc:
            err = exc.errors()[0]
            report.skip(name, "config_item_invalid", field=".".join(str(x) for x in err["loc"]), detail=err["msg"])
        except IntegrityError:
            report.skip(name, "config_item_conflict")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            report.skip(name, "config_item_invalid", field="", detail=str(exc)[:200])


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def plain(value: Any) -> Any:
    """JSON-ready (Decimals as strings, the way the API writes amounts)."""
    return _plain(value)


def same(a: Any, b: Any) -> bool:
    """Equal once both are JSON-ready (a Decimal 1.500 and the text "1.500" from a file compare equal)."""
    return _norm(_plain(a)) == _norm(_plain(b))


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return ("n", Decimal(value).normalize()) if value.strip() and value.strip()[0] in "-0123456789" else value
        except ArithmeticError:
            return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return ("n", Decimal(str(value)).normalize())
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def by_label(rows: Iterable, labels: Callable[[Any], Iterable[str]], wanted: Iterable[str]):
    """The first row one of whose labels matches one of the wanted ones (spaces and case ignored)."""
    keys = {" ".join(w.split()).casefold() for w in wanted if w}
    for row in rows:
        if keys & {" ".join(x.split()).casefold() for x in labels(row) if x}:
            return row
    return None


def upsert_by(db: Session, model, where: dict, values: dict) -> str:
    """A row found by its natural key (where) created or brought to these values; its version (when it has one)
    goes up on a change, so an open form elsewhere sees it changed."""
    from sqlalchemy import select

    row = db.scalar(select(model).filter_by(**where).with_for_update())
    if row is None:
        db.add(model(**where, **values))
        db.flush()
        return CREATED
    if all(same(getattr(row, k), v) for k, v in values.items()):
        return UNCHANGED
    for k, v in values.items():
        setattr(row, k, v)
    if hasattr(row, "version"):
        row.version += 1
    db.flush()
    return UPDATED


def columns(row, names: Iterable[str]) -> dict:
    return {n: plain(getattr(row, n)) for n in names}
