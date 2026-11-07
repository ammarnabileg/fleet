import re
from collections.abc import AsyncIterator
from functools import lru_cache

import anyio
import anyio.to_thread
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
    "finance",
    "approvals",
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


POOL_SIZE = 10  # connections per API worker process
POOL_OVERFLOW = 5  # for a request that also opens one of its own (the rate limits count on a separate connection)


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url, pool_size=POOL_SIZE, max_overflow=POOL_OVERFLOW, pool_pre_ping=True
    )


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


_open: anyio.Semaphore | None = None  # sessions open at once in this worker process
_closing: anyio.CapacityLimiter | None = None


async def get_session() -> AsyncIterator[Session]:
    """A request's session, at most POOL_SIZE open at once in a worker; the others wait their turn before taking
    anything. A request holds its connection across several threads in turn (the device check, then the endpoint):
    without the limit, under load every thread waited for a connection while every connection waited, in a request
    between two steps, for a thread, and the worker stopped for good (300 phones sending positions at once). With
    it every open session has its connection, and threads to spare. Closing (which hands the connection back) runs
    in threads of its own, never behind the requests waiting for it."""
    global _open, _closing
    if _open is None:
        _open, _closing = anyio.Semaphore(POOL_SIZE), anyio.CapacityLimiter(POOL_SIZE)
    async with _open:
        session = new_session()
        try:
            yield session
        finally:
            await anyio.to_thread.run_sync(session.close, limiter=_closing)


def violated_constraint(exc: Exception) -> str | None:
    """Name of the constraint behind an IntegrityError, to turn it into a precise error code."""
    return getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)


def like_pattern(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
