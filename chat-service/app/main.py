"""FastAPI main application for Chat Service"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings, validate_chat_service_configuration
from .routes import router
import time

from .http_client import close_shared_http_client

app = FastAPI(
    title="Promption Chat Service",
    description="Backend Demo para Promption Shop - Manejo de chat con integración Filter API",
    version=settings.version,
)


@app.on_event("startup")
def _startup_chat_service_validation() -> None:
    validate_chat_service_configuration()


@app.on_event("shutdown")
async def _shutdown_chat_service() -> None:
    await close_shared_http_client()


# CORS middleware - AÑADIDO A LA APP, NO AL ROUTER
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from promption.limiter import BodySizeLimitMiddleware
from promption.utils.config import load_config

_limits_conf = load_config().get("limits", {})
_max_body = int(_limits_conf.get("max_body_bytes", 2097152))
app.add_middleware(BodySizeLimitMiddleware, max_bytes=_max_body)

# Include routes
app.include_router(router, prefix="/api/v1")

_start_time = time.time()


@app.get("/", tags=["root"])
def root():
    """Root endpoint"""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/v1/health",
        "chat": "POST /api/v1/chat",
        "status": "/api/v1/status",
        "deployment_marker": "chat-service-2026-09-13",
        "uptime_seconds": time.time() - _start_time
    }


@app.get("/health")
def health_simple():
    """Simple health check"""
    return {"status": "ok", "service": settings.service_name}
