"""The daily report's evidence (BRD FR-DWR-02, FR-DWR-05, FR-DWR-08): today's report after a started day waits for the
end-of-day odometer photo and reading; the reviewer sees the day's readings and distance beside the driver's averages
over the 30 days before; orders or cash far from the average are flagged, by a percent the client sets."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.core.clock import KUWAIT, today
from tests.conftest import bearer, bind_device, hand_over, jpeg, make_driver, make_vehicle, upload
from tests.test_odometer import _camera
from tests.test_report_alerts import send_report


def at(day, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=KUWAIT)


def _id(db, table: str, public_id: str) -> int:
    return db.execute(text(f"SELECT id FROM {table} WHERE public_id = :p"), {"p": public_id}).scalar()  # noqa: S608


def read(client, h, kind: str, km: int, when: datetime | None = None):
    return client.post(
        "/api/v1/driver/odometer",
        headers=h,
        json={
            "kind": kind,
            "value_km": km,
            "photo_sha256": _camera(client, h),
            "recorded_at": (when or datetime.now(UTC)).isoformat(),
        },
    )


def on_the_road(admin_client, client, company, km=30_000):
    v = make_vehicle(admin_client, company["id"], km=km)
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    c = hand_over(admin_client, v, d, km=km, started_at=(datetime.now(UTC) - timedelta(days=6)).isoformat())
    return v, d, h, c


def setting(admin_client, **value):
    current = admin_client.get("/api/v1/settings").json()["daily_report"]
    r = admin_client.put(
        "/api/v1/settings/daily_report", json={"version": current["version"], "value": current["value"] | value}
    )
    assert r.status_code == 200, r.text


def test_todays_report_waits_for_the_end_of_day_reading(admin_client, client, new_client, company, db):
    v, d, h, c = on_the_road(admin_client, client, company)
    assert client.get("/api/v1/driver/reports/form", headers=h).json()["end_reading"] is True
    # yesterday started and never closed: its report, sent late, is not held back
    yesterday = today() - timedelta(days=1)
    assert read(client, h, "start_day", 30_010, at(yesterday, 10)).status_code == 201
    assert send_report(client, h, yesterday)["late"] is True
    # today: started, the report is refused until the day is closed
    assert read(client, h, "start_day", 30_200).status_code == 201
    shot = client.post(
        "/api/v1/driver/files", params={"source": "upload"}, headers=h, files={"file": ("s.jpg", jpeg(), "image/jpeg")}
    ).json()["sha256"]
    body = {"business_date": str(today()), "orders_count": 5, "cash_amount": "10", "screenshot_sha256": shot}
    r = client.post("/api/v1/driver/reports", headers=h, json=body)
    assert r.status_code == 409 and r.json()["code"] == "end_reading_required"
    assert client.get("/api/v1/driver/today", headers=h).json()["end_day_done"] is False
    assert read(client, h, "end_day", 30_290).status_code == 201
    assert client.get("/api/v1/driver/today", headers=h).json()["end_day_done"] is True
    send_report(client, h, today())

    # the vehicle returned by the office closes the day too
    other = new_client()
    v2, d2, h2, c2 = on_the_road(admin_client, other, company, km=50_000)
    assert read(other, h2, "start_day", 50_010).status_code == 201
    r = admin_client.post(
        f"/api/v1/custodies/{c2['id']}/return", json={"odometer_km": 50_060, "photo_sha256": upload(admin_client)}
    )
    assert r.status_code == 200, r.text
    assert other.get("/api/v1/driver/today", headers=h2).json() == {
        "custody": None,
        "start_day_done": False,
        "end_day_done": False,
    }
    send_report(other, h2, today())

    # a client who does not ask for it
    third = new_client()
    _, _, h3, _ = on_the_road(admin_client, third, company, km=70_000)
    assert read(third, h3, "start_day", 70_010).status_code == 201
    setting(admin_client, require_end_reading=False)
    assert third.get("/api/v1/driver/reports/form", headers=h3).json()["end_reading"] is False
    send_report(third, h3, today())


def history(db, admin_client, d, v, c, rows):
    """Past days straight into the tables: (days back, orders, cash, approved cash, status, start km, end km[, start
    hour])."""
    eid, vid, cid = (
        _id(db, "people.employees", d["id"]),
        _id(db, "fleet.vehicles", v["id"]),
        _id(db, "fleet.custodies", c["id"]),
    )
    company_id = db.execute(text("SELECT company_id FROM people.employees WHERE id = :e"), {"e": eid}).scalar()
    photo = upload(admin_client)
    db.execute(text("UPDATE fleet.custodies SET started_at = now() - interval '40 days' WHERE id = :c"), {"c": cid})
    for back, orders, cash, approved, status, start_km, end_km, *start_hour in rows:
        day = today() - timedelta(days=back)
        db.execute(
            text(
                "INSERT INTO daily_ops.reports (employee_id, company_id, business_date, orders_count, cash_amount, "
                "approved_cash, status, submitted_at) VALUES (:e, :co, :d, :o, :c, :a, :s, :t)"
            ),
            {
                "e": eid,
                "co": company_id,
                "d": day,
                "o": orders,
                "c": cash,
                "a": approved,
                "s": status,
                "t": at(day, 21),
            },
        )
        for kind, km, hour in (("start_day", start_km, (start_hour or [9])[0]), ("end_day", end_km, 20)):
            if km is None:
                continue
            db.execute(
                text(
                    "INSERT INTO fleet.odometer_readings (vehicle_id, custody_id, driver_id, kind, value_km, "
                    "photo_sha256, recorded_at, business_date) VALUES (:v, :c, :d, :k, :km, :p, :t, :b)"
                ),
                {"v": vid, "c": cid, "d": eid, "k": kind, "km": km, "p": photo, "t": at(day, hour), "b": day},
            )
    db.commit()


def test_the_reviewer_sees_the_odometer_and_the_drivers_average(admin_client, client, new_client, company, db):
    v, d, h, c = on_the_road(admin_client, client, company, km=30_000)
    history(
        db,
        admin_client,
        d,
        v,
        c,
        [
            (7, 20, "10", None, "approved", 30_000, 30_100),
            (6, 20, "10", None, "approved", 30_200, 30_300),
            (5, 20, "10", None, "approved", 30_400, 30_500),
            (4, 20, "10", None, "approved", 30_600, 30_700),
            (3, 20, "9", "12", "approved", 30_800, None, 21),  # counted at the approved cash; never closed
            (2, 20, "10", None, "approved", 31_000, 31_160, 8),  # its close is not the evening before's
            (8, 500, "900", None, "rejected", None, None),  # refused: not in the average
            (31, 500, "900", None, "approved", None, None),  # before the 30 days
        ],
    )
    assert read(client, h, "start_day", 31_200).status_code == 201
    assert read(client, h, "end_day", 31_280).status_code == 201
    report = send_report(client, h, today())  # 5 orders, 10 cash
    r = admin_client.get(f"/api/v1/daily-reports/{report['id']}/evidence")
    assert r.status_code == 200, r.text
    ev = r.json()
    assert (ev["start"]["km"], ev["end"]["km"], ev["km"]) == (31_200, 31_280, 80)
    assert ev["start"]["kind"] == "start_day" and ev["end"]["kind"] == "end_day"
    assert ev["average"] == {"days": 6, "orders": "20.0", "cash": "10.333", "km": 112, "km_days": 5}
    assert ev["deviations"] == ["orders"]  # 5 against 20; 10 cash is near 10.333
    listed = {x["id"]: x for x in admin_client.get("/api/v1/daily-reports").json()}
    assert listed[report["id"]]["deviations"] == ["orders"]
    # with the history in the same page (all statuses), each report keeps its own 30 days
    everything = {x["id"]: x for x in admin_client.get("/api/v1/daily-reports", params={"status": ""}).json()}
    assert len(everything) == 9 and everything[report["id"]]["deviations"] == ["orders"]
    assert client.get("/api/v1/driver/reports", headers=h).json()[0]["deviations"] == []  # the reviewers' only

    photos = [admin_client.get(f"/api/v1/daily-reports/{report['id']}/odometer/{w}") for w in ("start", "end")]
    assert [p.status_code for p in photos] == [200, 200] and photos[0].content != photos[1].content
    assert all(p.headers["content-type"].startswith("image/") for p in photos)
    assert new_client().get(f"/api/v1/daily-reports/{report['id']}/odometer/end", headers=h).status_code == 401

    # approved, it is not part of its own average
    assert admin_client.post(f"/api/v1/daily-reports/{report['id']}/approve", json={}).status_code == 200
    assert admin_client.get(f"/api/v1/daily-reports/{report['id']}/evidence").json()["average"]["days"] == 6
    # the percent is the client's: 75% off is within 80%
    setting(admin_client, deviation_percent=80)
    assert admin_client.get(f"/api/v1/daily-reports/{report['id']}/evidence").json()["deviations"] == []
    setting(admin_client, deviation_percent=70)
    assert admin_client.get(f"/api/v1/daily-reports/{report['id']}/evidence").json()["deviations"] == ["orders"]


def test_too_little_history_flags_nothing(admin_client, client, company, db):
    v, d, h, c = on_the_road(admin_client, client, company, km=40_000)
    history(db, admin_client, d, v, c, [(back, 20, "10", None, "approved", None, None) for back in (2, 3, 4, 5)])
    report = send_report(client, h, today())  # no reading today: nothing to wait for
    ev = admin_client.get(f"/api/v1/daily-reports/{report['id']}/evidence").json()
    assert ev["average"]["days"] == 4 and ev["deviations"] == []
    assert (ev["start"], ev["end"], ev["km"], ev["average"]["km"]) == (None, None, None, None)
    assert admin_client.get(f"/api/v1/daily-reports/{report['id']}/odometer/start").status_code == 404
    assert Decimal(ev["average"]["cash"]) == Decimal("10.000")
