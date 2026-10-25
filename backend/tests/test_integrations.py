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


def files_status(client) -> dict:
    return connection(client, "storage")["status"]["files"]


def disk_path(data: bytes):
    from app.core.config import get_settings
    from app.core.storage import LocalStorage

    return LocalStorage(get_settings().files_dir).path(hashlib.sha256(data).hexdigest())


def test_files_go_to_r2_once_it_is_on_and_old_ones_stay_readable_until_copied(admin_client, company, r2, db):
    from app.modules.files import service as files

    before = jpeg()
    old = fine_with_file(admin_client, company, before)
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200

    after = jpeg()
    new = fine_with_file(admin_client, company, after)
    sha = hashlib.sha256(after).hexdigest()
    assert r2.objects[f"files/{sha}"] == (after, "image/jpeg")
    assert not disk_path(after).exists()  # R2 alone: no disk copy
    assert hashlib.sha256(before).hexdigest() not in "".join(r2.objects)
    assert files_status(admin_client).items() >= {"local": 1, "r2": 1, "to_r2": 1, "to_disk": 1}.items()
    assert connection(admin_client, "storage")["status"]["sync"] == ["to_r2"]
    for f, data in ((old, before), (new, after)):
        r = admin_client.get(f"/api/v1/fines/{f['id']}/file")
        assert r.status_code == 200 and r.content == data, r.text
        assert r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"].startswith("private")

    # the background copy puts the old file in R2 too; it is then read from R2 even if the disk copy is gone
    assert files.sync(db, "to_r2") == {"copied": 1, "missing": [], "last": None}
    with pytest.raises(Exception, match="storage_sync_off"):
        files.sync(db, "to_disk")  # R2 alone: nothing is copied back to the disk
    disk_path(before).unlink()
    assert admin_client.get(f"/api/v1/fines/{old['id']}/file").content == before
    assert files_status(admin_client).items() >= {"r2": 2, "to_r2": 0}.items()

    # the same file uploaded again is not written twice
    r2.objects.clear()
    upload(admin_client, after)
    assert not r2.objects


def test_both_keeps_a_copy_on_the_disk_and_in_r2_and_copies_each_way(admin_client, company, r2, db):
    """The office's choice "both": every new file is written to the disk and to R2; the files written before (on the
    disk alone, or in R2 alone) are copied the other way; a file is read from wherever a copy is."""
    from app.modules.files import service as files

    on_disk = jpeg()
    fine_disk = fine_with_file(admin_client, company, on_disk)  # the disk alone (R2 off)
    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200
    in_r2 = jpeg()
    fine_r2 = fine_with_file(admin_client, company, in_r2)  # R2 alone
    r = admin_client.put(f"{C}/storage", json={"version": 1, "config": storage_body()["config"] | {"provider": "both"}})
    assert r.status_code == 200 and r.json()["config"]["provider"] == "both", r.text
    assert r.json()["status"]["sync"] == ["to_r2", "to_disk"]

    both = jpeg()
    fine_with_file(admin_client, company, both)
    assert disk_path(both).read_bytes() == both
    assert r2.objects[f"files/{hashlib.sha256(both).hexdigest()}"][0] == both
    assert files_status(admin_client) == {"total": 3, "local": 2, "r2": 2, "to_r2": 1, "to_disk": 1}

    # "sync now": each way at once
    r = admin_client.post(f"{C}/storage/sync")
    assert r.status_code == 200, r.text
    assert r.json()["status"]["copied"] == {"to_r2": 1, "to_disk": 1}
    assert r.json()["status"]["files"] == {"total": 3, "local": 3, "r2": 3, "to_r2": 0, "to_disk": 0}
    assert disk_path(in_r2).read_bytes() == in_r2
    assert r2.objects[f"files/{hashlib.sha256(on_disk).hexdigest()}"][0] == on_disk

    # either copy alone is enough to read
    r2.down = True
    assert admin_client.get(f"/api/v1/fines/{fine_r2['id']}/file").content == in_r2
    r2.down = False
    disk_path(on_disk).unlink()
    assert admin_client.get(f"/api/v1/fines/{fine_disk['id']}/file").content == on_disk

    # nothing left to copy: another sync copies nothing
    assert admin_client.post(f"{C}/storage/sync").json()["status"]["copied"] == {"to_r2": 0, "to_disk": 0}
    assert files.sync(db, "to_disk", after="") == {"copied": 0, "missing": [], "last": None}


def test_both_with_r2_down_keeps_the_upload_on_the_disk_and_copies_it_later(admin_client, company, r2):
    assert admin_client.put(f"{C}/storage", json=storage_body(provider="both")).status_code == 200
    r2.down = True
    data = jpeg()
    f = fine_with_file(admin_client, company, data)  # accepted: the disk holds it
    assert admin_client.get(f"/api/v1/fines/{f['id']}/file").content == data
    assert files_status(admin_client).items() >= {"to_r2": 1}.items()
    assert admin_client.post(f"{C}/storage/sync").json()["status"]["copied"] == {"to_r2": 0, "to_disk": 0}
    r2.down = False
    assert admin_client.post(f"{C}/storage/sync").json()["status"]["copied"]["to_r2"] == 1
    assert r2.objects[f"files/{hashlib.sha256(data).hexdigest()}"][0] == data


