from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import whatsapp_webhook, escalations, recommend
from app.services.scheduler import check_and_alert, create_scheduler


# ── Lifespan: start/stop APScheduler alongside the FastAPI process ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    on startup  : create and start the APScheduler (every 6 h drought alert).
    on shutdown : gracefully stop the scheduler so in-flight jobs can finish.
    """
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)


# ── Application factory ────────────────────────────────────────────────────────
app = FastAPI(
    title="Kisan Alert Backend",
    description="API for Kisan Alert farm monitoring and alert notification system",
    version="1.0.0",
    lifespan=lifespan,
)

# WARNING: CORS is configured wide open to allow the separate frontend team
# to interface with the API from different origins. This MUST be restricted
# to specific domains (e.g. your production frontend URL) before deploying to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include API routers ────────────────────────────────────────────────────────
app.include_router(whatsapp_webhook.router)
app.include_router(escalations.router)
app.include_router(recommend.router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check():
    """
    Simple health check endpoint to verify backend service status.
    """
    return {"status": "healthy"}


# ── Admin: on-demand alert trigger ────────────────────────────────────────────
@app.post(
    "/admin/trigger-alerts",
    tags=["Admin"],
    summary="Manually trigger the drought alert job",
    description=(
        "Runs check_and_alert() immediately without waiting for the next "
        "6-hour scheduler tick. Useful for demos and smoke-testing. "
        "Returns a per-plot summary of what was sent, skipped, or errored."
    ),
    response_class=JSONResponse,
)
async def trigger_alerts():
    """
    Run the drought-alert job on demand.

    Executes synchronously within the request so the caller receives the
    full per-plot result. For a fire-and-forget background variant, use
    BackgroundTasks (swap the implementation below if needed).
    """
    result = await check_and_alert()
    return result
