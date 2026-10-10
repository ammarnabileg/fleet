"""External services set up from the control panel. Each kind has its settings (shown and edited in clear) and its
secrets (write-only: the panel sees whether one is set and its last characters, never the value)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _text(pattern: str):
    return Annotated[str, StringConstraints(strip_whitespace=True, pattern=pattern)]


AccountId = _text(r"^[0-9a-f]{32}$")
Bucket = _text(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
AccessKeyId = _text(r"^[A-Za-z0-9]{16,128}$")
BaseUrl = _text(r"^https?://[^\s/?#]+(/[^\s?#]*)?$")
Instance = _text(r"^[A-Za-z0-9_.-]{1,100}$")


class StorageConfig(_Config):
    """Where new files are written. R2: a private bucket and an R2 API token (Object Read & Write on that bucket)."""

    provider: Literal["local", "r2"] = "local"
    account_id: AccountId | None = None
    bucket: Bucket | None = None
    access_key_id: AccessKeyId | None = None
    jurisdiction: Literal["default", "eu", "fedramp"] = "default"  # the bucket's jurisdiction in Cloudflare


class WhatsappConfig(_Config):
    """The Evolution API instance the sign-in codes and activation links are sent through."""

    enabled: bool = False
    url: BaseUrl | None = None
    instance: Instance | None = None


AppId = _text(r"^1:[0-9]{6,20}:android:[0-9a-f]{8,40}$")
ClientKey = _text(r"^[A-Za-z0-9_-]{20,60}$")
SenderId = _text(r"^[0-9]{6,20}$")


class PushConfig(_Config):
    """Firebase Cloud Messaging: the Android app's client values from the Firebase console (Project settings > Your
    apps), sent to the app so it registers without a rebuild, and the service account key the server sends with."""

    enabled: bool = False
    app_id: AppId | None = None
    api_key: ClientKey | None = None  # the client API key: public, it only identifies the app to Firebase
    sender_id: SenderId | None = None


# kind -> (settings model, secret names)
KINDS: dict[str, tuple[type[_Config], tuple[str, ...]]] = {
    "storage": (StorageConfig, ("secret_access_key",)),
    "whatsapp": (WhatsappConfig, ("api_key",)),
    "push": (PushConfig, ("service_account",)),
}

Secret = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=8192)]  # a JSON key fits


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)  # 0 = never saved
    config: dict
    # a name with a value replaces that secret, with null removes it; a secret left out stays as it is
    secrets: dict[str, Secret | None] = Field(default_factory=dict)


class SecretOut(BaseModel):
    set: bool
    hint: str | None  # the last 4 characters, to tell two keys apart


class ConnectionOut(BaseModel):
    kind: str
    version: int
    config: dict
    secrets: dict[str, SecretOut]
    updated_at: datetime | None
    checked_at: datetime | None
    check_ok: bool | None
    check_error: str | None
    status: dict  # what the panel shows next to the form (e.g. how many files are on the disk and in R2)