def test_back_to_the_disk_copies_the_r2_files_home_and_a_copy_already_there_is_only_recorded(
    admin_client, company, r2, db
):
    """Choosing the disk again while R2 is set up: the files in R2 alone are copied back to the disk (none is
    deleted from R2), so the server reads them without R2. A disk copy an operator kept is not downloaded again."""
    from app.modules.files import service as files

    assert admin_client.put(f"{C}/storage", json=storage_body()).status_code == 200
    first, second = jpeg(), jpeg()
    f1 = fine_with_file(admin_client, company, first)
    fine_with_file(admin_client, company, second)
    kept = disk_path(second)
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_bytes(second)  # the operator's copy
    r = admin_client.put(
        f"{C}/storage", json={"version": 1, "config": storage_body()["config"] | {"provider": "local"}}
    )
    assert r.status_code == 200 and r.json()["status"]["sync"] == ["to_disk"], r.text

    gets = []
    real = r2.get_object
    r2.get_object = lambda **kw: gets.append(kw["Key"]) or real(**kw)
    assert files.sync(db, "to_disk") == {"copied": 2, "missing": [], "last": None}
    assert gets == [f"files/{hashlib.sha256(first).hexdigest()}"]  # only the file the disk lacked was downloaded
    assert len([k for k in r2.objects if not k.endswith(".connection-test")]) == 2  # nothing deleted from R2
    r2.down = True
    assert admin_client.get(f"/api/v1/fines/{f1['id']}/file").content == first  # R2 no longer needed to read


def test_a_file_on_no_reachable_copy_is_a_clear_error(admin_client, company, db):
    """A second server on the same database, before a disk-only file reached R2: a clear 503, never a crash."""
    data = jpeg()
    f = fine_with_file(admin_client, company, data)
    disk_path(data).unlink()
    r = admin_client.get(f"/api/v1/fines/{f['id']}/file")
    assert r.status_code == 503 and r.json()["code"] == "storage_unavailable", r.text


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
    assert files_status(admin_client).items() >= {"local": 1, "r2": 1}.items()

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


def test_whatsapp_readiness_tells_a_working_connection_from_messages_that_went_out(
    admin_client, evolution, company, db, owner_db, monkeypatch
):
    """not configured -> working; the test button tries a switched-off service too (no message sent) and a dropped
    WhatsApp session is a failed test; each message is logged as the provider answered, without its text."""
    from app.modules.identity import service as identity
    from tests.conftest import make_driver

    assert connection(admin_client, "whatsapp")["state"] == "not_configured"
    assert admin_client.put(f"{C}/whatsapp", json=whatsapp_body()).status_code == 200
    assert connection(admin_client, "whatsapp")["state"] == "working"

    driver = make_driver(admin_client, company["id"])
    r = admin_client.post("/api/v1/driver/auth/otp", json={"phone": driver["phone"], "device_uid": "f" * 32})
    assert r.status_code == 202
    w = connection(admin_client, "whatsapp")
    (m,) = w["status"]["messages"]["recent"]
    assert (m["status"], m["purpose"], m["provider"], m["recipient"]) == (
        "accepted",
        "otp",
        "evolution",
        "…" + driver["phone"][-4:],
    )
    assert w["status"]["messages"]["accepted"] == 1 and w["status"]["messages"]["last_accepted_at"]
    stored = owner_db.execute(text("SELECT row_to_json(m)::text FROM integrations.message_log m")).scalar()
    assert driver["phone"].lstrip("+") not in stored and "provider_ref" in stored  # no number, no text (code)
    assert '"provider_ref":"1"' in stored

    # the provider refuses: logged as failed even though the caller rolls its transaction back
    state = {"refuse": True}
    real_send = messaging.EvolutionProvider.send

    def refusing(self, to, body):
        if state["refuse"]:
            raise messaging.DeliveryError("evolution api answered 500")
        return real_send(self, to, body)

    monkeypatch.setattr(messaging.EvolutionProvider, "send", refusing)
    r = admin_client.post(f"/api/v1/employees/{driver['id']}/activation-link", json={"channel": "whatsapp"})
    assert r.status_code == 502
    w = connection(admin_client, "whatsapp")["status"]["messages"]
    assert [(x["status"], x["purpose"]) for x in w["recent"]] == [("failed", "activation"), ("accepted", "otp")]
    assert w["last_error"] == "evolution api answered 500"

    # switched off: "disabled", and its test really tries the saved settings
    off = {"version": 1, "config": {"enabled": False, "url": "https://evo.example.com", "instance": "fleet"}}
    assert admin_client.put(f"{C}/whatsapp", json=off).status_code == 200
    w = connection(admin_client, "whatsapp")
    assert (w["state"], w["checked_at"]) == ("disabled", None)
    before = len(evolution)
    checked = admin_client.post(f"{C}/whatsapp/check").json()
    assert checked["check_ok"] is True and checked["state"] == "disabled" and len(evolution) == before + 1
    assert not [c for c in evolution[before:] if "sendText" in c.url.path]  # a test never sends a message

    # on again, then its WhatsApp session drops: the scheduler's check makes the last test a failure
    on = whatsapp_body(version=2)
    on.pop("secrets")
    assert admin_client.put(f"{C}/whatsapp", json=on).status_code == 200
    monkeypatch.setattr(messaging.EvolutionProvider, "connection_state", lambda self: "close")
    integrations._cache.clear()
    integrations._built.clear()
    assert identity.check_messaging_channel(db) == "close"
    w = connection(admin_client, "whatsapp")
    assert w["state"] == "failed" and "close" in w["check_error"]
    checked = admin_client.post(f"{C}/whatsapp/check").json()
    assert checked["check_ok"] is False and "QR" in checked["check_error"]


def test_a_transport_error_is_logged_as_a_failed_message(admin_client, owner_db):
    class Hanging:
        def send(self, to, text):
            raise TimeoutError("read timed out")

    with pytest.raises(TimeoutError):
        integrations.Recorded(Hanging(), "otp").send("+96550001234", "code 123456")
    row = owner_db.execute(text("SELECT status, error, recipient FROM integrations.message_log")).one()
    assert tuple(row) == ("failed", "TimeoutError", "…1234")
