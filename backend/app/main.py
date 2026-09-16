from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.api.v1 import api_v1_router
from app.services.escalation import run_escalation_sweep

# In-process asynchronous scheduler for background tasks
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager.
    Startup: Launches APScheduler for the 60-second automated escalation sweep.
    Shutdown: Shuts down background scheduler and connection pools cleanly.
    """
    print(f"[*] Starting ERAS Clinical Monitoring API...")
    print(f"[*] CORS Allowed Origins: {settings.cors_origins_list}")

    # Launch escalation sweep scheduler
    scheduler.add_job(
        run_escalation_sweep,
        "interval",
        seconds=settings.ESCALATION_SWEEP_INTERVAL_SECS,
        id="escalation_sweep",
        replace_existing=True
    )
    scheduler.start()
    print(f"[+] APScheduler started: {settings.ESCALATION_SWEEP_INTERVAL_SECS}s escalation sweep active.")

    yield

    print(f"[*] Shutting down ERAS Clinical Monitoring API...")
    scheduler.shutdown(wait=False)
    print(f"[+] APScheduler stopped cleanly.")

app = FastAPI(
    title="ERAS Clinical Monitoring API",
    version="0.1.0",
    description="Post-Operative Remote Patient Monitoring Backend for Knee Replacement (Page 1: Dashboard / Risk Queue)",
    lifespan=lifespan
)

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(api_v1_router)

@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe returning application and background job status."""
    return {
        "status": "healthy",
        "service": "eras-backend",
        "version": "0.1.0",
        "scheduler_running": scheduler.running
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
