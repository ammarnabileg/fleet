"""Broadcasts (ركن الإشعارات): a message to all drivers or a group, through the inbox (always), Firebase push and
WhatsApp when their integrations are on; each recipient and channel once, the WhatsApp number's shared pace kept, the
text in the driver's language (English, then Arabic, when his is not written). No real message leaves: push goes to a
fake Google, WhatsApp to the development log."""

from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.core import messaging
from app.core.clock import KUWAIT, utcnow
from app.modules.fleet import service as fleet
from app.modules.identity import link_queue
from app.modules.integrations import service as integrations
from app.modules.notifications import broadcasts, channels
from tests.conftest import bearer, bind_device, hand_over, login, make_driver, make_user, make_vehicle, name
from tests.test_push import TOKEN_A, TOKEN_B, FakeGoogle, switch_on

B = "/api/v1/broadcasts"
NOON = datetime.now(KUWAIT).replace(hour=12, minute=0, second=0, microsecond=0)
TITLE = {"ar": "تنبيه مهم", "en": "Important notice", "sw": "Tangazo muhimu"}
BODY = {"ar": "الدوام يبدأ الساعة الثامنة", "en": "Work starts at eight", "sw": "Kazi inaanza saa mbili"}


@pytest.fixture
def google(monkeypatch):
    g = FakeGoogle()
    monkeypatch.setattr(integrations, "_fcm_transport", lambda loaded: httpx.MockTransport(g.handler))
    return g


@pytest.fixture
def whatsapp_on(monkeypatch):
    """WhatsApp counted as switched on; the messages go to the development log (never out)."""
    monkeypatch.setattr(integrations, "whatsapp_enabled", lambda db: True)
    messaging.provider().sent.clear()


def compose(admin_client, audience=None, channels_=(), **extra):
    body = {"title": TITLE, "body": BODY, "audience": audience or {"kind": "all"}, "channels": list(channels_)}
    r = admin_client.post(B, json=body | extra)
    assert r.status_code == 201, r.text
    return r.json()


def rows(db, broadcast_id):
    return db.execute(
        text("""SELECT e.public_id::text, d.channel, d.status, d.reason, d.attempts
                FROM notifications.broadcast_deliveries d JOIN notifications.broadcasts b ON b.id = d.broadcast_id
                JOIN people.employees e ON e.id = d.employee_id WHERE b.public_id = :p ORDER BY d.id"""),
        {"p": broadcast_id},
    ).all()


def notices(client, headers, lang=None):
    h = headers | ({"Accept-Language": lang} if lang else {})
    return [
        n for n in client.get("/api/v1/driver/notifications", headers=h).json()["items"] if n["kind"] == "broadcast"
    ]


def test_the_audience_all_by_company_by_platform_selected_and_on_duty(admin_client, companies, monkeypatch, db):
    a1, a2 = make_driver(admin_client, companies["a"]["id"]), make_driver(admin_client, companies["a"]["id"])
    b1 = make_driver(admin_client, companies["b"]["id"])
    p = admin_client.post("/api/v1/payroll/platforms", json={"code": "plat_bc", "name": name("منصة", "Platform")})
    assert p.status_code == 201, p.text
    r = admin_client.post(
        "/api/v1/employees/platform", json={"employee_ids": [b1["id"]], "platform_id": p.json()["id"]}
    )
    assert r.status_code in (200, 204), r.text

    def count(audience):
        r = admin_client.post(f"{B}/preview", json={"audience": audience, "channels": []})
        assert r.status_code == 200, r.text
        return r.json()["recipients"]

    assert count({"kind": "all"}) == 3
    assert count({"kind": "company", "company_ids": [companies["a"]["id"]]}) == 2
    assert count({"kind": "platform", "platform_ids": [p.json()["id"]]}) == 1
    assert count({"kind": "selected", "employee_ids": [a2["id"]]}) == 1
    assert count({"kind": "on_duty"}) == 0
    hand_over(admin_client, make_vehicle(admin_client, companies["a"]["id"]), a1)
    monkeypatch.setattr(fleet, "on_duty_now", lambda db, ids: set(ids))  # his day started
    assert count({"kind": "on_duty"}) == 1
    r = admin_client.post(f"{B}/preview", json={"audience": {"kind": "company", "company_ids": []}, "channels": []})
    assert r.status_code == 422 and r.json()["code"] == "invalid_audience"


