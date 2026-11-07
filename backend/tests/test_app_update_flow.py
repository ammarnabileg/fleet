"""«تحديث التطبيق»: the announced version and the forced update, published to Firebase Remote Config with the push
service account (GET with its ETag, PUT with If-Match, through a fake Google: no request leaves the test); the
public download link on our own address; the latest GitHub release imported once into our store (fake GitHub)."""

import json

import httpx
import pytest

from app.modules.app_updates import apk
from app.modules.app_updates import github as gh
from app.modules.integrations import service as integrations
from tests.conftest import login, make_user
from tests.test_push import APP, C, FakeGoogle, _b64decode

PKG = "com.example.fleet.driver"
U = "/api/v1/app-update"
RC = "/v1/projects/fleet-test/remoteConfig"


@pytest.fixture(autouse=True)
def package(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "android_package", PKG)
    monkeypatch.setattr(get_settings(), "public_url", "https://fleet.example.com")


def put_apk(client, code, name=None):
    body = apk.build_apk(PKG, code, name or f"0.1.{code}")
    r = client.post("/api/v1/app-releases", files={"file": ("app.apk", body, "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()


def settings(admin_client) -> dict:
    r = admin_client.get(U)
    assert r.status_code == 200, r.text
    return r.json()


def save(admin_client, **value):
    s = settings(admin_client)
    return admin_client.put(U, json={"version": s["version"], "value": s["value"] | value})


def check(client, code):
    return client.get("/api/v1/driver/app-update", params={"version_code": code}).json()


class FakeRemoteConfig(FakeGoogle):
    """Google's token endpoint (both scopes) and the Remote Config template with its ETag."""

    def __init__(self) -> None:
        super().__init__()
        self.template = {
            "parameters": {"welcome": {"defaultValue": {"value": "hi"}}},
            "conditions": [{"name": "android", "expression": "device.os == 'android'"}],
            "version": {"versionNumber": "7"},
        }
        self.etag = "etag-7"
        self.puts: list[dict] = []
        self.gets = 0
        self.scopes: list[str] = []
        self.refuse: tuple[int, str] | None = None
        self.change_before_put = 0  # someone else publishes between our GET and PUT this many times

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            claims = json.loads(_b64decode(form["assertion"].split(".")[1]))
            self.scopes.append(claims["scope"])
            return httpx.Response(200, json={"access_token": "at-rc", "expires_in": 3600})
        assert request.url.host == "firebaseremoteconfig.googleapis.com" and request.url.path == RC
        assert request.headers["authorization"] == "Bearer at-rc"
        if self.refuse:
            status, message = self.refuse
            return httpx.Response(status, json={"error": {"code": status, "message": message}})
        if request.method == "GET":
            self.gets += 1
            return httpx.Response(200, json=self.template, headers={"ETag": self.etag})
        assert request.method == "PUT"
        if self.change_before_put:
            self.change_before_put -= 1
            self.etag += "x"
        if request.headers.get("if-match") != self.etag:
            return httpx.Response(412, json={"error": {"code": 412, "message": "etag mismatch"}})
        body = json.loads(request.content)
        assert "version" not in body
        self.puts.append(body)
        self.template = body | {"version": {"versionNumber": str(8 + len(self.puts))}}
        self.etag = f"etag-{8 + len(self.puts)}"
        return httpx.Response(200, json=self.template, headers={"ETag": self.etag})

    def values(self) -> dict:
        return {k: v["defaultValue"]["value"] for k, v in self.template["parameters"].items()}


@pytest.fixture
def firebase(monkeypatch, admin_client):
    g = FakeRemoteConfig()
    monkeypatch.setattr(integrations, "_fcm_transport", lambda loaded: httpx.MockTransport(g.handler))
    r = admin_client.put(
        f"{C}/push",
        json={"version": 0, "config": APP, "secrets": {"service_account": json.dumps(g.account)}},
    )
    assert r.status_code == 200, r.text
    return g


# ------------------------------------------------------------------ the setting and the server's check


def test_the_version_must_be_a_release_we_have_and_saving_publishes_it(admin_client, client):
    r = save(admin_client, latest_version="0.1.1057")
    assert r.status_code == 422 and r.json()["code"] == "app_update_release_missing"
    assert r.json()["params"] == {"version_code": 1057}
    for bad in ("1.2", "v0.1.1057", "0.1.1057+1", "abc", "0.1.0", "0.1.99999999999"):
        r = save(admin_client, latest_version=bad)
        assert r.status_code == 422 and r.json()["code"] == "invalid_settings", bad
    r = save(admin_client, force_update=True)
    assert r.status_code == 422 and "force_update" in r.json()["detail"]

    draft = put_apk(admin_client, 1057)
    assert check(client, 1000)["latest"] is None  # a draft is not offered
    r = save(admin_client, latest_version="0.1.1057", notes="Faster start")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["announced"]["version_code"] == 1057 and out["announced"]["forced"] is False
    assert out["download_url"] == "https://fleet.example.com/app/download"
    assert out["remote"]["state"] == "not_configured" and out["remote"]["configured"] is False
    releases = admin_client.get("/api/v1/app-releases").json()["releases"]
    assert releases[0]["id"] == draft["id"] and releases[0]["status"] == "published"
    body = check(client, 1000)
    assert body["latest"]["version_code"] == 1057 and body["required"] is False
    assert body["latest"]["notes"] == "Faster start"  # the release has none: the setting's
    assert check(client, 1057) == {"latest": None, "required": False}

    # forced: every older app must update; the versionCode alone names the same release
    assert save(admin_client, latest_version="1057", force_update=True).status_code == 200
    assert check(client, 1000)["required"] is True


def test_the_announced_version_holds_a_newer_published_one_moves_it_and_it_cannot_be_unpublished(admin_client, client):
    put_apk(admin_client, 1100)
    assert save(admin_client, latest_version="0.1.1100").status_code == 200
    newer = put_apk(admin_client, 1101)
    assert check(client, 1000)["latest"]["version_code"] == 1100  # the draft waits
    pinned = next(x for x in admin_client.get("/api/v1/app-releases").json()["releases"] if x["version_code"] == 1100)
    r = admin_client.post(f"/api/v1/app-releases/{pinned['id']}/unpublish")
    assert r.status_code == 409 and r.json()["code"] == "app_release_announced"
    # publishing a newer one in «تحديثات التطبيق» announces it
    assert admin_client.post(f"/api/v1/app-releases/{newer['id']}/publish").status_code == 200
    assert settings(admin_client)["value"]["latest_version"] == "0.1.1101"
    assert check(client, 1000)["latest"]["version_code"] == 1101
    assert admin_client.post(f"/api/v1/app-releases/{pinned['id']}/unpublish").status_code == 200


def test_left_empty_the_newest_published_release_is_announced_as_before(admin_client, client):
    r = admin_client.get("/api/v1/app-releases")
    assert r.status_code == 200
    first = put_apk(admin_client, 30)
    admin_client.post(f"/api/v1/app-releases/{first['id']}/publish")
    assert settings(admin_client)["value"]["latest_version"] == ""
    assert check(client, 1)["latest"]["version_code"] == 30


def test_the_generic_settings_endpoint_goes_through_the_same_checks(admin_client, client):
    s = admin_client.get("/api/v1/settings").json()["app_update"]
    r = admin_client.put(
        "/api/v1/settings/app_update", json={"version": s["version"], "value": s["value"] | {"latest_version": "77"}}
    )
    assert r.status_code == 422 and r.json()["code"] == "app_update_release_missing"
    put_apk(admin_client, 77)
    r = admin_client.put(
        "/api/v1/settings/app_update", json={"version": s["version"], "value": s["value"] | {"latest_version": "77"}}
    )
    assert r.status_code == 200 and r.json()["value"]["latest_version"] == "77"
    assert check(client, 1)["latest"]["version_code"] == 77


def test_permissions(admin_client, new_client):
    make_user(admin_client, "viewer", permissions=["settings.view"])
    viewer = new_client()
    login(viewer, "viewer")
    assert viewer.get(U).status_code == 200
    assert viewer.get("/api/v1/app-download").status_code == 200
    s = viewer.get(U).json()
    assert viewer.put(U, json={"version": s["version"], "value": s["value"]}).status_code == 403
    assert viewer.post(f"{U}/github-import").status_code == 403
    assert viewer.post(f"{U}/remote-config").status_code == 403
    assert new_client().get(U).status_code == 401


# ------------------------------------------------------------------ Firebase Remote Config


def test_saving_publishes_to_remote_config_with_the_etag(admin_client, firebase):
    put_apk(admin_client, 1057)
    r = save(admin_client, latest_version="0.1.1057", force_update=True, notes="Required fix")
    assert r.status_code == 200, r.text
    remote = r.json()["remote"]
    assert remote["configured"] is True and remote["state"] == "published" and remote["error"] is None
    assert firebase.gets == 1 and len(firebase.puts) == 1
    assert "https://www.googleapis.com/auth/firebase.remoteconfig" in firebase.scopes
    assert firebase.values() == {
        "welcome": "hi",  # someone else's parameter stays
        "driver_latest_version_code": "1057",
        "driver_latest_version_name": "0.1.1057",
        "driver_force_update": "true",
        "driver_download_url": "https://fleet.example.com/app/download",
        "driver_update_notes": "Required fix",
    }
    params = firebase.template["parameters"]
    assert params["driver_latest_version_code"]["valueType"] == "NUMBER"
    assert params["driver_force_update"]["valueType"] == "BOOLEAN"
    assert firebase.template["conditions"][0]["name"] == "android"  # the rest of the template untouched
    assert remote["values"]["driver_latest_version_code"] == "1057"

    # nothing changed: a release published elsewhere that is not announced costs no request
    other = put_apk(admin_client, 1058)
    assert len(firebase.puts) == 1
    # optional again: published at once
    assert save(admin_client, force_update=False).json()["remote"]["state"] == "published"
    assert firebase.values()["driver_force_update"] == "false" and len(firebase.puts) == 2
    # a newer one published in «تحديثات التطبيق» becomes the announced one: Remote Config follows
    admin_client.post(f"/api/v1/app-releases/{other['id']}/publish")
    assert firebase.values()["driver_latest_version_code"] == "1058" and len(firebase.puts) == 3


def test_a_template_changed_in_between_is_read_again_not_overwritten(admin_client, firebase):
    put_apk(admin_client, 1057)
    firebase.change_before_put = 1
    r = save(admin_client, latest_version="0.1.1057")
    assert r.json()["remote"]["state"] == "published"
    assert firebase.gets == 2 and len(firebase.puts) == 1  # 412 on the first PUT: GET again, then PUT with its ETag
    firebase.change_before_put = 5  # keeps changing: given up with the reason, the save itself kept
    r = save(admin_client, notes="x")
    assert r.status_code == 200
    assert r.json()["remote"]["state"] == "failed" and "412" in r.json()["remote"]["error"]
    assert r.json()["value"]["notes"] == "x"


def test_a_refusal_is_shown_and_the_save_kept_then_published_again(admin_client, client, firebase):
    put_apk(admin_client, 1057)
    firebase.refuse = (403, "The caller does not have permission")
    r = save(admin_client, latest_version="0.1.1057")
    assert r.status_code == 200
    remote = r.json()["remote"]
    assert remote["state"] == "failed" and "403" in remote["error"] and "permission" in remote["error"]
    assert check(client, 1000)["latest"]["version_code"] == 1057  # the server's own check answers anyway
    firebase.refuse = None
    r = admin_client.post(f"{U}/remote-config")
    assert r.status_code == 200 and r.json()["remote"]["state"] == "published"
    assert firebase.values()["driver_latest_version_code"] == "1057"


def test_without_push_nothing_is_sent(admin_client, monkeypatch):
    sent = []
    monkeypatch.setattr(integrations, "_fcm_transport", lambda loaded: httpx.MockTransport(sent.append))
    put_apk(admin_client, 1057)
    assert save(admin_client, latest_version="0.1.1057").json()["remote"]["state"] == "not_configured"
    assert sent == []


def test_the_client_alone_against_errors():
    from app.core.remote_config import RemoteConfigClient, RemoteConfigError

    g = FakeRemoteConfig()
    client = RemoteConfigClient(json.dumps(g.account), transport=httpx.MockTransport(g.handler))
    etag = client.publish({"driver_force_update": ("true", "BOOLEAN", "d")})
    assert etag == g.etag and g.values()["driver_force_update"] == "true"
    g.refuse = (404, "project not found")
    with pytest.raises(RemoteConfigError, match="404"):
        client.publish({"x": ("1", "NUMBER", "d")})

    def down(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(RemoteConfigError, match="unreachable|token request failed"):
        RemoteConfigClient(json.dumps(g.account), transport=httpx.MockTransport(down)).publish({})

    def no_etag(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={})

    with pytest.raises(RemoteConfigError, match="ETag"):
        RemoteConfigClient(json.dumps(g.account), transport=httpx.MockTransport(no_etag)).publish({})
    with pytest.raises(RemoteConfigError):
        RemoteConfigClient("not json")


# ------------------------------------------------------------------ the public download link


def test_the_public_link_serves_the_announced_apk_under_its_version_name(admin_client, client, monkeypatch):
    assert client.get("/app/download").status_code == 404  # nothing published yet
    rel = put_apk(admin_client, 1057)
    assert client.get("/app/download").status_code == 404  # a draft is not public
    assert client.get("/app/download/0.1.1057").status_code == 404
    s = settings(admin_client)
    admin_client.put(
        U,
        json={
            "version": s["version"],
            "value": s["value"] | {"latest_version": "0.1.1057", "download_name": "Fleet-Driver"},
        },
    )
    r = client.get("/app/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    assert 'filename="Fleet-Driver-0.1.1057.apk"' in r.headers["content-disposition"]
    assert len(r.content) == rel["size_bytes"] and r.content.startswith(b"PK")
    for v in ("0.1.1057", "1057"):
        r = client.get(f"/app/download/{v}")
        assert r.status_code == 200 and "Fleet-Driver-0.1.1057.apk" in r.headers["content-disposition"]
    assert client.head("/app/download").status_code == 200
    assert client.get("/app/download/9.9.9").status_code == 404
    assert client.get("/app/download/..%2F..%2Fetc").status_code == 404
    part = client.get("/app/download", headers={"Range": "bytes=5-"})
    assert part.status_code == 206

    info = admin_client.get("/api/v1/app-download").json()
    assert info["url"] == "https://fleet.example.com/app/download"
    assert info["version_url"] == "https://fleet.example.com/app/download/0.1.1057"
    assert info["release"]["file_name"] == "Fleet-Driver-0.1.1057.apk"
    assert info["release"]["size_bytes"] == rel["size_bytes"]

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_app_download_per_15min", 2)
    codes = [client.get("/app/download").status_code for _ in range(3)]
    assert 429 in codes


# ------------------------------------------------------------------ GitHub releases


class FakeGitHub:
    def __init__(self, data: bytes, name="0.1.1057", asset=None) -> None:
        self.data = data
        self.release = {
            "tag_name": f"v{name}",
            "name": name,
            "assets": [
                {"name": "notes.txt", "size": 4, "url": "https://api.github.com/repos/o/r/releases/assets/1"},
                {
                    "name": asset or f"{name}.apk",
                    "size": len(data),
                    "url": "https://api.github.com/repos/o/r/releases/assets/2",
                },
            ],
        }
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/repos/o/r/releases/latest":
            if self.status != 200:
                return httpx.Response(self.status, json={"message": "Not Found"})
            return httpx.Response(200, json=self.release)
        if request.url.path == "/repos/o/r/releases/assets/2":
            assert request.headers["accept"] == "application/octet-stream"
            return httpx.Response(302, headers={"Location": "https://objects.githubusercontent.com/file?sig=1"})
        assert request.url.host == "objects.githubusercontent.com"
        assert "authorization" not in request.headers  # the token never goes to the storage host
        return httpx.Response(200, content=self.data)


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub(apk.build_apk(PKG, 1057, "0.1.1057"))
    monkeypatch.setattr(gh, "_transport", lambda: httpx.MockTransport(fake.handler))
    return fake


def test_import_the_latest_github_release_once_as_a_draft(admin_client, client, github, monkeypatch):
    r = admin_client.post(f"{U}/github-import")
    assert r.status_code == 422 and r.json()["code"] == "github_not_configured"
    assert save(admin_client, github_repo="o/r").status_code == 200
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "github_token", "ghp_secret")
    r = admin_client.post(f"{U}/github-import")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True and body["tag"] == "v0.1.1057"
    rel = body["release"]
    assert (rel["version_code"], rel["version_name"], rel["status"], rel["origin"]) == (
        1057,
        "0.1.1057",
        "draft",
        "github",
    )
    assert github.requests[0].headers["authorization"] == "Bearer ghp_secret"
    gh_state = settings(admin_client)["github"]
    assert gh_state["state"] == "imported" and gh_state["release"] == "0.1.1057" and gh_state["token"] is True
    assert "ghp_secret" not in json.dumps(settings(admin_client))
    # not announced by the import: a human decision
    assert check(client, 1000)["latest"] is None
    assert client.get("/app/download").status_code == 404

    # again: recognised by its name, nothing downloaded
    n = len(github.requests)
    again = admin_client.post(f"{U}/github-import").json()
    assert again["created"] is False and again["release"]["id"] == rel["id"]
    assert len(github.requests) == n + 1
    assert settings(admin_client)["github"]["state"] == "up_to_date"

    # announced: the public link serves the file from our store, GitHub is not asked
    assert save(admin_client, latest_version="0.1.1057").status_code == 200
    n = len(github.requests)
    r = client.get("/app/download")
    assert r.status_code == 200 and r.content == github.data and len(github.requests) == n


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "github_no_release"),
        ("no_apk", "github_no_apk"),
        ("mismatch", "github_apk_mismatch"),
        ("down", "github_unreachable"),
        ("wrong_package", "apk_wrong_package"),
    ],
)
def test_github_problems_are_reported_and_nothing_is_stored(admin_client, github, case, code):
    assert save(admin_client, github_repo="o/r").status_code == 200
    if case == "missing":
        github.status = 404
    elif case == "no_apk":
        github.release["assets"] = github.release["assets"][:1]
    elif case == "mismatch":
        github.data = apk.build_apk(PKG, 1056, "0.1.1056")
    elif case == "down":
        github.status = 500
    else:
        github.data = apk.build_apk("com.other.app", 1057, "0.1.1057")
    r = admin_client.post(f"{U}/github-import")
    assert r.status_code in (404, 413, 422, 502) and r.json()["code"] == code, r.text
    assert admin_client.get("/api/v1/app-releases").json()["releases"] == []
    gh_state = settings(admin_client)["github"]
    assert gh_state["state"] == "failed" and gh_state["error"] == code


def test_the_hourly_import_only_when_switched_on(admin_client, github, db):
    assert save(admin_client, github_repo="o/r").status_code == 200
    assert gh.auto_import(db) is False and github.requests == []
    assert save(admin_client, github_auto_import=True).status_code == 200
    from app.modules.org import service as org

    org._cache.clear()
    assert gh.auto_import(db) is True
    rel = admin_client.get("/api/v1/app-releases").json()["releases"][0]
    assert rel["origin"] == "github" and rel["status"] == "draft"
    assert gh.auto_import(db) is False  # already there
