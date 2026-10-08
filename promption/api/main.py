"""FastAPI entry point.

Run:
    uvicorn promption.api.main:app --reload --port 8000
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from promption.utils.config import ROOT_DIR, load_config

load_dotenv(ROOT_DIR / ".env", override=False)

from promption.api.routes import router
from promption.utils.logger import logger

_CONF = load_config()

app = FastAPI(
    title="Promption Filter API",
    description="API multi-tenant para proteger entradas y salidas de chatbots con "
                "heurísticas, ML y Output Guard.",
    version="1.0.0",
)

_cors_origins = [
    origin.strip()
    for origin in os.environ.get("PROMPTION_CORS_ORIGINS", "").split(",")
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

from promption.api.auth import is_demo_mode, is_production_environment, validate_auth_configuration
from promption.limiter import BodySizeLimitMiddleware, init_rate_limiter_from_config

# Initialize shared rate limiter backend according to config or environment
init_rate_limiter_from_config()

@app.on_event("startup")
def _startup_rate_limiter() -> None:
    init_rate_limiter_from_config()

@app.on_event("startup")
def _startup_auth_validation() -> None:
    has_any_registry = bool(
        os.environ.get("PIF_API_KEYS", "").strip()
        or os.environ.get("PROMPTION_API_KEYS", "").strip()
        or os.environ.get("PROMPTION_ADMIN_API_KEYS", "").strip()
        or os.environ.get("PROMPTION_API_KEY", "").strip()
        or os.environ.get("PROMPTION_TENANT_ID", "").strip()
    )
    if (
        is_production_environment()
        or is_demo_mode()
        or has_any_registry
        or os.environ.get("PROMPTION_ENFORCE_AUTH_ON_STARTUP", "").lower() in ("1", "true", "yes")
    ):
        validate_auth_configuration()
    else:
        logger.warning(
            "No API credentials configured and PROMPTION_DEMO_MODE is disabled. Protected API requests will be rejected (401). "
            "Set PROMPTION_API_KEYS='tenant:key' or PROMPTION_DEMO_MODE=true for local demo."
        )

_limits_conf = _CONF.get("limits", {})
_max_body = int(_limits_conf.get("max_body_bytes", 2097152))
app.add_middleware(BodySizeLimitMiddleware, max_bytes=_max_body)

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
