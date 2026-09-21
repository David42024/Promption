"""API routes."""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.auth import TenantContext, require_scope, require_tenant
from src.api.classification import classify_security_result
from src.api.models import (AuditEventRequest, BenchmarkRequest, FilterRequest,
                             FilterResponse, OutputGuardRequest,
                             OutputGuardResponse, SystemInfo)
from src.benchmark.runner import BenchmarkRunner, RunnerOptions, json_safe, sanitize_prompt
from src.filter.ensemble_filter import EnsembleFilter
from src.filter.heuristic_filter import HeuristicFilter
from src.llm import get_llm_client
from src.utils.config import load_config
from src.utils.logger import logger

router = APIRouter()
_CONF = load_config()

_filter = EnsembleFilter()
_tenant_filters: dict[tuple, EnsembleFilter] = {}
_ollama = get_llm_client()
_start_time = time.time()
_require_filter = require_scope("filter")
_require_output_guard = require_scope("output_guard")
_require_admin = require_scope("admin")
_require_benchmark = require_scope("benchmark")
_require_metrics = require_scope("metrics")
_AUDIT_PRIVATE_KEYS = {"prompt", "reply", "text", "content", "password", "token", "secret"}


def _sanitize_audit_value(value, key: str = ""):
    normalized_key = key.strip().lower()
    if normalized_key in _AUDIT_PRIVATE_KEYS or any(
        private in normalized_key for private in ("password", "token", "secret")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k)[:80]: _sanitize_audit_value(v, str(k)) for k, v in list(value.items())[:80]}
    if isinstance(value, list):
        return [_sanitize_audit_value(item) for item in value[:80]]
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:500]


def _filter_for(tenant: TenantContext, final_override: float | None = None) -> EnsembleFilter:
    """Return a cached attack filter configured with tenant thresholds."""
    th = tenant.thresholds or {}
    h_thr = th.get("heuristic")
    m_thr = th.get("ml")
    f_thr = final_override if final_override is not None else th.get("final")

    if h_thr is None and m_thr is None and f_thr is None:
        return _filter
    key = (tenant.tenant_id, h_thr, m_thr, f_thr)
    if key not in _tenant_filters:
        flt = EnsembleFilter(
            heuristic=HeuristicFilter(threshold=float(h_thr)) if h_thr is not None else None,
            ml_threshold=float(m_thr) if m_thr is not None else None,
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


@router.get("/tenant", tags=["tenant"])
def tenant_info(tenant: TenantContext = Depends(require_tenant)):
    """Validate an API key and return only its resolved tenant metadata."""
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name or tenant.tenant_id,
        "thresholds": tenant.thresholds,
        "scopes": tenant.scopes,
    }


