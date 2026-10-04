"""Initial data import from the onboarding workbook (the contract's data template): check first, then import all at
once; importing the same file again updates and never duplicates."""

import io
from datetime import date

import openpyxl
import pytest
from sqlalchemy import text

from app.modules.imports.workbook import OPENING, OPENING_COLUMNS, PEOPLE, PEOPLE_COLUMNS, VEHICLE_COLUMNS, VEHICLES
from tests.conftest import login, make_user

COMPANY = "شركة أ"  # the "companies" fixture names


def workbook(vehicles=(), people=(), opening=(), *, break_header=False) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "التعليمات"
    for title, columns, rows in (
        (VEHICLES, VEHICLE_COLUMNS, vehicles),
        (PEOPLE, PEOPLE_COLUMNS, people),
        (OPENING, OPENING_COLUMNS, opening),
    ):
        ws = wb.create_sheet(title)
        ws.append(columns[:-1] + ["something else"] if break_header and title == PEOPLE else columns)
        ws.append(["مثال"] + ["x"] * (len(columns) - 1))  # the grey example row
        for i, row in enumerate(rows, start=1):
            ws.append([i, *row])
        ws.append([len(rows) + 1])  # numbered but empty: ignored
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def vehicle(plate="12/34567", vin="MR0AA0000BB000001", **kw):
    row = {
        "plate": plate,
        "make": "تويوتا",
        "model": "يارس",
        "year": 2023,
        "color": "أبيض",
        "vin": vin,
        "company": COMPANY,
        "branch": "الفرع الرئيسي",
        "insurance": "15/03/2027",
        "registration": date(2027, 6, 20),
    }
    row.update(kw)
    return list(row.values())


def person(name="Ahmed Ali", role="سائق", civil="290010112345", phone="98765432", **kw):
    row = {
        "name": name,
        "role": role,
        "civil": civil,
        "phone": phone,
        "company": COMPANY,
        "branch": "الفرع الرئيسي",
        "dept": "العمليات",
        "job": "سائق توصيل",
        "status": "على رأس العمل",
        "salary": "150.000",
        "residence": "30/09/2027",
        "model": "Samsung A15",
    }
    row.update(kw)
    return list(row.values())


def post(client, data, apply=False):
    return client.post(
        "/api/v1/imports/workbook",
        params={"apply": apply},
        files={"file": ("data.xlsx", data, "application/octet-stream")},
    )


@pytest.fixture
def main_branch(admin_client):
    branch = next(b for b in admin_client.get("/api/v1/branches").json() if b["is_default"])
    return branch["name"]["ar"]


