"""Reading a client's own workbook (not the contract template): any sheet names, any column order, with or without
a header row. Each sheet is offered as vehicles or employees with a suggested column for every field, found from the
header (Arabic or English, typos tolerated) or, when there is no header, from what the column holds (12-digit civil
IDs, plates, years...). The person importing confirms or corrects the suggestion; nothing is imported on a guess.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.errors import AppError
from app.modules.imports.workbook import _text, parse_phone

SAMPLES = 5
_ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": ""})


def norm(value) -> str:
    """For comparing headers: case, spaces, the asterisk of required columns and Arabic letter variants ignored."""
    return " ".join(_text(value).lower().translate(_ARABIC).replace("*", " ").split())


@dataclass(frozen=True)
class Field:
    key: str
    required: bool = False
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(norm(a) for a in self.aliases))


FIELDS: dict[str, tuple[Field, ...]] = {
    "vehicles": (
        Field(
            "plate_number",
            True,
            ("رقم المركبه", "رقم المركبة", "رقم اللوحه", "اللوحه", "car number", "plate", "plate number"),
        ),
        Field(
            "make", False, ("نوع المركبه", "النوع", "الماركه", "vehicle type", "vichel tybe", "type", "make", "brand")
        ),
        Field("model", False, ("الطراز", "model name")),
        Field("year", False, ("سنه الصنع", "السنه", "الموديل", "year", "model year")),
        Field("color", False, ("اللون", "color", "colour")),
        Field("vin", False, ("رقم الهيكل", "رقم الشاصي", "vin", "chassis")),
        Field(
            "registration_expiry",
            False,
            (
                "تاريخ انتهاء الدفتر",
                "انتهاء الدفتر",
                "تاريخ انتهاء الاستماره",
                "انتهاء الاستماره",
                "date of expier",
                "date of expiry",
                "expiry date",
                "registration expiry",
            ),
        ),
        Field("insurance_expiry", False, ("تاريخ انتهاء التامين", "انتهاء التامين", "insurance expiry")),
    ),
    "employees": (
        Field("civil_id", True, ("الرقم المدني", "رقم البطاقه المدنيه", "civil id", "civil no")),
        Field("name", True, ("الاسم", "اسم السائق", "اسم الموظف", "name", "driver name", "employee name")),
        Field(
            "job_title", False, ("المهنه", "الوظيفه", "المسمي الوظيفي", "profession", "job", "job title", "occupation")
        ),
        Field("phone", False, ("الهاتف", "رقم الهاتف", "الموبايل", "phone", "mobile")),
        Field("nationality", False, ("الجنسيه", "nationality")),
        Field("iban", False, ("رقم الايبان", "الايبان", "iban")),
    ),
}


def _parts(header: str) -> list[str]:
    whole = norm(header)
    return [whole] + [
        p.strip() for p in re.split(r"\s[-–/|]\s|\s-|-\s|[()]", whole) if p.strip() and p.strip() != whole
    ]


# ------------------------------------------------------------------ what a column holds


def _is_civil_id(v) -> bool:
    return bool(re.fullmatch(r"\d{12}", _text(v).replace(" ", "")))


def _is_plate(v) -> bool:
    return bool(re.fullmatch(r"\d{1,3}\s*[-/]\s*\d{2,6}", _text(v)))


def _is_year(v) -> bool:
    t = _text(v)
    return t.isdigit() and 1980 <= int(t) <= 2100


def _is_date(v) -> bool:
    from app.modules.imports.workbook import parse_date

    return isinstance(v, datetime | date) or parse_date(v) is not None


CONTENT = {
    "civil_id": _is_civil_id,
    "plate_number": _is_plate,
    "year": _is_year,
    "phone": lambda v: parse_phone(v) is not None,
}


def _share(values: list, test) -> float:
    filled = [v for v in values if _text(v)]
    return sum(1 for v in filled if test(v)) / len(filled) if filled else 0.0


def _is_serial(values: list) -> bool:
    """A row-number column (1, 2, 3... with gaps allowed): never a civil ID or a year."""
    nums = [_text(v) for v in values if _text(v)]
    if len(nums) < 2 or not all(n.isdigit() for n in nums):
        return False
    ints = [int(n) for n in nums]
    return ints == sorted(ints) and ints[-1] - ints[0] <= 2 * len(ints)


# ------------------------------------------------------------------ reading


@dataclass
class Sheet:
    name: str
    header_row: int | None  # 1-based, None when the sheet has no header
    first_row: int  # 1-based, the first data row
    headers: list[str]
    rows: list[tuple[int, list]] = field(default_factory=list)  # (Excel row number, values) below the header
    all_rows: list[tuple[int, list]] = field(default_factory=list)  # every non-empty row, header included


def read(data: bytes) -> list[Sheet]:
    import openpyxl  # defusedxml makes openpyxl parse the XML safely

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    out = []
    for ws in wb.worksheets:
        rows = [(n, list(values)) for n, values in enumerate(ws.iter_rows(values_only=True), start=1)]
        rows = [(n, v) for n, v in rows if any(_text(x) for x in v)]
        if not rows:
            out.append(Sheet(ws.title, None, 1, []))
            continue
        width = max(len(v) for _, v in rows)
        rows = [(n, v + [None] * (width - len(v))) for n, v in rows]
        first_n, first = rows[0]
        known = {a for fields in FIELDS.values() for f in fields for a in f.aliases}
        is_header = any(set(_parts(c)) & known for c in first if _text(c)) or (
            all(not isinstance(c, int | float | datetime | date) for c in first if c is not None)
            and len(rows) > 1
            and any(isinstance(c, int | float | datetime | date) for c in rows[1][1] if c is not None)
        )
        if is_header:
            start = rows[1][0] if len(rows) > 1 else first_n + 1
            out.append(Sheet(ws.title, first_n, start, [_text(c) for c in first], rows[1:], rows))
        else:
            out.append(Sheet(ws.title, None, first_n, [""] * width, rows, rows))
    wb.close()
    return out


def suggest(sheet: Sheet) -> tuple[str | None, dict[str, int]]:
    """The likely kind of the sheet and a column (0-based) for each field found."""
    columns = list(range(len(sheet.headers)))
    values = {c: [r[1][c] for r in sheet.rows[:200]] for c in columns}
    best: tuple[str | None, dict[str, int], int] = (None, {}, 0)
    for kind, fields in FIELDS.items():
        mapping: dict[str, int] = {}
        taken: set[int] = set()
        # 1. headers: a whole-header match wins over a match on one part ("الموديل - year")
        for exact in (True, False):
            for f in fields:
                if f.key in mapping:
                    continue
                for c in columns:
                    if c in taken:
                        continue
                    parts = _parts(sheet.headers[c])
                    hit = parts[0] in f.aliases if exact else any(p in f.aliases for p in parts[1:])
                    test = CONTENT.get(f.key)
                    if hit and (test is None or _share(values[c], test) >= 0.8):
                        mapping[f.key] = c
                        taken.add(c)
                        break
        # 2. content, for what the headers did not name
        for key, test in CONTENT.items():
            if key in mapping or key not in {f.key for f in fields}:
                continue
            for c in columns:
                if c not in taken and not _is_serial(values[c]) and _share(values[c], test) >= 0.9:
                    mapping[key] = c
                    taken.add(c)
                    break
        if kind == "employees" and "name" not in mapping:
            text_cols = [
                c
                for c in columns
                if c not in taken and _share(values[c], lambda v: isinstance(v, str) and not _text(v).isdigit()) >= 0.9
            ]
            distinct = {c: len({norm(v) for v in values[c] if _text(v)}) for c in text_cols}
            if text_cols:
                name_col = max(text_cols, key=lambda c: distinct[c])
                mapping["name"] = name_col
                taken.add(name_col)
                rest = [c for c in text_cols if c != name_col and distinct[c] <= max(3, len(sheet.rows[:200]) // 5)]
                if rest and "job_title" not in mapping:
                    mapping["job_title"] = rest[0]
        if kind == "vehicles" and "registration_expiry" not in mapping:
            dates = [c for c in columns if c not in taken and _share(values[c], _is_date) >= 0.9]
            if len(dates) == 1 and not any(_text(h) for h in sheet.headers):
                mapping["registration_expiry"] = dates[0]
        required = [f.key for f in fields if f.required]
        score = sum(2 if k in required else 1 for k in mapping) if all(k in mapping for k in required) else 0
        if score > best[2]:
            best = (kind, mapping, score)
    return best[0], best[1]


def _sample(v) -> str:
    if isinstance(v, datetime):
        v = v.date()
    return v.strftime("%d/%m/%Y") if isinstance(v, date) else _text(v)


def preview(data: bytes) -> dict:
    sheets = []
    for s in read(data):
        kind, mapping = suggest(s) if s.rows else (None, {})
        sheets.append(
            {
                "name": s.name,
                "rows": len(s.rows),
                "header_row": s.header_row,
                "first_row": s.first_row,
                "columns": [
                    {"index": c, "header": s.headers[c], "samples": [_sample(r[1][c]) for r in s.rows[:SAMPLES]]}
                    for c in range(len(s.headers))
                ],
                "kind": kind,
                "mapping": mapping,
            }
        )
    return {
        "sheets": sheets,
        "fields": {k: [{"key": f.key, "required": f.required} for f in v] for k, v in FIELDS.items()},
    }
