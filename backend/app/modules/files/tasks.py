import logging
import time

from app.core.db import new_session
from app.core.errors import AppError
from app.modules.files import service
from app.modules.integrations import service as integrations
from app.worker import celery

log = logging.getLogger("fleet.files")


@celery.task(name="files.copy_to_r2")
def copy_to_r2() -> int:
    """Once R2 is switched on, the files written to the disk before are copied there in the background, a few
    minutes of work per run; each copied file is read from R2 from then on."""
    copied, after, deadline = 0, "", time.monotonic() + 240
    with new_session() as db:
        if integrations.load(db, "storage").config.provider != "r2" or not service.counts(db)["local"]:
            return 0
        while time.monotonic() < deadline:
            try:
                out = service.copy_to_r2(db, after=after)
            except AppError as exc:
                log.warning("copying files to R2 stopped: %s", exc.code)
                break
            copied += out["copied"]
            if out["missing"]:
                log.warning("files missing from the disk, left as they are: %s", out["missing"])
            if out["last"] is None:
                break
            after = out["last"]
    return copied
