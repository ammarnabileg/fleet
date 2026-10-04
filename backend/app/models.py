"""Imports every module's models so that Base.metadata is complete (Alembic, tests)."""

from app.modules.audit import models as audit  # noqa: F401
from app.modules.documents import models as documents  # noqa: F401
from app.modules.files import models as files  # noqa: F401
from app.modules.fleet import models as fleet  # noqa: F401
from app.modules.i18n import models as i18n  # noqa: F401
from app.modules.identity import models as identity  # noqa: F401
from app.modules.integrations import models as integrations  # noqa: F401
from app.modules.notifications import models as notifications  # noqa: F401
from app.modules.onboarding import models as onboarding  # noqa: F401
from app.modules.org import models as org  # noqa: F401
from app.modules.people import models as people  # noqa: F401
from app.modules.tracking import models as tracking  # noqa: F401
