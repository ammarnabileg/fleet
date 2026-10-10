"""Pay rules as ordered blocks, designed in the dashboard (docs/payroll-schemes.md, section 12): the catalog
of block types, the engine that runs a version's blocks on a driver's month, the templates a scheme can start from,
and the four old calculators written as blocks."""

import copy
import json
import pathlib
from functools import cache

from app.modules.payroll.rules.engine import validate

_TEMPLATES = pathlib.Path(__file__).with_name("templates.json")


@cache
def _load() -> tuple[dict, ...]:
    rows = json.loads(_TEMPLATES.read_text(encoding="utf-8"))
    for t in rows:  # a template that does not pass the checks would be refused when copied
        t["blocks"] = validate(t["blocks"])
    return tuple(rows)


def templates() -> list[dict]:
    """The starting points, values editable once copied (none of their prices is a rule for everyone). Those taken
    from the plan document carry needs_confirmation: «قيم أولية تحتاج تأكيد»."""
    return copy.deepcopy(list(_load()))


def template(code: str) -> dict | None:
    return next((t for t in templates() if t["code"] == code), None)