def test_only_the_inbox_when_push_and_whatsapp_are_off(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    pre = admin_client.post(f"{B}/preview", json={"audience": {"kind": "all"}, "channels": ["push", "whatsapp"]}).json()
    assert pre["recipients"] == 1 and pre["inbox_only"] == 1
    assert pre["channels"]["inbox"] == {"will": 1, "skipped": {}}
    assert pre["channels"]["push"] == {"will": 0, "skipped": {"channel_disabled": 1}}
    assert pre["channels"]["whatsapp"] == {"will": 0, "skipped": {"channel_disabled": 1}}
    states = {s["name"]: s["enabled"] for s in admin_client.get(f"{B}/channels").json()}
    assert states == {"inbox": True, "push": False, "whatsapp": False}

    b = compose(admin_client, channels_=["push", "whatsapp"])
    assert b["status"] == "sent" and b["recipients"] == 1  # the inbox goes at once; nothing else waits
    assert b["stats"]["inbox"]["sent"] == 1 and b["stats"]["push"]["skipped"] == 1
    assert {(c, s, r) for _, c, s, r, _ in rows(db, b["id"])} == {
        ("inbox", "sent", None),
        ("push", "skipped", "channel_disabled"),
        ("whatsapp", "skipped", "channel_disabled"),
    }
    [n] = notices(client, h, "en")
    assert (n["title"], n["body"]) == ("Important notice", "Work starts at eight")
    assert n["message"] == "Important notice\nWork starts at eight"
    assert db.execute(text("SELECT pushed_at IS NOT NULL FROM notifications.driver_notices")).scalar()  # not re-pushed
    failed = admin_client.get(f"{B}/{b['id']}/deliveries", params={"status": "skipped"}).json()
    assert {x["reason"] for x in failed} == {"channel_disabled"}


def test_the_text_in_the_drivers_language_falling_back_to_english_then_arabic(admin_client, client, company):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    compose(admin_client)
    assert notices(client, h, "sw")[0]["title"] == "Tangazo muhimu"
    assert notices(client, h, "fr")[0]["title"] == "Important notice"  # French not written: English
    assert notices(client, h, "ar")[0]["body"] == BODY["ar"]
    assert channels.text_in({"ar": "عربي"}, "fr") == "عربي"  # neither: Arabic
    r = admin_client.post(B, json={"title": {"ar": "x"}, "body": BODY, "audience": {"kind": "all"}, "channels": []})
    assert r.status_code == 422 and r.json()["code"] == "broadcast_text_required"


def test_push_goes_once_in_the_drivers_language_with_its_payload(admin_client, client, new_client, company, google, db):
    switch_on(admin_client, google)
    d1, d2 = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    h1 = bearer(bind_device(client, d1["phone"]))
    other = new_client()
    h2 = bearer(bind_device(other, d2["phone"]))
    assert (
        client.post("/api/v1/driver/push-token", headers=h1, json={"token": TOKEN_A, "lang": "sw"}).status_code == 204
    )
    pre = admin_client.post(f"{B}/preview", json={"audience": {"kind": "all"}, "channels": ["push"]}).json()
    assert pre["channels"]["push"] == {"will": 1, "skipped": {"no_token": 1}} and pre["inbox_only"] == 1

    b = compose(admin_client, channels_=["push"])
    assert b["status"] == "sending" and google.sent == []  # push goes with the scheduler
    broadcasts.run(db)
    broadcasts.run(db)  # again: nothing twice
    [m] = google.sent
    assert m["token"] == TOKEN_A
    assert m["notification"] == {"title": "Tangazo muhimu", "body": "Kazi inaanza saa mbili"}
    [notice] = notices(client, h1)
    assert m["data"] == {
        "id": notice["id"],
        "kind": "broadcast",
        "entity_type": "broadcast",
        "entity_id": b["id"],
        "style": "info",
        "layout": "standard",
    }
    assert m["android"] == {"priority": "normal", "notification": {"channel_id": "driver_messages"}}
    assert admin_client.get(f"{B}/{b['id']}").json()["status"] == "sent"
    assert {(c, s, r) for _, c, s, r, _ in rows(db, b["id"]) if c == "push"} == {
        ("push", "sent", None),
        ("push", "skipped", "no_token"),
    }
    assert notices(other, h2)  # in his inbox all the same
    logged = db.execute(text("SELECT purpose, status FROM integrations.message_log WHERE channel = 'push'")).all()
    assert logged == [("broadcast", "accepted")]

    # a dead token fails with its reason, and only the failed are sent again
    google.dead.add(TOKEN_A)
    b2 = compose(admin_client, channels_=["push"])
    broadcasts.run(db)
    assert [(s, r) for _, c, s, r, _ in rows(db, b2["id"]) if c == "push" and s != "skipped"] == [
        ("failed", "invalid_token")
    ]
    assert other.post("/api/v1/driver/push-token", headers=h2, json={"token": TOKEN_B}).status_code == 204
    google.dead.clear()
    r = admin_client.post(f"{B}/{b2['id']}/resend", json={})
    assert r.status_code == 200 and r.json()["requeued"] == 1
    broadcasts.run(db)
    # d1's token was forgotten: the resend skips him now, and never touches the rows already settled
    assert len(google.sent) == 1


def test_whatsapp_one_at_a_time_at_the_shared_pace(admin_client, company, whatsapp_on, db):
    d1 = make_driver(admin_client, company["id"])
    d2 = make_driver(admin_client, company["id"])
    r = admin_client.post(
        "/api/v1/employees",
        json={"employee_number": "NOPH1", "name": name("بلا رقم", "No phone"), "company_id": company["id"],
              "is_driver": True, "phone": None},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    pre = admin_client.post(f"{B}/preview", json={"audience": {"kind": "all"}, "channels": ["whatsapp"]}).json()
    assert pre["channels"]["whatsapp"] == {"will": 2, "skipped": {"no_phone": 1}}
    assert pre["pace"]["interval_seconds"] == 60

    b = compose(admin_client, channels_=["whatsapp"])
    assert broadcasts.run(db, NOON)["whatsapp"] == "sent"
    assert broadcasts.run(db, NOON + timedelta(seconds=10))["whatsapp"] == "too_soon"
    assert link_queue.send_next(db, NOON + timedelta(seconds=20)) == "too_soon"  # one pace for the number
    assert broadcasts.run(db, NOON - timedelta(hours=5))["whatsapp"] == "outside_hours"  # 7:00 in Kuwait
    assert broadcasts.run(db, NOON + timedelta(minutes=2))["whatsapp"] == "sent"
    sent = messaging.provider().sent
    assert sorted(m.to for m in sent) == sorted([d1["phone"], d2["phone"]])
    assert sent[0].text == "*تنبيه مهم*\n\nالدوام يبدأ الساعة الثامنة"  # no preferred language: the default
    assert admin_client.get(f"{B}/{b['id']}").json()["status"] == "sent"
    logged = db.execute(text("SELECT count(*) FROM integrations.message_log WHERE purpose = 'broadcast'")).scalar()
    assert logged == 2


def test_a_scheduled_broadcast_goes_when_due_and_a_cancelled_one_never(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    later = utcnow() + timedelta(hours=1)
    b = compose(admin_client, scheduled_at=later.isoformat())
    gone = compose(admin_client, scheduled_at=later.isoformat())
    assert b["status"] == gone["status"] == "scheduled"
    assert admin_client.post(f"{B}/{gone['id']}/cancel").json()["status"] == "cancelled"
    assert broadcasts.run(db)["started"] == 0 and notices(client, h) == []
    assert broadcasts.run(db, utcnow() + timedelta(hours=2))["started"] == 1
    assert len(notices(client, h)) == 1
    assert admin_client.get(f"{B}/{b['id']}").json()["status"] == "sent"
    assert rows(db, gone["id"]) == []
    r = admin_client.post(f"{B}/{b['id']}/cancel")
    assert r.status_code == 409 and r.json()["code"] == "broadcast_not_cancellable"
    actions = (
        db.execute(text("SELECT action FROM audit.events WHERE entity_type = 'broadcast' ORDER BY id")).scalars().all()
    )
    assert actions.count("broadcast.created") == 2 and "broadcast.cancelled" in actions and "broadcast.sent" in actions


def test_a_draft_is_kept_until_sent(admin_client, client, company, db):
    d = make_driver(admin_client, company["id"])
    h = bearer(bind_device(client, d["phone"]))
    b = compose(admin_client, send=False)
    assert b["status"] == "draft" and notices(client, h) == []
    assert admin_client.post(f"{B}/{b['id']}/send").json()["status"] == "sent"
    assert len(notices(client, h)) == 1
    assert admin_client.post(f"{B}/{b['id']}/send").status_code == 409
    listed = admin_client.get(B, params={"q": "Important"}).json()
    assert [x["id"] for x in listed] == [b["id"]]


def test_permissions(admin_client, new_client, company):
    make_driver(admin_client, company["id"])
    make_user(admin_client, "bc_viewer", permissions=["broadcasts.view"])
    make_user(admin_client, "bc_sender", permissions=["broadcasts.view", "broadcasts.send"])
    viewer, sender = new_client(), new_client()
    login(viewer, "bc_viewer")
    login(sender, "bc_sender")
    body = {"title": TITLE, "body": BODY, "audience": {"kind": "all"}, "channels": []}
    assert viewer.get(B).status_code == 200
    assert viewer.post(B, json=body).status_code == 403
    assert viewer.post(f"{B}/preview", json={"audience": {"kind": "all"}}).status_code == 403
    r = sender.post(B, json=body)
    assert r.status_code == 201 and r.json()["recipients"] == 1
    labels = {p["code"] for g in admin_client.get("/api/v1/permissions").json() for p in g["permissions"]}
    assert {"broadcasts.view", "broadcasts.send"} <= labels


def test_an_interrupted_send_is_failed_not_sent_twice(admin_client, company, whatsapp_on, db):
    make_driver(admin_client, company["id"])
    b = compose(admin_client, channels_=["whatsapp"])
    db.execute(
        text("""UPDATE notifications.broadcast_deliveries SET claimed_at = now() - interval '1 hour', attempts = 1
                WHERE channel = 'whatsapp'""")
    )  # a worker died while sending it
    db.commit()
    broadcasts.run(db, NOON)
    assert messaging.provider().sent == []
    assert [(s, r) for _, c, s, r, _ in rows(db, b["id"]) if c == "whatsapp"] == [("failed", "interrupted")]


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def upload(admin_client, data=PNG, name_="card.png"):
    r = admin_client.post("/api/v1/files", files={"file": (name_, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["sha256"]


def test_the_style_layout_image_and_action_reach_the_inbox_push_and_whatsapp(
    admin_client, client, new_client, company, google, whatsapp_on, db
):
    switch_on(admin_client, google)
    d1, d2 = make_driver(admin_client, company["id"]), make_driver(admin_client, company["id"])
    h1 = bearer(bind_device(client, d1["phone"]))
    other = new_client()
    h2 = bearer(bind_device(other, d2["phone"]))
    assert (
        client.post("/api/v1/driver/push-token", headers=h1, json={"token": TOKEN_A, "lang": "en"}).status_code == 204
    )
    sha = upload(admin_client)
    action = {"target": "cash", "label": {"ar": "  افتح العهدة ", "en": "Open cash", "fr": " "}}
    b = compose(
        admin_client, channels_=["push", "whatsapp"], style="urgent", layout="highlight", image=sha, action=action
    )
    assert (b["style"], b["layout"], b["image"]) == ("urgent", "highlight", sha)
    assert b["action"] == {"target": "cash", "label": {"ar": "افتح العهدة", "en": "Open cash"}}
    assert admin_client.get(B).json()[0]["style"] == "urgent"  # the history shows it
    for _ in range(3):
        broadcasts.run(db, NOON)  # within the WhatsApp sending hours whatever the hour the suite runs at
    [m] = google.sent
    assert m["notification"]["title"] == "\u26a0\ufe0f Important notice"  # urgent: marked
    assert m["android"] == {"priority": "high", "notification": {"channel_id": "driver_alerts"}}
    assert (m["data"]["style"], m["data"]["layout"]) == ("urgent", "highlight")
    [n] = notices(client, h1, "en")
    assert (n["style"], n["layout"], n["image"], n["action"]["target"]) == ("urgent", "highlight", sha, "cash")
    assert any(m.text.startswith("*\u26a0\ufe0f ") for m in messaging.provider().sent)

    # the picture: to a driver whose inbox holds it, and to the panel; nobody else
    assert client.get(f"/api/v1/driver/broadcast-images/{sha}", headers=h1).content == PNG
    assert admin_client.get(f"{B}/images/{sha}").status_code == 200
    stranger = upload(admin_client, PNG + b"x")
    assert client.get(f"/api/v1/driver/broadcast-images/{stranger}", headers=h1).status_code == 404
    assert notices(other, h2)[0]["image"] == sha  # his own inbox holds it too

    # a plain one: defaults, and quietly on the normal channel
    b2 = compose(admin_client, channels_=["push"], style="reminder")
    broadcasts.run(db, NOON)
    assert google.sent[-1]["android"]["notification"]["channel_id"] == "driver_messages"
    assert google.sent[-1]["notification"]["title"] == "Important notice"
    assert (b2["layout"], b2["image"], b2["action"]) == ("standard", None, None)


@pytest.mark.parametrize(
    "extra",
    [
        {"style": "party"},
        {"layout": "poster"},
        {"action": {"target": "url", "label": {}}},
        {"action": {"target": "https://example.com"}},
        {"image": "not-a-sha"},
        {"image": "0" * 64},  # never uploaded
    ],
)
def test_a_style_layout_action_or_image_outside_the_lists_is_refused(admin_client, company, extra):
    body = {"title": TITLE, "body": BODY, "audience": {"kind": "all"}, "channels": []}
    r = admin_client.post(B, json=body | extra)
    assert r.status_code == 422, r.text


def test_a_large_or_non_image_picture_is_refused(admin_client, company):
    body = {"title": TITLE, "body": BODY, "audience": {"kind": "all"}, "channels": []}
    pdf = upload(admin_client, b"%PDF-1.4\n" + b"0" * 64, "x.pdf")
    assert admin_client.post(B, json=body | {"image": pdf}).status_code == 415
    big = upload(admin_client, PNG + b"0" * broadcasts.IMAGE_MAX_BYTES)
    assert admin_client.post(B, json=body | {"image": big}).status_code == 413
