"""A platform's own input fields, set in the dashboard: the driver's daily form (built-in fields and the platform's
own, older apps unaffected), the office's monthly fields, the month review with its problems, approved exceptions,
and the month imported from Excel (the partner's batch report or the simple template), checked before it is applied
and never counted twice."""

import io
from datetime import timedelta

import openpyxl
import pytest
from sqlalchemy import text

from app.core.clock import today
from tests.conftest import bearer, bind_device, jpeg, login, make_driver, make_user

P = "/api/v1/payroll"
MONTH = today().replace(day=1)


def platform(admin_client, code, **rule):
    r = admin_client.post(f"{P}/platforms", json={"code": code, "name": {"ar": code, "en": code}} | rule)
    assert r.status_code == 201, r.text
    return r.json()


def lab(ar, en=None):
    return {"ar": ar, "en": en or ar}


DAILY = [
    {"key": "orders", "builtin": "orders", "type": "int", "label": lab("عدد الطلبات", "Orders"), "required": True},
    {
        "key": "valid_day",
        "builtin": "valid_day",
        "type": "bool",
        "label": lab("اليوم صالح", "Valid day"),
        "required": True,
    },
    {"key": "grocery", "type": "int", "label": lab("طلبات البقالة", "Grocery orders"), "required": True},
    {"key": "tips_cash", "type": "money", "label": lab("إكراميات", "Tips"), "help": lab("ما استلمته نقداً")},
    {"key": "uniform", "type": "bool", "label": lab("ارتدى الزي", "Uniform")},
    {
        "key": "zone",
        "type": "choice",
        "label": lab("المنطقة", "Zone"),
        "options": [
            {"value": "north", "label": lab("الشمال", "North")},
            {"value": "south", "label": lab("الجنوب", "South")},
        ],
    },
]
MONTHLY = [
    {"key": "batch_orders", "builtin": "batch_orders", "type": "batch_orders", "label": lab("الطلبات حسب الباتش")},
    {
        "key": "attendance_marks",
        "builtin": "attendance_marks",
        "type": "int",
        "label": lab("العلامات"),
        "required": True,
    },
    {"key": "star_day_failed", "builtin": "star_day_failed", "type": "bool", "label": lab("فوّت Star Day")},
    {"key": "rating", "type": "money", "label": lab("التقييم", "Rating")},
    {
        "key": "task_counts",
        "builtin": "task_counts",
        "type": "task_counts",
        "label": lab("المهام"),
        "options": [
            {"value": "pharmacy", "label": lab("صيدلية", "Pharmacy")},
            {"value": "parcel", "label": lab("طرد", "Parcel")},
        ],
    },
]


def set_fields(admin_client, p, daily=DAILY, monthly=MONTHLY, version=0, **extra):
    return admin_client.put(
        f"{P}/platforms/{p['id']}/fields", json={"version": version, "daily": daily, "monthly": monthly} | extra
    )


def send(client, h, day, **fields):
    r = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    )
    body = {"business_date": str(day), "screenshot_sha256": r.json()["sha256"]} | fields
    return client.post("/api/v1/driver/reports", headers=h, json=body)


@pytest.fixture
def keeta(admin_client):
    p = platform(admin_client, "kplat", daily_fields=["orders", "cash"])
    r = set_fields(admin_client, p)
    assert r.status_code == 200, r.text
    return p


