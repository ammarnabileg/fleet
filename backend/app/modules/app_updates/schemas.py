import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReleaseOut(BaseModel):
    id: uuid.UUID
    version_code: int
    version_name: str
    package: str
    sha256: str
    size_bytes: int
    notes: dict[str, str]
    required: bool  # once published: every older app must update
    status: str  # draft | published
    published_at: datetime | None
    created_at: datetime
    installed: int = 0  # signed-in phones that reported this versionCode


class DriverVersionOut(BaseModel):
    id: uuid.UUID
    name: dict
    app_version: str | None
    version_code: int | None  # None: an app too old to say
    last_seen_at: datetime | None
    outdated: bool


class OverviewOut(BaseModel):
    package: str | None  # what an upload must be
    max_mb: int
    latest: int | None  # the newest published versionCode
    releases: list[ReleaseOut]
    unknown_version: int  # phones whose app does not report its versionCode (older than this feature)
    drivers: list[DriverVersionOut]


class ReleaseUpdateIn(BaseModel):
    notes: dict[str, str] | None = Field(None, max_length=20)
    required: bool | None = None


class LatestOut(BaseModel):
    version_code: int
    version_name: str
    size: int
    sha256: str
    notes: str | None
    url: str  # under the server's address; Range requests resume a download


class UpdateCheckOut(BaseModel):
    latest: LatestOut | None
    required: bool