def test_check_then_import_then_reimport(admin_client, companies, main_branch, db):
    data = workbook(
        [vehicle(branch=main_branch), vehicle("12/34568", "MR0AA0000BB000002", branch=main_branch)],
        [
            person(branch=main_branch),
            person("سالم", role="مشرف", civil="290010112346", phone="98765433", branch=main_branch),
        ],
    )
    check = post(admin_client, data).json()
    assert check["applied"] is False and check["errors"] == []
    assert check["vehicles"] == {"created": 2, "updated": 0} and check["people"] == {"created": 2, "updated": 0}
    assert check["documents"] == 6  # insurance + registration per vehicle, residence per person
    assert admin_client.get("/api/v1/vehicles").json() == []  # a check changes nothing

    done = post(admin_client, data, apply=True).json()
    assert done["applied"] is True and done["vehicles"]["created"] == 2
    vehicles = admin_client.get("/api/v1/vehicles").json()
    assert sorted(v["plate_number"] for v in vehicles) == ["12/34567", "12/34568"]
    driver = admin_client.get("/api/v1/employees", params={"is_driver": True}).json()[0]
    assert (driver["phone"], driver["civil_id"], driver["app_access"]) == ("+96598765432", "290010112345", "active")
    assert driver["name"] == {"ar": "Ahmed Ali", "en": "Ahmed Ali"} and driver["employee_number"] == "E00001"
    assert driver["basic_salary"] == "150.000"
    supervisor = admin_client.get("/api/v1/employees", params={"is_driver": False}).json()[0]
    assert supervisor["app_access"] == "none" and supervisor["employee_number"] == "E00002"
    docs = admin_client.get("/api/v1/documents", params={"owner_type": "vehicle", "owner_id": vehicles[0]["id"]})
    assert sorted((d["type_code"], d["expiry_date"]) for d in docs.json()) == [
        ("insurance", "2027-03-15"),
        ("registration", "2027-06-20"),
    ]

    again = post(
        admin_client,
        workbook(
            [vehicle(branch=main_branch, color="فضي"), vehicle("12/34568", "MR0AA0000BB000002", branch=main_branch)],
            [
                person(branch=main_branch, residence="30/09/2028"),
                person("سالم", role="مشرف", civil="290010112346", phone="98765433", branch=main_branch),
            ],
        ),
        apply=True,
    ).json()
    assert again["vehicles"] == {"created": 0, "updated": 2} and again["people"] == {"created": 0, "updated": 2}
    assert again["documents"] == 1  # only the renewed residence
    assert len(admin_client.get("/api/v1/vehicles").json()) == 2
    assert {v["color"] for v in admin_client.get("/api/v1/vehicles").json()} == {"فضي", "أبيض"}
    assert db.execute(text("SELECT count(*) FROM people.employees")).scalar() == 2
    assert db.execute(text("SELECT count(*) FROM audit.events WHERE action = 'import.applied'")).scalar() == 2


def test_every_row_error_is_reported_and_nothing_is_imported(admin_client, companies, main_branch, db):
    data = workbook(
        [
            vehicle(branch=main_branch),
            vehicle("12 /34567", "MR0AA0000BB000009", branch=main_branch),  # same plate, other spacing
            vehicle("55/55555", "MR0AA0000BB000003", branch="فرع لا يوجد", insurance="2027-15-03"),
        ],
        [
            person(branch=main_branch, phone="1234"),
            person("Ali", civil="12345", phone="98765439", branch=main_branch),
            person("Omar", civil="", phone="98765440", branch=main_branch),  # civil ID only for visa in process
            person("Visa", civil="", phone="98765441", status="تحت إجراء الفيزا", branch=main_branch),
            person(
                "Zed", civil="290010112350", phone="98765442", status="هارب", company="شركة لا توجد", branch=main_branch
            ),
        ],
    )
    r = post(admin_client, data, apply=True).json()
    assert r["applied"] is False
    found = {(e["sheet"], e["row"], e["code"]) for e in r["errors"]}
    assert found == {
        (VEHICLES, 3, "duplicate_in_file"),
        (VEHICLES, 4, "duplicate_in_file"),
        (VEHICLES, 5, "unknown_value"),
        (PEOPLE, 3, "invalid_phone"),
        (PEOPLE, 4, "invalid_civil_id"),
        (PEOPLE, 5, "field_required"),
        (PEOPLE, 7, "unknown_value"),
    }
    unknown_branch = next(e for e in r["errors"] if e["sheet"] == VEHICLES and e["row"] == 5)
    assert unknown_branch["params"] == {"field": "الفرع", "value": "فرع لا يوجد"}
    assert r["people"]["created"] == 1  # the visa row is fine on its own
    assert db.execute(text("SELECT count(*) FROM people.employees")).scalar() == 0
    assert db.execute(text("SELECT count(*) FROM fleet.vehicles")).scalar() == 0


def test_conflicts_with_existing_records_are_row_errors(admin_client, companies, main_branch):
    admin_client.post(
        "/api/v1/employees",
        json={
            "employee_number": "X1",
            "name": {"ar": "قديم"},
            "company_id": companies["a"]["id"],
            "civil_id": "290010112399",
        },
    )
    r = post(
        admin_client,
        workbook(
            [vehicle(branch=main_branch)],
            [
                person(branch=main_branch, phone="98765450", civil="290010112398"),
                person("Other", civil="290010112397", phone="98765450", branch=main_branch),
            ],  # same phone in file
        ),
    ).json()
    assert {(e["sheet"], e["code"]) for e in r["errors"]} == {(PEOPLE, "duplicate_in_file")}


