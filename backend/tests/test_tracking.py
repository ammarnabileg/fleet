"""GPS during custody: the ingest contract (stored + rejected = every point sent, resend-safe); UAT-13 tracking
follows the custody and stops at the return; UAT-14 signal loss alerts; UAT-15 fake locations are rejected and
logged; the live map per company; route history; phone health alerts."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle


def now():
    return datetime.now(UTC)


@pytest.fixture
def on_duty(admin_client, client, company):
    """A driver with a bound phone, holding a vehicle since an hour ago."""
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    custody = hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=1)).isoformat())
    return {"vehicle": v, "driver": d, "custody": custody, "headers": bearer(bind_device(client, d["phone"]))}


def point(seq, t, lat=29.3759, lng=47.9774, **extra):
    return {"seq": seq, "recorded_at": t.isoformat(), "lat": lat, "lng": lng, "speed_kmh": 40, **extra}


def send(client, headers, points, sent_at=None):
    r = client.post(
        "/api/v1/driver/positions", headers=headers, json={"sent_at": (sent_at or now()).isoformat(), "points": points}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_uat15_every_point_is_stored_or_rejected_and_a_resend_is_safe(client, on_duty, db):
    t = now() - timedelta(minutes=5)
    batch = [
        point(1, t),
        point(2, t + timedelta(seconds=30), lat=29.38),
        point(3, t + timedelta(seconds=60), is_mock=True),
        point(4, t + timedelta(seconds=90), lat=95),
        point(5, now() + timedelta(hours=1)),
        point(6, now() - timedelta(hours=3)),  # before the custody started
        point(7, t + timedelta(seconds=120), lat=0, lng=0),
    ]
    ack = send(client, on_duty["headers"], batch)
    assert ack["stored_seqs"] == [1, 2]
    assert {r["seq"]: r["reason"] for r in ack["rejected"]} == {
        3: "mock",
        4: "invalid",
        5: "future",
        6: "no_custody",
        7: "invalid",
    }
    again = send(client, on_duty["headers"], batch)  # the answer was lost: the app sends everything again
    assert again["stored_seqs"] == ack["stored_seqs"] and again["rejected"] == ack["rejected"]
    assert db.execute(text("SELECT count(*) FROM tracking.positions")).scalar() == 2
    assert db.execute(text("SELECT count(*) FROM tracking.rejected_points")).scalar() == 5
    assert db.execute(text("SELECT count(*) FROM tracking.mock_events")).scalar() == 1


def test_mock_location_alerts_once_a_day(admin_client, client, on_duty):
    t = now() - timedelta(minutes=2)
    send(client, on_duty["headers"], [point(1, t, is_mock=True)])
    send(client, on_duty["headers"], [point(2, t + timedelta(seconds=5), is_mock=True)])
    alerts = admin_client.get("/api/v1/alerts").json()
    assert [a["kind"] for a in alerts] == ["mock_location"] and alerts[0]["severity"] == "critical"


def test_a_wrong_phone_clock_is_corrected(client, on_duty, db):
    phone_now = now() - timedelta(hours=2)  # the phone clock is two hours behind
    ack = send(client, on_duty["headers"], [point(1, phone_now - timedelta(seconds=10))], sent_at=phone_now)
    assert ack["stored_seqs"] == [1]
    recorded, offset = db.execute(text("SELECT recorded_at, device_offset_s FROM tracking.positions")).one()
    assert abs((recorded - (now() - timedelta(seconds=10))).total_seconds()) < 5
    assert abs(offset - 7200) < 5


def test_live_map_per_company_and_last_position(admin_client, client, new_client, companies, on_duty):
    t = now() - timedelta(minutes=3)
    send(client, on_duty["headers"], [point(1, t + timedelta(seconds=60), lat=29.1), point(2, t, lat=29.0)])
    send(client, on_duty["headers"], [point(3, t - timedelta(minutes=1), lat=28.0)])  # late, older point
    live = admin_client.get("/api/v1/tracking/live").json()
    assert len(live) == 1
    assert live[0]["position"]["lat"] == 29.1 and live[0]["signal_lost"] is False
    assert live[0]["driver"]["id"] == on_duty["driver"]["id"]
    make_user(admin_client, "map_b", permissions=["tracking.live"], company_ids=[companies["b"]["id"]])
    c = new_client()
    login(c, "map_b")
    assert c.get("/api/v1/tracking/live").json() == []
    make_user(admin_client, "no_map", permissions=["vehicles.view"])
    c = new_client()
    login(c, "no_map")
    assert c.get("/api/v1/tracking/live").status_code == 403
    assert c.get("/api/v1/tracking/live/stream").status_code == 403


def test_live_stream_only_carries_the_companies_in_scope(companies):
    from app.core import live
    from app.modules.tracking import service

    a, b = companies["a"]["id"], companies["b"]["id"]

    async def run():
        stream = service.live_events({a}, keepalive=0.05, max_events=1)
        assert (await anext(stream)).startswith("retry:")
        assert await anext(stream) == ": keep-alive\n\n"  # subscribed now
        live.broker().publish(b, {"plate": "B"})
        live.broker().publish(a, {"plate": "A"})
        return [e async for e in stream if not e.startswith(":")]

    assert asyncio.run(run()) == ['event: position\ndata: {"plate": "A"}\n\n']


@pytest.fixture
def live_server(app):
    """The app on a real HTTP server: the test client buffers whole responses and cannot read an endless stream."""
    import socket
    import threading
    import time

    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(5)


def test_live_stream_endpoint_streams_published_positions(live_server, superuser, client, on_duty):
    import threading

    import httpx

    from tests.conftest import PASSWORD

    received = []
    http = httpx.Client(base_url=live_server, timeout=10)
    assert http.post("/api/v1/auth/login", json={"username": superuser, "password": PASSWORD}).status_code == 200

    def listen():
        with http.stream("GET", "/api/v1/tracking/live/stream") as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if line.startswith("data:"):
                    received.append(line)
                    return

    thread = threading.Thread(target=listen, daemon=True)
    thread.start()
    for seq in range(1, 50):  # until the stream is subscribed and carries the event
        send(client, on_duty["headers"], [point(seq, now() - timedelta(seconds=60 - seq))])
        thread.join(timeout=0.1)
        if received:
            break
    http.close()
    assert received and on_duty["vehicle"]["plate_number"] in received[0]


def test_route_history(admin_client, client, new_client, companies, on_duty):
    t = now() - timedelta(minutes=30)
    send(client, on_duty["headers"], [point(i, t + timedelta(minutes=i), lat=29.0 + i * 0.01) for i in range(5)])
    r = admin_client.get("/api/v1/tracking/route", params={"custody_id": on_duty["custody"]["id"]})
    assert r.status_code == 200
    route = r.json()
    assert [p["lat"] for p in route["points"]] == [29.0, 29.01, 29.02, 29.03, 29.04]
    assert 4.0 < route["distance_km"] < 5.0 and route["from"] and route["truncated"] is False
    params = {
        "vehicle_id": on_duty["vehicle"]["id"],
        "start": (t - timedelta(days=3)).isoformat(),
        "end": now().isoformat(),
    }
    r = admin_client.get("/api/v1/tracking/route", params=params)
    assert r.status_code == 422 and r.json()["code"] == "range_too_long"
    make_user(admin_client, "hist_b", permissions=["tracking.history"], company_ids=[companies["b"]["id"]])
    c = new_client()
    login(c, "hist_b")
    assert c.get("/api/v1/tracking/route", params={"custody_id": on_duty["custody"]["id"]}).status_code == 404


def test_uat14_signal_loss_alerts_once_per_silence(admin_client, client, on_duty, db):
    from app.modules.tracking import service

    send(client, on_duty["headers"], [point(1, now() - timedelta(minutes=30))])
    assert service.scan_signal_loss(db) == 1
    assert service.scan_signal_loss(db) == 0
    alert = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()[0]
    assert alert["kind"] == "signal_lost" and "30 minutes" in alert["message"]
    assert admin_client.post(f"/api/v1/alerts/{alert['id']}/ack").status_code == 204
    assert service.scan_signal_loss(db) == 0  # acknowledged: the same silence does not come back
    assert admin_client.get("/api/v1/tracking/live").json()[0]["signal_lost"] is True
    send(client, on_duty["headers"], [point(2, now() - timedelta(seconds=10))])
    assert admin_client.get("/api/v1/tracking/live").json()[0]["signal_lost"] is False
    assert service.scan_signal_loss(db) == 0


def test_a_new_point_closes_the_open_signal_alert(admin_client, client, on_duty, db):
    from app.modules.tracking import service

    service.scan_signal_loss(db)  # no point at all since the handover an hour ago
    assert [a["kind"] for a in admin_client.get("/api/v1/alerts").json()] == ["signal_lost"]
    send(client, on_duty["headers"], [point(1, now())])
    assert admin_client.get("/api/v1/alerts").json() == []


def test_phone_health_alerts_during_custody_only(admin_client, client, company, on_duty):
    h = on_duty["headers"]
    r = client.post(
        "/api/v1/driver/status",
        headers=h,
        json={"location_permission": "while_in_use", "gps_enabled": False, "battery_level": 40},
    )
    assert r.status_code == 200 and r.json()["tracking_required"] and r.json()["interval_moving_s"] == 30
    kinds = sorted(a["kind"] for a in admin_client.get("/api/v1/alerts").json())
    assert kinds == ["gps_off", "location_permission_off"]
    client.post("/api/v1/driver/status", headers=h, json={"location_permission": "while_in_use", "gps_enabled": False})
    assert len(admin_client.get("/api/v1/alerts").json()) == 2  # one open alert per situation
    client.post("/api/v1/driver/status", headers=h, json={"location_permission": "always", "gps_enabled": True})
    assert admin_client.get("/api/v1/alerts").json() == []  # healthy again: closed by itself
    off_duty = make_driver(admin_client, company["id"])
    r = client.post(
        "/api/v1/driver/status", headers=bearer(bind_device(client, off_duty["phone"])), json={"gps_enabled": False}
    )
    assert r.json()["tracking_required"] is False
    assert admin_client.get("/api/v1/alerts").json() == []


def test_uat13_tracking_stops_at_the_return(admin_client, client, on_duty):
    from tests.conftest import upload

    admin_client.post(
        f"/api/v1/custodies/{on_duty['custody']['id']}/return",
        json={"odometer_km": 10_050, "photo_sha256": upload(admin_client)},
    )
    ack = send(client, on_duty["headers"], [point(1, now() - timedelta(minutes=30)), point(2, now())])
    assert ack["stored_seqs"] == [1] and ack["rejected"] == [{"seq": 2, "reason": "no_custody"}]
    assert admin_client.get("/api/v1/tracking/live").json() == []
    status = client.post("/api/v1/driver/status", headers=on_duty["headers"], json={"gps_enabled": True}).json()
    assert status["tracking_required"] is False  # the app stops tracking


def test_partitions_need_no_privilege_beyond_two_functions(database_url, db):
    from app.modules.tracking import service

    service.maintain_partitions(db)
    names = {
        n
        for (n,) in db.execute(
            text(
                "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = 'tracking.positions'::regclass"
            )
        )
    }
    assert len(names) >= 3
    assert db.execute(text("SELECT current_user")).scalar() == "fleet_app"
    engine = create_engine(database_url["app_url"])
    with engine.connect() as c:
        c.execute(text("SELECT tracking.ensure_month_partition('2031-01-01')"))
        c.commit()
        with pytest.raises(DBAPIError, match="permission denied"):
            c.execute(text("CREATE TABLE tracking.sneaky (id int)"))
        c.rollback()
        with pytest.raises(DBAPIError, match="must be owner"):
            c.execute(text("DROP TABLE tracking.positions_2031_01"))
    engine.dispose()
