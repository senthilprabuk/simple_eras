from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.episodes import router as episodes_router
from app.api.v1.checkin import router as checkin_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(episodes_router)
api_v1_router.include_router(checkin_router)

__all__ = ["api_v1_router"]
