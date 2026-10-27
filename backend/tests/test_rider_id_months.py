"""A platform's driver ID by month: an ID worked by another employee from one month to the next. Each month starts as
the one before it, the office moves only the IDs that changed, and a month's sheet is read with that month's IDs: the
same ID's orders are the first employee's last month and the second's this month."""

from app.core.clock import today
from app.modules.payroll.service import add_months
from tests.conftest import make_driver
from tests.test_month_mapping import MAPPING, MONTHLY, file, platform

P = "/api/v1/payroll"
MONTH = today().replace(day=1)
LAST = add_months(MONTH, -1)


def table(admin_client, p, month):
    r = admin_client.get(f"{P}/platforms/{p['id']}/rider-ids", params={"month": str(month)})
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()}


def check(admin_client, p, month, rows):
    form = {"platform_id": str(p["id"]), "month": str(month), "format": "mapped", "replace_month": "false"}
    import json

    form["mapping"] = json.dumps(MAPPING, ensure_ascii=False)
    r = admin_client.post(f"{P}/month-imports/check", data=form, files={"file": ("m.xlsx", file(rows), "x/y")})
    assert r.status_code == 200, r.text
    return r.json()


def test_an_id_moves_to_another_employee_from_a_month_and_each_months_sheet_follows(admin_client, company):
    k = platform(admin_client, "kmove", MONTHLY)
    a = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="K-7")
    b = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="K-8")

    first = table(admin_client, k, LAST)  # nothing recorded yet: the IDs on the drivers' files
    assert (first[a["id"]]["rider_id"], first[b["id"]]["rider_id"]) == ("K-7", "K-8")

    url = f"{P}/platforms/{k['id']}/rider-ids/{b['id']}"
    r = admin_client.put(url, json={"month": str(MONTH), "rider_id": "K-7"})  # b works a's ID this month
    assert r.status_code == 200, r.text
    now = {x["id"]: x for x in r.json()}
    assert (now[b["id"]]["rider_id"], now[b["id"]]["previous"], now[b["id"]]["changed"]) == ("K-7", "K-8", True)
    assert now[a["id"]]["rider_id"] is None and now[a["id"]]["previous"] == "K-7"
    before = table(admin_client, k, LAST)  # last month stays as it was
    assert (before[a["id"]]["rider_id"], before[b["id"]]["rider_id"]) == ("K-7", "K-8")
    after = table(admin_client, k, add_months(MONTH, 1))  # a month with nothing of its own follows this one
    assert (after[a["id"]]["rider_id"], after[b["id"]]["rider_id"]) == (None, "K-7")
    files = {d["id"]: d["platform_driver_id"] for d in admin_client.get(f"{P}/platforms/{k['id']}/drivers").json()}
    assert files == {a["id"]: None, b["id"]: "K-7"}  # this month's IDs are on the files too

    row = [["K-7", 1, None, None, 100, None, None, ""]]
    assert [d["employee"]["id"] for d in check(admin_client, k, LAST, row)["drivers"]] == [a["id"]]
    assert [d["employee"]["id"] for d in check(admin_client, k, MONTH, row)["drivers"]] == [b["id"]]

    r = admin_client.put(f"{P}/platforms/{k['id']}/rider-ids/{a['id']}", json={"month": str(MONTH), "rider_id": "K-9"})
    assert table(admin_client, k, MONTH)[a["id"]]["rider_id"] == "K-9"
    r = admin_client.put(url, json={"month": str(MONTH), "rider_id": ""})  # none this month
    assert r.status_code == 200 and table(admin_client, k, MONTH)[b["id"]]["rider_id"] is None


def test_a_driver_put_on_the_platform_after_the_months_began_works_his_id_from_now(admin_client, company):
    k = platform(admin_client, "knew", MONTHLY)
    a = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="N-1")
    r = admin_client.put(f"{P}/platforms/{k['id']}/rider-ids/{a['id']}", json={"month": str(MONTH), "rider_id": "N-2"})
    assert r.status_code == 200, r.text
    c = make_driver(admin_client, company["id"], platform_id=k["id"], platform_driver_id="N-3")  # after the list began
    assert table(admin_client, k, MONTH)[c["id"]]["rider_id"] == "N-3"
    assert table(admin_client, k, LAST)[c["id"]]["rider_id"] is None  # not back in time
    row = [["N-3", 1, None, None, 10, None, None, ""]]
    assert [d["employee"]["id"] for d in check(admin_client, k, MONTH, row)["drivers"]] == [c["id"]]