@router.get("/system/logs", tags=["system"])
def tail_logs(lines: int = 100, tenant: TenantContext = Depends(_require_admin)):
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
    tenant: TenantContext = Depends(_require_admin),
):
    """Get structured logs with filtering."""
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
    tenant_id: str | None = None,
    since: str | None = None,
    tenant: TenantContext = Depends(_require_admin),
):
    """Get dashboard-ready security statistics from structured audit events."""
    from src.utils.structured_logger import get_structured_logger

    structured = get_structured_logger()
    logs = structured.get_logs(limit=10000, tenant_id=tenant_id, since=since)

    stats = {
        "total": len(logs),
        "by_level": {},
        "by_category": {},
        "by_tenant": {},
        "recent_24h": 0,
        "summary": {
            "requests": 0,
            "allowed": 0,
            "blocked": 0,
            "uncertain": 0,
            "redacted": 0,
            "errors": 0,
        },
        "classifications": {},
        "block_reasons": {},
        "guard_actions": {},
        "top_rules": {},
        "top_users": {},
        "by_role": {},
        "timeline": {},
        "latency": {"average_ms": 0.0, "p95_ms": 0.0, "count": 0},
    }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    latencies: list[float] = []
    has_chat_transactions = any(
        log.get("category") == "chat"
        and (log.get("details") or {}).get("event_type") == "chat_completed"
        for log in logs
    )

    for log in logs:
        stats["by_level"][log["level"]] = stats["by_level"].get(log["level"], 0) + 1
        stats["by_category"][log["category"]] = stats["by_category"].get(log["category"], 0) + 1
        if log["tenant_id"]:
            stats["by_tenant"][log["tenant_id"]] = stats["by_tenant"].get(log["tenant_id"], 0) + 1
        log_time = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
        if log_time >= cutoff:
            stats["recent_24h"] += 1
        bucket = log_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00Z")
        stats["timeline"][bucket] = stats["timeline"].get(bucket, 0) + 1

        details = log.get("details") or {}
        if log["category"] == "chat" and details.get("event_type") == "chat_completed":
            stats["summary"]["requests"] += 1
            blocked = bool(details.get("blocked"))
            key = "blocked" if blocked else "allowed"
            stats["summary"][key] += 1
            classification = str(details.get("security_classification") or "UNCERTAIN")
            stats["classifications"][classification] = stats["classifications"].get(classification, 0) + 1
            if classification == "UNCERTAIN":
                stats["summary"]["uncertain"] += 1
            block_type = details.get("block_type")
            if block_type:
                stats["block_reasons"][block_type] = stats["block_reasons"].get(block_type, 0) + 1
            guard = details.get("guard")
            if guard:
                stats["guard_actions"][guard] = stats["guard_actions"].get(guard, 0) + 1
                if guard == "REDACT":
                    stats["summary"]["redacted"] += 1
            latency = details.get("latency_ms")
            if isinstance(latency, (int, float)):
                latencies.append(float(latency))
        elif log["category"] == "filter":
            if not has_chat_transactions:
                stats["summary"]["requests"] += 1
                decision = details.get("decision")
                stats["summary"]["blocked" if decision == "BLOCKED" else "allowed"] += 1
                classification = (
                    details.get("layers", {}).get("classification", {}).get("label")
                    or "UNCERTAIN"
                )
                stats["classifications"][classification] = stats["classifications"].get(classification, 0) + 1
                if classification == "UNCERTAIN":
                    stats["summary"]["uncertain"] += 1
            for rule in details.get("layers", {}).get("heuristic", {}).get("matched_rules", []):
                name = rule.get("name") if isinstance(rule, dict) else str(rule)
                if name:
                    stats["top_rules"][name] = stats["top_rules"].get(name, 0) + 1

        if log["level"] == "ERROR":
            stats["summary"]["errors"] += 1
        if log.get("user_id"):
            user_id = str(log["user_id"])
            stats["top_users"][user_id] = stats["top_users"].get(user_id, 0) + 1
        for role in log.get("roles") or []:
            stats["by_role"][role] = stats["by_role"].get(role, 0) + 1

    if latencies:
        ordered = sorted(latencies)
        p95_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))
        stats["latency"] = {
            "average_ms": round(sum(ordered) / len(ordered), 2),
            "p95_ms": round(ordered[p95_index], 2),
            "count": len(ordered),
        }
    stats["timeline"] = [
        {"bucket": bucket, "count": count}
        for bucket, count in sorted(stats["timeline"].items())
    ]
    return stats


@router.post("/audit/events", tags=["audit"])
def ingest_audit_event(
    req: AuditEventRequest,
    tenant: TenantContext = Depends(_require_filter),
):
    """Accept a sanitized lifecycle event from an authenticated tenant backend."""
    from src.utils.structured_logger import log_external_event

    details = _sanitize_audit_value(dict(req.details))
    details["event_type"] = req.event_type
    log_external_event(
        level=req.level,
        category=req.category,
        message=req.message or req.event_type,
        tenant_id=tenant.tenant_id,
        user_id=req.user_id,
        roles=req.roles,
        details=details,
    )
    return {"status": "accepted", "tenant_id": tenant.tenant_id}


@router.get("/system/config", tags=["system"])
def get_config(tenant: TenantContext = Depends(_require_admin)):
    return _CONF


