"""Firebase Remote Config, written from the server (REST API v1) with the same service account as push, so the
driver app learns its newest version from Firebase without asking our server. A publish reads the current template
with its ETag, changes only our parameters (the rest of the template stays as it was) and writes it back with
If-Match: a template changed by someone else in between is read again once, never overwritten blindly.

The service account needs the Remote Config permission (role «Firebase Remote Config Admin», or the
cloudconfig.configs.get/update permissions) besides the messaging one; without it Google answers 403 and the panel
shows that. Failures raise RemoteConfigError with a short reason."""

import httpx

from app.core.push import PushError, ServiceAccountAuth, parse_service_account

SCOPE = "https://www.googleapis.com/auth/firebase.remoteconfig"
URL = "https://firebaseremoteconfig.googleapis.com/v1/projects/{project}/remoteConfig"


class RemoteConfigError(Exception):
    pass


def _reason(r: httpx.Response) -> str:
    try:
        message = r.json().get("error", {}).get("message") or r.text
    except ValueError:
        message = r.text
    return f"Remote Config refused ({r.status_code}): {message[:200]}"


class RemoteConfigClient:
    def __init__(self, service_account: str, *, transport=None, timeout: float = 15.0) -> None:
        try:
            self._key = parse_service_account(service_account)
        except PushError as exc:
            raise RemoteConfigError(str(exc)) from None
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._auth = ServiceAccountAuth(self._key, SCOPE, self._client, error=RemoteConfigError)

    @property
    def project_id(self) -> str:
        return self._key["project_id"]

    @property
    def url(self) -> str:
        return URL.format(project=self.project_id)

    def _headers(self, **extra: str) -> dict:
        return {"Authorization": f"Bearer {self._auth.token()}", "Accept-Encoding": "gzip"} | extra

    def _get(self) -> tuple[dict, str]:
        try:
            r = self._client.get(self.url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise RemoteConfigError(f"Remote Config unreachable: {exc}") from None
        if r.status_code == 401:
            self._auth.reset()
        if r.status_code != 200:
            raise RemoteConfigError(_reason(r))
        etag = r.headers.get("etag")
        if not etag:
            raise RemoteConfigError("Remote Config answered without an ETag")
        return r.json(), etag

    def publish(self, parameters: dict[str, tuple[str, str, str]]) -> str:
        """parameters: {name: (value, valueType STRING|NUMBER|BOOLEAN, description)}. Returns the new ETag."""
        for attempt in range(2):
            template, etag = self._get()
            template.pop("version", None)  # set by Firebase on each publish
            params = template.setdefault("parameters", {})
            for name, (value, value_type, description) in parameters.items():
                current = params.get(name, {})
                params[name] = current | {
                    "defaultValue": {"value": value},
                    "valueType": value_type,
                    "description": description,
                }
            try:
                r = self._client.put(
                    self.url,
                    json=template,
                    headers=self._headers(**{"If-Match": etag, "Content-Type": "application/json; UTF8"}),
                )
            except httpx.HTTPError as exc:
                raise RemoteConfigError(f"Remote Config unreachable: {exc}") from None
            if r.status_code == 200:
                return r.headers.get("etag", "")
            if r.status_code in (409, 412) and attempt == 0:
                continue  # changed by someone else since our read: read it again and apply ours on top
            raise RemoteConfigError(_reason(r))
        raise RemoteConfigError("Remote Config kept changing during the publish")  # pragma: no cover
