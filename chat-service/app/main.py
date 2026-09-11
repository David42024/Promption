"""FastAPI main application for Chat Service"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routes import router
import time

app = FastAPI(
    title="Promption Chat Service",
    description="Backend Demo para Promption Shop - Manejo de chat con integración Filter API",
    version=settings.version,
)

# CORS middleware - AÑADIDO A LA APP, NO AL ROUTER
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "uptime_seconds": time.time() - _start_time
    }


@app.get("/health")
def health_simple():
    """Simple health check"""
    return {"status": "ok", "service": settings.service_name}