@router.post("/system/reload", tags=["system"])
def reload_filter(tenant: TenantContext = Depends(_require_admin)):
    """Reload the heuristic rules / ML model without restarting the API."""
    global _filter
    _filter = EnsembleFilter()
    _tenant_filters.clear()
    return {"status": "reloaded", "layers": _filter.layers_status()}


# ------------------------------------------------------------------ filtering
@router.post("/filter", tags=["filter"])
def filter_prompt(req: FilterRequest, tenant: TenantContext = Depends(_require_filter)) -> FilterResponse:
    t0 = time.perf_counter()
    flt = _filter_for(tenant, req.threshold)
    merged_roles = list(req.roles) + list(getattr(tenant, "roles", []) or [])
    res = flt.analyze(req.text, use_ml=req.use_ml, roles=merged_roles)
    latency = (time.perf_counter() - t0) * 1000

    rules = [{"name": r["name"], "severity": r["severity"], "description": r.get("description", "")}
             for r in res.heuristic.matched_rules]
    ml_info = {
        "available": res.ml is not None,
        "blocked": res.ml.blocked if res.ml else None,
        "probability": res.ml.probability if res.ml else None,
        "threshold": res.ml.threshold if res.ml else None,
    }
    classification_conf = _CONF.get("classification", {})
    benign_threshold = float(classification_conf.get("ml_benign_threshold", 0.33))
    malicious_threshold = float(classification_conf.get("ml_malicious_threshold", 0.66))
    classification, requires_review = classify_security_result(
        blocked=res.blocked,
        ml_probability=res.ml.probability if res.ml else None,
        benign_threshold=benign_threshold,
        malicious_threshold=malicious_threshold,
        explicit_benign=bool(res.merged_features.get("explicit_benign_override")),
        requires_output_guard=res.requires_output_guard,
    )
    layers = {
        "heuristic": {"blocked": res.heuristic.blocked, "score": res.heuristic.score,
                      "signal": res.heuristic.signal,
                      "matched_rules": rules, "threshold": res.heuristic.threshold,
                      "benign_matched": list(res.heuristic.benign_matched)},
        "ml": ml_info,
        "ensemble": {"score": res.score, "threshold": flt.final_threshold,
                     "decision": res.decision,
                     "requires_output_guard": res.requires_output_guard,
                     "heuristic_band": res.merged_features.get("heuristic_band"),
                     "ml_band": res.merged_features.get("ml_band"),
                     "decision_low_threshold": flt.low_threshold,
                     "decision_high_threshold": flt.high_threshold,
                     "benign_matched": list(res.heuristic.benign_matched)},
        "classification": {
            "label": classification,
            "requires_review": requires_review,
            "ml_benign_threshold": benign_threshold,
            "ml_malicious_threshold": malicious_threshold,
        },
    }
    logger.info("Filter [%s] tenant=%s user=%s roles=%s length=%d in %.1fms",
                res.decision, tenant.tenant_id, req.user_id, req.roles, len(req.text), latency)
    
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
        classification=classification,
        requires_review=requires_review,
        requires_output_guard=res.requires_output_guard,
    )


@router.post("/filter/batch", tags=["filter"])
def filter_batch(reqs: list[FilterRequest], tenant: TenantContext = Depends(_require_filter)):
    t0 = time.perf_counter()
    out = []
    for req in reqs:
        r = filter_prompt(req, tenant)
        out.append(r.model_dump())
    return {"n": len(out), "total_ms": round((time.perf_counter() - t0) * 1000, 3), "results": out}


# ------------------------------------------------------------------ output guard
@router.post("/output-guard", tags=["output-guard"])
def output_guard(req: OutputGuardRequest, tenant: TenantContext = Depends(_require_output_guard)) -> OutputGuardResponse:
    """Inspecciona una respuesta del LLM antes de entregarla (PASS/REDACT/BLOCK)."""
    from src.output_guard import guard_response, scan
    from src.utils.structured_logger import log_output_guard
    
    roles = {
        str(role).strip().lower()
        for role in [*req.roles, *(req.context.get("roles", []) or [])]
        if str(role).strip()
    }
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
def run_benchmark(req: BenchmarkRequest, tenant: TenantContext = Depends(_require_benchmark)):
    opts = RunnerOptions(sample_size=req.sample_size, use_llm=req.use_llm, save=True)
    runner = BenchmarkRunner(filter=_filter, ollama=_ollama, opts=opts)
    df, metrics = runner.run()
    total_ms = _results_df()["filter_latency_ms"].mean() if not df.empty else 0
    metrics_json = _latest_payload()
    return {"status": "ok", "n_rows": int(len(df)), "metrics": metrics, "payload": metrics_json}


