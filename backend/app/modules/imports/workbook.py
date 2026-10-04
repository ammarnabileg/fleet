"""Reading the onboarding workbook (the data template annexed to the contract) exactly as it is laid out:
same sheet names, same column headers in the same order, dates as day/month/year, phones without country code."""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.core.errors import AppError

VEHICLES = "السيارات"
PEOPLE = "المستخدمون والسائقون"
VEHICLE_COLUMNS = [
    "#",
    "رقم اللوحة *",
    "النوع *",
    "الموديل *",
    "السنة *",
    "اللون *",
    "رقم الهيكل (VIN) *",
    "الشركة *",
    "الفرع *",
    "تاريخ انتهاء التأمين *",
    "تاريخ انتهاء الاستمارة *",
]
PEOPLE_COLUMNS = [
    "#",
    "الاسم *",
    "الدور *",
    "الرقم المدني *",
    "رقم الهاتف (لرمز التحقق) *",
    "الشركة *",
    "الفرع *",
    "القسم *",
    "الوظيفة *",
    "الحالة الوظيفية *",
    "الراتب الأساسي (د.ك) *",
    "تاريخ انتهاء الإقامة *",
    "موديل الهاتف (للسائقين)",
]
OPENING = "الأرصدة الافتتاحية"
OPENING_COLUMNS = [
    "#",
    "اسم السائق *",
    "الرقم المدني *",
    "الرصيد الافتتاحي (د.ك) *",
    "تاريخ الرصيد *",
    "اعتماد المحاسب (الاسم) *",
]
EXAMPLE = "مثال"  # the grey example row is never imported
DRIVER_ROLE = "سائق"
COUNTRY_CODE = "965"


@dataclass
class Issue:
    sheet: str
    row: int
    code: str
    params: dict = field(default_factory=dict)


@dataclass
class Row:
    sheet: str
    number: int  # the row number in Excel, for the error list
    values: dict


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def parse_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", _text(v))
    if not m:
        return None
    try:
        return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


def parse_phone(v) -> str | None:
    digits = re.sub(r"\D", "", _text(v))
    if len(digits) == 8:
        return f"+{COUNTRY_CODE}{digits}"
    if len(digits) == 11 and digits.startswith(COUNTRY_CODE):
        return f"+{digits}"
    return None


def parse_decimal(v, *, signed: bool = False) -> Decimal | None:
    try:
        d = Decimal(_text(v).replace(",", ""))
    except InvalidOperation:
        return None
    if not d.is_finite() or d.as_tuple().exponent < -3:
        return None
    return d if signed or d >= 0 else None


def read(data: bytes) -> dict[str, list[Row]]:
    """Rows of the sheets imported now (vehicles, people, opening balances); maintenance centres come with M3."""
    import openpyxl  # with defusedxml installed, openpyxl parses the XML safely

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    out: dict[str, list[Row]] = {}
    for sheet, columns in ((VEHICLES, VEHICLE_COLUMNS), (PEOPLE, PEOPLE_COLUMNS), (OPENING, OPENING_COLUMNS)):
        if sheet not in wb.sheetnames:
            raise AppError(422, "import_bad_template", sheet=sheet)
        rows = wb[sheet].iter_rows(values_only=True)
        header = [_text(c) for c in next(rows, ())][: len(columns)]
        if header != columns:
            raise AppError(422, "import_bad_template", sheet=sheet)
        out[sheet] = []
        for number, values in enumerate(rows, start=2):
            values = list(values) + [None] * (len(columns) - len(values))
            if _text(values[0]) == EXAMPLE or not any(_text(v) for v in values[1 : len(columns)]):
                continue
            out[sheet].append(Row(sheet, number, dict(zip(columns, values[: len(columns)], strict=True))))
    wb.close()
    return out


def text(row: Row, column: str) -> str:
    return _text(row.values.get(column))
