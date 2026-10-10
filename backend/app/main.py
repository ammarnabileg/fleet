import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import errors, messaging, middleware
from app.core.config import get_settings
from app.core.db import new_session
from app.modules.accidents.api import router as accidents_router
from app.modules.approvals.api import router as approvals_router
from app.modules.attendance.api import router as attendance_router
from app.modules.audit.api import router as audit_router
from app.modules.cash.api import router as cash_router
from app.modules.daily_ops.api import router as daily_ops_router
from app.modules.documents.api import router as documents_router
from app.modules.files.api import router as files_router
from app.modules.finance.api import router as finance_router
from app.modules.fines.api import router as fines_router
from app.modules.fleet.api import router as fleet_router
from app.modules.i18n.api import router as i18n_router
from app.modules.identity.api import router as identity_router
from app.modules.imports.api import router as imports_router
from app.modules.integrations.api import router as integrations_router
from app.modules.maintenance.api import router as maintenance_router
from app.modules.notifications.api import router as notifications_router
from app.modules.onboarding.api import router as onboarding_router
from app.modules.org.api import router as org_router
from app.modules.payroll.api import router as payroll_router
from app.modules.payroll.designer_api import router as payroll_rules_router
from app.modules.people.api import router as people_router
from app.modules.reports.api import router as reports_router
from app.modules.tracking.api import router as tracking_router

VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production:
        messaging.provider()  # a missing or unsafe messaging configuration stops the deploy, not the first driver
    logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    docs = not settings.is_production
    app = FastAPI(
        title="BrilliantTech Fleet API",
        version=VERSION,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    errors.install(app)
    middleware.install(app)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok", "version": VERSION}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        try:
            with new_session() as db:
                db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "database_unavailable"}, status_code=503)
        return {"status": "ready"}

    for router in (
        identity_router,
        org_router,
        i18n_router,
        audit_router,
        files_router,
        people_router,
        documents_router,
        fleet_router,
        tracking_router,
        notifications_router,
        onboarding_router,
        imports_router,
        integrations_router,
        maintenance_router,
        accidents_router,
        fines_router,
        payroll_router,
        payroll_rules_router,
        attendance_router,
        finance_router,
        approvals_router,
        daily_ops_router,
        cash_router,
        reports_router,
    ):
        app.include_router(router)
    return app
