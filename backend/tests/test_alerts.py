"""In-app alerts reach only the users holding the alert's permission, within their companies."""

import pytest

from app.modules.notifications import service as notifications
from tests.conftest import login, make_user


@pytest.fixture
def alerts(db, companies):
    a, b = companies["a"]["id"], companies["b"]["id"]
    driver = {"ar": "أحمد", "en": "Ahmed"}
    notifications.raise_alert(db, "gps_off", company_id=a, params={"driver": driver, "plate": "11-111"})
    notifications.raise_alert(db, "gps_off", company_id=b, params={"driver": driver, "plate": "22-222"})
    notifications.raise_alert(db, "odometer_photo_reused", company_id=a, params={"driver": driver, "plate": "11-111"})
    db.commit()


def test_permission_and_company_filtering(admin_client, new_client, companies, alerts):
    a = companies["a"]["id"]
    assert len(admin_client.get("/api/v1/alerts").json()) == 3
    make_user(admin_client, "live_a", permissions=["tracking.live"], company_ids=[a])
    c = new_client()
    login(c, "live_a")
    seen = c.get("/api/v1/alerts").json()
    assert [(x["kind"], x["company_id"]) for x in seen] == [("gps_off", a)]
    hidden = [x for x in admin_client.get("/api/v1/alerts").json() if x["company_id"] != a or x["kind"] != "gps_off"]
    for alert in hidden:
        assert c.post(f"/api/v1/alerts/{alert['id']}/ack").status_code == 404
    for alert in hidden:
        assert c.post(f"/api/v1/alerts/{alert['id']}/resolve", json={"note": "x"}).status_code == 404
    # seen is not handled: the alert stays open, marked seen by him, until he says what was done
    assert c.post(f"/api/v1/alerts/{seen[0]['id']}/ack").status_code == 204
    still = c.get("/api/v1/alerts").json()
    assert [x["status"] for x in still] == ["seen"] and still[0]["acknowledged_by"]["name"].endswith("(live_a)")
    assert c.post(f"/api/v1/alerts/{seen[0]['id']}/resolve", json={"note": "  "}).status_code == 422
    assert c.post(f"/api/v1/alerts/{seen[0]['id']}/resolve", json={"note": "اتصلنا بالسائق"}).status_code == 204
    assert c.get("/api/v1/alerts").json() == []
    closed = c.get("/api/v1/alerts", params={"open": False}).json()
    assert closed[0]["resolution"] == "manual" and closed[0]["resolution_note"] == "اتصلنا بالسائق"
    assert c.post(f"/api/v1/alerts/{seen[0]['id']}/resolve", json={"note": "again"}).status_code == 409


def test_messages_follow_the_readers_language(admin_client, alerts):
    ar = admin_client.get("/api/v1/alerts", params={"kind": "gps_off"}, headers={"Accept-Language": "ar"}).json()
    en = admin_client.get("/api/v1/alerts", params={"kind": "gps_off"}, headers={"Accept-Language": "en"}).json()
    assert "أحمد" in ar[0]["message"] and "Ahmed" in en[0]["message"]
    assert en[0]["params"]["driver"] == "Ahmed" and "{" not in en[0]["message"]


def test_an_alert_without_its_params_is_a_bug(db):
    with pytest.raises(ValueError, match="plate"):
        notifications.raise_alert(db, "gps_off", company_id=None, params={"driver": "x"})


def test_one_open_alert_per_situation(db, admin_client):
    for _ in range(3):
        notifications.raise_alert(
            db, "gps_off", company_id=None, params={"driver": "x", "plate": "1"}, dedupe_key="gps_off:1"
        )
    db.commit()
    assert len(admin_client.get("/api/v1/alerts").json()) == 1
    notifications.resolve(db, "gps_off:1")
    db.commit()
    assert admin_client.get("/api/v1/alerts").json() == []


