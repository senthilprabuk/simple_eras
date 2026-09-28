import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.api.v1 import api_v1_router
from app.services.escalation import run_escalation_sweep
from app.services.missed_checkins import run_missed_checkin_sweep
from app.services.notifications import dispatch_queued_notifications
from app.services.daily_dispatch import run_daily_checkin_dispatch

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger("eras")

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # max_instances=1 stops a slow tick overlapping the next one in this process;
    # the sweep's advisory lock covers other processes.
    scheduler.add_job(
        run_escalation_sweep, "interval",
        seconds=settings.ESCALATION_SWEEP_INTERVAL_SECS,
        id="escalation_sweep", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        dispatch_queued_notifications, "interval",
        seconds=settings.NOTIFICATION_DISPATCH_INTERVAL_SECS,
        id="notification_dispatch", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        run_missed_checkin_sweep, "interval",
        seconds=settings.MISSED_CHECKIN_SWEEP_INTERVAL_SECS,
        id="missed_checkin_sweep", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        run_daily_checkin_dispatch, "interval",
        seconds=settings.DAILY_DISPATCH_INTERVAL_SECS,
        id="daily_checkin_dispatch", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Started: escalation sweep every %ss, notification dispatch every %ss, "
        "missed check-in sweep every %ss, patient WhatsApp dispatch every %ss "
        "(notification provider: %s, WhatsApp provider: %s). CORS origins: %s",
        settings.ESCALATION_SWEEP_INTERVAL_SECS,
        settings.NOTIFICATION_DISPATCH_INTERVAL_SECS,
        settings.MISSED_CHECKIN_SWEEP_INTERVAL_SECS,
        settings.DAILY_DISPATCH_INTERVAL_SECS,
        settings.NOTIFICATION_PROVIDER,
        settings.WHATSAPP_PROVIDER,
        settings.cors_origins_list,
    )

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")

app = FastAPI(
    title="ERAS Clinical Monitoring API",
    version="0.2.0",
    description="Post-Operative Remote Patient Monitoring Backend for Knee Replacement",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    # Every method the API uses; a missing one fails only in the browser, at the CORS preflight.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_v1_router)

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe returning application and background job status."""
    return {
        "status": "healthy",
        "service": "eras-backend",
        "version": app.version,
        "scheduler_running": scheduler.running,
        "notification_provider": settings.NOTIFICATION_PROVIDER,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
