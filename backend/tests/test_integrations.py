"""External services set up from the control panel: Cloudflare R2 for files, WhatsApp (Evolution API) for sign-in
codes. Secrets are write-only and encrypted; switching a service on tries it first; files stay readable wherever
they were written."""

import base64
import hashlib
import json

import httpx
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import text

from app.core import messaging
from app.modules.integrations import service as integrations
from tests.conftest import jpeg, login, make_user, make_vehicle, upload

C = "/api/v1/integrations/connections"
ACCOUNT = "0123456789abcdef0123456789abcdef"
KEY_ID = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
SECRET = "s3cr3t-0123456789abcdef0123456789abcdef0123456789abcdef01234567"


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def iter_chunks(self, size: int):
        for i in range(0, len(self.data), size):
            yield self.data[i : i + size]


def _error(status: int, code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, "op")


class FakeR2:
    """The S3 calls R2Storage makes, against a dict. It checks the MD5 like R2 does."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.bucket = "fleet-files"
        self.refuse = False  # wrong credentials
        self.down = False  # R2 unreachable

    def _guard(self, bucket):
        if self.down:
            raise _error(503, "ServiceUnavailable")
        if self.refuse:
            raise _error(403, "AccessDenied")
        if bucket != self.bucket:
            raise _error(404, "NoSuchBucket")

    def head_bucket(self, Bucket):  # noqa: N803 (boto3's argument names)
        self._guard(Bucket)
        return {}

    def put_object(self, Bucket, Key, Body, ContentType, ContentMD5):  # noqa: N803
        self._guard(Bucket)
        assert base64.b64encode(hashlib.md5(Body).digest()).decode() == ContentMD5  # noqa: S324
        self.objects[Key] = (Body, ContentType)
        return {}

    def head_object(self, Bucket, Key):  # noqa: N803
        self._guard(Bucket)
        if Key not in self.objects:
            raise _error(404, "404")
        return {"ContentLength": len(self.objects[Key][0])}

    def get_object(self, Bucket, Key):  # noqa: N803
        self._guard(Bucket)
        if Key not in self.objects:
            raise _error(404, "NoSuchKey")
        data = self.objects[Key][0]
        return {"ContentLength": len(data), "Body": _Body(data)}


@pytest.fixture
def r2(monkeypatch):
    fake = FakeR2()
    monkeypatch.setattr(
        integrations, "_r2_client", lambda loaded: fake if loaded.config.bucket == fake.bucket else _wrong(loaded)
    )
    return fake


def _wrong(loaded):
    other = FakeR2()
    other.bucket = "someone-else"
    return other


def storage_body(version=0, **config) -> dict:
    return {
        "version": version,
        "config": {"provider": "r2", "account_id": ACCOUNT, "bucket": "fleet-files", "access_key_id": KEY_ID} | config,
        "secrets": {"secret_access_key": SECRET},
    }


def connection(client, kind) -> dict:
    r = client.get(C)
    assert r.status_code == 200, r.text
    return next(c for c in r.json() if c["kind"] == kind)


def fine_with_file(client, company, data: bytes) -> dict:
    vehicle = make_vehicle(client, company["id"])
    r = client.post(
        "/api/v1/fines",
        json={
            "vehicle_id": vehicle["id"],
            "occurred_at": "2026-01-10T10:00:00+03:00",
            "violation": "Red light",
            "amount": "50.000",
            "file_sha256": upload(client, data),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_secrets_are_write_only_and_encrypted_at_rest(admin_client, r2, owner_db):
    assert connection(admin_client, "storage")["config"]["provider"] == "local"
    r = admin_client.put(f"{C}/storage", json=storage_body())
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["secrets"] == {"secret_access_key": {"set": True, "hint": "…4567"}}
    assert SECRET not in r.text and out["check_ok"] is True and out["version"] == 1
    raw = owner_db.execute(text("SELECT config::text, secrets::text FROM integrations.connections")).one()
    assert SECRET not in raw[0] + raw[1] and KEY_ID in raw[0]
    audit = owner_db.execute(text("SELECT after::text FROM audit.events WHERE action = 'integration.changed'")).one()
    assert SECRET not in audit[0] and "secret_access_key" in audit[0]
    assert SECRET not in admin_client.get(C).text

    # saving again without the secret keeps it; the version guards concurrent edits
    body = storage_body(version=1)
    del body["secrets"]
    r = admin_client.put(f"{C}/storage", json=body)
    assert r.status_code == 200 and r.json()["secrets"]["secret_access_key"]["set"] is True, r.text
    assert admin_client.put(f"{C}/storage", json=storage_body(version=1)).json()["code"] == "version_conflict"


def test_switching_on_tries_the_service_first_and_saves_nothing_when_it_fails(admin_client, r2):
    r2.refuse = True
    r = admin_client.put(f"{C}/storage", json=storage_body())
    assert r.status_code == 422 and r.json()["code"] == "connection_check_failed", r.text
    assert "AccessDenied" in r.json()["params"]["error"]
    assert connection(admin_client, "storage")["version"] == 0
    upload(admin_client)  # uploads still go to the disk
    assert not r2.objects

    body = storage_body()
    body["secrets"] = {}
    r = admin_client.put(f"{C}/storage", json=body)
    assert r.status_code == 422 and r.json()["code"] == "connection_incomplete", r.text
    assert "secret_access_key" in r.json()["params"]["fields"]
    for bad in ({"bucket": "Bad_Bucket"}, {"account_id": "x"}, {"provider": "s3"}, {"extra": 1}):
        r = admin_client.put(f"{C}/storage", json=storage_body(**bad))
        assert r.status_code == 422 and r.json()["code"] == "invalid_connection", (bad, r.text)
    r = admin_client.put(f"{C}/storage", json=storage_body() | {"secrets": {"token": "x" * 10}})
    assert r.json()["code"] == "invalid_connection"
    assert admin_client.put(f"{C}/ftp", json=storage_body()).json()["code"] == "unknown_connection"


def test_files_go_to_r2_once_it_is_on_and_old_ones_stay_readable_until_copied(admin_client, company, r2, db):
    from app.core.config import get_settings
    from app.core.storage import LocalStorage
    from app.modules.files import service as files

    before = jpeg()
    old = fine_with_file(admin_client, company, before)
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200

    after = jpeg()
    new = fine_with_file(admin_client, company, after)
    sha = hashlib.sha256(after).hexdigest()
    assert r2.objects[f"files/{sha}"] == (after, "image/jpeg")
    assert hashlib.sha256(before).hexdigest() not in "".join(r2.objects)
    assert connection(admin_client, "storage")["status"]["files"] == {"local": 1, "r2": 1}
    for f, data in ((old, before), (new, after)):
        r = admin_client.get(f"/api/v1/fines/{f['id']}/file")
        assert r.status_code == 200 and r.content == data, r.text
        assert r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"].startswith("private")

    # the background copy moves the old file; it is then read from R2 even if the disk copy is gone
    out = files.copy_to_r2(db, after="")
    assert out == {"copied": 1, "missing": [], "last": None}
    LocalStorage(get_settings().files_dir).path(hashlib.sha256(before).hexdigest()).unlink()
    assert admin_client.get(f"/api/v1/fines/{old['id']}/file").content == before
    assert connection(admin_client, "storage")["status"]["files"] == {"local": 0, "r2": 2}

    # the same file uploaded again is not written twice
    r2.objects.clear()
    upload(admin_client, after)
    assert not r2.objects


def test_the_bucket_holding_files_cannot_be_switched_away_but_its_key_can_be_replaced(
    admin_client, company, r2, owner_db
):
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200
    fine_with_file(admin_client, company, jpeg())
    r = admin_client.put(f"{C}/storage", json=storage_body(version=1, bucket="another-bucket"))
    assert r.status_code == 409 and r.json()["code"] == "storage_in_use", r.text
    r = admin_client.put(f"{C}/storage", json=storage_body(version=1) | {"secrets": {"secret_access_key": None}})
    assert r.json()["code"] == "connection_incomplete"
    gone = storage_body(version=1, provider="local") | {"secrets": {"secret_access_key": None}}
    assert admin_client.put(f"{C}/storage", json=gone).json()["code"] == "storage_in_use"
    new_secret = "rotated-" + "f" * 56
    r = admin_client.put(f"{C}/storage", json=storage_body(version=1) | {"secrets": {"secret_access_key": new_secret}})
    assert r.status_code == 200 and r.json()["secrets"]["secret_access_key"]["hint"] == "…ffff", r.text
    # back to the disk for new files: the files in R2 stay readable from there
    r = admin_client.put(
        f"{C}/storage", json={"version": 2, "config": storage_body()["config"] | {"provider": "local"}}
    )
    assert r.status_code == 200, r.text
    upload(admin_client)
    assert connection(admin_client, "storage")["status"]["files"] == {"local": 1, "r2": 1}

    # settings lost (a restore, a manual delete): the same bucket can be entered again
    owner_db.execute(text("DELETE FROM integrations.connections"))
    owner_db.commit()
    integrations._cache.clear()
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200


def test_r2_down_is_a_clear_error_not_a_crash(admin_client, company, r2):
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200
    f = fine_with_file(admin_client, company, jpeg())
    r2.down = True
    r = admin_client.get(f"/api/v1/fines/{f['id']}/file")
    assert r.status_code == 503 and r.json()["code"] == "storage_unavailable", r.text
    r = admin_client.post("/api/v1/files", files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 503 and r.json()["code"] == "storage_unavailable", r.text
    r = admin_client.post(f"{C}/storage/check")
    assert r.status_code == 200 and r.json()["check_ok"] is False and "ServiceUnavailable" in r.json()["check_error"]
    r2.down = False
    assert admin_client.post(f"{C}/storage/check").json()["check_ok"] is True


@pytest.fixture
def evolution(monkeypatch):
    calls, state = [], {"status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("apikey") != "evo-key-123456":
            return httpx.Response(401, json={"error": "Unauthorized"})
        if request.url.path.startswith("/instance/connectionState/"):
            return httpx.Response(state["status"], json={"instance": {"state": "open"}})
        return httpx.Response(201, json={"key": {"id": "1"}})

    def build(loaded):
        c = loaded.config
        return messaging.EvolutionProvider(
            c.url, loaded.secrets["api_key"], c.instance, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(integrations, "_evolution", build)
    return calls


def whatsapp_body(version=0, key="evo-key-123456", **config) -> dict:
    return {
        "version": version,
        "config": {"enabled": True, "url": "https://evo.example.com", "instance": "fleet"} | config,
        "secrets": {"api_key": key},
    }


def test_whatsapp_from_the_panel_sends_the_sign_in_codes(admin_client, evolution, company):
    from tests.conftest import make_driver

    assert connection(admin_client, "whatsapp")["status"]["server_mode"] == "log"
    r = admin_client.put(f"{C}/whatsapp", json=whatsapp_body(key="wrong-key-0000"))
    assert r.status_code == 422 and r.json()["code"] == "connection_check_failed", r.text
    assert admin_client.put(f"{C}/whatsapp", json=whatsapp_body()).status_code == 200

    driver = make_driver(admin_client, company["id"])
    r = admin_client.post("/api/v1/driver/auth/otp", json={"phone": driver["phone"], "device_uid": "d" * 32})
    assert r.status_code == 202, r.text
    sent = [c for c in evolution if c.url.path == "/message/sendText/fleet"]
    assert len(sent) == 1 and json.loads(sent[0].content)["number"] == driver["phone"].lstrip("+")
    assert not [m for m in messaging.provider().sent if m.to == driver["phone"]]

    # switched off: the server's own configuration again (the log in tests)
    off = {"version": 1, "config": {"enabled": False, "url": "https://evo.example.com", "instance": "fleet"}}
    assert admin_client.put(f"{C}/whatsapp", json=off).status_code == 200
    admin_client.post("/api/v1/driver/auth/otp", json={"phone": driver["phone"], "device_uid": "e" * 32})
    assert [m for m in messaging.provider().sent if m.to == driver["phone"]]


def test_only_integrations_manage_sees_or_changes_connections(admin_client, new_client, r2):
    make_user(admin_client, "settings_only", permissions=["settings.view", "settings.update"])
    c = new_client()
    login(c, "settings_only")
    for r in (c.get(C), c.put(f"{C}/storage", json=storage_body()), c.post(f"{C}/storage/check")):
        assert r.status_code == 403 and r.json()["code"] == "permission_denied", r.text
    # the settings screen never carries a connection's secrets
    assert "connections" not in c.get("/api/v1/settings").json()
