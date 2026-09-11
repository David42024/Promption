"""API routes."""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth import TenantContext, require_tenant
from src.api.models import (BenchmarkRequest, FilterRequest, FilterResponse,
                             OutputGuardRequest, OutputGuardResponse, SystemInfo)
from src.benchmark.runner import BenchmarkRunner, RunnerOptions, json_safe, sanitize_prompt
from src.filter.ensemble_filter import EnsembleFilter
from src.filter.heuristic_filter import HeuristicFilter
from src.filter.ml_filter import MLFilter
from src.llm import get_llm_client
from src.utils.config import load_config
from src.utils.logger import logger

router = APIRouter()
_CONF = load_config()

_filter = EnsembleFilter()
_tenant_filters: dict[tuple, EnsembleFilter] = {}
_ollama = get_llm_client()
_start_time = time.time()


def _filter_for(tenant: TenantContext, final_override: float | None = None) -> EnsembleFilter:
    """Filtro del tenant (cacheado): aplica sus umbrales propios Y ajusta por rol."""
    # Ajustar umbrales basados en rol
    roles = getattr(tenant, "roles", [])
    is_admin = "admin" in roles
    
    # Umbrales base del tenant
    th = tenant.thresholds or {}
    h_thr = th.get("heuristic")
    m_thr = th.get("ml")
    f_thr = final_override if final_override is not None else th.get("final")
    
    # Ajustar por rol: admin gets lower thresholds (more permissive)
    if is_admin:
        # Admin: más permisivo, umbrales más bajos
        if h_thr is None: h_thr = 0.5
        if m_thr is None: m_thr = 0.3
        if f_thr is None: f_thr = 0.3
    else:
        # Usuario regular/cliente: más restrictivo, umbrales más altos
        if h_thr is None: h_thr = 0.6
        if m_thr is None: m_thr = 0.5
        if f_thr is None: f_thr = 0.5
    
    if h_thr is None and m_thr is None and f_thr is None:
        return _filter
    key = (tenant.tenant_id, h_thr, m_thr, f_thr)
    if key not in _tenant_filters:
        flt = EnsembleFilter(
            heuristic=HeuristicFilter(threshold=float(h_thr)) if h_thr is not None else None,
            ml=MLFilter(threshold=float(m_thr)) if m_thr is not None else None,
        )
        if f_thr is not None:
            flt.final_threshold = float(f_thr)
        _tenant_filters[key] = flt
    return _tenant_filters[key]


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
def tail_logs(lines: int = 100, tenant: TenantContext = Depends(require_tenant)):
    log_file = Path(_CONF["logging"].get("file", "logs/system.log"))
    if not log_file.exists():
        return {"logs": []}
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"logs": content[-lines:]}


@router.get("/logs/structured", tags=["system"])
def get_structured_logs(
    limit: int = 100,
    level: str | None = None,
    category: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    since: str | None = None,
    admin_key: str | None = Query(None),
):
    """Get structured logs with filtering (admin only in production)."""
    # Simple admin check - in production use proper admin authentication
    ADMIN_SECRET = os.environ.get("PIF_ADMIN_SECRET", "admin_secret_change_me")
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Admin access required")
    
    from src.utils.structured_logger import get_structured_logger
    
    logger = get_structured_logger()
    logs = logger.get_logs(
        limit=limit,
        level=level,
        category=category,
        tenant_id=tenant_id,
        user_id=user_id,
        since=since,
    )
    
    return {
        "logs": logs,
        "categories": logger.get_categories(),
        "tenants": logger.get_tenants(),
        "total": len(logs),
    }


@router.get("/logs/stats", tags=["system"])
def get_log_stats(
    admin_key: str | None = Query(None),
):
    """Get statistics about logs (admin only)."""
    # Simple admin check - in production use proper admin authentication
    ADMIN_SECRET = os.environ.get("PIF_ADMIN_SECRET", "admin_secret_change_me")
    if admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Admin access required")
    
    from src.utils.structured_logger import get_structured_logger
    
    logger = get_structured_logger()
    logs = logger.get_logs(limit=10000)  # Get more for stats
    
    stats = {
        "total": len(logs),
        "by_level": {},
        "by_category": {},
        "by_tenant": {},
        "recent_24h": 0,
    }
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    for log in logs:
        # Count by level
        stats["by_level"][log["level"]] = stats["by_level"].get(log["level"], 0) + 1
        
        # Count by category
        stats["by_category"][log["category"]] = stats["by_category"].get(log["category"], 0) + 1
        
        # Count by tenant
        if log["tenant_id"]:
            stats["by_tenant"][log["tenant_id"]] = stats["by_tenant"].get(log["tenant_id"], 0) + 1
        
        # Count recent
        log_time = datetime.fromisoformat(log["timestamp"])
        if log_time >= cutoff:
            stats["recent_24h"] += 1
    
    return stats


@router.get("/system/config", tags=["system"])
def get_config(tenant: TenantContext = Depends(require_tenant)):
    return _CONF


@router.post("/system/reload", tags=["system"])
def reload_filter(tenant: TenantContext = Depends(require_tenant)):
    """Reload the heuristic rules / ML model without restarting the API."""
    global _filter
    _filter = EnsembleFilter()
    _tenant_filters.clear()
    return {"status": "reloaded", "layers": _filter.layers_status()}


