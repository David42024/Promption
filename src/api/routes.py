"""API routes."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, status

from src.api.models import BenchmarkRequest, FilterRequest, FilterResponse, SystemInfo
from src.benchmark.runner import BenchmarkRunner, RunnerOptions, json_safe, sanitize_prompt
from src.filter.ensemble_filter import EnsembleFilter
from src.llm.ollama_client import OllamaClient
from src.utils.config import load_config
from src.utils.logger import logger

router = APIRouter()
_CONF = load_config()

_filter = EnsembleFilter()
_ollama = OllamaClient()
_start_time = time.time()


def _latest_payload() -> dict:
    p = Path(_CONF["paths"]["results"]) / "benchmark_results_latest.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="No hay resultados de benchmark guardados todavía")
    return json.loads(p.read_text(encoding="utf-8"))


def _results_df() -> pd.DataFrame:
    p = Path(_CONF["paths"]["results"]) / "benchmark_results.csv"
    if not p.exists():
        raise HTTPException(status_code=404, detail="No hay resultados de benchmark guardados todavía")
    return pd.read_csv(p, encoding="utf-8")


# ------------------------------------------------------------------- system
@router.get("/health", tags=["system"])
def health() -> SystemInfo:
    import psutil
    mem = psutil.virtual_memory()
    return SystemInfo(
        status="ok",
        uptime_seconds=time.time() - _start_time,
        memory_used_percent=mem.percent,
        cpu_percent=psutil.cpu_percent(interval=0.2),
        ollama=_ollama.health(),
        filter_layers=_filter.layers_status(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/system/logs", tags=["system"])
def tail_logs(lines: int = 100):
    log_file = Path(_CONF["logging"].get("file", "logs/system.log"))
    if not log_file.exists():
        return {"logs": []}
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"logs": content[-lines:]}


@router.get("/system/config", tags=["system"])
def get_config():
    return _CONF


@router.post("/system/reload", tags=["system"])
def reload_filter():
    """Reload the heuristic rules / ML model without restarting the API."""
    global _filter
    _filter = EnsembleFilter()
    return {"status": "reloaded", "layers": _filter.layers_status()}


# ------------------------------------------------------------------ filtering
@router.post("/filter", tags=["filter"])
def filter_prompt(req: FilterRequest) -> FilterResponse:
    t0 = time.perf_counter()
    res = _filter.analyze(req.text, use_ml=req.use_ml)
    latency = (time.perf_counter() - t0) * 1000

    rules = [{"name": r["name"], "severity": r["severity"], "description": r.get("description", "")}
             for r in res.heuristic.matched_rules]
    ml_info = {
        "available": res.ml is not None,
        "blocked": res.ml.blocked if res.ml else None,
        "probability": res.ml.probability if res.ml else None,
        "threshold": res.ml.threshold if res.ml else None,
    }
    layers = {
        "heuristic": {"blocked": res.heuristic.blocked, "score": res.heuristic.score,
                      "matched_rules": rules, "threshold": res.heuristic.threshold},
        "ml": ml_info,
        "ensemble": {"score": res.score, "threshold": _filter.final_threshold},
    }
    logger.info("Filter [%s] in %.1fms: %s", res.decision, latency, req.text[:80])
    return FilterResponse(
        text=req.text,
        decision=res.decision,
        blocked=res.blocked,
        confidence=res.score,
        latency_ms=round(latency, 3),
        reason=res.blocking_reason,
        layers=layers,
        sanitized=sanitize_prompt(req.text, res) if res.blocked else req.text,
    )


@router.post("/filter/batch", tags=["filter"])
def filter_batch(reqs: list[FilterRequest]):
    t0 = time.perf_counter()
    out = []
    for req in reqs:
        r = filter_prompt(req)
        out.append(r.model_dump())
    return {"n": len(out), "total_ms": round((time.perf_counter() - t0) * 1000, 3), "results": out}


# ------------------------------------------------------------------ benchmark
@router.post("/benchmark", tags=["benchmark"])
def run_benchmark(req: BenchmarkRequest):
    opts = RunnerOptions(sample_size=req.sample_size, use_llm=req.use_llm, save=True)
    runner = BenchmarkRunner(filter=_filter, ollama=_ollama, opts=opts)
    df, metrics = runner.run()
    total_ms = _results_df()["filter_latency_ms"].mean() if not df.empty else 0
    metrics_json = _latest_payload()
    return {"status": "ok", "n_rows": int(len(df)), "metrics": metrics, "payload": metrics_json}


@router.get("/benchmark/latest", tags=["benchmark"])
def benchmark_latest():
    return _latest_payload()


@router.get("/benchmark/results", tags=["benchmark"])
def benchmark_results():
    df = _results_df()
    return {"n_rows": len(df), "columns": list(df.columns), "data": json_safe(df.to_dict(orient="records"))}


@router.get("/benchmark/history", tags=["benchmark"])
def benchmark_history():
    hist = Path(_CONF["benchmark"].get("history_dir", "data/results/history"))
    if not hist.exists():
        return {"runs": []}
    runs = []
    for p in sorted(hist.glob("run_*.csv"), reverse=True):
        df = pd.read_csv(p)
        runs.append({
            "file": p.name,
            "rows": int(len(df)),
            "asr_without": float(pd.to_numeric(df["llm_success_no_filter"], errors="coerce").mean()),
            "asr_with": float(pd.to_numeric(df["llm_success_with_filter"], errors="coerce").mean()),
        })
    return {"runs": runs}


# ------------------------------------------------------------------ metrics / model
@router.get("/metrics", tags=["metrics"])
def metrics_endpoint():
    df = _results_df()
    from src.benchmark.metrics import all_metrics, by_attack_type, by_dataset
    return json_safe({
        "overall": all_metrics(df),
        "by_dataset": by_dataset(df),
        "by_attack_type": by_attack_type(df),
    })


@router.get("/model/features", tags=["model"])
def model_features(top: int = 384):
    if not _filter.ml.is_loaded:
        try:
            _filter.ml._ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Modelo no disponible: {exc}")
    imp = _filter.ml.feature_importance(top_k=top)
    return {"features": [{"dimension": k, "importance": v} for k, v in imp.items()]}


@router.get("/model/predict", tags=["model"])
def model_predict(text: str):
    if not text:
        raise HTTPException(status_code=422, detail="Parámetro 'text' requerido")
    return filter_prompt(FilterRequest(text=text))


# ------------------------------------------------------------------ misc
@router.get("/files", tags=["system"])
def list_output_files():
    base = Path(_CONF["paths"]["results"])
    files = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base.parent).as_posix()
            files.append({"path": rel, "size": p.stat().st_size})
    return {"files": files}