def test_the_office_sets_a_platforms_fields(admin_client, new_client, company):
    p = platform(admin_client, "plain", daily_fields=["orders", "valid_day"])
    f = admin_client.get(f"{P}/platforms/{p['id']}/fields").json()  # never set: what its daily_fields say
    assert [x["key"] for x in f["daily"]] == ["orders", "valid_day"] and f["monthly"] == [] and f["version"] == 0
    bad = [
        ([{"key": "orders", "type": "int", "label": lab("x")}], "platform_field_invalid"),  # a reserved name
        ([{"key": "trips", "type": "int", "label": lab("x")}] * 2, "platform_field_duplicate"),
        ([{"key": "zone", "type": "choice", "label": lab("x")}], "platform_field_invalid"),  # a list without options
        ([{"key": "cash", "builtin": "valid_day", "type": "bool", "label": lab("x")}], "platform_field_invalid"),
    ]
    for daily, code in bad:
        r = set_fields(admin_client, p, daily=daily, monthly=[])
        assert r.status_code == 422 and r.json()["code"] == code, (daily, r.text)
    r = set_fields(admin_client, p, daily=DAILY, monthly=[{"key": "grocery", "type": "int", "label": lab("x")}])
    assert r.status_code == 422 and r.json()["code"] == "platform_field_duplicate"  # daily and monthly keys differ
    r = set_fields(admin_client, p, screenshot=False)
    assert r.status_code == 200, r.text
    f = r.json()
    assert [x["key"] for x in f["daily"]] == ["orders", "valid_day", "grocery", "tips_cash", "uniform", "zone"]
    assert f["screenshot"] is False and f["version"] == 1
    plat = next(x for x in admin_client.get(f"{P}/platforms").json() if x["id"] == p["id"])
    assert plat["daily_fields"] == ["orders", "valid_day"]  # the built-in ones, for the apps that know only those
    assert set_fields(admin_client, p).json()["code"] == "version_conflict"

    make_user(admin_client, "viewer", permissions=["payroll.view"])
    c = new_client()
    login(c, "viewer")
    assert c.get(f"{P}/platforms/{p['id']}/fields").status_code == 200
    assert set_fields(c, p, version=1).status_code == 403


def test_the_app_draws_the_platforms_daily_form_and_older_apps_keep_working(admin_client, client, company, keeta):
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"])
    h = bearer(bind_device(client, d["phone"]))
    form = client.get("/api/v1/driver/reports/form", headers=h).json()
    assert form["fields"] == ["orders", "valid_day"]  # what an older app reads
    assert [i["key"] for i in form["items"]] == ["orders", "valid_day", "grocery", "tips_cash", "uniform", "zone"]
    zone = form["items"][-1]
    assert zone["type"] == "choice" and [o["value"] for o in zone["options"]] == ["north", "south"]
    assert form["items"][3]["help"]["ar"] == "ما استلمته نقداً"

    r = send(client, h, today(), orders_count=10, valid_day=True, extra={})
    assert r.status_code == 422 and r.json()["params"]["field"] == "grocery"  # a newer app: required is required
    r = send(client, h, today(), orders_count=10, valid_day=True, extra={"grocery": 2, "zone": "east"})
    assert r.status_code == 422 and r.json()["code"] == "field_invalid"
    r = send(client, h, today(), orders_count=10, valid_day=True, extra={"grocery": 2, "speed": 1})
    assert r.status_code == 422 and r.json()["code"] == "field_unknown"
    extra = {"grocery": 4, "tips_cash": "1.250", "uniform": True, "zone": "north"}
    r = send(client, h, today(), orders_count=10, valid_day=True, extra=extra)
    assert r.status_code == 201, r.text
    assert r.json()["extra"] == {"grocery": 4, "tips_cash": "1.250", "uniform": True, "zone": "north"}
    edited = client.patch(f"/api/v1/driver/reports/{r.json()['id']}", headers=h, json={"extra": {"grocery": 5}})
    assert edited.status_code == 200 and edited.json()["extra"]["grocery"] == 5 and edited.json()["extra"]["uniform"]

    # an older app sends only the built-in fields: accepted
    r = send(client, h, today() - timedelta(days=1), orders_count=7, valid_day=False)
    assert r.status_code == 201 and r.json()["extra"] == {}


