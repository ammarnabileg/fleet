"""The daily report's deadlines (BRD FR-DWR-07, BR-04, BR-05, TRK-13 / UAT-10): who started the day and sent no
report is named at the end of it and reminded in the app; a report sent after its own day shows as late; one left
unreviewed is escalated to the manager; distance driven off duty names both drivers."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.clock import today
from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload
from tests.test_odometer import _camera


def started(admin_client, client, company, km=40_000):
    """A driver holding a vehicle who sent this morning's start-of-day reading."""
    v = make_vehicle(admin_client, company["id"], km=km)
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    hand_over(admin_client, v, d, started_at=(datetime.now(UTC) - timedelta(hours=3)).isoformat())
    r = client.post(
        "/api/v1/driver/odometer",
        headers=h,
        json={
            "kind": "start_day",
            "value_km": km + 5,
            "photo_sha256": _camera(client, h),
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return d, h


def send_report(client, h, day) -> dict:
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    r = client.post(
        "/api/v1/driver/reports",
        headers=h,
        json={"business_date": str(day), "orders_count": 5, "cash_amount": "10", "screenshot_sha256": shot},
    )
    assert r.status_code == 201, r.text
    return r.json()


def open_alerts(admin_client, kind) -> list[dict]:
    return [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == kind]


def test_started_the_day_and_sent_no_report(admin_client, client, new_client, company, db):
    from app.modules.daily_ops import service

    d, h = started(admin_client, client, company)
    other = new_client()
    d2, h2 = started(admin_client, other, company, km=50_000)
    send_report(other, h2, today())
    make_driver(admin_client, company["id"])  # did not start: owes nothing
    took = make_driver(admin_client, company["id"])  # took a vehicle today, never started the day: owes nothing
    hand_over(admin_client, make_vehicle(admin_client, company["id"], km=70_000), took, km=70_000)

    assert service.scan_missing(db, today() - timedelta(days=1)) == 0  # nobody started yesterday
    assert service.scan_missing(db) == 1
    assert service.scan_missing(db) == 0  # once a day
    (alert,) = open_alerts(admin_client, "daily_report_missing")
    assert d["name"]["ar"] in alert["message"] and str(today()) in alert["message"]
    told = client.get("/api/v1/driver/notifications", headers=h).json()["items"]
    assert [n["kind"] for n in told] == ["report_missing"]
    assert other.get("/api/v1/driver/notifications", headers=h2).json()["items"] == []
    # sent after all, the same evening: the alert closes
    send_report(client, h, today())
    assert open_alerts(admin_client, "daily_report_missing") == []


def test_a_report_sent_after_its_own_day_is_late(admin_client, client, company):
    d, h = started(admin_client, client, company)
    yesterday = send_report(client, h, today() - timedelta(days=1))
    on_time = send_report(client, h, today())
    assert (yesterday["late"], on_time["late"]) == (True, False)
    listed = {r["id"]: r["late"] for r in admin_client.get("/api/v1/daily-reports").json()}
    assert listed[yesterday["id"]] is True and listed[on_time["id"]] is False


def test_an_unreviewed_report_is_escalated_to_the_manager(admin_client, client, new_client, company, owner_db, db):
    from app.modules.daily_ops import service

    d, h = started(admin_client, client, company)
    report = send_report(client, h, today())
    other = send_report(client, h, today() - timedelta(days=1))
    owner_db.execute(text("UPDATE daily_ops.reports SET submitted_at = now() - interval '25 hours'"))
    owner_db.commit()
    service.scan_overdue(db)
    make_user(admin_client, "superv", permissions=["daily_reports.review"])
    make_user(admin_client, "boss", permissions=["daily_reports.escalations"])
    sup, boss = new_client(), new_client()
    login(sup, "superv")
    login(boss, "boss")
    assert [a["kind"] for a in sup.get("/api/v1/alerts").json()] == ["daily_report_overdue"] * 2
    assert [a["kind"] for a in boss.get("/api/v1/alerts").json()] == ["daily_report_escalated"] * 2
    # the management template holds the permission; reviewed either way, all close
    perms = {r["code"]: r["permissions"] for r in admin_client.get("/api/v1/roles").json()}
    assert "daily_reports.escalations" in perms["management"] and "daily_reports.escalations" not in perms["supervisor"]
    assert admin_client.post(f"/api/v1/daily-reports/{report['id']}/approve", json={}).status_code == 200
    r = admin_client.post(f"/api/v1/daily-reports/{other['id']}/reject", json={"reason": "لقطة قديمة"})
    assert r.status_code == 200, r.text
    assert (
        open_alerts(admin_client, "daily_report_escalated") == open_alerts(admin_client, "daily_report_overdue") == []
    )


def test_off_duty_distance_names_the_driver_who_handed_and_the_one_who_took(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"], km=60_000)
    first, second = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, first, km=60_000, started_at=(datetime.now(UTC) - timedelta(hours=9)).isoformat())
    r = admin_client.post(
        f"/api/v1/custodies/{c['id']}/return",
        json={
            "odometer_km": 60_100,
            "photo_sha256": upload(admin_client),
            "ended_at": (datetime.now(UTC) - timedelta(hours=6)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    hand_over(admin_client, v, second, km=60_130)  # 30 km nobody accounts for
    (alert,) = open_alerts(admin_client, "odometer_off_duty")
    assert first["name"]["ar"] in alert["message"] and second["name"]["ar"] in alert["message"]
    assert alert["message"].index(first["name"]["ar"]) < alert["message"].index(second["name"]["ar"])
