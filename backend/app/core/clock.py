"""Business dates are Kuwait dates: a reading taken at 01:00 Kuwait time belongs to that Kuwait day."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

KUWAIT = ZoneInfo("Asia/Kuwait")


def utcnow() -> datetime:
    return datetime.now(UTC)


def business_date(t: datetime) -> date:
    return t.astimezone(KUWAIT).date()


def today() -> date:
    return business_date(utcnow())