@router.get("/benchmark/latest", tags=["benchmark"])
def benchmark_latest(tenant: TenantContext = Depends(_require_benchmark)):
    return _latest_payload()


@router.get("/benchmark/results", tags=["benchmark"])
def benchmark_results(tenant: TenantContext = Depends(_require_benchmark)):
    df = _results_df()
    return {"n_rows": len(df), "columns": list(df.columns), "data": json_safe(df.to_dict(orient="records"))}


@router.get("/benchmark/history", tags=["benchmark"])
def benchmark_history(tenant: TenantContext = Depends(_require_benchmark)):
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
def metrics_endpoint(
    dataset: str | None = Query(default=None),
    threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    tenant: TenantContext = Depends(_require_metrics),
):
    df = _results_df()
    available_datasets = sorted(str(value) for value in df["dataset"].dropna().unique())
    if dataset:
        if dataset not in available_datasets:
            raise HTTPException(status_code=404, detail=f"Dataset no encontrado: {dataset}")
        df = df[df["dataset"].astype(str) == dataset].copy()
    if threshold is not None:
        df = df.copy()
        scores = pd.to_numeric(df["ensemble_score"], errors="coerce").fillna(0.0)
        df["filter_blocked"] = (scores >= threshold).astype(int)
    from src.benchmark.metrics import all_metrics, by_attack_type, by_dataset
    results_path = Path(_CONF["paths"]["results"]) / "benchmark_results.csv"
    latest_payload = _latest_payload()
    latest_overall = latest_payload.get("overall", {})
    llm_evaluation = {
        key: latest_overall[key]
        for key in (
            "strict_leaks_without_filter",
            "strict_leaks_with_filter",
            "strict_leak_rate_without_filter",
            "strict_leak_rate_with_filter",
            "benign_refusal_rate_without_filter",
            "benign_rejection_rate_with_filter",
            "output_guard",
            "llm_coverage",
        )
        if key in latest_overall
    }
    return json_safe({
        "overall": all_metrics(df),
        "by_dataset": by_dataset(df),
        "by_attack_type": by_attack_type(df),
        "token_usage": latest_payload.get("overall", {}).get("token_usage", {}),
        "llm_evaluation": llm_evaluation,
        "benchmark_options": latest_payload.get("options", {}),
        "token_usage_scope": latest_payload.get("overall", {}).get(
            "token_usage", {}
        ).get("scope", "unknown"),
        "available_datasets": available_datasets,
        "filters": {"dataset": dataset, "threshold": threshold},
        "generated_at": datetime.fromtimestamp(
            results_path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    })


@router.get("/model/features", tags=["model"])
def model_features(top: int = 384, tenant: TenantContext = Depends(_require_metrics)):
    if not _filter.ml.is_loaded:
        try:
            _filter.ml._ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Modelo no disponible: {exc}")
    imp = _filter.ml.feature_importance(top_k=top)
    return {"features": [{"dimension": k, "importance": v} for k, v in imp.items()]}


@router.get("/model/predict", tags=["model"])
def model_predict(text: str, tenant: TenantContext = Depends(_require_filter)):
    if not text:
        raise HTTPException(status_code=422, detail="Parámetro 'text' requerido")
    return filter_prompt(FilterRequest(text=text), tenant)


# ------------------------------------------------------------------ misc
@router.get("/files", tags=["system"])
def list_output_files(tenant: TenantContext = Depends(_require_admin)):
    base = Path(_CONF["paths"]["results"])
    files = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base.parent).as_posix()
            files.append({"path": rel, "size": p.stat().st_size})
    return {"files": files}
