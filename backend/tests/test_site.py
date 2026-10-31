"""The company's public site: content edited in the panel (the "site" settings section), read by anyone; the contact
form's messages reach the office as messages and an alert; the public reads only the logo set now."""

from tests.conftest import jpeg, make_user, upload


def save_site(admin_client, **changes) -> dict:
    current = admin_client.get("/api/v1/settings").json()["site"]
    r = admin_client.put(
        "/api/v1/settings/site", json={"version": current["version"], "value": current["value"] | changes}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_public_reads_the_content_set_in_the_panel(client, admin_client):
    r = client.get("/api/v1/site")
    assert r.status_code == 200 and r.json()["company_name"]["ar"], r.text
    assert r.json()["download"] is False  # no app release announced yet
    save_site(
        admin_client,
        company_name={"ar": "شركتنا", "en": "Our company"},
        phone="+96512345678",
        services=[{"title": {"ar": "توصيل", "en": "Delivery"}, "text": {"ar": "سائقون", "en": "Drivers"}}],
    )
    body = client.get("/api/v1/site").json()
    assert body["company_name"] == {"ar": "شركتنا", "en": "Our company"} and body["phone"] == "+96512345678"
    assert body["services"][0]["title"]["en"] == "Delivery"

    save_site(admin_client, enabled=False)
    assert client.get("/api/v1/site").json()["code"] == "site_off"


def test_only_the_logo_set_now_is_public(client, admin_client):
    logo, other = jpeg(), jpeg()
    sha, other_sha = upload(admin_client, logo), upload(admin_client, other)
    save_site(admin_client, logo=sha)
    r = client.get(f"/api/v1/site/logo/{sha}")
    assert r.status_code == 200 and r.content == logo
    assert client.get(f"/api/v1/site/logo/{other_sha}").status_code == 404  # any other file stays private


def test_a_contact_message_reaches_the_office(client, admin_client):
    r = client.post("/api/v1/site/contact", json={"name": "سعد", "message": "عايز أشتغل معاكم"})
    assert r.status_code == 422 and r.json()["code"] == "contact_needed"
    r = client.post(
        "/api/v1/site/contact",
        json={"name": "سعد", "phone": "+96550000000", "message": "عايز أشتغل معاكم"},
        headers={"Accept-Language": "ar-KW"},
    )
    assert r.status_code == 204, r.text
    # a bot filling the hidden field is thanked and nothing is kept
    assert (
        client.post(
            "/api/v1/site/contact", json={"name": "bot", "phone": "1", "message": "spam spam", "website": "x"}
        ).status_code
        == 204
    )

    box = admin_client.get("/api/v1/site/messages").json()
    assert box["counts"] == {"new": 1, "read": 0, "done": 0}
    msg = box["items"][0]
    assert msg["name"] == "سعد" and msg["lang"] == "ar" and msg["status"] == "new"
    alerts = admin_client.get("/api/v1/alerts").json()
    items = alerts["items"] if isinstance(alerts, dict) else alerts
    assert any(a["kind"] == "site_message" for a in items)

    r = admin_client.post(f"/api/v1/site/messages/{msg['id']}/status", json={"status": "done"})
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert admin_client.get("/api/v1/site/messages?status=new").json()["items"] == []

    save_site(admin_client, show_contact_form=False)
    r = client.post("/api/v1/site/contact", json={"name": "سعد", "phone": "1", "message": "تاني مرة"})
    assert r.status_code == 404


def test_only_settings_permissions_read_or_handle_messages(admin_client, new_client):
    make_user(admin_client, "clerk", permissions=["employees.view"])
    from tests.conftest import login

    c = new_client()
    login(c, "clerk")
    assert c.get("/api/v1/site/messages").status_code == 403
