"""Odometer: UAT-07 start of day needs photo and number; UAT-08 a correction keeps both values and the reason;
UAT-09 a lower reading is accepted and sent to review; UAT-10 distance between end of day and next start alerts;
UAT-19 a start of day sent late keeps its original time."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import bearer, bind_device, hand_over, jpeg, login, make_driver, make_user, make_vehicle, upload


def now():
    return datetime.now(UTC)


def _return(admin_client, custody, km, **extra):
    r = admin_client.post(
        f"/api/v1/custodies/{custody['id']}/return",
        json={"odometer_km": km, "photo_sha256": upload(admin_client), **extra},
    )
    assert r.status_code == 200, r.text


def test_uat08_uat09_a_lower_reading_goes_to_review_and_a_correction_is_audited(admin_client, company, db):
    v = make_vehicle(admin_client, company["id"], km=80_000)
    c = hand_over(admin_client, v, make_driver(admin_client, company["id"]), km=79_900)
    readings = admin_client.get("/api/v1/odometer/readings", params={"review_status": "pending"}).json()
    assert len(readings) == 1 and readings[0]["flags"] == ["lower_than_previous"]
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["odometer_lower"]
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["last_odometer_km"] == 79_900
    r = admin_client.post(
        f"/api/v1/odometer/readings/{readings[0]['id']}/review",
        json={"corrected_km": 80_100, "reason": "photo shows 80100"},
    )
    assert r.status_code == 200
    out = r.json()
    assert (out["value_km"], out["corrected_km"], out["effective_km"], out["review_status"]) == (
        79_900,
        80_100,
        80_100,
        "reviewed",
    )
    assert admin_client.get(f"/api/v1/vehicles/{v['id']}").json()["last_odometer_km"] == 80_100
    before, after = db.execute(text("SELECT before, after FROM audit.events WHERE action = 'odometer.reviewed'")).one()
    assert before["corrected_km"] is None and after["corrected_km"] == 80_100
    # the next reading is compared with the corrected value
    _return(admin_client, c, 80_050)
    last = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v["id"]}).json()[0]
    assert last["kind"] == "return" and last["flags"] == ["lower_than_previous"]


def test_daily_limit_and_off_duty_distance_are_flagged(admin_client, company):
    v = make_vehicle(admin_client, company["id"], km=10_000)
    d = make_driver(admin_client, company["id"])
    start = now() - timedelta(days=3)
    c = hand_over(admin_client, v, d, km=10_000, started_at=start.isoformat())
    _return(admin_client, c, 10_900, ended_at=(start + timedelta(hours=10)).isoformat())  # 900 km in one day
    hand_over(admin_client, v, d, km=10_950, started_at=(start + timedelta(days=1)).isoformat())  # moved 50 km idle
    flags = {
        r["kind"]: r["flags"]
        for r in admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v["id"]}).json()
    }
    assert flags["return"] == ["daily_limit"]
    kinds = sorted(a["kind"] for a in admin_client.get("/api/v1/alerts").json())
    assert kinds == ["odometer_daily_limit", "odometer_off_duty"]
    readings = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v["id"]}).json()
    assert [r["flags"] for r in readings][0] == ["off_duty_km"]


def test_a_reused_photo_is_flagged(admin_client, company):
    photo = jpeg()
    v1, v2 = make_vehicle(admin_client, company["id"]), make_vehicle(admin_client, company["id"])
    sha = upload(admin_client, photo)
    for v in (v1, v2):
        r = admin_client.post(
            "/api/v1/custodies",
            json={
                "vehicle_id": v["id"],
                "odometer_km": 10_000,
                "driver_id": make_driver(admin_client, company["id"])["id"],
                "photo_sha256": sha,
            },
        )
        assert r.status_code == 201
    second = admin_client.get("/api/v1/odometer/readings", params={"vehicle_id": v2["id"]}).json()[0]
    assert second["flags"] == ["photo_reused"]


def test_start_of_day_from_the_driver_app(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"], km=20_000)
    d = make_driver(admin_client, company["id"])
    tokens = bind_device(client, d["phone"])
    h = bearer(tokens)
    r = client.post("/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=h)
    assert r.status_code == 201
    camera = r.json()["sha256"]
    body = {"value_km": 20_050, "photo_sha256": camera, "recorded_at": now().isoformat(), "lat": 29.37, "lng": 47.97}
    r = client.post("/api/v1/driver/odometer", json=body, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "no_open_custody"
    hand_over(admin_client, v, d, km=20_000, started_at=(now() - timedelta(hours=1)).isoformat())
    assert client.get("/api/v1/driver/today", headers=h).json()["start_day_done"] is False
    office_photo = upload(admin_client)
    r = client.post("/api/v1/driver/odometer", json=body | {"photo_sha256": office_photo}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "photo_not_from_camera"
    r = client.post(
        "/api/v1/driver/odometer", json=body | {"recorded_at": (now() - timedelta(days=3)).isoformat()}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_recorded_at"
    r = client.post("/api/v1/driver/odometer", json=body, headers=h)
    assert r.status_code == 201 and r.json()["source"] == "device" and r.json()["flags"] == []
    today = client.get("/api/v1/driver/today", headers=h).json()
    assert today["start_day_done"] and today["custody"]["last_odometer_km"] == 20_050
    r2 = client.post("/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=h)
    r = client.post("/api/v1/driver/odometer", json=body | {"photo_sha256": r2.json()["sha256"]}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "reading_exists"
    # the camera endpoint takes images only
    r = client.post("/api/v1/driver/files", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=h)
    assert r.status_code == 415
    # another device's camera photo is refused too
    other = make_driver(admin_client, company["id"])
    t2 = bind_device(client, other["phone"])
    foreign = client.post(
        "/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=bearer(t2)
    ).json()["sha256"]
    r = client.post("/api/v1/driver/odometer", json=body | {"kind": "end_day", "photo_sha256": foreign}, headers=h)
    assert r.json()["code"] == "photo_not_from_camera"


def test_review_needs_permission_and_scope(admin_client, new_client, companies):
    a, b = companies["a"], companies["b"]
    v = make_vehicle(admin_client, b["id"], km=5_000)
    hand_over(admin_client, v, make_driver(admin_client, b["id"]), km=4_000)
    reading = admin_client.get("/api/v1/odometer/readings").json()[0]
    make_user(admin_client, "viewer_b", permissions=["odometer.view"], company_ids=[b["id"]])
    make_user(admin_client, "reviewer_a", permissions=["odometer.view", "odometer.review"], company_ids=[a["id"]])
    c = new_client()
    login(c, "viewer_b")
    assert c.get(f"/api/v1/odometer/readings/{reading['id']}/photo").status_code == 200
    r = c.post(f"/api/v1/odometer/readings/{reading['id']}/review", json={"reason": "ok as is"})
    assert r.status_code == 403
    c = new_client()
    login(c, "reviewer_a")
    assert c.get("/api/v1/odometer/readings").json() == []
    assert c.post(f"/api/v1/odometer/readings/{reading['id']}/review", json={"reason": "ok as is"}).status_code == 404
    assert c.get("/api/v1/alerts").json() == []  # the alert belongs to company B


def _camera(client, headers):
    r = client.post("/api/v1/driver/files", files={"file": ("p.jpg", jpeg(), "image/jpeg")}, headers=headers)
    assert r.status_code == 201
    return r.json()["sha256"]


def test_uat07_start_of_day_needs_the_photo_and_the_number(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    hand_over(
        admin_client, make_vehicle(admin_client, company["id"]), d, started_at=(now() - timedelta(hours=1)).isoformat()
    )
    body = {"value_km": 10_010, "photo_sha256": _camera(client, h), "recorded_at": now().isoformat()}
    for missing in ("value_km", "photo_sha256"):
        r = client.post("/api/v1/driver/odometer", json={k: v for k, v in body.items() if k != missing}, headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", missing
    assert client.post("/api/v1/driver/odometer", json=body, headers=h).status_code == 201


def test_uat10_distance_between_end_of_day_and_next_start_alerts(admin_client, client, company):
    v = make_vehicle(admin_client, company["id"], km=30_000)
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=40)).isoformat())
    end = {
        "kind": "end_day",
        "value_km": 30_150,
        "photo_sha256": _camera(client, h),
        "recorded_at": (now() - timedelta(hours=20)).isoformat(),
    }
    assert client.post("/api/v1/driver/odometer", json=end, headers=h).status_code == 201
    start = {
        "kind": "start_day",
        "value_km": 30_162,
        "photo_sha256": _camera(client, h),
        "recorded_at": (now() - timedelta(hours=8)).isoformat(),
    }
    r = client.post("/api/v1/driver/odometer", json=start, headers=h)
    assert r.status_code == 201 and r.json()["flags"] == ["off_duty_km"] and r.json()["review_status"] == "pending"
    alert = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()[0]
    assert alert["kind"] == "odometer_off_duty" and "12 km" in alert["message"]


def test_uat19_a_start_of_day_sent_late_keeps_its_original_time(admin_client, client, company):
    from app.core.clock import business_date

    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    hand_over(
        admin_client, make_vehicle(admin_client, company["id"]), d, started_at=(now() - timedelta(hours=30)).isoformat()
    )
    taken = now() - timedelta(hours=26)  # taken offline yesterday, sent now
    r = client.post(
        "/api/v1/driver/odometer",
        headers=h,
        json={"value_km": 10_005, "photo_sha256": _camera(client, h), "recorded_at": taken.isoformat()},
    )
    assert r.status_code == 201
    assert datetime.fromisoformat(r.json()["recorded_at"]) == taken
    assert r.json()["business_date"] == str(business_date(taken))


def test_a_late_reading_higher_than_the_one_after_it_is_flagged(admin_client, client, company):
    """An offline phone sends this morning's reading after the vehicle was already returned with a lower one."""
    v = make_vehicle(admin_client, company["id"], km=50_000)
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    c = hand_over(admin_client, v, d, km=50_000, started_at=(now() - timedelta(hours=10)).isoformat())
    _return(admin_client, c, 50_300, ended_at=(now() - timedelta(hours=1)).isoformat())
    assert admin_client.get("/api/v1/odometer/readings", params={"review_status": "pending"}).json() == []

    def late(kind, km, hours_ago):
        taken = (now() - timedelta(hours=hours_ago)).isoformat()
        r = client.post(
            "/api/v1/driver/odometer",
            headers=h,
            json={"kind": kind, "value_km": km, "photo_sha256": _camera(client, h), "recorded_at": taken},
        )
        assert r.status_code == 201, r.text
        return r.json()

    assert late("start_day", 50_200, 3)["flags"] == []  # fits between the handover and the return
    assert late("end_day", 50_400, 2)["flags"] == ["higher_than_next"]
    alerts = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()
    assert [a["kind"] for a in alerts] == ["odometer_higher_than_next"]
    assert "50400" in alerts[0]["message"] and "50300" in alerts[0]["message"]


def test_a_handover_at_the_moment_of_the_return_is_not_compared_with_it_as_next(admin_client, company):
    v = make_vehicle(admin_client, company["id"], km=60_000)
    c = hand_over(
        admin_client, v, make_driver(admin_client, company["id"]), started_at=(now() - timedelta(hours=5)).isoformat()
    )
    moment = (now() - timedelta(hours=2)).isoformat()
    _return(admin_client, c, 60_100, ended_at=moment)
    nxt = hand_over(admin_client, v, make_driver(admin_client, company["id"]), km=60_110, started_at=moment)
    flags = admin_client.get(f"/api/v1/custodies/{nxt['id']}").json()["readings"][0]["flags"]
    assert flags == ["off_duty_km"]  # 10 km idle: yes; "higher than the next reading": the return is not next
