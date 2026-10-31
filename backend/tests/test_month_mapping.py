"""The month from any Excel file through a column mapping chosen in the panel (the client keeps no fixed column
names): the file's sheets and headers read first, each field fed by the column chosen for it, checked as before,
applied, the mapping kept for the platform's next file; batch rows week by week (the same batch twice in a month,
each with its period), paid line by line on the payslip; Keeta's batch rule on a real run."""

import io
import json
from datetime import timedelta

import openpyxl

from app.core.clock import today
from tests.conftest import make_driver

P = "/api/v1/payroll"
MONTH = today().replace(day=1)
IBAN = "KW81CBKU0000000000001234560101"


def xlsx(sheets: dict) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def platform(admin_client, code, monthly=None):
    r = admin_client.post(f"{P}/platforms", json={"code": code, "name": {"ar": code, "en": code}, "daily_fields": []})
    assert r.status_code == 201, r.text
    p = r.json()
    if monthly:
        r = admin_client.put(f"{P}/platforms/{p['id']}/fields", json={"version": 0, "daily": [], "monthly": monthly})
        assert r.status_code == 200, r.text
    return p


MONTHLY = [
    {"key": "batch_orders", "builtin": "batch_orders", "type": "batch_orders", "label": {"ar": "باتش", "en": "B"}},
    {"key": "attendance_marks", "builtin": "attendance_marks", "type": "int", "label": {"ar": "X", "en": "Marks"}},
    {"key": "star_day_failed", "builtin": "star_day_failed", "type": "bool", "label": {"ar": "ستار", "en": "Star"}},
]


def days(n):
    return MONTH + timedelta(days=n)


def file(rows):
    """A client's file: a cover sheet, then its own headers in Arabic, a title row above them."""
    head = ["كود المندوب", "الفئة", "من تاريخ", "إلى تاريخ", "التوصيلات", "إكس", "فوت النجمة", "ملاحظة"]
    return xlsx({"غلاف": [["تقرير الشهر"]], "البيانات": [["تقرير كيتا"], head, *rows]})


MAPPING = {
    "sheet": "البيانات",
    "columns": {
        "platform_driver_id": "كود المندوب",
        "batch": "الفئة",
        "period_start": "من تاريخ",
        "period_end": "إلى تاريخ",
        "orders": "التوصيلات",
        "attendance_marks": "إكس",
        "star_day_failed": "فوت النجمة",
    },
}


def post(admin_client, path, p, data, mapping=MAPPING, replace=False):
    form = {"platform_id": str(p["id"]), "month": str(MONTH), "format": "mapped", "replace_month": str(replace).lower()}
    if mapping is not None:
        form["mapping"] = json.dumps(mapping, ensure_ascii=False)
    return admin_client.post(f"{P}/{path}", data=form, files={"file": ("m.xlsx", data, "application/octet-stream")})


