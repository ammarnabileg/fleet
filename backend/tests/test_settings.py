import json
import pathlib

from sqlalchemy import text

from app.core.db import new_session
from app.modules.org import service as org

TENANT = pathlib.Path(__file__).resolve().parents[2] / "deploy" / "tenants" / "ajwad" / "settings.json"


def test_defaults_validation_versioning_audit_and_event(admin_client, db):
    s = admin_client.get("/api/v1/settings").json()
    assert s["tracking"] == {
        "version": 0,
        "value": {
            "interval_moving_s": 30,
            "interval_stationary_s": 300,
            "signal_loss_minutes": 10,
            "retention_months": 0,
        },
    }
    bad = admin_client.put("/api/v1/settings/tracking", json={"version": 0, "value": {"interval_moving_s": 1}})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_settings"
    extra = admin_client.put("/api/v1/settings/tracking", json={"version": 0, "value": {"surprise": 1}})
    assert extra.status_code == 422
    assert admin_client.put("/api/v1/settings/nope", json={"version": 0, "value": {}}).status_code == 404

    ok = admin_client.put("/api/v1/settings/cash", json={"version": 0, "value": {"driver_balance_alert": "75.500"}})
    assert ok.status_code == 200 and ok.json() == {
        "version": 1,
        "value": {"driver_balance_alert": "75.500", "report_review_hours": 24, "fuel_max_amount": "50.000"},
    }
    stale = admin_client.put("/api/v1/settings/cash", json={"version": 0, "value": {}})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"

    audit_row = db.execute(
        text(
            "SELECT before->>'driver_balance_alert', after->>'driver_balance_alert' "
            "FROM audit.events WHERE action = 'settings.changed'"
        )
    ).one()
    assert audit_row == ("80.000", "75.500")
    event = db.execute(
        text("SELECT payload FROM integrations.outbox WHERE event_type = 'settings.changed'")
    ).scalar_one()
    assert event == {"section": "cash", "version": 1}
    assert str(org.get_section(db, "cash").driver_balance_alert) == "75.500"


def test_client_settings_file_applies_cleanly(database_url):
    from app.ops.apply_settings import main

    assert main(str(TENANT)) == 0
    wanted = json.loads(TENANT.read_text(encoding="utf-8"))
    with new_session() as db:
        for section, value in wanted.items():
            version, model = org.all_sections(db)[section]
            assert version == 1
            assert {k: model.model_dump(mode="json")[k] for k in value} == value


def test_branding_is_public_and_follows_the_settings(client, admin_client):
    assert client.get("/api/v1/branding").json() == {"display_name": "BrilliantTech Fleet", "primary_color": "#0A6CFF"}
    v = admin_client.get("/api/v1/settings").json()["branding"]["version"]
    r = admin_client.put("/api/v1/settings/branding", json={"version": v, "value": {"display_name": "شركة التجربة"}})
    assert r.status_code == 200, r.text
    anonymous = client.__class__(client.app)  # no session cookie
    assert anonymous.get("/api/v1/branding").json()["display_name"] == "شركة التجربة"
