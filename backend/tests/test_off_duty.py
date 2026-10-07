"""Movement outside the work day (BRD FR-TRK-09): in custody but before the driver's start of day or after his end of
day is his own time. The route marks it, and the route, the live map and its stream show it only to who holds
tracking.off_duty; the others see the work day alone."""

import asyncio
import json
from datetime import timedelta

from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle, upload
from tests.test_reports_more import _id, reading
from tests.test_tracking import now, point, send

KM = 11.12  # 0.1 degree of latitude


def history(admin_client, client, company, db):
    """Custody since ten hours ago: his day from 8 to 3 hours ago; a point before it, two in it, two after it."""
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=10)).isoformat())
    headers = bearer(bind_device(client, d["phone"]))
    vid, did, cid = (
        _id(db, "fleet.vehicles", v["id"]),
        _id(db, "people.employees", d["id"]),
        _id(db, "fleet.custodies", c["id"]),
    )
    photo = upload(admin_client)
    reading(db, vid, cid, did, "start_day", 10_010, now() - timedelta(hours=8), photo)
    reading(db, vid, cid, did, "end_day", 10_100, now() - timedelta(hours=3), photo)
    db.commit()
    hours = (9, 6, 5, 2, 1)
    send(client, headers, [point(i + 1, now() - timedelta(hours=h), lat=29.0 + i * 0.1) for i, h in enumerate(hours)])
    return {"vehicle": v, "driver": d, "headers": headers, "ids": (vid, cid, did), "photo": photo}


def test_the_route_marks_the_work_day_and_keeps_the_rest_to_its_permission(
    admin_client, client, new_client, company, db
):
    h = history(admin_client, client, company, db)
    params = {
        "vehicle_id": h["vehicle"]["id"],
        "start": (now() - timedelta(hours=10)).isoformat(),
        "end": now().isoformat(),
    }
    full = admin_client.get("/api/v1/tracking/route", params=params).json()
    assert [p["on_duty"] for p in full["points"]] == [False, True, True, False, False]
    assert abs(full["distance_km"] - 4 * KM) < 0.1 and abs(full["off_duty_km"] - KM) < 0.05  # the last two only
    assert full["hidden_off_duty"] == 0

    make_user(admin_client, "routes_only", permissions=["tracking.history"])
    c = new_client()
    login(c, "routes_only")
    mine = c.get("/api/v1/tracking/route", params=params).json()
    assert [p["lat"] for p in mine["points"]] == [29.1, 29.2]  # his day, nothing of his own time
    assert mine["hidden_off_duty"] == 3 and mine["off_duty_km"] == 0 and abs(mine["distance_km"] - KM) < 0.05

    make_user(admin_client, "routes_all", permissions=["tracking.history", "tracking.off_duty"])
    c = new_client()
    login(c, "routes_all")
    assert len(c.get("/api/v1/tracking/route", params=params).json()["points"]) == 5


def test_the_live_map_hides_a_vehicle_once_the_day_ends(admin_client, client, new_client, company, db, monkeypatch):
    from app.core import live

    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=10)).isoformat())
    headers = bearer(bind_device(client, d["phone"]))
    ids = _id(db, "fleet.vehicles", v["id"]), _id(db, "fleet.custodies", c["id"]), _id(db, "people.employees", d["id"])
    photo = upload(admin_client)
    reading(db, *ids, "start_day", 10_010, now() - timedelta(hours=2), photo)
    db.commit()
    published = []
    monkeypatch.setattr(live.broker(), "publish", lambda company, message: published.append(message))
    send(client, headers, [point(1, now() - timedelta(minutes=1), lat=29.5)])
    make_user(admin_client, "live_only", permissions=["tracking.live"])
    viewer = new_client()
    login(viewer, "live_only")

    def seen(who):
        return next(x for x in who.get("/api/v1/tracking/live").json() if x["vehicle"]["id"] == v["id"])

    on = seen(viewer)  # at work: everyone with the live map sees him
    assert (on["on_duty"], on["position"]["lat"], on["position_hidden"]) == (True, 29.5, False)

    reading(db, *ids, "end_day", 10_100, now() - timedelta(seconds=30), photo)  # his day ends
    db.commit()
    off = seen(viewer)
    assert (off["on_duty"], off["position"], off["position_hidden"]) == (False, None, True)
    full = seen(admin_client)
    assert (full["on_duty"], full["position"]["lat"], full["position_hidden"]) == (False, 29.5, False)
    send(client, headers, [point(2, now() - timedelta(seconds=10), lat=29.6)])
    assert [m["on_duty"] for m in published] == [True, False]  # what the stream filters on


def test_a_day_never_closed_ends_after_24_hours(admin_client, client, company, db):
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    c = hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=40)).isoformat())
    headers = bearer(bind_device(client, d["phone"]))
    ids = _id(db, "fleet.vehicles", v["id"]), _id(db, "fleet.custodies", c["id"]), _id(db, "people.employees", d["id"])
    reading(db, *ids, "start_day", 10_010, now() - timedelta(hours=30), upload(admin_client))  # and no end
    db.commit()
    send(
        client,
        headers,
        [point(1, now() - timedelta(hours=29), lat=29.0), point(2, now() - timedelta(hours=3), lat=29.1)],
    )
    params = {"vehicle_id": v["id"], "start": (now() - timedelta(hours=40)).isoformat(), "end": now().isoformat()}
    route = admin_client.get("/api/v1/tracking/route", params=params).json()
    assert [p["on_duty"] for p in route["points"]] == [True, False]


def test_the_live_stream_leaves_off_duty_positions_to_who_may_see_them(companies):
    from app.core import live
    from app.modules.tracking import service

    a = companies["a"]["id"]

    async def run(see):
        stream = service.live_events({a}, see_off_duty=see, keepalive=0.05, max_events=2 if see else 1)
        assert (await anext(stream)).startswith("retry:")
        assert await anext(stream) == ": keep-alive\n\n"  # subscribed now
        live.broker().publish(a, {"plate": "OFF", "on_duty": False})
        live.broker().publish(a, {"plate": "ON", "on_duty": True})
        return [json.loads(e.split("data: ")[1])["plate"] for e in [e async for e in stream] if e.startswith("event:")]

    assert asyncio.run(run(False)) == ["ON"]
    assert asyncio.run(run(True)) == ["OFF", "ON"]
