from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.episodes import router as episodes_router
from app.api.v1.patients import router as patients_router
from app.api.v1.enrollment import router as enrollment_router
from app.api.v1.rulesets import router as rulesets_router
from app.api.v1.hospital import router as hospital_router
from app.api.v1.templates import router as templates_router
from app.api.v1.reports import router as reports_router
from app.api.v1.clinicians import router as clinicians_router
from app.api.v1.checkin import router as checkin_router
from app.api.v1.app_admin import router as app_admin_router

api_v1_router = APIRouter(prefix="/api/v1")

for router in (
    auth_router,
    dashboard_router,
    alerts_router,
    episodes_router,
    patients_router,
    enrollment_router,
    rulesets_router,
    hospital_router,
    templates_router,
    reports_router,
    clinicians_router,
    checkin_router,
    app_admin_router,
):
    api_v1_router.include_router(router)

__all__ = ["api_v1_router"]
