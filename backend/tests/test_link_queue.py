"""Bulk activation links: queued, then sent one at a time over WhatsApp at a person's pace (interval, daily limit,
daytime hours), retried when the channel is down, never all at once."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.core import messaging
from app.core.clock import KUWAIT
from app.modules.identity import link_queue
from tests.conftest import bind_device, login, make_driver, make_user

MORNING = datetime.now(KUWAIT).replace(hour=10, minute=0, second=0, microsecond=0)


def at(minutes=0, base=MORNING):
    return base + timedelta(minutes=minutes)


def sent_to():
    return [m.to for m in messaging.provider().sent]


@pytest.fixture
def drivers(admin_client, client, company):
    ready = [make_driver(admin_client, company["id"]) for _ in range(3)]
    bind_device(client, ready[2]["phone"])  # already has a phone: not in the first wave
    make_driver(admin_client, company["id"], app=False)  # no app access: never queued
    messaging.provider().sent.clear()
    return ready


def queue_all(admin_client):
    r = admin_client.post("/api/v1/activation-links/bulk", json={"all_unbound": True})
    assert r.status_code == 202, r.text
    return r.json()


def test_drivers_without_a_phone_are_queued_once(admin_client, drivers):
    assert queue_all(admin_client) == {"queued": 2, "skipped": []}
    again = queue_all(admin_client)
    assert again["queued"] == 0 and {s["reason"] for s in again["skipped"]} == {"already_queued"}
    queue = admin_client.get("/api/v1/activation-links/queue").json()
    assert queue["waiting"] == 2 and queue["sent_today"] == 0 and queue["estimated_days"] == 1
    assert sent_to() == []  # nothing is sent by the request itself


def test_one_message_at_a_time_at_the_configured_pace(admin_client, drivers, db):
    queue_all(admin_client)
    assert link_queue.send_next(db, at(0)) == "sent"
    assert link_queue.send_next(db, at(0.5)) == "too_soon"  # the default interval is 60 seconds
    assert link_queue.send_next(db, at(1.1)) == "sent"
    assert link_queue.send_next(db, at(2.2)) == "empty"
    assert sorted(sent_to()) == sorted(d["phone"] for d in drivers[:2])
    assert all("أكمل بياناتك" in m.text for m in messaging.provider().sent)  # first time: self-registration
    queue = admin_client.get("/api/v1/activation-links/queue").json()
    assert queue["waiting"] == 0 and queue["sent_today"] == 2 and {i["status"] for i in queue["items"]} == {"sent"}
    drafts = db.execute(text("SELECT count(*) FROM onboarding.submissions WHERE status = 'draft'")).scalar()
    assert drafts == 2


def test_daytime_hours_and_daily_limit(admin_client, drivers, db):
    queue_all(admin_client)
    assert link_queue.send_next(db, MORNING.replace(hour=3)) == "outside_hours"
    assert link_queue.send_next(db, MORNING.replace(hour=22, minute=30)) == "outside_hours"
    r = admin_client.put("/api/v1/settings/messaging", json={"version": 0, "value": {"bulk_daily_limit": 1}})
    assert r.status_code == 200
    from app.modules.org import service as org

    org._cache.clear()
    assert link_queue.send_next(db, at(0)) == "sent"
    assert link_queue.send_next(db, at(5)) == "daily_limit"
    assert admin_client.get("/api/v1/activation-links/queue").json()["estimated_days"] == 1


class Down:
    def __init__(self, error):
        self.error = error

    def send(self, to, text_):
        raise self.error

    def connection_state(self):
        return "close"


def test_channel_down_is_retried_later_then_fails(admin_client, drivers, db, monkeypatch):
    queue_all(admin_client)
    monkeypatch.setattr(messaging, "provider", lambda: Down(messaging.DeliveryError("down")))
    assert link_queue.send_next(db, at(0)) == "message_not_delivered"
    assert link_queue.send_next(db, at(1.1)) == "message_not_delivered"  # the second driver's turn
    assert link_queue.send_next(db, at(2.2)) == "empty"  # both wait 10 minutes before a retry
    assert link_queue.send_next(db, at(11)) == "message_not_delivered"
    assert link_queue.send_next(db, at(22)) == "message_not_delivered"
    assert link_queue.send_next(db, at(23.1)) == "message_not_delivered"  # third attempt: given up
    items = admin_client.get("/api/v1/activation-links/queue").json()["items"]
    first = next(i for i in items if i["attempts"] == 3)
    assert first["status"] == "failed" and first["error"] == "message_not_delivered"
    assert db.execute(text("SELECT count(*) FROM identity.activation_links")).scalar() == 0  # no usable link left


def test_a_number_without_whatsapp_fails_at_once(admin_client, drivers, db, monkeypatch):
    queue_all(admin_client)
    monkeypatch.setattr(messaging, "provider", lambda: Down(messaging.NotOnWhatsApp("no")))
    assert link_queue.send_next(db, at(0)) == "phone_not_on_whatsapp"
    items = admin_client.get("/api/v1/activation-links/queue").json()["items"]
    assert [i["status"] for i in items].count("failed") == 1


def test_cancel_stops_what_is_waiting(admin_client, drivers, db):
    queue_all(admin_client)
    assert admin_client.post("/api/v1/activation-links/queue/cancel").json() == {"cancelled": 2}
    assert link_queue.send_next(db, at(0)) == "empty"
    assert queue_all(admin_client)["queued"] == 2  # can be queued again later


def test_scope_and_permission(admin_client, new_client, companies, db):
    a, b = companies["a"]["id"], companies["b"]["id"]
    make_driver(admin_client, a)
    in_b = make_driver(admin_client, b)
    make_user(admin_client, "sup_a", permissions=["devices.manage"], company_ids=[a])
    c = new_client()
    login(c, "sup_a")
    assert c.post("/api/v1/activation-links/bulk", json={"all_unbound": True}).json()["queued"] == 1
    r = c.post("/api/v1/activation-links/bulk", json={"employee_ids": [in_b["id"]]})
    assert r.status_code == 404
    assert c.get("/api/v1/activation-links/queue").json()["waiting"] == 1
    make_user(admin_client, "viewer", permissions=["employees.view"])
    c = new_client()
    login(c, "viewer")
    assert c.post("/api/v1/activation-links/bulk", json={"all_unbound": True}).status_code == 403
