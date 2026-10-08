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
    assert c.post(f"/api/v1/alerts/{seen[0]['id']}/ack").status_code == 204
    assert c.get("/api/v1/alerts").json() == []
    closed = c.get("/api/v1/alerts", params={"open": False}).json()
    assert closed[0]["acknowledged_at"] is not None


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
    assert c.get("/api/v1/alerts/summary").json() == {"open": 0, "critical": 0, "warning": 0, "info": 0, "latest": None}