def test_the_template_must_be_used_as_it_is(admin_client, companies):
    r = post(admin_client, workbook(break_header=True))
    assert r.status_code == 422 and r.json()["code"] == "import_bad_template" and r.json()["params"]["sheet"] == PEOPLE
    r = post(admin_client, b"PK\x03\x04 not really a zip")
    assert r.status_code == 422 and r.json()["code"] == "import_not_xlsx"


def test_permissions_scope_and_salary(admin_client, new_client, companies, main_branch):
    data = workbook([vehicle(branch=main_branch)], [person(branch=main_branch)])
    make_user(admin_client, "viewer", permissions=["employees.view", "vehicles.view"])
    c = new_client()
    login(c, "viewer")
    assert post(c, data).status_code == 403
    make_user(
        admin_client,
        "importer_b",
        company_ids=[companies["b"]["id"]],
        permissions=["employees.create", "employees.update", "vehicles.create", "vehicles.update", "documents.manage"],
    )
    c = new_client()
    login(c, "importer_b")
    r = post(c, data).json()
    assert {e["code"] for e in r["errors"]} == {"company_out_of_scope"}  # the rows belong to company A
    make_user(
        admin_client,
        "importer_a",
        company_ids=[companies["a"]["id"]],
        permissions=["employees.create", "employees.update", "vehicles.create", "vehicles.update", "documents.manage"],
    )
    c = new_client()
    login(c, "importer_a")
    r = post(c, data, apply=True).json()
    assert r["applied"] and [w["code"] for w in r["warnings"]] == ["salary_skipped"]
    assert admin_client.get("/api/v1/employees").json()[0]["basic_salary"] is None


def test_opening_balances_are_imported_once(admin_client, client, companies, main_branch):

    people = [person(branch=main_branch)]
    opening = [["Ahmed Ali", "290010112345", "35.750", "24/10/2026", "المحاسب"]]
    r = post(admin_client, workbook(people=people, opening=opening), apply=True).json()
    assert r["applied"] and r["opening_balances"] == 1
    driver = admin_client.get("/api/v1/employees", params={"is_driver": True}).json()[0]
    statement = admin_client.get(f"/api/v1/cash/drivers/{driver['id']}/statement").json()
    assert statement["posted"] == "35.750" and statement["lines"][0]["kind"] == "opening"
    assert statement["lines"][0]["reason"] == "approved by المحاسب"
    again = post(admin_client, workbook(people=people, opening=opening), apply=True).json()
    assert again["applied"] and again["opening_balances"] == 0  # same amount: unchanged
    changed = post(admin_client, workbook(people=people, opening=[opening[0][:2] + ["40", "24/10/2026", "x"]])).json()
    assert [e["code"] for e in changed["errors"]] == ["opening_balance_exists"]
    unknown = post(admin_client, workbook(opening=[["X", "290010199999", "1", "24/10/2026", "x"]])).json()
    assert [e["code"] for e in unknown["errors"]] == ["unknown_value"]


def test_opening_balances_need_the_cash_permission(admin_client, new_client, companies, main_branch):
    make_user(
        admin_client,
        "importer",
        permissions=["employees.create", "employees.update", "vehicles.create", "vehicles.update", "documents.manage"],
    )
    c = new_client()
    login(c, "importer")
    r = post(
        c,
        workbook(people=[person(branch=main_branch)], opening=[["Ahmed Ali", "290010112345", "1", "24/10/2026", "x"]]),
    ).json()
    assert [(e["sheet"], e["code"]) for e in r["errors"]] == [(OPENING, "permission_denied")]