def test_the_summary_counts_visible_open_alerts_and_names_the_newest(admin_client, db, company):
    before = admin_client.get("/api/v1/alerts/summary").json()
    for i in range(3):
        notifications.raise_alert(
            db, "gps_off", company_id=company["id"], params={"driver": f"S{i}", "plate": "1"}, dedupe_key=f"sum:{i}"
        )
    db.commit()
    s = admin_client.get("/api/v1/alerts/summary").json()
    assert s["open"] == before["open"] + 3 and s["warning"] == before["warning"] + 3
    newest = admin_client.get("/api/v1/alerts", params={"limit": 1}).json()[0]
    assert s["latest"]["id"] == newest["id"] and "S2" in s["latest"]["message"]
    admin_client.post(f"/api/v1/alerts/{newest['id']}/ack")
    seen = admin_client.get("/api/v1/alerts/summary").json()
    assert seen["open"] == s["open"] and seen["new"] == s["new"] - 1  # seen: off the bell, still open
    admin_client.post(f"/api/v1/alerts/{newest['id']}/resolve", json={"note": "done"})
    after = admin_client.get("/api/v1/alerts/summary").json()
    assert after["open"] == s["open"] - 1 and after["latest"]["id"] != newest["id"]


def test_the_summary_is_not_capped_and_follows_permissions(admin_client, new_client, db, company):
    for i in range(205):
        notifications.raise_alert(
            db, "gps_off", company_id=company["id"], params={"driver": f"C{i}", "plate": "1"}, dedupe_key=f"cap:{i}"
        )
    db.commit()
    assert admin_client.get("/api/v1/alerts/summary").json()["open"] >= 205  # the bell no longer stops at 200
    make_user(admin_client, "nobody", permissions=["employees.view"])
    c = new_client()
    login(c, "nobody")
    assert c.get("/api/v1/alerts/summary").json() == {
        "open": 0,
        "critical": 0,
        "warning": 0,
        "info": 0,
        "new": 0,
        "mine": 0,
        "latest": None,
    }


# ------------------------------------------------------------------ handling: filters, assignee, escalation, log


def _raise(db, kind, company_id, params, key):
    notifications.raise_alert(db, kind, company_id=company_id, params=params, dedupe_key=key)


def test_filters_search_period_and_the_most_severe_first(admin_client, db, companies):
    a = companies["a"]["id"]
    _raise(db, "gps_off", a, {"driver": {"ar": "سالم", "en": "Salem"}, "plate": "71-111"}, "f:1")
    _raise(db, "odometer_photo_reused", a, {"driver": "Fahd", "plate": "72-222"}, "f:2")
    _raise(db, "onboarding_submitted", a, {"driver": "Nasser"}, "f:3")
    db.commit()
    get = lambda **p: admin_client.get("/api/v1/alerts", params=p, headers={"Accept-Language": "ar"}).json()  # noqa: E731
    assert [x["severity"] for x in get(sort="severity")] == ["critical", "warning", "info"]
    assert [x["kind"] for x in get(severity="critical")] == ["odometer_photo_reused"]
    assert [x["kind"] for x in get(q="سالم")] == ["gps_off"]  # a name in the params
    assert [x["kind"] for x in get(q="72-222")] == ["odometer_photo_reused"]  # a plate
    assert {x["kind"] for x in get(q="مستخدمة من قبل")} == {"odometer_photo_reused"}  # words of the text itself
    assert get(q="%") == []  # a wildcard is a character searched, not a pattern
    assert len(get(since="2000-01-01T00:00:00+03:00")) == 3 and get(until="2000-01-01T00:00:00+03:00") == []
    assert len(get(status="new")) == 3 and get(status="seen") == []
    assert [x["id"] for x in get(sort="severity", limit=1, offset=1)] == [get(sort="severity")[1]["id"]]


