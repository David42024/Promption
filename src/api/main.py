"""FastAPI entry point.

Run:
    uvicorn src.api.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()

app = FastAPI(
    title="Prompt Injection Filter API",
    description="Sistema de detección de Prompt Injection en dos capas (heurística + ML) "
                "con dashboard Streamlit.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["root"])
def root():
    return {
        "service": "Prompt Injection Filter",
        "docs": "/docs",
        "health": "/api/v1/health",
        "filter": "POST /api/v1/filter",
        "benchmark": "POST /api/v1/benchmark",
        "version": "1.0.0",
    }


logger.info("API inicializada (config: %s)", _CONF["paths"]["root"])