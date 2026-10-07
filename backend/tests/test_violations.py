"""Work violations (BRD FR-VIO-01..05, BR-09, BR-10, BR-13, UAT-05; TRK-M-02, TRK-M-03): recorded by the office or
from an alert, or opened by the system; excluded at once for a cause outside the driver's responsibility; reviewed,
objected to from the app within the deadline, decided finally; the penalty deducted only once final."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle

V = "/api/v1/violations"


def now():
    return datetime.now(UTC)


def setup(admin_client, client, company) -> dict:
    v = make_vehicle(admin_client, company["id"])
    d = make_driver(admin_client, company["id"])
    hand_over(admin_client, v, d, started_at=(now() - timedelta(hours=2)).isoformat())
    return {"vehicle": v, "driver": d, "h": bearer(bind_device(client, d["phone"]))}


def codes(admin_client, path="types") -> dict:
    return {t["code"]: t for t in admin_client.get(f"{V}/{path}").json()}


def record(admin_client, s, code, **extra):
    body = {
        "employee_id": s["driver"]["id"],
        "type_id": codes(admin_client)[code]["id"],
        "occurred_at": (now() - timedelta(minutes=30)).isoformat(),
        "description": "طلب تأخر 40 دقيقة",
        **extra,
    }
    return admin_client.post(V, json=body)


def kinds(admin_client) -> list[str]:
    return sorted(a["kind"] for a in admin_client.get("/api/v1/alerts").json())


def mine(client, s) -> dict:
    return {x["number"]: x for x in client.get("/api/v1/driver/violations", headers=s["h"]).json()}


def notices(client, s) -> list[dict]:
    return client.get("/api/v1/driver/notifications", headers=s["h"]).json()["items"]


def test_uat05_a_cause_outside_the_driver_excludes_the_violation_at_once(admin_client, client, company):
    s = setup(admin_client, client, company)
    cancelled = codes(admin_client, "causes")["customer_cancelled"]
    r = record(admin_client, s, "order_rejected", reference="T-1001", cause_id=cancelled["id"])
    assert r.status_code == 201, r.text
    excluded = r.json()
    assert (excluded["status"], excluded["final"], excluded["cause"]["code"]) == (
        "excluded",
        True,
        "customer_cancelled",
    )
    assert "violation_review" not in kinds(admin_client)  # nothing to review
    assert mine(client, s) == {}  # no violation on the driver
    assert admin_client.post(f"{V}/{excluded['id']}/approve", json={}).status_code == 409

    # the list is the client's: a cause switched off no longer excludes, a new one does
    r = admin_client.put(
        f"{V}/causes/{cancelled['id']}",
        json={"name": cancelled["name"], "active": False, "version": cancelled["version"]},
    )
    assert r.status_code == 200, r.text
    again = record(admin_client, s, "order_rejected", cause_id=cancelled["id"]).json()
    assert again["status"] == "pending"
    r = admin_client.post(f"{V}/causes", json={"code": "app_down", "name": {"ar": "عطل المنصة", "en": "Platform down"}})
    assert r.status_code == 201, r.text
    assert record(admin_client, s, "order_late", cause_id=r.json()["id"]).json()["status"] == "excluded"
    dup = admin_client.post(f"{V}/causes", json={"code": "app_down", "name": {"ar": "س", "en": "x"}})
    assert dup.status_code == 409 and dup.json()["code"] == "violation_cause_exists"


def test_reviewed_objected_to_from_the_app_and_decided_finally(admin_client, client, new_client, company):
    s = setup(admin_client, client, company)
    v = record(admin_client, s, "order_late", reference="T-2002").json()
    assert (v["status"], v["origin"], v["vehicle_plate"]) == ("pending", "office", s["vehicle"]["plate_number"])
    assert "violation_review" in kinds(admin_client)
    assert mine(client, s) == {}  # under review: not the driver's yet

    make_user(admin_client, "vio_clerk", permissions=["violations.view", "violations.manage"])
    clerk = new_client()
    login(clerk, "vio_clerk")
    assert clerk.post(f"{V}/{v['id']}/approve", json={"amount": "5"}).status_code == 403  # recording is not deciding

    r = admin_client.post(f"{V}/{v['id']}/approve", json={"amount": "5.000", "note": "ثاني تأخير هذا الأسبوع"})
    assert r.status_code == 200, r.text
    approved = r.json()
    late = admin_client.post(f"{V}/{v['id']}/exclude", json={"note": "بعد الاعتماد"})
    assert late.status_code == 409 and late.json()["code"] == "violation_not_pending"  # the objection is the way now
    assert (approved["status"], approved["final"], approved["amount"], approved["deduction"]) == (
        "approved",
        False,
        "5.000",
        None,  # not before the objection deadline
    )
    deadline = datetime.fromisoformat(approved["objection_deadline"])
    assert timedelta(hours=47, minutes=59) < deadline - now() <= timedelta(hours=48)  # BR-09
    assert "violation_review" not in kinds(admin_client)
    told = notices(client, s)[0]
    assert told["kind"] == "violation_approved" and "5.000" in told["message"] and "48" in told["message"]
    assert mine(client, s)[v["number"]]["can_object"] is True

    # the driver objects from the app, with a screenshot from his phone
    shot = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=s["h"],
        files={"file": ("s.jpg", b"\xff\xd8\xff\xe0shot", "image/jpeg")},
    ).json()["sha256"]
    path = f"/api/v1/driver/violations/{v['id']}/objection"
    r = client.post(path, headers=s["h"], json={"text": "المطعم أخّر الطلب 35 دقيقة", "file_sha256": shot})
    assert r.status_code == 201, r.text
    assert (r.json()["status"], r.json()["can_object"]) == ("objected", False)
    again = client.post(path, headers=s["h"], json={"text": "مرة أخرى"})
    assert again.status_code == 409 and again.json()["code"] == "objection_exists"  # a retry is recognised
    assert "violation_objected" in kinds(admin_client)
    full = admin_client.get(f"{V}/{v['id']}").json()
    assert (full["objection"], full["objection_sha256"]) == ("المطعم أخّر الطلب 35 دقيقة", shot)
    assert admin_client.get(f"{V}/{v['id']}/files/{shot}").status_code == 200

    r = admin_client.post(f"{V}/{v['id']}/decide", json={"uphold": True, "note": "سجل المطعم يقول التسليم في وقته"})
    assert r.status_code == 200, r.text
    final = r.json()
    assert (final["status"], final["final"], final["deduction"]["total"], final["deduction"]["status"]) == (
        "upheld",
        True,
        "5.000",
        "approved",
    )
    assert final["deduction"]["source_type"] == "violation"
    assert notices(client, s)[0]["kind"] == "violation_upheld"
    assert "violation_objected" not in kinds(admin_client)
    assert admin_client.post(f"{V}/{v['id']}/decide", json={"uphold": False, "note": "مرة ثانية"}).status_code == 409

    # another objection accepted: no penalty at all
    w = record(admin_client, s, "complaint").json()
    admin_client.post(f"{V}/{w['id']}/approve", json={"amount": "2"})
    client.post(f"/api/v1/driver/violations/{w['id']}/objection", headers=s["h"], json={"text": "العميل غيّر العنوان"})
    over = admin_client.post(f"{V}/{w['id']}/decide", json={"uphold": False, "note": "ثبت تغيير العنوان"}).json()
    assert (over["status"], over["final"], over["deduction"]) == ("overturned", True, None)
    assert notices(client, s)[0]["kind"] == "violation_overturned"

    # excluded by the reviewer: a reason is required, and the driver never sees it
    x = record(admin_client, s, "absence").json()
    assert admin_client.post(f"{V}/{x['id']}/exclude", json={}).status_code == 422
    assert admin_client.post(f"{V}/{x['id']}/exclude", json={"note": "إجازة مسجلة"}).json()["status"] == "excluded"
    assert set(mine(client, s)) == {v["number"], w["number"]}


def test_the_penalty_is_deducted_once_the_deadline_passes_without_an_objection(admin_client, client, company, db):
    from app.modules.violations import service

    s = setup(admin_client, client, company)
    v = record(admin_client, s, "cash_deposit_late").json()
    warning = record(admin_client, s, "report_late").json()
    admin_client.post(f"{V}/{v['id']}/approve", json={"amount": "3"})
    admin_client.post(f"{V}/{warning['id']}/approve", json={"amount": "0"})  # a warning
    assert service.finalize_due(db) == 0
    db.execute(text("UPDATE violations.violations SET objection_deadline = now() - interval '1 minute'"))
    db.commit()
    assert service.finalize_due(db) == 1  # the warning has nothing to deduct
    assert service.finalize_due(db) == 0
    after = admin_client.get(f"{V}/{v['id']}").json()
    assert (after["final"], after["deduction"]["total"]) == (True, "3.000")
    assert admin_client.get(f"{V}/{warning['id']}").json()["final"] is True
    late = client.post(f"/api/v1/driver/violations/{v['id']}/objection", headers=s["h"], json={"text": "متأخر"})
    assert late.status_code == 409 and late.json()["code"] == "objection_too_late"
    assert mine(client, s)[v["number"]]["can_object"] is False

    # no objection window at all: final, and deducted, as it is approved
    current = admin_client.get("/api/v1/settings").json()["violations"]
    r = admin_client.put(
        "/api/v1/settings/violations",
        json={"version": current["version"], "value": current["value"] | {"objection_hours": 0}},
    )
    assert r.status_code == 200, r.text
    now_final = record(admin_client, s, "cash_shortage").json()
    r = admin_client.post(f"{V}/{now_final['id']}/approve", json={"amount": "1.500"}).json()
    assert (r["final"], r["deduction"]["total"]) == (True, "1.500")


def test_the_system_opens_violations_for_a_fake_location_and_repeated_signal_loss(admin_client, client, company, db):
    from app.modules.tracking import service as tracking

    s = setup(admin_client, client, company)

    def send(points):
        r = client.post(
            "/api/v1/driver/positions", headers=s["h"], json={"sent_at": now().isoformat(), "points": points}
        )
        assert r.status_code == 200, r.text

    def point(seq, minutes_ago, **extra):
        t = now() - timedelta(minutes=minutes_ago)
        return {"seq": seq, "recorded_at": t.isoformat(), "lat": 29.37, "lng": 47.97, "speed_kmh": 30, **extra}

    send([point(1, 100, is_mock=True)])
    send([point(2, 99, is_mock=True)])  # the same day: one violation
    [fake] = admin_client.get(V, params={"driver_id": s["driver"]["id"]}).json()
    assert (fake["type"]["code"], fake["origin"], fake["status"]) == ("mock_location", "system", "pending")
    assert "تزييف الموقع" in fake["description"]

    def silence(seq, minutes_ago):
        send([point(seq, minutes_ago)])
        assert tracking.scan_signal_loss(db) == 1

    silence(3, 90)
    silence(4, 70)
    assert len(admin_client.get(V, params={"driver_id": s["driver"]["id"]}).json()) == 1  # two: not yet
    silence(5, 50)  # the third within 7 days
    rows = admin_client.get(V, params={"driver_id": s["driver"]["id"], "source": "tracking"}).json()
    assert sorted(x["type"]["code"] for x in rows) == ["mock_location", "signal_loss"]
    silence(6, 30)  # the count starts again after the violation
    assert len(admin_client.get(V, params={"driver_id": s["driver"]["id"]}).json()) == 2

    # a type the client switched off is not opened by the system (another driver: not today's once-a-day key)
    t = codes(admin_client)["mock_location"]
    admin_client.put(f"{V}/types/{t['id']}", json={"name": t["name"], "active": False, "version": t["version"]})
    other = setup(admin_client, client, company)
    r = client.post(
        "/api/v1/driver/positions",
        headers=other["h"],
        json={"sent_at": now().isoformat(), "points": [point(1, 20, is_mock=True)]},
    )
    assert r.json()["rejected"] == [{"seq": 1, "reason": "mock"}]
    assert admin_client.get(V, params={"driver_id": other["driver"]["id"]}).json() == []


def test_speeding_is_an_alert_until_a_supervisor_makes_it_a_violation(admin_client, client, company):
    s = setup(admin_client, client, company)

    def send(seq, speed, minutes_ago=5):
        t = now() - timedelta(minutes=minutes_ago)
        point = {"seq": seq, "recorded_at": t.isoformat(), "lat": 29.37, "lng": 47.97, "speed_kmh": speed}
        client.post("/api/v1/driver/positions", headers=s["h"], json={"sent_at": now().isoformat(), "points": [point]})

    send(1, 118)
    assert "speeding" not in kinds(admin_client)  # under the 120 limit
    t = now() - timedelta(minutes=4)
    fast = [
        {"seq": 2, "recorded_at": t.isoformat(), "lat": 29.37, "lng": 47.97, "speed_kmh": 163.6},
        {
            "seq": 3,
            "recorded_at": (t + timedelta(seconds=30)).isoformat(),
            "lat": 29.38,
            "lng": 47.97,
            "speed_kmh": 151,
        },
        {
            "seq": 4,
            "recorded_at": (t + timedelta(seconds=60)).isoformat(),
            "lat": 29.39,
            "lng": 47.97,
            "speed_kmh": 190,
            "accuracy_m": 80,
        },  # too imprecise to count
    ]
    client.post("/api/v1/driver/positions", headers=s["h"], json={"sent_at": now().isoformat(), "points": fast})
    send(5, 170, 2)  # once a custody a day
    [alert] = [a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "speeding"]
    assert alert["params"]["speed"] == 164  # the fastest precise point of the batch
    assert admin_client.get(V, params={"driver_id": s["driver"]["id"]}).json() == []  # BR-13: only an alert

    r = record(admin_client, s, "speeding", alert_id=alert["id"], description="151 كم/س على الدائري السادس")
    assert r.status_code == 201, r.text
    assert (r.json()["origin"], r.json()["status"]) == ("alert", "pending")
    assert "speeding" not in kinds(admin_client)  # the alert is handled by becoming a violation
    assert record(admin_client, s, "speeding", alert_id=alert["id"]).status_code == 201  # acknowledged already: fine

    current = admin_client.get("/api/v1/settings").json()["tracking"]
    admin_client.put(
        "/api/v1/settings/tracking",
        json={"version": current["version"], "value": current["value"] | {"speed_limit_kmh": 0}},
    )
    other = setup(admin_client, client, company)
    t = now() - timedelta(minutes=1)
    client.post(
        "/api/v1/driver/positions",
        headers=other["h"],
        json={
            "sent_at": now().isoformat(),
            "points": [{"seq": 1, "recorded_at": t.isoformat(), "lat": 29.37, "lng": 47.97, "speed_kmh": 200}],
        },
    )
    assert len([a for a in admin_client.get("/api/v1/alerts").json() if a["kind"] == "speeding"]) == 0


def test_scopes_types_and_the_hidden_screen(admin_client, client, new_client, company):
    s = setup(admin_client, client, company)
    other = admin_client.post("/api/v1/companies", json={"name": {"ar": "شركة ب", "en": "Company B"}}).json()
    make_user(admin_client, "vio_b", permissions=["violations.view", "violations.manage"], company_ids=[other["id"]])
    b = new_client()
    login(b, "vio_b")
    v = record(admin_client, s, "order_late").json()
    assert b.get(f"{V}/{v['id']}").status_code == 404
    assert record(b, s, "order_late").status_code == 404  # not his company's driver

    t = codes(admin_client)["order_late"]
    r = admin_client.put(f"{V}/types/{t['id']}", json={"name": t["name"], "amount": "2.500", "version": t["version"]})
    assert r.status_code == 200 and r.json()["amount"] == "2.500"
    stale = admin_client.put(f"{V}/types/{t['id']}", json={"name": t["name"], "version": t["version"]})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    w = record(admin_client, s, "order_late").json()
    assert admin_client.post(f"{V}/{w['id']}/approve", json={}).json()["amount"] == "2.500"  # the type's penalty
    # his own file only: another driver's upload is refused
    other = setup(admin_client, client, company)
    theirs = client.post(
        "/api/v1/driver/files",
        params={"source": "upload"},
        headers=other["h"],
        files={"file": ("o.jpg", b"\xff\xd8\xff\xe0other", "image/jpeg")},
    ).json()["sha256"]
    r = client.post(
        f"/api/v1/driver/violations/{w['id']}/objection",
        headers=s["h"],
        json={"text": "ليست مخالفتي", "file_sha256": theirs},
    )
    assert r.status_code == 422 and r.json()["code"] == "file_not_found"
    assert (
        client.post(
            f"/api/v1/driver/violations/{w['id']}/objection", headers=other["h"], json={"text": "ليست لي"}
        ).status_code
        == 404
    )
    future = record(admin_client, s, "order_late", occurred_at=(now() + timedelta(hours=1)).isoformat())
    assert future.status_code == 422 and future.json()["code"] == "time_in_future"

    current = admin_client.get("/api/v1/settings").json()["driver_app"]
    admin_client.put(
        "/api/v1/settings/driver_app",
        json={"version": current["version"], "value": current["value"] | {"hidden_screens": ["violations"]}},
    )
    r = client.get("/api/v1/driver/violations", headers=s["h"])
    assert r.status_code == 403 and r.json()["code"] == "screen_off"
