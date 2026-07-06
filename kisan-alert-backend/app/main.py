from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import whatsapp_webhook, escalations, recommend

app = FastAPI(
    title="Kisan Alert Backend",
    description="API for Kisan Alert farm monitoring and alert notification system",
    version="1.0.0"
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

# Include API Routers
app.include_router(whatsapp_webhook.router)
app.include_router(escalations.router)
app.include_router(recommend.router)

@app.get("/health", tags=["Health"])
def health_check():
    """
    Simple health check endpoint to verify backend service status.
    """
    return {"status": "healthy"}
