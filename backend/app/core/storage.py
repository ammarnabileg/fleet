"""Where the bytes of stored files live: the server's disk, or a Cloudflare R2 bucket (its S3-compatible API).

Files are named by their sha256 and never change, so a key is written once and every copy of it is the same file.
Each backend only puts, reads and checks keys; which one a file is in is recorded on its row (files.files.storage).
"""

import base64
import hashlib
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

CHUNK = 64 * 1024


class StorageError(Exception):
    """The storage could not be reached or refused the request (the message is safe to show an administrator)."""


@dataclass(frozen=True)
class Blob:
    size: int
    chunks: Iterator[bytes]


class LocalStorage:
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def path(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256[2:4] / sha256

    def put(self, sha256: str, data: bytes, content_type: str) -> None:
        target = self.path(sha256)
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)  # atomic: a reader never sees half a file
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def size(self, sha256: str) -> int | None:
        target = self.path(sha256)
        return target.stat().st_size if target.exists() else None

    def read(self, sha256: str) -> bytes:
        return self.path(sha256).read_bytes()


class R2Storage:
    """A private R2 bucket. Credentials are an R2 API token's access key ID and secret (Object Read & Write on this
    bucket only). Every upload carries its MD5, so R2 refuses a body damaged on the way."""

    name = "r2"

    def __init__(
        self,
        *,
        account_id: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        jurisdiction: str = "default",
        prefix: str = "files/",
        client=None,
        endpoint: str | None = None,  # another S3-compatible server (tests)
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        if client is None:
            import boto3
            from botocore.config import Config

            sub = "" if jurisdiction == "default" else f"{jurisdiction}."
            client = boto3.client(
                "s3",
                endpoint_url=endpoint or f"https://{account_id}.{sub}r2.cloudflarestorage.com",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=5,
                    read_timeout=30,
                    retries={"max_attempts": 3, "mode": "standard"},
                    request_checksum_calculation="when_required",  # integrity comes from Content-MD5
                    response_checksum_validation="when_required",
                ),
            )
        self.client = client

    def key(self, sha256: str) -> str:
        return f"{self.prefix}{sha256}"

    @staticmethod
    def _error(exc) -> StorageError:
        from botocore.exceptions import ClientError

        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {})
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            return StorageError(f"{error.get('Code') or status}: {error.get('Message') or 'refused'}")
        return StorageError(exc.__class__.__name__)

    def _call(self, method: str, **kwargs):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return getattr(self.client, method)(Bucket=self.bucket, **kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise self._error(exc) from None

    def put(self, sha256: str, data: bytes, content_type: str) -> None:
        md5 = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()
        self._call("put_object", Key=self.key(sha256), Body=data, ContentType=content_type, ContentMD5=md5)

    def size(self, sha256: str) -> int | None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return self.client.head_object(Bucket=self.bucket, Key=self.key(sha256))["ContentLength"]
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return None
            raise self._error(exc) from None
        except BotoCoreError as exc:
            raise self._error(exc) from None

    def open(self, sha256: str) -> Blob:
        body = self._call("get_object", Key=self.key(sha256))
        return Blob(body["ContentLength"], body["Body"].iter_chunks(CHUNK))

    def read(self, sha256: str) -> bytes:
        return b"".join(self.open(sha256).chunks)

    def check(self) -> None:
        """The bucket exists and this token can write to it (one small object, always the same key)."""
        self._call("head_bucket")
        probe = b"fleet connection test\n"
        md5 = base64.b64encode(hashlib.md5(probe, usedforsecurity=False).digest()).decode()
        key = f"{self.prefix}.connection-test"
        self._call("put_object", Key=key, Body=probe, ContentType="text/plain", ContentMD5=md5)
