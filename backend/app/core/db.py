import re
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

NAMING = {
    "ix": "%(table_name)s_%(column_0_name)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


MIGRATED_SCHEMAS = {
    "org",
    "identity",
    "audit",
    "integrations",
    "i18n",
    "files",
    "people",
    "documents",
    "fleet",
    "tracking",
    "notifications",
    "onboarding",
    "cash",
    "daily_ops",
    "maintenance",
    "accidents",
    "fines",
    "payroll",
    "attendance",
}
PARTITION = re.compile(r"^positions_\d{4}_\d{2}$")  # monthly partitions of tracking.positions, made at runtime


def include_name(name, type_, parent_names) -> bool:
    """Alembic filter: only our schemas are compared and migrated."""
    if type_ == "schema":
        return name in MIGRATED_SCHEMAS
    if type_ == "table":
        return not (parent_names.get("schema_name") == "tracking" and PARTITION.match(name))
    return True


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_size=10, max_overflow=5, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


def get_session() -> Iterator[Session]:
    session = new_session()
    try:
        yield session
    finally:
        session.close()


def violated_constraint(exc: Exception) -> str | None:
    """Name of the constraint behind an IntegrityError, to turn it into a precise error code."""
    return getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)


def like_pattern(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
