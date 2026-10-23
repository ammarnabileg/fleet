"""The arithmetic of leave types, without the database: which days a leave counts, how they split into pay tiers,
service years and months of service, and the annual leave accrued.

Defaults follow the Kuwait private-sector labour law (Law No. 6 of 2010) as read for this system and are stored as
data (attendance.leave_types): «قيم افتراضية حسب قانون العمل — راجعها مع الموارد البشرية/المستشار القانوني».
"""

from collections.abc import Iterable
from datetime import date, timedelta


def days(first: date, last: date):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def counted(first: date, last: date, counts: str, weekend: Iterable[int]) -> list[date]:
    """The days a leave uses up: every calendar day, or only the working days (the weekly rest days left out)."""
    rest = set(weekend) if counts == "working" else set()
    return [d for d in days(first, last) if d.weekday() not in rest]


def split(n: int, tiers: list[dict], used_before: int = 0) -> list[dict]:
    """n days paid along the tiers, after used_before days of the same period already took the first ones. A tier
    without days has no end; days past every tier are unpaid. Neighbouring parts at the same percent are merged."""
    out: list[dict] = []

    def add(k: int, pct: int) -> None:
        if k <= 0:
            return
        if out and out[-1]["pay_percent"] == pct:
            out[-1]["days"] += k
        else:
            out.append({"days": k, "pay_percent": pct})

    skip, left = used_before, n
    for t in tiers:
        if left <= 0:
            break
        size = t.get("days")
        if size is None:
            add(left, int(t["pay_percent"]))
            left = 0
            break
        room = size - min(skip, size)
        skip = max(0, skip - size)
        take = min(room, left)
        add(take, int(t["pay_percent"]))
        left -= take
    add(left, 0)
    return out


def pay_by_day(day_list: list[date], parts: list[dict]) -> dict[date, int]:
    """Each counted day's pay percent, the split laid over the days in order."""
    out, i = {}, 0
    for p in parts:
        for _ in range(int(p["days"])):
            if i >= len(day_list):
                return out
            out[day_list[i]] = int(p["pay_percent"])
            i += 1
    for d in day_list[i:]:
        out[d] = 0
    return out


def add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 February
        return d.replace(year=d.year + n, day=28)


def months_between(first: date, last: date) -> int:
    """Whole months from first to last."""
    m = (last.year - first.year) * 12 + last.month - first.month
    return m - (1 if last.day < first.day else 0)


def service_year(hire: date | None, d: date) -> tuple[date, date]:
    """The service year (from a hire anniversary) holding d; the calendar year without a hire date."""
    if hire is None or hire > d:
        return date(d.year, 1, 1), date(d.year, 12, 31)
    n = d.year - hire.year
    start = add_years(hire, n)
    if start > d:
        start = add_years(hire, n - 1)
    return start, add_years(start, 1) - timedelta(days=1)


def accrued(hire: date | None, on: date, per_year: int) -> int | None:
    """Annual leave earned from the hire date to `on`, pro rata (per_year a year), whole days."""
    if hire is None or on < hire:
        return None if hire is None else 0
    return ((on - hire).days + 1) * per_year // 365