def test_daily_fields_add_up_in_the_month_review(admin_client, client, company, keeta, owner_db):
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"], platform_driver_id="R-100")
    h = bearer(bind_device(client, d["phone"]))
    sent = []
    for back, grocery, uniform in ((2, 3, True), (1, 4, False), (0, 5, True)):
        extra = {"grocery": grocery, "uniform": uniform, "tips_cash": "0.500"}
        sent.append(send(client, h, today() - timedelta(days=back), orders_count=10, valid_day=True, extra=extra))
    for i, r in enumerate(sent):
        owner_db.execute(
            text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :id"),
            {"d": MONTH + timedelta(days=i), "id": r.json()["id"]},
        )
    owner_db.commit()
    for r in sent[:2]:
        admin_client.post(f"/api/v1/daily-reports/{r.json()['id']}/approve", json={})
    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == d["id"])
    assert row["daily"] == {"grocery": "7", "tips_cash": "1.000", "uniform": "1"}  # approved reports only
    assert row["orders"] == 20 and row["pending_reports"] == 1
    assert set(row["problems"]) == {"values_missing", "daily_pending"} and row["missing"] == ["attendance_marks"]


def test_the_office_enters_a_drivers_month(admin_client, company, keeta, owner_db, new_client):
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"])
    url = f"{P}/month-review/{d['id']}"
    body = {
        "month": str(MONTH),
        "values": {"attendance_marks": 2, "star_day_failed": False, "rating": "4.5"},
        "batches": [{"batch": 4, "orders": 118}, {"batch": 2, "orders": 39}],
        "tasks": {"pharmacy": 3},
    }
    r = admin_client.put(url, json=body)
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["values"] == {"attendance_marks": "2.000", "star_day_failed": "0.000", "rating": "4.500"}
    assert got["batches"] == [{"batch": 2, "orders": 39}, {"batch": 4, "orders": 118}] and got["tasks"] == {
        "pharmacy": 3
    }
    r = admin_client.put(
        url, json={"month": str(MONTH), "values": {"rating": None}, "batches": [{"batch": 3, "orders": 5}]}
    )
    assert r.json()["values"] == {"attendance_marks": "2.000", "star_day_failed": "0.000"}
    assert r.json()["batches"] == [{"batch": 3, "orders": 5}]  # sent: replaces his rows for the month

    for wrong, code in (
        ({"values": {"speed": 1}}, "field_unknown"),
        ({"values": {"attendance_marks": 1.5}}, "field_invalid"),
        ({"batches": [{"batch": 1, "orders": 1}, {"batch": 1, "orders": 2}]}, "batch_duplicate"),
        ({"tasks": {"courier": 1}}, "field_unknown"),
    ):
        r = admin_client.put(url, json={"month": str(MONTH)} | wrong)
        assert r.status_code == 422 and r.json()["code"] == code, (wrong, r.text)

    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == d["id"])
    assert "orders_conflict" not in row["problems"]  # no approved daily orders to compare with
    assert "driver_id_missing" in row["problems"] and review["problems"]["driver_id_missing"] >= 1

    make_user(admin_client, "viewer", permissions=["payroll.view"])
    c = new_client()
    login(c, "viewer")
    assert c.put(url, json={"month": str(MONTH)}).status_code == 403

    # a month whose payroll is approved does not change
    owner_db.execute(
        text(
            "INSERT INTO payroll.runs (company_id, month, status, cap_percent, cap_base, prepared_by, approved_at)"
            " VALUES (:c, :m, 'approved', 50, 'gross', 1, now())"
        ),
        {"c": company["id"], "m": MONTH},
    )
    owner_db.commit()
    r = admin_client.put(url, json=body)
    assert r.status_code == 409 and r.json()["code"] == "payroll_locked"


