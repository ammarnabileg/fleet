"""A scheme's rules as blocks through the whole month: made from a template, versions «يسري من شهر» in the designer,
a driver's month (statement, monthly fields, exceptions, the partner's batch rows) paid by the run, the payslip
explaining each line, approved months never changed, and every existing scheme written as blocks by the migration
with the same money."""

import io
from decimal import Decimal as D

import openpyxl
import pytest
from sqlalchemy import text

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.conftest import bearer, bind_device, make_driver

P = "/api/v1/payroll"
MONTH = today().replace(day=1)
NEXT = add_months(MONTH, 1)
IBAN = "KW81CBKU0000000000001234560101"


def set_cap(client):
    version = client.get("/api/v1/settings").json()["payroll"]["version"]
    r = client.put(
        "/api/v1/settings/payroll",
        json={"version": version, "value": {"max_deduction_percent": "50.00", "deduction_cap_base": "gross"}},
    )
    assert r.status_code == 200, r.text


def platform(admin_client, code):
    r = admin_client.post(f"{P}/platforms", json={"code": code, "name": {"ar": code, "en": code}, "daily_fields": []})
    assert r.status_code == 201, r.text
    return r.json()


def from_template(admin_client, p, template, code):
    r = admin_client.post(
        f"{P}/schemes/from-template",
        json={"platform_id": p["id"], "template": template, "code": code, "name": {"ar": code, "en": code}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def assign(admin_client, s, *drivers, month=MONTH, **extra):
    r = admin_client.post(
        f"{P}/schemes/{s['id']}/assign",
        json={"employee_ids": [d["id"] for d in drivers], "month": str(month)} | extra,
    )
    assert r.status_code == 200 and r.json()["set"] == len(drivers), r.text


def statement(admin_client, d, **figures):
    r = admin_client.post(f"{P}/statements", json={"employee_id": d["id"], "month": str(MONTH)} | figures)
    assert r.status_code == 201, r.text


def values(admin_client, d, **data):
    r = admin_client.put(f"{P}/month-review/{d['id']}", json={"month": str(MONTH)} | data)
    assert r.status_code == 200, r.text


def run_lines(admin_client, company):
    run = admin_client.post(f"{P}/runs", json={"company_id": company["id"], "month": str(MONTH)})
    assert run.status_code == 201, run.text
    return run.json(), {x["employee"]["id"]: x for x in run.json()["lines"]}


def test_keeta_as_actually_paid_through_the_run(admin_client, client, company, payroll_live):
    set_cap(admin_client)
    k = platform(admin_client, "kpaid")
    s = from_template(admin_client, k, "keeta_paid", "as_paid")
    assert (
        s["calculator"] == "blocks"
        and s["designed"]
        and [b["type"] for b in s["blocks"]][:2]
        == [
            "fixed_salary",
            "target_overage",
        ]
    )
    drv = {}
    for name, basic, orders, marks, star in (
        ("a", "200.000", 603, 0, False),
        ("b", "165.000", 293, 0, False),
        ("c", "300.000", 310, 2, False),
        ("d", "250.000", 400, 0, True),
    ):
        drv[name] = make_driver(admin_client, company["id"], basic_salary=basic, iban=IBAN, platform_id=k["id"])
        statement(admin_client, drv[name], orders=orders, tips="1.500" if name == "a" else "0")
        values(admin_client, drv[name], values={"attendance_marks": marks, "star_day_failed": star})
    assign(admin_client, s, *drv.values())
    run, lines = run_lines(admin_client, company)
    a, b, c, d = (lines[drv[x]["id"]] for x in "abcd")
    assert (a["gross"], a["net"], a["flags"]) == ("348.000", "348.000", [])  # 200 + 146.5 + tips 1.5
    assert [(x["code"], x["amount"]) for x in a["breakdown"]] == [
        ("fixed_salary", "200.000"),
        ("target_bonus", "146.500"),
    ]
    assert a["breakdown"][1]["formula"] == "(603 − 310) × 0.500 = 146.500" and a["breakdown"][1]["block"] == 2
    assert a["cells"]["fixed_salary"] == "200.000" and a["cells"]["target_bonus"] == "146.500"
    assert b["net"] == "156.500" and b["cells"]["target_shortfall"] == "8.500"  # 165 - 8.5
    assert c["net"] == "260.000" and c["cells"]["marks_deduction"] == "40.000"  # 300 - 2 x 20
    assert d["net"] == "195.000" and d["cells"]["special_day_deduction"] == "100.000"  # 250 + 45 - 100 (invalid)

    # an approved exception day excuses the star day (the template's star-day block neutralizes it)
    r = admin_client.post(
        f"{P}/month-exceptions",
        json={"employee_id": drv["d"]["id"], "month": str(MONTH), "kind": "accepted_excuse", "excuses": ["marks"],
              "note": "عذر عن العلامات"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    again = admin_client.post(f"{P}/runs/{run['id']}/recompute").json()
    assert next(x for x in again["lines"] if x["employee"]["id"] == drv["d"]["id"])["net"] == "195.000"  # not the star
    r = admin_client.post(
        f"{P}/month-exceptions",
        json={"employee_id": drv["d"]["id"], "month": str(MONTH), "kind": "accepted_excuse", "excuses": ["star_day"],
              "note": "يوم النجمة معتمد"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    again = admin_client.post(f"{P}/runs/{run['id']}/recompute").json()
    assert next(x for x in again["lines"] if x["employee"]["id"] == drv["d"]["id"])["net"] == "295.000"

    # approved: the payslip names every line in both languages, with its formula
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").json()["status"] == "approved"
    h = bearer(bind_device(client, drv["a"]["phone"]))
    slip = client.get("/api/v1/driver/payslips", headers=h).json()[0]
    bonus = slip["breakdown"][1]
    assert bonus["label"] == {"ar": "مكافأة تجاوز التارجت", "en": "Target overage bonus"}
    assert bonus["formula"] == "(603 − 310) × 0.500 = 146.500" and slip["net"] == "348.000"


def test_a_missing_figure_is_flagged_never_guessed(admin_client, company):
    set_cap(admin_client)
    k = platform(admin_client, "kmiss")
    s = from_template(admin_client, k, "keeta_paid", "as_paid")
    d = make_driver(admin_client, company["id"], basic_salary="200.000", iban=IBAN, platform_id=k["id"])
    statement(admin_client, d, orders=500)
    assign(admin_client, s, d)
    _, lines = run_lines(admin_client, company)
    line = lines[d["id"]]
    assert "figures_missing" in line["flags"] and line["breakdown"] == []
    review = admin_client.get(f"{P}/month-review", params={"platform_id": k["id"], "month": str(MONTH)}).json()
    assert review["rows"][0]["missing"] == ["attendance_marks", "star_day_failed"]


def test_talabat_as_paid_from_the_partners_batch_report(admin_client, company):
    set_cap(admin_client)
    t = platform(admin_client, "tpaid")
    s = from_template(admin_client, t, "talabat_batch_paid", "as_paid")
    a = make_driver(admin_client, company["id"], iban=IBAN, platform_id=t["id"], platform_driver_id="T-1")
    b = make_driver(admin_client, company["id"], iban=IBAN, platform_id=t["id"], platform_driver_id="T-2")
    assign(admin_client, s, a)
    assign(admin_client, s, b, personal_rate="0.800")  # a flat rate agreed with him, across batches
    wb = openpyxl.Workbook()
    header = ["Rider ID", "Batch No.", "Total Completed Deliveries"]
    for row in (header, ["T-1", 4, 118], ["T-1", 2, 39], ["T-2", 1, 50], ["T-2", 3, 50]):
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    r = admin_client.post(
        f"{P}/month-imports",
        data={"platform_id": str(t["id"]), "month": str(MONTH), "format": "partner_batches"},
        files={"file": ("p.xlsx", buf.getvalue(), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    _, lines = run_lines(admin_client, company)
    la, lb = lines[a["id"]], lines[b["id"]]
    assert la["gross"] == "92.200" and la["cells"]["orders_pay"] == "92.200"  # 118 x 0.550 + 39 x 0.700
    assert [(x["why"]["batch_level"], x["amount"]) for x in la["breakdown"]] == [(2, "27.300"), (4, "64.900")]
    assert lb["gross"] == "80.000" and lb["breakdown"][0]["why"]["personal"] is True  # 100 x 0.800


def test_versions_in_the_designer(admin_client, company, payroll_live, owner_db):
    set_cap(admin_client)
    p = platform(admin_client, "vers")
    s = from_template(admin_client, p, None, "plain")  # blank: one price per order to set
    d = admin_client.get(f"{P}/schemes/{s['id']}/designer").json()
    assert [v["blocks"][0]["params"]["rate"] for v in d["versions"]] == ["0.000"] and not d["used"]
    rate = {"type": "per_order", "params": {"rate": "0.400", "source": "orders"}}
    url = f"{P}/schemes/{s['id']}/blocks"
    r = admin_client.post(url, json={"version": d["scheme"]["version"], "blocks": [rate]})
    assert r.status_code == 200 and len(r.json()["versions"]) == 1, r.text  # nobody paid on it: redefined
    bad = admin_client.post(url, json={"version": r.json()["scheme"]["version"], "blocks": [{"type": "nope"}]})
    assert bad.status_code == 422 and bad.json()["code"] == "rule_block_unknown"

    drv = make_driver(admin_client, company["id"], iban=IBAN, platform_id=p["id"])
    assign(admin_client, s, drv)
    statement(admin_client, drv, orders=100)
    run, lines = run_lines(admin_client, company)
    assert lines[drv["id"]]["gross"] == "40.000"
    assert admin_client.post(f"{P}/runs/{run['id']}/approve").json()["status"] == "approved"

    d = admin_client.get(f"{P}/schemes/{s['id']}/designer").json()
    assert d["used"] and d["change_from"] == str(NEXT)
    version = d["scheme"]["version"]
    r = admin_client.post(url, json={"version": version, "blocks": [rate | {"params": {"rate": "0.500"}}]})
    assert r.status_code == 422 and r.json()["params"]["field"] == "effective_month"
    r = admin_client.post(url, json={"version": version, "blocks": [rate], "effective_month": str(MONTH)})
    assert r.status_code == 409 and r.json()["code"] == "scheme_version_month"  # this month is paid
    change = {"type": "per_order", "params": {"rate": "0.500", "source": "orders"}}
    r = admin_client.post(
        url, json={"version": version, "blocks": [change], "effective_month": str(NEXT), "note": "زيادة"}
    )
    assert r.status_code == 200, r.text
    vs = r.json()["versions"]
    assert [(v["version_no"], v["effective_month"], v["blocks"][0]["params"]["rate"]) for v in vs] == [
        (2, str(NEXT), "0.500"),
        (1, str(MONTH), "0.400"),
    ]
    # the approved month keeps what it paid
    line = owner_db.execute(
        text(
            "SELECT gross, scheme_version FROM payroll.lines l JOIN payroll.runs r ON r.id = l.run_id WHERE r.id = "
            "(SELECT id FROM payroll.runs WHERE public_id = :p)"
        ),  # fmt: skip
        {"p": run["id"]},
    ).first()
    assert (line.gross, line.scheme_version) == (D("40.000"), 1)
    # the old form cannot change a designed scheme's terms
    s2 = next(x for x in admin_client.get(f"{P}/schemes").json() if x["id"] == s["id"])
    r = admin_client.patch(
        f"{P}/schemes/{s['id']}", json={"version": s2["version"], "per_order": "1.000", "effective_month": str(NEXT)}
    )
    assert r.status_code == 409 and r.json()["code"] == "scheme_designed"
    r = admin_client.patch(f"{P}/schemes/{s['id']}", json={"version": s2["version"], "is_active": False})
    assert r.status_code == 200 and not r.json()["is_active"]


def test_company_covers_follow_the_expense_blocks(admin_client):
    p = platform(admin_client, "covers")
    assert from_template(admin_client, p, "talabat_fixed_550", "f550")["company_covers"] == ["housing", "maintenance"]
    assert from_template(admin_client, p, "talabat_fixed_350", "f350")["company_covers"] == [
        "gas",
        "housing",
        "maintenance",
        "sim",
    ]
    r = admin_client.post(
        f"{P}/schemes/from-template",
        json={"platform_id": p["id"], "template": "nope", "code": "x_1", "name": {"ar": "x", "en": "x"}},
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ the migration


@pytest.mark.parametrize("paid", [False, True])
def test_the_migration_writes_every_scheme_as_blocks_with_the_same_money(database_url, admin_engine, paid):
    import itertools
    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from app.modules.payroll import calculators as calc
    from app.modules.payroll.calculators import Month, Rules, Step
    from app.modules.payroll.rules.engine import Facts, run, validate
    from tests.conftest import BACKEND, _url

    name = f"fleet_mig_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        cfg.set_main_option("sqlalchemy.url", _url(name).replace("%", "%%"))
        command.upgrade(cfg, "0050_platform_fields")
        engine = create_engine(_url(name))
        with engine.begin() as c:
            pid = c.scalar(text("SELECT id FROM payroll.platforms WHERE code = 'keeta'"))
            schemes = {
                "keeta": ("tiered_target", "0.350", "0.350", "0.200",
                          [("tier_bonus", 450, 50), ("tier_bonus", 540, 90), ("tier_bonus", 710, 200),
                           ("marks_deduction", 3, 10), ("marks_deduction", 4, 30), ("marks_reduce", 5, None)]),
                "batch": ("batch", None, None, None, [("batch_rate", 1, "0.700"), ("batch_rate", 3, "0.600")]),
                "fixed": ("per_order", "0.550", "0.100", None, []),
            }  # fmt: skip
            ids = {}
            for code, (calculator, per_order, missing, reduced, steps) in schemes.items():
                ids[code] = c.scalar(
                    text(
                        "INSERT INTO payroll.schemes (platform_id, code, name, calculator, per_order,"
                        " missing_order_rate, reduced_rate, created_by)"
                        ' VALUES (:p, :c, \'{"ar": "x"}\', :calc, :po, :m, :r, 1) RETURNING id'
                    ),
                    {"p": pid, "c": code, "calc": calculator, "po": per_order, "m": missing, "r": reduced},
                )
                rows = [{"kind": k, "threshold": str(t), "amount": None if a is None else str(a)} for k, t, a in steps]
                c.execute(
                    text(
                        "INSERT INTO payroll.scheme_versions (scheme_id, version_no, effective_month, per_order,"
                        " target_orders, required_valid_days, missing_order_rate, reduced_rate, bonus_when_reduced,"
                        " marks_when_reduced, floor_at_zero, steps) VALUES (:s, 1, :m, :po, 420, 28, :mr, :r, false,"
                        " false, true, CAST(:st AS jsonb))"
                    ),
                    {
                        "s": ids[code],
                        "m": MONTH,
                        "po": per_order,
                        "mr": missing,
                        "r": reduced,
                        "st": __import__("json").dumps(rows),
                    },  # fmt: skip
                )
            if paid:  # the keeta scheme paid this month: its blocks start next month
                company = c.scalar(text("""INSERT INTO org.companies (name, cr_number) VALUES ('{"ar": "ش"}', 'CR-9')
                                           RETURNING id"""))  # fmt: skip
                emp = c.scalar(
                    text(
                        "INSERT INTO people.employees"
                        " (employee_number, name, company_id, branch_id, status_code, is_driver)"
                        """ VALUES ('M1', '{"ar": "س"}', :c, (SELECT min(id) FROM org.branches),"""
                        " (SELECT code FROM people.employment_statuses LIMIT 1), true) RETURNING id"
                    ),
                    {"c": company},
                )
                r = c.scalar(
                    text(
                        "INSERT INTO payroll.runs (company_id, month, status, cap_percent, cap_base, prepared_by,"
                        " approved_at) VALUES (:c, :m, 'approved', 50, 'gross', 1, now()) RETURNING id"
                    ),
                    {"c": company, "m": MONTH},
                )
                c.execute(
                    text(
                        "INSERT INTO payroll.lines (run_id, employee_id, cells, gross, deductions, net, scheme_id)"
                        " VALUES (:r, :e, '{}', 0, 0, 0, :s)"
                    ),
                    {"r": r, "e": emp, "s": ids["keeta"]},
                )
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            versions = {
                code: c.execute(
                    text(
                        "SELECT version_no, effective_month, blocks FROM payroll.scheme_versions"
                        " WHERE scheme_id = :s ORDER BY version_no"
                    ),  # fmt: skip
                    {"s": i},
                ).all()
                for code, i in ids.items()
            }
        engine.dispose()
        keeta = versions["keeta"]
        if paid:  # the paid month keeps its calculator; the blocks are the next version, from the next month
            assert [(v.version_no, v.effective_month, v.blocks is None) for v in keeta] == [
                (1, MONTH, True),
                (2, NEXT, False),
            ]
        else:  # never paid on: the version itself is written as blocks
            assert [(v.version_no, v.blocks is None) for v in keeta] == [(1, False)]

        def steps(rows):
            out = {}
            for k, t, a in rows:
                out.setdefault(k, []).append(Step(D(str(t)), None if a is None else D(str(a))))
            return out

        old = {
            "keeta": Rules(calculator="tiered_target", per_order=D("0.350"), missing_order_rate=D("0.350"),
                           reduced_rate=D("0.200"), steps=steps(schemes["keeta"][4])),
            "batch": Rules(calculator="batch", steps=steps(schemes["batch"][4])),
            "fixed": Rules(calculator="per_order", per_order=D("0.550"), missing_order_rate=D("0.100")),
        }  # fmt: skip
        for code, rules in old.items():
            blocks = validate(versions[code][-1].blocks)
            for orders, marks, star, level in itertools.product((0, 300, 449, 540, 800), (0, 3, 4, 6), (False, True),
                                                                (1, 2, 3)):  # fmt: skip
                month = Month(orders=orders, attendance_marks=marks, star_day_failed=star, batch_level=level)
                a = calc.run(rules, month)
                b = run(blocks, Facts(orders=orders, attendance_marks=marks, star_day_failed=star, batch_level=level))
                assert [(i.code, i.amount) for i in b.items] == [(i.code, i.amount) for i in a.items], (code, month)
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_what_a_block_cannot_read_or_price_flags_the_line_never_the_run(admin_client, company, owner_db):
    set_cap(admin_client)
    k = platform(admin_client, "kflags")
    paid = from_template(admin_client, k, "keeta_paid", "as_paid")
    nobasic = make_driver(admin_client, company["id"], iban=IBAN, platform_id=k["id"])  # no basic salary on his file
    owner_db.execute(text("UPDATE people.employees SET basic_salary = NULL WHERE public_id = :p"), {"p": nobasic["id"]})
    owner_db.commit()
    statement(admin_client, nobasic, orders=400)
    values(admin_client, nobasic, values={"attendance_marks": 0, "star_day_failed": False})
    assign(admin_client, paid, nobasic)

    t = platform(admin_client, "tflags")
    batch = from_template(admin_client, t, "talabat_batch_paid", "as_paid")  # batches 1 to 6
    seventh = make_driver(admin_client, company["id"], iban=IBAN, platform_id=t["id"])
    values(admin_client, seventh, batches=[{"batch": 7, "orders": 10}])
    assign(admin_client, batch, seventh)

    broken = from_template(admin_client, t, None, "broken")
    owner_db.execute(  # a stored block the checks would refuse today (a day's wage over 0 days)
        text(
            "UPDATE payroll.scheme_versions SET blocks = CAST(:b AS jsonb) WHERE scheme_id ="
            " (SELECT id FROM payroll.schemes WHERE public_id = :s)"
        ),
        {
            "s": broken["id"],
            "b": '[{"type": "fixed_salary", "params": {"mode": "amount", "amount": "300.000"}, "condition": [],'
            ' "on_exception": "none", "group": null, "label": null}, {"type": "absence", "params": {"mode":'
            ' "daily_wage", "divisor": 0}, "condition": [], "on_exception": "none", "group": null, "label": null}]',
        },
    )
    owner_db.commit()
    victim = make_driver(admin_client, company["id"], iban=IBAN, platform_id=t["id"])
    values(admin_client, victim, values={"absent_days": 2})
    assign(admin_client, broken, victim)

    run, lines = run_lines(admin_client, company)  # the run is made: each problem stays on its own line
    assert "figures_missing" in lines[nobasic["id"]]["flags"]
    review = admin_client.get(f"{P}/month-review", params={"platform_id": k["id"], "month": str(MONTH)}).json()
    assert review["rows"][0]["missing"] == ["basic_salary"]
    assert "rules_incomplete" in lines[seventh["id"]]["flags"]
    assert any(x.get("info") == "batch_rate_missing" for x in lines[seventh["id"]]["trace"])
    assert lines[victim["id"]]["flags"] == ["rules_error"] and lines[victim["id"]]["gross"] == "0.000"
    assert run["blocking"] == 3


def test_the_sheet_shows_a_rule_deduction_and_a_higher_price_as_earned(admin_client, company):
    set_cap(admin_client)
    p = platform(admin_client, "cells")
    s = from_template(admin_client, p, None, "cells")
    d = admin_client.get(f"{P}/schemes/{s['id']}/designer").json()
    blocks = [
        {"type": "fixed_salary", "params": {"mode": "contract"}},
        {"type": "per_order", "params": {"rate": "0.300"}},
        {"type": "invalid_days", "params": {"mode": "fixed", "amount": "5"}},
        {"type": "price_change", "params": {"rate": "0.400", "mode": "separate"},
         "condition": [{"fact": "orders", "op": "gte", "value": 100}]},
    ]  # fmt: skip
    r = admin_client.post(f"{P}/schemes/{s['id']}/blocks", json={"version": d["scheme"]["version"], "blocks": blocks})
    assert r.status_code == 200, r.text
    drv = make_driver(admin_client, company["id"], basic_salary="200.000", iban=IBAN, platform_id=p["id"])
    statement(admin_client, drv, orders=100, working_days=26, valid_days=24)
    assign(admin_client, s, drv)
    _, lines = run_lines(admin_client, company)
    cells = lines[drv["id"]]["cells"]
    assert cells["invalid_days_deduction"] == "10.000"  # 2 days x 5: the block's, on the sheet
    assert cells["orders_pay"] == "40.000" and not cells.get("price_change")  # 30 + 10 more: earned, no deduction
    assert lines[drv["id"]]["net"] == "230.000"


def test_a_migrated_scheme_saved_in_the_designer_keeps_what_the_company_covers(admin_client):
    import importlib.util

    from tests.conftest import BACKEND

    spec = importlib.util.spec_from_file_location("m51", BACKEND / "migrations" / "versions" / "0051_scheme_blocks.py")
    m51 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m51)
    version = {"per_order": "0.550", "missing_order_rate": None, "target_orders": 420, "steps": [],
               "company_covers": ["gas", "sim"]}  # fmt: skip
    migrated = m51.blocks_of("per_order", version) + m51.covers_of(version)
    p = platform(admin_client, "covmig")
    s = from_template(admin_client, p, None, "migrated")
    d = admin_client.get(f"{P}/schemes/{s['id']}/designer").json()
    r = admin_client.post(f"{P}/schemes/{s['id']}/blocks", json={"version": d["scheme"]["version"], "blocks": migrated})
    assert r.status_code == 200, r.text
    saved = next(x for x in admin_client.get(f"{P}/schemes").json() if x["id"] == s["id"])
    assert saved["company_covers"] == ["gas", "sim"]  # the fuel claims still see the company paying for gas
    from app.modules.payroll.calculators import Rules
    from app.modules.payroll.rules import convert

    same = convert.from_rules(Rules(calculator="per_order", per_order=D("0.550")), ["gas", "sim"])
    assert [b["params"] for b in same if b["type"] == "expense"] == [
        b["params"] for b in migrated if b["type"] == "expense"
    ]
