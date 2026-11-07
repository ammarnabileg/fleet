"""A driver's cash balance read the same everywhere: positive, he owes it to the company (cash he holds); negative, the
company owes it to him (a credit to settle). The dashboard, the cash page, the cash report and their exports keep the
two apart and give the net, never one netted figure that hides either; every driver with a balance is listed, whatever
his app access."""

import io
from datetime import timedelta

from openpyxl import load_workbook

from app.core.clock import today
from tests.conftest import make_driver

ADJ = "/api/v1/cash/adjustments"


def adjust(admin_client, driver, amount):
    r = admin_client.post(ADJ, json={"driver_id": driver["id"], "amount": amount, "reason": "رصيد افتتاحي للاختبار"})
    assert r.status_code == 201, r.text


def test_owed_by_and_owed_to_drivers_kept_apart_everywhere(admin_client, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    owes = make_driver(admin_client, a)
    owed = make_driver(admin_client, a)
    no_app = make_driver(admin_client, b, app=False)  # no app access: still owes the company
    adjust(admin_client, owes, "50")
    adjust(admin_client, owed, "-20")
    adjust(admin_client, no_app, "7.250")

    dash = admin_client.get("/api/v1/dashboard").json()
    assert dash["driver_cash"] == {
        "owed_by_drivers": "57.250",
        "owed_to_drivers": "20.000",
        "net": "37.250",
        "drivers_owing": 2,
        "drivers_owed": 1,
    }
    assert dash["cash"]["held_by_drivers"] == "37.250"  # the old key, the net, until the dashboard reads driver_cash
    rows = {r["company_id"]: r for r in dash["by_company"]}
    assert (rows[a]["cash_owed_by_drivers"], rows[a]["cash_owed_to_drivers"], rows[a]["cash_held"]) == (
        "50.000",
        "20.000",
        "30.000",
    )
    assert rows[b]["cash_owed_by_drivers"] == "7.250" and rows[b]["cash_owed_to_drivers"] == "0.000"

    # the cash page: every driver with a balance, each with its side
    balances = {x["driver"]["id"]: x for x in admin_client.get("/api/v1/cash/balances").json()}
    assert {k: (v["total"], v["side"]) for k, v in balances.items()} == {
        owes["id"]: ("50.000", "owes"),
        owed["id"]: ("-20.000", "owed"),
        no_app["id"]: ("7.250", "owes"),
    }

    # the export: the side as a key in CSV, in words in Excel
    csv = admin_client.get("/api/v1/reports/cash-balances").content.decode("utf-8").splitlines()
    assert csv[0].lstrip("﻿") == "driver,approved,unapproved,total,over_limit,balance_side"
    assert sorted(line.rsplit(",", 1)[1] for line in csv[1:]) == ["owed", "owes", "owes"]
    r = admin_client.get("/api/v1/reports/cash-balances", params={"format": "xlsx"}, headers={"Accept-Language": "ar"})
    ws = load_workbook(io.BytesIO(r.content)).active
    sheet = list(ws.values)
    assert sheet[0][-1] == "اتجاه الرصيد"
    assert {float(row[3]): row[5] for row in sheet[1:]}[-20] == "له عند الشركة (يحتاج تسوية)"

    # the cash report: the same split in its totals, each row with its total and side
    params = {"date_from": str(today() - timedelta(days=6)), "date_to": str(today())}
    rep = admin_client.get("/api/v1/reports/cash", params=params).json()
    totals = rep["aging"]["totals"]
    assert (totals["owed_by_drivers"], totals["owed_to_drivers"], totals["net"]) == ("57.250", "20.000", "37.250")
    assert (totals["drivers_owing"], totals["drivers_owed"]) == (2, 1)
    assert sorted((x["total"], x["side"]) for x in rep["aging"]["rows"]) == [
        ("-20.000", "owed"),
        ("50.000", "owes"),
        ("7.250", "owes"),
    ]
    csv = admin_client.get("/api/v1/reports/cash", params=params | {"format": "csv"}).content.decode("utf-8")
    assert csv.splitlines()[0].endswith(",oldest,total,balance_side")
    assert ",-20.000,owed" in csv


def test_a_company_user_sees_only_his_drivers_balances(admin_client, new_client, companies):
    from tests.conftest import login, make_user

    a, b = companies["a"]["id"], companies["b"]["id"]
    adjust(admin_client, make_driver(admin_client, a), "-15")
    mine = make_driver(admin_client, b)
    adjust(admin_client, mine, "9")
    make_user(admin_client, "cash_b", permissions=["dashboard.view", "cash.view"], company_ids=[b])
    c = new_client()
    login(c, "cash_b")
    assert c.get("/api/v1/dashboard").json()["driver_cash"] == {
        "owed_by_drivers": "9.000",
        "owed_to_drivers": "0.000",
        "net": "9.000",
        "drivers_owing": 1,
        "drivers_owed": 0,
    }
    assert [x["driver"]["id"] for x in c.get("/api/v1/cash/balances").json()] == [mine["id"]]
