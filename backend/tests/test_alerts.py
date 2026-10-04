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
