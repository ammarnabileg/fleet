"""A driver who ended his day may start it again: the business day holds several work sessions, one open at a time,
each with its own end reading and report. The day's distance and figures are their sum; payroll counts the day
once (test_daily_fields)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.core.clock import KUWAIT, today
from app.modules.daily_ops import service
from tests.conftest import jpeg
from tests.test_report_alerts import open_alerts, send_report
from tests.test_report_evidence import at, on_the_road, read


def driver_today(client, h) -> dict:
    return client.get("/api/v1/driver/today", headers=h).json()


def post_report(client, h, orders: int = 1):
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    body = {"business_date": str(today()), "orders_count": orders, "cash_amount": "1", "screenshot_sha256": shot}
    return client.post("/api/v1/driver/reports", headers=h, json=body)


def test_the_driver_starts_again_after_ending_the_day(admin_client, client, company):
    v, d, h, c = on_the_road(admin_client, client, company)
    now = datetime.now(UTC)
    first, end1, second, end2 = (now - timedelta(minutes=m) for m in (40, 30, 20, 10))
    if first.astimezone(KUWAIT).date() != today():  # just after midnight: the whole day in the last minutes
        first, end1, second, end2 = (now - timedelta(seconds=s) for s in (4, 3, 2, 1))
    assert driver_today(client, h) | {"custody": None} == {
        "custody": None,
        "start_day_done": False,
        "end_day_done": False,
        "sessions": 0,
    }
    assert read(client, h, "start_day", 30_010, first).status_code == 201
    # the day is open: another start is refused for what it is, the same one sent again is already there
    r = read(client, h, "start_day", 30_015, end1)
    assert r.status_code == 409 and r.json()["code"] == "day_already_started"
    r = read(client, h, "start_day", 30_010, first)
    assert r.status_code == 409 and r.json()["code"] == "reading_exists"
    assert read(client, h, "end_day", 30_050, end1).status_code == 201
    r = read(client, h, "end_day", 30_055, second)
    assert r.status_code == 409 and r.json()["code"] == "day_already_ended"
    assert driver_today(client, h) | {"custody": None} == {
        "custody": None,
        "start_day_done": True,
        "end_day_done": True,
        "sessions": 1,
    }
    one = send_report(client, h, today())
    assert one["session"] == 1

    # he starts again: the day is open once more, and its report waits for the end reading
    assert read(client, h, "start_day", 30_060, second).status_code == 201
    assert driver_today(client, h) | {"custody": None} == {
        "custody": None,
        "start_day_done": True,
        "end_day_done": False,
        "sessions": 2,
    }
    r = post_report(client, h)
    assert r.status_code == 409 and r.json()["code"] == "end_reading_required"
    assert read(client, h, "end_day", 30_110, end2).status_code == 201
    two = send_report(client, h, today())
    assert (two["session"], two["status"]) == (2, "submitted")
    # sent again without a new start: the same session's report, to edit
    again = post_report(client, h)
    assert again.status_code == 409 and again.json()["params"]["report_id"] == two["id"]

    # the reviewer sees the day: its first start, its last end, the distance of both sessions
    ev = admin_client.get(f"/api/v1/daily-reports/{two['id']}/evidence").json()
    assert (ev["start"]["km"], ev["end"]["km"], ev["km"]) == (30_010, 30_110, 90)
    listed = admin_client.get("/api/v1/daily-reports", params={"business_date": str(today())}).json()
    assert sorted(r["session"] for r in listed if r["driver"]["id"] == d["id"]) == [1, 2]

    # each session's cash is its own collection: both wait, and approving one leaves the other waiting
    cash = client.get("/api/v1/driver/cash", headers=h).json()
    assert (D(cash["posted"]), D(cash["pending"])) == (D("0"), D("20"))
    assert admin_client.post(f"/api/v1/daily-reports/{one['id']}/approve", json={}).status_code == 200
    cash = client.get("/api/v1/driver/cash", headers=h).json()
    assert (D(cash["posted"]), D(cash["pending"])) == (D("10"), D("10"))
    listed = admin_client.get("/api/v1/daily-reports", params={"business_date": str(today())}).json()
    assert next(r for r in listed if r["id"] == two["id"])["status"] == "submitted"


def test_a_night_shift_ends_after_midnight_and_the_day_still_closes(admin_client, client, company):
    v, d, h, c = on_the_road(admin_client, client, company)
    now = datetime.now(UTC)
    midnight = datetime.combine(today(), datetime.min.time(), tzinfo=KUWAIT)
    step = (now - midnight) / 4
    assert read(client, h, "start_day", 30_010, at(today() - timedelta(days=1), 22)).status_code == 201
    assert read(client, h, "end_day", 30_080, midnight + step).status_code == 201  # yesterday's shift, ended today
    assert read(client, h, "start_day", 30_100, midnight + 2 * step).status_code == 201
    # this evening's end is today's second end of day, after its own start: accepted (it was refused before)
    assert read(client, h, "end_day", 30_150, now).status_code == 201
    assert driver_today(client, h) | {"custody": None} == {
        "custody": None,
        "start_day_done": True,
        "end_day_done": True,
        "sessions": 1,
    }


def test_a_second_session_without_its_report_is_missed_at_the_end_of_the_day(admin_client, client, company, db):
    v, d, h, c = on_the_road(admin_client, client, company)
    now = datetime.now(UTC)
    times = [now - timedelta(minutes=m) for m in (40, 30, 20)]
    if times[0].astimezone(KUWAIT).date() != today():
        times = [now - timedelta(seconds=s) for s in (3, 2, 1)]
    assert read(client, h, "start_day", 30_010, times[0]).status_code == 201
    assert read(client, h, "end_day", 30_050, times[1]).status_code == 201
    send_report(client, h, today())
    assert service.scan_missing(db) == 0
    assert read(client, h, "start_day", 30_060, times[2]).status_code == 201
    assert service.scan_missing(db) == 1  # started again and sent nothing for it
    assert [a for a in open_alerts(admin_client, "daily_report_missing") if a["entity_id"] == d["id"]]