def test_exceptions_are_approved_with_a_note_and_cancelled_never_deleted(admin_client, company, keeta, new_client):
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"])
    base = {"employee_id": d["id"], "month": str(MONTH)}
    r = admin_client.post(f"{P}/month-exceptions", json=base | {"kind": "exception_day", "days": 2, "note": "مرض"})
    assert r.status_code == 201 and r.json()["approved_by"] and r.json()["days"] == 2, r.text
    first = r.json()["id"]
    r = admin_client.post(f"{P}/month-exceptions", json=base | {"kind": "company_error", "note": "خطأ في التقرير"})
    assert r.status_code == 422 and r.json()["params"]["field"] == "corrections"
    r = admin_client.post(
        f"{P}/month-exceptions", json=base | {"kind": "accepted_excuse", "note": "عذر", "corrections": {"orders": 1}}
    )
    assert r.status_code == 422
    fix = {
        "kind": "company_error",
        "note": "صححت المنصة الرقم",
        "corrections": {"orders": 450, "star_day_failed": False},
    }
    r = admin_client.post(f"{P}/month-exceptions", json=base | fix)
    assert r.status_code == 201 and r.json()["corrections"] == {"orders": 450, "star_day_failed": False}, r.text
    r = admin_client.post(f"{P}/month-exceptions", json=base | {"kind": "accepted_excuse", "note": "x"})
    assert r.status_code == 422  # a note of at least three letters

    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == d["id"])
    assert [x["kind"] for x in row["exceptions"]] == ["exception_day", "company_error"]
    assert admin_client.post(f"{P}/month-exceptions/{first}/cancel", json={"note": "أُدخل خطأ"}).status_code == 200
    r = admin_client.post(f"{P}/month-exceptions/{first}/cancel", json={"note": "مرة أخرى"})
    assert r.status_code == 409 and r.json()["code"] == "exception_cancelled"
    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    assert [x["kind"] for x in next(x for x in review["rows"] if x["employee"]["id"] == d["id"])["exceptions"]] == [
        "company_error"
    ]

    make_user(admin_client, "preparer", permissions=["payroll.view", "payroll.prepare"])
    c = new_client()
    login(c, "preparer")  # approving an exception is an approval
    assert c.post(f"{P}/month-exceptions", json=base | {"kind": "accepted_excuse", "note": "عذر"}).status_code == 403


# ------------------------------------------------------------------ the month from Excel


def xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def post_file(admin_client, path, data, p, fmt="partner_batches", month=MONTH):
    return admin_client.post(
        f"{P}/{path}",
        data={"platform_id": str(p["id"]), "month": str(month), "format": fmt},
        files={"file": ("month.xlsx", data, "application/octet-stream")},
    )


PARTNER = ["Rider ID", "Batch No.", "Total Completed Deliveries"]


def test_the_partners_batch_report_is_checked_then_applied_once(admin_client, client, company, keeta, owner_db):
    a = make_driver(admin_client, company["id"], platform_id=keeta["id"], platform_driver_id="R-1")
    b = make_driver(admin_client, company["id"], platform_id=keeta["id"], platform_driver_id="R-2")
    h = bearer(bind_device(client, a["phone"]))  # his approved daily orders: 150
    r = send(client, h, today(), orders_count=150, valid_day=True, extra={"grocery": 1})
    owner_db.execute(text("UPDATE daily_ops.reports SET business_date = :d WHERE public_id = :id"),
                     {"d": MONTH, "id": r.json()["id"]})  # fmt: skip
    owner_db.commit()
    admin_client.post(f"/api/v1/daily-reports/{r.json()['id']}/approve", json={})

    data = xlsx(
        [
            ["Partner report"],  # a title row before the header
            PARTNER,
            ["R-1", 4, 118],
            ["R-1", 2, 39],
            ["R-2", 1, 200],
            ["R-2", 1, 200],  # the same row twice: counted once, listed
            ["R-9", 1, 50],  # nobody here
        ]
    )
    check = post_file(admin_client, "month-imports/check", data, keeta)
    assert check.status_code == 200, check.text
    c = check.json()
    assert c["rows"] == 5 and [u["rider"] for u in c["unknown"]] == ["R-9"]
    assert [(x["employee"]["platform_driver_id"], x["same"]) for x in c["duplicates"]] == [("R-2", True)]
    assert c["conflicts"] == [{"employee": c["conflicts"][0]["employee"], "file_orders": 157, "daily_orders": 150}]
    assert not c["blocking"] and not c["imported_before"]
    batches = {x["employee"]["platform_driver_id"]: x["batches"] for x in c["drivers"]}
    assert batches == {
        "R-1": [{"batch": 2, "orders": 39}, {"batch": 4, "orders": 118}],
        "R-2": [{"batch": 1, "orders": 200}],
    }

    r = post_file(admin_client, "month-imports", data, keeta)
    assert r.status_code == 201 and r.json()["applied"] == 2, r.text
    again = post_file(admin_client, "month-imports/check", data, keeta).json()
    assert again["imported_before"] and all(x["replaces"] for x in again["drivers"])
    assert post_file(admin_client, "month-imports", data, keeta).status_code == 201  # once more: replaces, never adds
    rows = owner_db.execute(
        text("SELECT sub, value FROM payroll.month_values WHERE key = 'batch_orders' ORDER BY employee_id, sub")
    ).all()
    assert [(s, int(v)) for s, v in rows] == [("2", 39), ("4", 118), ("1", 200)]
    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == a["id"])
    assert "orders_conflict" in row["problems"]

    # a corrected report next week: the driver's rows are the file's (batch 2 gone)
    post_file(admin_client, "month-imports", xlsx([PARTNER, ["R-1", 4, 150]]), keeta)
    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == a["id"])
    assert row["batches"] == [{"batch": 4, "orders": 150}] and "orders_conflict" not in row["problems"]
    assert next(x for x in review["rows"] if x["employee"]["id"] == b["id"])["batches"] == [{"batch": 1, "orders": 200}]

    # two different figures for the same rider and batch: the file is not applied
    bad = xlsx([PARTNER, ["R-2", 1, 200], ["R-2", 1, 150]])
    assert post_file(admin_client, "month-imports/check", bad, keeta).json()["blocking"]
    r = post_file(admin_client, "month-imports", bad, keeta)
    assert r.status_code == 409 and r.json()["code"] == "month_import_blocked"
    r = post_file(admin_client, "month-imports/check", xlsx([["name", "orders"], ["x", 1]]), keeta)
    assert r.status_code == 422 and r.json()["code"] == "month_import_headers"


