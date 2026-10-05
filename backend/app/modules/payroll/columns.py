"""What a salary-sheet column can hold. A platform's sheet is a list of these codes in the client's order, each with
the client's own header; the codes are found from the headers of the client's template (Arabic or English), and a
header the system does not know becomes a "blank" column the user can assign or leave empty."""

import io
import re
import zipfile
from dataclasses import dataclass

from app.core.errors import AppError
from app.core.text import cell_text, norm


@dataclass(frozen=True)
class Column:
    code: str
    kind: str  # text | int | number | money
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(norm(a) for a in self.aliases))


COLUMNS: tuple[Column, ...] = (
    Column("platform_driver_id", "text", ("driver id", "رقم السائق", "معرف السائق", "رقم السائق في المنصة")),
    Column("name", "text", ("اسم السائق", "الاسم", "اسم الموظف", "name", "driver name")),
    Column("job_title", "text", ("المهنه", "الوظيفه", "profession", "job title")),
    Column("civil_id", "text", ("الرقم المدني", "civil id")),
    Column("iban", "text", ("رقم الايبان", "الايبان", "iban")),
    Column("bank_name", "text", ("نوع البنك", "البنك", "اسم البنك", "bank")),
    Column("payment_method", "text", ("طريقه الدفع", "payment method")),
    Column("basic", "money", ("الراتب الاساسي", "الاساسي", "basic salary")),
    Column("hours", "number", ("اجمالي الساعات", "عدد الساعات", "الساعات", "hours")),
    Column("orders", "int", ("اجمالي الطلبات", "عدد الطلبات", "orders")),
    Column("working_days", "int", ("عدد ايام الدوام", "ايام الدوام", "working days")),
    Column("valid_days", "int", ("عدد الايام الصالحه", "الايام الصالحه", "valid days")),
    Column("bonus", "money", ("البونص", "المكافاه", "المكافات", "الحوافز", "bonus")),
    Column("tips", "money", ("البقشيش", "tips")),
    Column("gross", "money", ("اجمالي الراتب", "الراتب المستحق", "الاجمالي", "gross")),
    Column("invalid_days_deduction", "money", ("خصم الايام الغير صالحه", "خصم الايام غير الصالحه")),
    Column("car_repair", "money", ("خصم تصليح السياره", "خصم تصليح المركبه", "خصم الحوادث")),
    Column("traffic_fines", "money", ("خصم مخالفات المرور", "خصم المخالفات المروريه", "خصم المخالفات")),
    Column("cancelled_orders", "money", ("خصومات الطلبات الملغاه", "خصم الطلبات الملغاه")),
    Column("platform_deductions", "money", ("خصومات المنصه", "platform deductions")),
    Column("sim", "money", ("خصم شريحه الهاتف", "خصم الشريحه")),
    Column("advance", "money", ("خصم السلفه", "خصم السلف", "السلف")),
    Column("cash_shortage", "money", ("خصم الكاش", "عجز الكاش")),
    Column("late", "money", ("خصم التاخير", "التاخير")),
    Column("other_deductions", "money", ("خصومات اخري", "خصم اخر", "other deductions")),
    Column("carried", "money", ("مرحل للشهر القادم", "carried")),
    Column("net", "money", ("صافي الراتب", "الصافي", "net salary", "net")),
    Column("blank", "text"),  # a column of the client's sheet the system leaves empty
)
BY_CODE = {c.code: c for c in COLUMNS}
# "خصومات من <platform name>": the platform's own deductions, whatever the platform is called
PREFIXES = {"platform_deductions": (norm("خصومات من"), norm("خصم من"))}
TITLE_WORDS = ("نموذج", "رواتب", "راتب", "كشف", "template", "salaries", "salary", "payroll")


def code_for(header: str) -> str:
    h = norm(header)
    for c in COLUMNS:
        if h in c.aliases:
            return c.code
    for code, prefixes in PREFIXES.items():
        if any(h.startswith(p) for p in prefixes):
            return code
    return "blank"


def suggested_name(title: str) -> str:
    """ "نموذج رواتب كيتا" -> "كيتا": the platform's name is what remains of the sheet title."""
    words = [w for w in cell_text(title).split() if norm(w) not in {norm(t) for t in TITLE_WORDS}]
    return " ".join(words) or cell_text(title)


def read_template(data: bytes) -> list[dict]:
    """Every sheet with a header row: its columns (header and the code found for it) and what the columns imply."""
    import openpyxl  # defusedxml makes openpyxl parse the XML safely

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        raise AppError(422, "import_not_xlsx") from None
    out = []
    for ws in wb.worksheets:
        first = next((r for r in ws.iter_rows(values_only=True) if any(cell_text(c) for c in r)), None)
        if not first:
            continue
        headers = [cell_text(c) for c in first if cell_text(c)]
        if not headers or all(re.fullmatch(r"[\d.,\-/ ]+", h) for h in headers):
            continue  # a data row, not headers
        columns = [{"header": h, "code": code_for(h)} for h in headers]
        codes = {c["code"] for c in columns}
        if len(codes - {"blank"}) < 2:
            continue
        out.append(
            {
                "sheet": ws.title,
                "suggested_name": suggested_name(ws.title),
                "columns": columns,
                "driver_fields": [f for f in ("valid_days",) if f in codes],
                "invalid_days": "daily_wage" if "invalid_days_deduction" in codes else "none",
            }
        )
    wb.close()
    return out
