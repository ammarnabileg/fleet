"""Imports every module's models so that Base.metadata is complete (Alembic, tests)."""

from app.modules.audit import models as audit  # noqa: F401
from app.modules.i18n import models as i18n  # noqa: F401
from app.modules.identity import models as identity  # noqa: F401
from app.modules.integrations import models as integrations  # noqa: F401
from app.modules.org import models as org  # noqa: F401
