"""Email through the SMTP server set up in the control panel: tried before it is switched on, the site's contact
messages and serious errors queued and sent by the background job to the office's addresses, an error not repeated
within 30 minutes, nothing queued while email is off."""

import pytest

from app.core import mailer
from app.modules.integrations import service as integrations

C = "/api/v1/integrations/connections"


class FakeSmtp:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.refuse = False

    def __call__(self, host, port, security, username, password, from_address, from_name):
        self.args = (host, port, security, username, password, from_address, from_name)
        return self

    def check(self):
        if self.refuse:
            raise mailer.MailError("SMTPAuthenticationError: (535, b'bad credentials')")

    def send(self, to, subject, body, reply_to=None):
        if self.refuse:
            raise mailer.MailError("SMTPServerDisconnected: down")
        self.sent.append({"to": to, "subject": subject, "body": body, "reply_to": reply_to})


@pytest.fixture
def smtp(monkeypatch):
    fake = FakeSmtp()
    monkeypatch.setattr(integrations, "_smtp_factory", fake)
    return fake


def email_body(version=0, **config):
    return {
        "version": version,
        "config": {
            "enabled": True,
            "host": "smtp.example.com",
            "port": 587,
            "security": "starttls",
            "username": "office@example.com",
            "from_address": "office@example.com",
            "from_name": "Office",
            "notify_to": ["boss@example.com", "ops@example.com"],
        }
        | config,
        "secrets": {"password": "app-password-123"},
    }


def test_switching_email_on_tries_the_server_and_secrets_stay_write_only(admin_client, smtp):
    smtp.refuse = True
    r = admin_client.put(f"{C}/email", json=email_body())
    assert r.status_code == 422 and r.json()["code"] == "connection_check_failed", r.text
    smtp.refuse = False
    r = admin_client.put(f"{C}/email", json=email_body())
    assert r.status_code == 200, r.text
    assert r.json()["secrets"]["password"] == {"set": True, "hint": "…-123"}
    assert smtp.args[:5] == ("smtp.example.com", 587, "starttls", "office@example.com", "app-password-123")
    r = admin_client.put(f"{C}/email", json=email_body(version=1, notify_to=[]))
    assert r.json()["code"] == "connection_incomplete"


def test_a_contact_message_is_emailed_to_the_office(client, admin_client, smtp, db):
    client.post("/api/v1/site/contact", json={"name": "قبل", "phone": "1", "message": "قبل تشغيل الإيميل"})
    assert integrations.send_queued_emails(db) == 0  # email off: nothing was queued
    assert admin_client.put(f"{C}/email", json=email_body()).status_code == 200
    r = client.post(
        "/api/v1/site/contact",
        json={"name": "سعد", "phone": "+96550000000", "email": "saad@example.com", "message": "عايز أشتغل"},
    )
    assert r.status_code == 204
    assert integrations.send_queued_emails(db) == 1
    mail = smtp.sent[0]
    assert mail["to"] == ["boss@example.com", "ops@example.com"] and "سعد" in mail["subject"]
    assert "عايز أشتغل" in mail["body"] and mail["reply_to"] == "saad@example.com"
    assert integrations.send_queued_emails(db) == 0  # sent once


def test_a_refused_email_waits_and_is_tried_again(client, admin_client, smtp, db):
    assert admin_client.put(f"{C}/email", json=email_body()).status_code == 200
    client.post("/api/v1/site/contact", json={"name": "سعد", "phone": "1", "message": "رسالة مهمة"})
    smtp.refuse = True
    assert integrations.send_queued_emails(db) == 0
    smtp.refuse = False
    assert integrations.send_queued_emails(db) == 1


def test_a_serious_error_is_emailed_once_per_half_hour(admin_client, smtp, db):
    assert admin_client.put(f"{C}/email", json=email_body()).status_code == 200

    def boom():
        raise RuntimeError("database exploded")

    for _ in range(3):
        try:
            boom()
        except RuntimeError as exc:
            integrations.report_error("GET /api/v1/test", exc)
    assert integrations.send_queued_emails(db) == 1
    assert "[Error] RuntimeError" in smtp.sent[0]["subject"] and "database exploded" in smtp.sent[0]["body"]

    admin_client.put(f"{C}/email", json=email_body(version=1, error_alerts=False))
    integrations._cache.clear()
    try:
        raise ValueError("other")
    except ValueError as exc:
        integrations.report_error("worker", exc)
    assert integrations.send_queued_emails(db) == 0  # error alerts turned off
