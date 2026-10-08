"""An old system's books from Excel: the template the accountant fills (two sheets, Arabic headers, a grey example row
marked «مثال» that is skipped) and its reading and checks. What is imported is decided in service.import_books.

    أرصدة افتتاحية   رمز الحساب | اسم الحساب (for the reader, ignored) | مدين | دائن | الرقم المدني للموظف
    قيود             رقم القيد في النظام القديم | التاريخ | رمز الحساب | مدين | دائن | البيان | الرقم المدني
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.core.errors import AppError

OPENING = "أرصدة افتتاحية"
ENTRIES = "قيود"
OPENING_COLUMNS = ["رمز الحساب", "اسم الحساب", "مدين", "دائن", "الرقم المدني للموظف"]
ENTRY_COLUMNS = ["رقم القيد في النظام القديم", "التاريخ", "رمز الحساب", "مدين", "دائن", "البيان", "الرقم المدني"]
EXAMPLE = "مثال"
EXAMPLES = {
    OPENING: [EXAMPLE, "البنك", 1500, None, None],
    ENTRIES: [EXAMPLE, "31/12/2025", "6130", 250, None, "إيجار ديسمبر", None],
}
MAX_LINES = 200
ZERO = Decimal("0.000")
FILS = Decimal("0.001")
EXCEL_EPOCH = date(1899, 12, 30)


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def parse_amount(v) -> Decimal | None:
    """Empty is 0; a number of at most 3 decimals, not negative; None when it is not one."""
    if v is None or _text(v) == "":
        return ZERO
    try:
        d = Decimal(str(v)) if isinstance(v, float) else Decimal(_text(v).replace(",", ""))
    except InvalidOperation:
        return None
    if not d.is_finite() or d < 0:
        return None
    q = d.quantize(FILS)
    return q if abs(q - d) < Decimal("0.0000001") else None


def parse_date(v) -> date | None:
    """A date cell, an Excel day number, or dd/mm/yyyy (also yyyy-mm-dd)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, int | float) and not isinstance(v, bool) and 1 <= v < 100000:
        return EXCEL_EPOCH + timedelta(days=int(v))
    t = _text(v)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t)
    parts = (m[3], m[2], m[1]) if m else None
    if not m and (m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)):
        parts = (m[1], m[2], m[3])
    if not parts:
        return None
    try:
        return date(*map(int, parts))
    except ValueError:
        return None


@dataclass
class Row:
    sheet: str
    number: int  # the row number in Excel
    values: dict


@dataclass
class Found:
    opening: list[Row]
    entries: list[Row]

    def civil_ids(self) -> set[str]:
        return {
            _text(r.values[c])
            for rows, c in ((self.opening, OPENING_COLUMNS[4]), (self.entries, ENTRY_COLUMNS[6]))
            for r in rows
            if _text(r.values[c])
        }


def read(data: bytes) -> Found:
    import openpyxl  # with defusedxml installed, openpyxl parses the XML safely

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    if OPENING not in wb.sheetnames and ENTRIES not in wb.sheetnames:
        raise AppError(422, "import_bad_template", sheet=f"{OPENING}، {ENTRIES}")
    out: dict[str, list[Row]] = {}
    for sheet, columns in ((OPENING, OPENING_COLUMNS), (ENTRIES, ENTRY_COLUMNS)):
        out[sheet] = []
        if sheet not in wb.sheetnames:  # either sheet may be left out (or empty)
            continue
        rows = wb[sheet].iter_rows(values_only=True)
        header = [_text(c) for c in next(rows, ())]
        if header[: len(columns)] != columns:
            raise AppError(422, "import_bad_template", sheet=sheet)
        for number, values in enumerate(rows, start=2):
            values = (list(values) + [None] * len(columns))[: len(columns)]
            if _text(values[0]) == EXAMPLE or not any(_text(v) for v in values):
                continue
            out[sheet].append(Row(sheet, number, dict(zip(columns, values, strict=True))))
    wb.close()
    return Found(out[OPENING], out[ENTRIES])


@dataclass
class Result:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    opening: list[dict] = field(default_factory=list)  # lines for service.create_opening
    entries: dict[str, dict] = field(default_factory=dict)  # old number -> {row, date, description, lines}

    def error(self, sheet: str, row: int | None, error_code: str, /, **params) -> None:
        self.errors.append({"sheet": sheet, "row": row, "code": error_code, "params": params})

    def warn(self, sheet: str, row: int | None, warning_code: str, /, **params) -> None:
        self.warnings.append({"sheet": sheet, "row": row, "code": warning_code, "params": params})

    def summary(self) -> dict:
        debit = sum((ln["debit"] for ln in self.opening), ZERO)
        credit = sum((ln["credit"] for ln in self.opening), ZERO)
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "opening": {"debit": debit, "credit": credit, "difference": debit - credit, "lines": len(self.opening)},
            "entries": len(self.entries),
            "lines": sum(len(e["lines"]) for e in self.entries.values()),
        }


