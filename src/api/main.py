"""FastAPI entry point.

Run:
    uvicorn src.api.main:app --reload --port 8000
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()

app = FastAPI(
    title="Promption Filter API",
    description="API multi-tenant para proteger entradas y salidas de chatbots con "
                "heurísticas, ML y Output Guard.",
    version="1.0.0",
)

_cors_default = (
    "http://localhost:3000,http://localhost:8501,"
    "https://promptionsi.vercel.app,https://promption.shop"
)
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("PROMPTION_CORS_ORIGINS", _cors_default).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Promption-API-Key",
    ],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["root"])
def root():
    return {
        "service": "Prompt Injection Filter",
        "docs": "/docs",
        "health": "/api/v1/health",
        "filter": "POST /api/v1/filter",
        "output_guard": "POST /api/v1/output-guard",
        "authentication": "X-Promption-API-Key",
        "benchmark": "POST /api/v1/benchmark",
        "version": "1.0.0",
        "deployment_marker": "filter-api-2026-09-14-multitenant",
    }


logger.info("API inicializada (config: %s)", _CONF["paths"]["root"])