# ------------------------------------------------------------------ filtering
@router.post("/filter", tags=["filter"])
def filter_prompt(req: FilterRequest, tenant: TenantContext = Depends(require_tenant)) -> FilterResponse:
    t0 = time.perf_counter()
    flt = _filter_for(tenant, req.threshold)
    res = flt.analyze(req.text, use_ml=req.use_ml)
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
                      "matched_rules": rules, "threshold": res.heuristic.threshold,
                      "benign_matched": list(res.heuristic.benign_matched)},
        "ml": ml_info,
        "ensemble": {"score": res.score, "threshold": flt.final_threshold,
                     "benign_matched": list(res.heuristic.benign_matched)},
    }
    logger.info("Filter [%s] tenant=%s user=%s roles=%s in %.1fms: %s",
                res.decision, tenant.tenant_id, req.user_id, req.roles, latency, req.text[:80])
    
    # Structured logging
    from src.utils.structured_logger import log_filter_decision
    log_filter_decision(
        decision=res.decision,
        confidence=res.score,
        tenant_id=tenant.tenant_id,
        user_id=req.user_id,
        roles=req.roles,
        text=req.text,
        layers=layers,
    )
    
    return FilterResponse(
        text=req.text,
        decision=res.decision,
        blocked=res.blocked,
        confidence=res.score,
        latency_ms=round(latency, 3),
        reason=res.blocking_reason,
        layers=layers,
        sanitized=sanitize_prompt(req.text, res) if res.blocked else req.text,
        tenant_id=tenant.tenant_id,
    )


@router.post("/filter/batch", tags=["filter"])
def filter_batch(reqs: list[FilterRequest], tenant: TenantContext = Depends(require_tenant)):
    t0 = time.perf_counter()
    out = []
    for req in reqs:
        r = filter_prompt(req, tenant)
        out.append(r.model_dump())
    return {"n": len(out), "total_ms": round((time.perf_counter() - t0) * 1000, 3), "results": out}


# ------------------------------------------------------------------ output guard
@router.post("/output-guard", tags=["output-guard"])
def output_guard(req: OutputGuardRequest, tenant: TenantContext = Depends(require_tenant)) -> OutputGuardResponse:
    """Inspecciona una respuesta del LLM antes de entregarla (PASS/REDACT/BLOCK)."""
    from src.output_guard import guard_response, scan
    from src.utils.structured_logger import log_output_guard
    
    # Verificar si el usuario es admin - si lo es, aplicar lógica más permisiva
    roles = getattr(req, "context", {}).get("roles", []) if hasattr(req, "context") else []
    is_admin = "admin" in roles
    
    res = guard_response(req.text, admin_mode=is_admin)
    findings = scan(req.text) if res.action != "PASS" else []
    fps = [f.fingerprint for f in findings]
    logger.info(
        "OutputGuard [%s] tenant=%s user=%s is_admin=%s cats=%s matches=%d risk=%.3f fps=%s",
        res.action, tenant.tenant_id, req.user_id, is_admin, res.categories, res.matches, res.risk,
        [f"sha256:{fp[:12]}" for fp in fps],
    )
    
    # Structured logging
    log_output_guard(
        action=res.action,
        categories=res.categories,
        tenant_id=tenant.tenant_id,
        user_id=req.user_id,
        matches=res.matches,
        risk=res.risk,
    )
    
    return OutputGuardResponse(**res.to_dict(), tenant_id=tenant.tenant_id)


# ------------------------------------------------------------------ benchmark
@router.post("/benchmark", tags=["benchmark"])
def run_benchmark(req: BenchmarkRequest, tenant: TenantContext = Depends(require_tenant)):
    opts = RunnerOptions(sample_size=req.sample_size, use_llm=req.use_llm, save=True)
    runner = BenchmarkRunner(filter=_filter, ollama=_ollama, opts=opts)
    df, metrics = runner.run()
    total_ms = _results_df()["filter_latency_ms"].mean() if not df.empty else 0
    metrics_json = _latest_payload()
    return {"status": "ok", "n_rows": int(len(df)), "metrics": metrics, "payload": metrics_json}


@router.get("/benchmark/latest", tags=["benchmark"])
def benchmark_latest(tenant: TenantContext = Depends(require_tenant)):
    return _latest_payload()


@router.get("/benchmark/results", tags=["benchmark"])
def benchmark_results(tenant: TenantContext = Depends(require_tenant)):
    df = _results_df()
    return {"n_rows": len(df), "columns": list(df.columns), "data": json_safe(df.to_dict(orient="records"))}


@router.get("/benchmark/history", tags=["benchmark"])
def benchmark_history(tenant: TenantContext = Depends(require_tenant)):
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
def metrics_endpoint(tenant: TenantContext = Depends(require_tenant)):
    df = _results_df()
    from src.benchmark.metrics import all_metrics, by_attack_type, by_dataset
    return json_safe({
        "overall": all_metrics(df),
        "by_dataset": by_dataset(df),
        "by_attack_type": by_attack_type(df),
    })


@router.get("/model/features", tags=["model"])
def model_features(top: int = 384, tenant: TenantContext = Depends(require_tenant)):
    if not _filter.ml.is_loaded:
        try:
            _filter.ml._ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Modelo no disponible: {exc}")
    imp = _filter.ml.feature_importance(top_k=top)
    return {"features": [{"dimension": k, "importance": v} for k, v in imp.items()]}


@router.get("/model/predict", tags=["model"])
def model_predict(text: str, tenant: TenantContext = Depends(require_tenant)):
    if not text:
        raise HTTPException(status_code=422, detail="Parámetro 'text' requerido")
    return filter_prompt(FilterRequest(text=text), tenant)


# ------------------------------------------------------------------ misc
@router.get("/files", tags=["system"])
def list_output_files(tenant: TenantContext = Depends(require_tenant)):
    base = Path(_CONF["paths"]["results"])
    files = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base.parent).as_posix()
            files.append({"path": rel, "size": p.stat().st_size})
    return {"files": files}