def _line(result: Result, row: Row, *, code_col: str, accounts: dict, civil_col: str, civil_ids: dict) -> dict | None:
    code = _text(row.values[code_col])
    account = accounts.get(code)
    ok = True
    if account is None:
        result.error(row.sheet, row.number, "unknown_account", code=code)
        ok = False
    elif not account.active:
        result.error(row.sheet, row.number, "account_inactive", code=code)
        ok = False
    debit, credit = parse_amount(row.values["مدين"]), parse_amount(row.values["دائن"])
    if debit is None or credit is None:
        result.error(row.sheet, row.number, "amount_invalid")
        ok = False
    elif (debit > 0) == (credit > 0):
        result.error(row.sheet, row.number, "line_one_side", code=code)
        ok = False
    civil_id = _text(row.values[civil_col])
    employee_id = civil_ids.get(civil_id) if civil_id else None
    if civil_id and employee_id is None:
        result.warn(row.sheet, row.number, "civil_id_not_found", civil_id=civil_id)
    if not ok:
        return None
    return {"account_id": account.id, "debit": debit, "credit": credit, "employee_id": employee_id}


def check(found: Found, *, accounts: dict, books_start: date | None, civil_ids: dict[str, int]) -> Result:
    """Every row checked; an entry's lines grouped by its old number and balanced; nothing written."""
    result = Result()
    for row in found.opening:
        line = _line(
            result,
            row,
            code_col=OPENING_COLUMNS[0],
            accounts=accounts,
            civil_col=OPENING_COLUMNS[4],
            civil_ids=civil_ids,
        )
        if line:
            result.opening.append(line)
    groups: dict[str, list[tuple[Row, dict | None, date | None]]] = {}
    for row in found.entries:
        number = _text(row.values[ENTRY_COLUMNS[0]])
        if not number:
            result.error(ENTRIES, row.number, "entry_number_missing")
            continue
        day = parse_date(row.values[ENTRY_COLUMNS[1]])
        if day is None:
            result.error(ENTRIES, row.number, "date_invalid", value=_text(row.values[ENTRY_COLUMNS[1]]))
        elif books_start and day < books_start:
            result.error(ENTRIES, row.number, "before_books_start", date=books_start.isoformat())
        line = _line(
            result, row, code_col=ENTRY_COLUMNS[2], accounts=accounts, civil_col=ENTRY_COLUMNS[6], civil_ids=civil_ids
        )
        if line is not None:
            line["memo"] = _text(row.values[ENTRY_COLUMNS[5]])[:500] or None
        groups.setdefault(number, []).append((row, line, day))
    for number, rows in groups.items():
        first = rows[0][0].number
        lines = [ln for _, ln, _ in rows if ln is not None]
        days = {d for _, _, d in rows if d is not None}
        if len(days) > 1:
            result.error(ENTRIES, first, "entry_dates_differ", number=number)
        if not 2 <= len(rows) <= MAX_LINES:
            result.error(ENTRIES, first, "entry_lines_count", min=2, max=MAX_LINES)
        if len(lines) == len(rows):
            difference = sum((ln["debit"] - ln["credit"] for ln in lines), ZERO)
            if difference:
                result.error(ENTRIES, first, "entry_not_balanced", number=number, difference=f"{difference:.3f}")
        description = next(
            (_text(r.values[ENTRY_COLUMNS[5]]) for r, _, _ in rows if _text(r.values[ENTRY_COLUMNS[5]])), ""
        )
        result.entries[number] = {
            "row": first,
            "date": min(days) if days else None,
            "description": description[:500],
            "lines": lines,
        }
    return result


def template() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    for title, header in ((OPENING, OPENING_COLUMNS), (ENTRIES, ENTRY_COLUMNS)):
        ws = wb.create_sheet(title)
        ws.sheet_view.rightToLeft = True
        ws.append(header)
        ws.append(EXAMPLES[title])
        for i, h in enumerate(header, start=1):
            ws.cell(1, i).font = Font(bold=True)
            ws.cell(2, i).fill = PatternFill("solid", fgColor="D9D9D9")
            ws.column_dimensions[get_column_letter(i)].width = max(len(h) + 4, 14)
        # codes and civil IDs stay text ("0101" keeps its zero)
        for col in (1 if title == OPENING else 3, len(header)):
            ws.column_dimensions[get_column_letter(col)].number_format = "@"
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