def test_the_simple_template(admin_client, company, keeta):
    d = make_driver(admin_client, company["id"], platform_id=keeta["id"], civil_id="290010100013")
    r = admin_client.get(f"{P}/month-imports/template", params={"platform_id": keeta["id"]})
    assert r.status_code == 200
    headers = [c.value for c in openpyxl.load_workbook(io.BytesIO(r.content)).active[1]]
    assert headers == [
        "platform_driver_id", "civil_id", "month", "batch", "batch_orders", "attendance_marks", "star_day_failed",
        "rating", "pharmacy", "parcel",
    ]  # fmt: skip
    other = MONTH.replace(year=MONTH.year - 1)
    data = xlsx(
        [
            headers,
            ["", "290010100013", MONTH.strftime("%Y-%m"), 3, 80, 1, "نعم", "4.250", 2, None],
            ["", "290010100013", MONTH.strftime("%Y-%m"), 5, 20, 1, "نعم", "4.250", 2, None],
            ["", "290010100013", other.strftime("%Y-%m"), 1, 10, None, None, None, None, None],
        ]
    )
    c = post_file(admin_client, "month-imports/check", data, keeta, fmt="generic").json()
    assert len(c["other_month"]) == 1 and not c["blocking"], c
    assert post_file(admin_client, "month-imports", data, keeta, fmt="generic").status_code == 201
    review = admin_client.get(f"{P}/month-review", params={"platform_id": keeta["id"], "month": str(MONTH)}).json()
    row = next(x for x in review["rows"] if x["employee"]["id"] == d["id"])
    assert row["batches"] == [{"batch": 3, "orders": 80}, {"batch": 5, "orders": 20}]
    assert row["values"] == {"attendance_marks": "1.000", "star_day_failed": "1.000", "rating": "4.250"}
    assert row["tasks"] == {"pharmacy": 2} and "values_missing" not in row["problems"]


def test_the_platform_form_and_the_field_list_agree(admin_client, keeta):
    plat = next(x for x in admin_client.get(f"{P}/platforms").json() if x["id"] == keeta["id"])
    r = admin_client.patch(f"{P}/platforms/{keeta['id']}", json={"version": plat["version"], "daily_fields": ["cash"]})
    assert r.status_code == 200, r.text
    f = admin_client.get(f"{P}/platforms/{keeta['id']}/fields").json()
    assert [x["key"] for x in f["daily"]] == ["cash", "grocery", "tips_cash", "uniform", "zone"] and f["version"] == 2