def columns(admin_client, p, data):
    r = admin_client.post(
        f"{P}/month-imports/columns",
        data={"platform_id": str(p["id"])},
        files={"file": ("m.xlsx", data, "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def weekly_rows(ref):
    return [
        [ref, 2, days(0), days(6), 120, 1, "لا", ""],
        [ref, 1, days(7), days(13), 100, None, None, ""],
        [ref, 2, days(14), days(20), 90, None, None, ""],  # batch 2 again, another week: its own row
        [ref, 3, days(21), days(27), 50, None, None, ""],
    ]


def test_the_file_is_read_then_mapped_checked_applied_and_the_mapping_kept(admin_client, company):
    k = platform(admin_client, "kmap", MONTHLY)
    d = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="K-1")
    data = file(weekly_rows("K-1") + [["K-404", 1, days(0), days(6), 10, None, None, ""]])

    c = columns(admin_client, k, data)  # nothing chosen before: the sheet with headers, its header row, a guess
    assert [s["name"] for s in c["sheets"]] == ["غلاف", "البيانات"] and c["sheet"] == "البيانات" and not c["saved"]
    sheet = c["sheets"][1]
    assert sheet["header_row"] == 2 and sheet["headers"][0] == "كود المندوب" and len(sheet["sample"]) == 5
    assert sheet["sample"][0][2] == str(days(0))
    keys = [f["key"] for f in c["fields"]]
    assert keys[:7] == ["platform_driver_id", "civil_id", "month", "batch", "orders", "period_start", "period_end"]
    assert {"attendance_marks", "star_day_failed", "exception_note"} <= set(keys)

    r = post(admin_client, "month-imports/check", k, data, mapping={"sheet": "البيانات", "columns": {"batch": "الفئة"}})
    assert r.status_code == 422 and r.json()["code"] == "month_import_driver_column"
    r = post(admin_client, "month-imports/check", k, data, mapping={**MAPPING, "columns": {"platform_driver_id": "?"}})
    assert r.status_code == 422 and r.json()["code"] == "month_import_column"
    r = post(admin_client, "month-imports/check", k, data, mapping={**MAPPING, "columns": {"nope": "الفئة"}})
    assert r.status_code == 422 and r.json()["code"] == "month_import_field_unknown"

    check = post(admin_client, "month-imports/check", k, data).json()
    assert [u["rider"] for u in check["unknown"]] == ["K-404"] and not check["blocking"], check
    assert check["drivers"][0]["batches"] == [
        {"batch": 2, "orders": 120, "period_start": str(days(0)), "period_end": str(days(6))},
        {"batch": 1, "orders": 100, "period_start": str(days(7)), "period_end": str(days(13))},
        {"batch": 2, "orders": 90, "period_start": str(days(14)), "period_end": str(days(20))},
        {"batch": 3, "orders": 50, "period_start": str(days(21)), "period_end": str(days(27))},
    ]
    assert check["drivers"][0]["values"] == {"attendance_marks": "1", "star_day_failed": "0"}
    r = post(admin_client, "month-imports", k, data)
    assert r.status_code == 201, r.text

    again = columns(admin_client, k, data)  # the next file starts from the columns chosen
    assert again["saved"] and again["mapping"] == MAPPING["columns"]
    renamed = xlsx({"البيانات": [["ID", "الفئة", "من تاريخ", "إلى تاريخ", "التوصيلات"], ["K-1", 1, None, None, 5]]})
    guess = columns(admin_client, k, renamed)["mapping"]
    assert "platform_driver_id" not in guess and guess["batch"] == "الفئة"  # a header gone is not guessed

    same = post(admin_client, "month-imports/check", k, data).json()  # the same file again: nothing counted twice
    assert same["same_as_existing"] and not same["blocking"]
    assert post(admin_client, "month-imports", k, data).status_code == 201
    review = admin_client.get(f"{P}/month-review", params={"platform_id": k["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == d["id"])
    assert [(b["batch"], b["orders"]) for b in row["batches"]] == [(2, 120), (1, 100), (2, 90), (3, 50)]

    changed = file([["K-1", 2, days(0), days(6), 130, 1, "لا", ""]])  # another file: the month replaced only on demand
    c2 = post(admin_client, "month-imports/check", k, changed).json()
    assert c2["blocking"] and "month_has_batches" in c2["reasons"]
    assert post(admin_client, "month-imports", k, changed, replace=True).status_code == 201
    review = admin_client.get(f"{P}/month-review", params={"platform_id": k["id"], "month": str(MONTH)}).json()
    assert [(b["batch"], b["orders"]) for b in review["rows"][0]["batches"]] == [(2, 130)]


def test_rows_the_mapping_cannot_read_stop_the_file(admin_client, company):
    k = platform(admin_client, "kbad", MONTHLY)
    make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="B-1")
    bad = file(
        [
            ["B-1", 2, days(6), days(0), 10, None, None, ""],  # the week ends before it starts
            ["B-1", "two", days(0), days(6), 10, None, None, ""],  # not a number
            ["B-1", 1, days(40), days(46), 10, None, None, ""],  # a week of another month
            ["B-1", 1, days(0), None, 10, None, None, ""],  # a start without an end
        ]
    )
    c = post(admin_client, "month-imports/check", k, bad).json()
    assert c["blocking"] and [x["row"] for x in c["invalid"]] == [3, 4, 5, 6]
    twice = file([["B-1", 1, days(0), days(6), 10, None, None, ""], ["B-1", 1, days(0), days(6), 11, None, None, ""]])
    c = post(admin_client, "month-imports/check", k, twice).json()
    assert "duplicate_conflict" in c["reasons"]


def test_the_partners_old_columns_are_a_preset_of_the_mapping(admin_client, company):
    """The partner's report (Rider ID, Batch No., Total Completed Deliveries) still imports as it is, and the mapping
    guesses those columns for a file that has them."""
    t = platform(admin_client, "tpre")
    make_driver(admin_client, company["id"], platform_id=t["id"], platform_driver_id="T-1")
    data = xlsx({"Riders": [["Rider ID", "Batch No.", "Total Completed Deliveries"], ["T-1", 4, 118], ["T-1", 2, 39]]})
    guess = columns(admin_client, t, data)["mapping"]
    assert guess == {"platform_driver_id": "Rider ID", "batch": "Batch No.", "orders": "Total Completed Deliveries"}
    mapped = post(admin_client, "month-imports/check", t, data, mapping={"sheet": None, "columns": guess}).json()
    old = admin_client.post(
        f"{P}/month-imports/check",
        data={"platform_id": str(t["id"]), "month": str(MONTH), "format": "partner_batches"},
        files={"file": ("p.xlsx", data, "application/octet-stream")},
    ).json()
    assert (
        mapped["drivers"][0]["batches"]
        == old["drivers"][0]["batches"]
        == [
            {"batch": 2, "orders": 39},
            {"batch": 4, "orders": 118},
        ]
    )


def test_the_office_enters_weekly_batch_rows_by_hand(admin_client, company):
    t = platform(admin_client, "tweek", MONTHLY)
    d = make_driver(admin_client, company["id"], platform_id=t["id"], platform_driver_id="W-1")
    url = f"{P}/month-review/{d['id']}"
    week = lambda b, n, a, z: {"batch": b, "orders": n, "period_start": str(days(a)), "period_end": str(days(z))}  # noqa: E731
    body = {"month": str(MONTH), "batches": [week(3, 40, 0, 6), week(2, 60, 7, 13), week(3, 30, 14, 20)]}
    r = admin_client.put(url, json=body)
    assert r.status_code == 200, r.text
    assert [(b["batch"], b["orders"], b["period_start"]) for b in r.json()["batches"]] == [
        (3, 40, str(days(0))),
        (2, 60, str(days(7))),
        (3, 30, str(days(14))),
    ]
    r = admin_client.put(url, json={"month": str(MONTH), "batches": [week(3, 40, 0, 6), week(3, 41, 0, 6)]})
    assert r.status_code == 422 and r.json()["code"] == "batch_duplicate"
    r = admin_client.put(url, json={"month": str(MONTH), "batches": [week(1, 5, 40, 46)]})
    assert r.status_code == 422 and r.json()["code"] == "batch_period_outside"
    r = admin_client.put(
        url, json={"month": str(MONTH), "batches": [{"batch": 1, "orders": 5, "period_start": str(MONTH)}]}
    )
    assert r.status_code == 422  # a start without its end


def test_keeta_batch_rule_on_a_run_with_weekly_rows_and_x(admin_client, company):
    """Keeta's default template on the month: each weekly batch row its own payslip line with its period, the 420
    target's missing orders at his current batch (the last week's), the marks (X) at 20 each, the star day kept."""
    version = admin_client.get("/api/v1/settings").json()["payroll"]["version"]
    admin_client.put(
        "/api/v1/settings/payroll",
        json={"version": version, "value": {"max_deduction_percent": "100.00", "deduction_cap_base": "gross"}},
    )
    k = platform(admin_client, "krun", MONTHLY)
    r = admin_client.post(
        f"{P}/schemes/from-template",
        json={"platform_id": k["id"], "template": "keeta_batches", "code": "batches", "name": {"ar": "ب", "en": "b"}},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    d = make_driver(admin_client, company["id"], iban=IBAN, platform_id=k["id"], platform_driver_id="K-9")
    r = admin_client.post(f"{P}/schemes/{s['id']}/assign", json={"employee_ids": [d["id"]], "month": str(MONTH)})
    assert r.status_code == 200, r.text
    assert post(admin_client, "month-imports", k, file(weekly_rows("K-9"))).status_code == 201
    run = admin_client.post(f"{P}/runs", json={"company_id": company["id"], "month": str(MONTH)})
    assert run.status_code == 201, run.text
    line = next(x for x in run.json()["lines"] if x["employee"]["id"] == d["id"])
    pay = [(x["why"]["batch_level"], x["why"]["period"]["from"], x["amount"]) for x in line["breakdown"][:4]]
    assert pay == [
        (2, str(days(0)), "47.040"),  # 120 × 0.392
        (1, str(days(7)), "47.500"),  # 100 × 0.475
        (2, str(days(14)), "35.280"),  # 90 × 0.392
        (3, str(days(21)), "17.500"),  # 50 × 0.350
    ]
    rest = [(x["code"], x["amount"]) for x in line["breakdown"][4:]]
    assert rest == [("missing_target", "-21.000"), ("marks_deduction", "-20.000")]  # 60 × 0.350; one X
    assert line["gross"] == "147.320", line