def test_assign_escalate_and_the_log_of_what_was_done(admin_client, new_client, db, companies, superuser):
    a, b = companies["a"]["id"], companies["b"]["id"]
    _raise(db, "gps_off", a, {"driver": "x", "plate": "73-333"}, "h:1")
    db.commit()
    alert = admin_client.get("/api/v1/alerts").json()[0]
    peer = make_user(admin_client, "peer_a", permissions=["tracking.live"], company_ids=[a])
    make_user(admin_client, "other_b", permissions=["tracking.live"], company_ids=[b])
    make_user(admin_client, "cash_a", permissions=["cash.view"], company_ids=[a])
    names = [u["name"] for u in admin_client.get(f"/api/v1/alerts/{alert['id']}/handlers").json()]
    assert any("(peer_a)" in n for n in names)
    assert not any("(other_b)" in n or "(cash_a)" in n for n in names)  # another company, another permission
    others = [u for u in admin_client.get("/api/v1/users").json() if u["username"] in ("other_b", "cash_a")]
    for u in others:
        r = admin_client.post(f"/api/v1/alerts/{alert['id']}/assign", json={"user_id": u["public_id"]})
        assert r.status_code == 422 and r.json()["code"] == "alert_handler_cannot_see"

    assert (
        admin_client.post(f"/api/v1/alerts/{alert['id']}/assign", json={"user_id": peer["public_id"]}).status_code
        == 204
    )
    c = new_client()
    login(c, "peer_a")
    assert admin_client.get("/api/v1/alerts/summary").json()["mine"] == 0
    assert c.get("/api/v1/alerts/summary").json()["mine"] == 1
    assert [x["id"] for x in c.get("/api/v1/alerts", params={"assigned": "me"}).json()] == [alert["id"]]
    me = admin_client.get("/api/v1/auth/me").json()["public_id"]
    r = c.post(f"/api/v1/alerts/{alert['id']}/escalate", json={"user_id": peer["public_id"], "note": "x"})
    assert r.status_code == 422 and r.json()["code"] == "alert_escalate_to_self"
    assert c.post(f"/api/v1/alerts/{alert['id']}/escalate", json={"user_id": me, "note": "  "}).status_code == 422
    assert (
        c.post(f"/api/v1/alerts/{alert['id']}/escalate", json={"user_id": me, "note": "يحتاج قرار"}).status_code == 204
    )
    d = admin_client.get(f"/api/v1/alerts/{alert['id']}").json()
    assert d["status"] == "seen" and d["escalated_at"] and d["assigned_to"]["id"] == me
    assert d["escalated_by"]["name"].endswith("(peer_a)")
    admin_client.post(f"/api/v1/alerts/{alert['id']}/resolve", json={"note": "أعيد تشغيل الـ GPS"})
    d = admin_client.get(f"/api/v1/alerts/{alert['id']}").json()
    assert [e["action"] for e in d["events"]] == ["assigned", "escalated", "resolved"]
    assert d["events"][1]["note"] == "يحتاج قرار" and d["events"][1]["by"]["name"].endswith("(peer_a)")
    assert d["status"] == "resolved" and d["resolution"] == "manual"
    r = admin_client.post(f"/api/v1/alerts/{alert['id']}/assign", json={"user_id": None})
    assert r.status_code == 409 and r.json()["code"] == "alert_resolved"
    log = admin_client.get("/api/v1/audit", params={"entity_type": "alert"}).json()
    assert {"alert.assigned", "alert.escalated", "alert.resolved"} <= {e["action"] for e in log}


def test_a_refreshed_alert_says_when_its_figures_changed(admin_client, db):
    for balance in ("210.000", "210.000", "260.000"):
        notifications.raise_alert(
            db,
            "cash_balance_high",
            company_id=None,
            params={"driver": "x", "balance": balance, "limit": "200.000"},
            dedupe_key="refresh:1",
            refresh=True,
        )
        db.commit()
        alert = admin_client.get("/api/v1/alerts").json()[0]
        assert (alert["updated_at"] is None) == (balance == "210.000")
    assert "260.000" in alert["message"]


def test_dates_in_a_text_read_day_first_and_the_cause_gone_closes_it_automatically(admin_client, db):
    notifications.raise_alert(
        db,
        "document_expired",
        company_id=None,
        params={"document": "Residence", "owner": "x", "date": "2026-11-05"},
        entity_type="document",
        entity_id="d-1",
    )
    db.commit()
    alert = admin_client.get("/api/v1/alerts", headers={"Accept-Language": "en"}).json()[0]
    assert "05-11-2026" in alert["message"] and alert["params"]["date"] == "2026-11-05"
    notifications.resolve_entity(db, "document", "d-1")
    db.commit()
    closed = admin_client.get("/api/v1/alerts", params={"status": "resolved"}).json()[0]
    assert closed["resolution"] == "auto" and closed["resolved_by"] is None and closed["acknowledged_at"] is None
