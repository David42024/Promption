"""Run the saved evaluation corpus against a rate-limited external LLM."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.metrics import all_metrics, by_attack_type, by_dataset  # noqa: E402
from src.benchmark.runner import (BenchmarkRunner, RunnerOptions, SYSTEM_PROMPT,  # noqa: E402
                                  contains_secret, is_compromised, sanitize_prompt)
from src.filter.ensemble_filter import build_default  # noqa: E402
from src.llm import get_llm_client  # noqa: E402
from src.utils.logger import logger  # noqa: E402


class EvenRateLimiter:
    """Reserve evenly spaced request slots across concurrent workers."""

    def __init__(self, requests_per_minute: float):
        self.interval = 60.0 / requests_per_minute
        self.next_slot = time.monotonic()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        delay = slot - now
        if delay > 0:
            time.sleep(delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, default=Path("data/results/benchmark_results.csv"))
    parser.add_argument("--checkpoint", type=Path,
                        default=Path("data/results/backups/gemma_benchmark_checkpoint.jsonl"))
    parser.add_argument("--rpm", type=float, default=15.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--input-usd-per-million", type=float, default=0.0)
    parser.add_argument("--output-usd-per-million", type=float, default=0.0)
    parser.add_argument(
        "--finalize-only",
        action="store_true",
        help="Genera resultados solo con el checkpoint existente, sin llamadas al LLM.",
    )
    return parser.parse_args()


def load_checkpoint(path: Path) -> dict[tuple[int, str], dict]:
    completed: dict[tuple[int, str], dict] = {}
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if int(item.get("total_tokens") or 0) <= 0:
            continue
        completed[(int(item["index"]), str(item["kind"]))] = item
    return completed


def append_checkpoint(path: Path, item: dict, lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(item, ensure_ascii=False)
    with lock:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
            stream.flush()


def build_filter_rows(source: pd.DataFrame) -> tuple[list[dict], list[tuple[int, str, str]]]:
    detector = build_default()
    rows: list[dict] = []
    jobs: list[tuple[int, str, str]] = []
    for position, item in source.reset_index(drop=True).iterrows():
        started = time.perf_counter()
        result = detector.analyze(str(item["prompt"]), use_ml=True)
        latency = (time.perf_counter() - started) * 1000
        ml_probability = result.ml.probability if result.ml else np.nan
        ml_blocked = int(result.ml.blocked) if result.ml else np.nan
        matched = ", ".join(rule["name"] for rule in result.heuristic.matched_rules[:5])
        is_attack = int(item["label"]) == 1
        row = {
            "id": int(position),
            "prompt": str(item["prompt"]),
            "dataset": str(item["dataset"]),
            "attack_type": str(item["attack_type"]),
            "source": str(item["source"]),
            "label": int(item["label"]),
            "heuristic_score": float(result.heuristic.score),
            "heuristic_blocked": int(result.heuristic.blocked),
            "ml_probability": float(ml_probability) if ml_probability == ml_probability else np.nan,
            "ml_blocked": float(ml_blocked) if ml_blocked == ml_blocked else np.nan,
            "ensemble_score": float(result.score),
            "filter_blocked": int(result.blocked),
            "filter_latency_ms": float(latency),
            "heuristic_latency_ms": float(result.heuristic_latency_ms),
            "ml_latency_ms": float(result.ml_latency_ms),
            "matched_rules": matched,
            "llm_success_no_filter": np.nan,
            "llm_success_with_filter": np.nan,
            "llm_latency_ms": np.nan,
            "response_no_filter": "(no aplica)",
            "response_filtered": "(no aplica)",
        }
        if is_attack:
            jobs.append((position, "raw", str(item["prompt"])))
            row["response_no_filter"] = "(no medido)"
            if result.blocked:
                row["response_filtered"] = "(bloqueado por el filtro)"
            else:
                jobs.append((position, "filtered", sanitize_prompt(str(item["prompt"]), result)))
                row["response_filtered"] = "(no medido)"
        rows.append(row)
        if (position + 1) % 500 == 0:
            logger.info("Filtro preparado: %d/%d", position + 1, len(source))
    return rows, jobs


def main() -> None:
    args = parse_args()
    if args.rpm <= 0 or args.rpm > 30:
        raise SystemExit("--rpm debe estar entre 0 y 30")
    source = pd.read_csv(args.input_csv, encoding="utf-8")
    required = {"prompt", "dataset", "attack_type", "source", "label"}
    missing = required.difference(source.columns)
    if missing:
        raise SystemExit(f"Faltan columnas: {sorted(missing)}")

    rows, jobs = build_filter_rows(source)
    completed = load_checkpoint(args.checkpoint)
    if args.finalize_only and not completed:
        raise SystemExit(f"El checkpoint no contiene resultados válidos: {args.checkpoint}")
    pending = [job for job in jobs if (job[0], job[1]) not in completed]
    checkpoint_models = {
        str(item.get("model")) for item in completed.values() if item.get("model")
    }
    model_name = sorted(checkpoint_models)[0] if checkpoint_models else "desconocido"
    client = None
    if args.finalize_only:
        logger.info(
            "Cierre sin LLM: filas=%d llamadas esperadas=%d observadas=%d pendientes=%d modelo=%s",
            len(source), len(jobs), len(completed), len(pending), model_name,
        )
    else:
        client = get_llm_client()
        health = client.health()
        if not health.get("connected"):
            raise SystemExit(f"LLM no disponible: {health.get('error')}")
        model_name = str(health.get("default_model") or model_name)
        logger.info(
            "Benchmark externo: filas=%d llamadas=%d reanudadas=%d pendientes=%d modelo=%s rpm=%.1f",
            len(source), len(jobs), len(completed), len(pending), model_name, args.rpm,
        )
        limiter = EvenRateLimiter(args.rpm)
        checkpoint_lock = threading.Lock()

        def execute(job: tuple[int, str, str]) -> dict:
            index, kind, prompt = job
            error = None
            for attempt in range(1, args.max_attempts + 1):
                limiter.wait()
                try:
                    response = client.generate(prompt, system=SYSTEM_PROMPT)
                    return {
                        "index": index,
                        "kind": kind,
                        "response": response.text[:2000],
                        "latency_ms": float(response.latency_ms),
                        "model": response.model,
                        "input_tokens": int(response.input_tokens),
                        "output_tokens": int(response.output_tokens),
                        "total_tokens": int(response.total_tokens),
                        "cached_tokens": int(response.cached_tokens),
                        "reasoning_tokens": int(response.reasoning_tokens),
                    }
                except Exception as exc:  # noqa: BLE001
                    error = f"{exc.__class__.__name__}: {exc}"
                    logger.warning(
                        "LLM error fila=%d tipo=%s intento=%d/%d: %s",
                        index, kind, attempt, args.max_attempts, error,
                    )
                    if attempt < args.max_attempts:
                        time.sleep(min(30.0, 2.0 ** attempt))
            raise RuntimeError(f"Fallo definitivo fila={index} tipo={kind}: {error}")

        processed = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(execute, job): job for job in pending}
            for future in as_completed(futures):
                result = future.result()
                completed[(result["index"], result["kind"])] = result
                append_checkpoint(args.checkpoint, result, checkpoint_lock)
                processed += 1
                if processed % 25 == 0 or processed == len(pending):
                    logger.info("Gemma completado: %d/%d llamadas pendientes", processed, len(pending))

    evaluable_indices: list[int] = []
    for position, row in enumerate(rows):
        if row["label"] != 1:
            continue
        raw = completed.get((position, "raw"))
        if raw is None:
            continue
        row["response_no_filter"] = raw["response"]
        if row["filter_blocked"]:
            row["llm_success_no_filter"] = float(is_compromised(raw["response"]))
            row["llm_success_with_filter"] = 0.0
            row["llm_latency_ms"] = raw["latency_ms"]
            evaluable_indices.append(position)
        else:
            filtered = completed.get((position, "filtered"))
            if filtered is None:
                continue
            row["llm_success_no_filter"] = float(is_compromised(raw["response"]))
            row["response_filtered"] = filtered["response"]
            row["llm_success_with_filter"] = float(is_compromised(filtered["response"]))
            row["llm_latency_ms"] = max(raw["latency_ms"], filtered["latency_ms"])
            evaluable_indices.append(position)

    output = pd.DataFrame(rows, columns=BenchmarkRunner.COLUMNS)
    metrics = all_metrics(output)
    attack_rows = output.iloc[evaluable_indices]
    strict_no_filter = int(attack_rows["response_no_filter"].map(contains_secret).sum())
    strict_with_filter = int(attack_rows["response_filtered"].map(contains_secret).sum())
    attack_count = int(len(attack_rows))
    job_keys = {(index, kind) for index, kind, _ in jobs}
    required_results = [item for key, item in completed.items() if key in job_keys]
    raw_results = [completed[(index, "raw")] for index in evaluable_indices]
    filtered_results = [
        completed[(index, "filtered")]
        for index in evaluable_indices
        if not rows[index]["filter_blocked"]
    ]
    blocked_raw_results = [
        completed[(index, "raw")]
        for index in evaluable_indices
        if rows[index]["filter_blocked"]
    ]
    observed_raw_count = sum(1 for index, row in enumerate(rows)
                             if row["label"] == 1 and (index, "raw") in completed)
    observed_filtered_count = sum(1 for index, row in enumerate(rows)
                                  if row["label"] == 1 and (index, "filtered") in completed)

    def token_totals(items: list[dict]) -> dict[str, int]:
        return {
            "input_tokens": sum(int(item.get("input_tokens") or 0) for item in items),
            "output_tokens": sum(int(item.get("output_tokens") or 0) for item in items),
            "total_tokens": sum(int(item.get("total_tokens") or 0) for item in items),
            "cached_tokens": sum(int(item.get("cached_tokens") or 0) for item in items),
            "reasoning_tokens": sum(int(item.get("reasoning_tokens") or 0) for item in items),
        }

    def estimated_cost(totals: dict[str, int]) -> float:
        return (
            totals["input_tokens"] * args.input_usd_per_million
            + (totals["output_tokens"] + totals["reasoning_tokens"])
            * args.output_usd_per_million
        ) / 1_000_000

    benchmark_totals = token_totals(required_results)
    without_filter_totals = token_totals(raw_results)
    with_filter_totals = token_totals(filtered_results)
    saved_totals = token_totals(blocked_raw_results)
    token_usage = {
        "model": model_name,
        "scope": "partial_evaluable_cohort" if len(required_results) < len(jobs) else "full_benchmark",
        "pricing_currency": "USD",
        "pricing_mode": "free_tier" if (
            args.input_usd_per_million == 0 and args.output_usd_per_million == 0
        ) else "configured",
        "input_usd_per_million": args.input_usd_per_million,
        "output_usd_per_million": args.output_usd_per_million,
        "benchmark_calls": len(required_results),
        "benchmark_expected_calls": len(jobs),
        "benchmark_observed": benchmark_totals,
        "calls_without_filter": len(raw_results),
        "without_filter": without_filter_totals,
        "calls_with_filter": len(filtered_results),
        "with_filter": with_filter_totals,
        "calls_avoided": len(blocked_raw_results),
        "saved_by_blocking": saved_totals,
        "token_savings_rate": (
            saved_totals["total_tokens"] / without_filter_totals["total_tokens"]
            if without_filter_totals["total_tokens"] else 0.0
        ),
        "estimated_cost_without_filter_usd": estimated_cost(without_filter_totals),
        "estimated_cost_with_filter_usd": estimated_cost(with_filter_totals),
        "estimated_cost_saved_usd": estimated_cost(saved_totals),
        "benchmark_observed_cost_usd": estimated_cost(benchmark_totals),
    }
    coverage = {
        "status": "partial" if len(required_results) < len(jobs) else "complete",
        "observed_calls": len(required_results),
        "expected_calls": len(jobs),
        "call_coverage_rate": len(required_results) / len(jobs) if jobs else 0.0,
        "observed_raw_calls": observed_raw_count,
        "observed_filtered_calls": observed_filtered_count,
        "evaluable_attacks": attack_count,
        "total_attacks": int(sum(int(row["label"]) == 1 for row in rows)),
        "attack_coverage_rate": attack_count / sum(int(row["label"]) == 1 for row in rows),
    }
    metrics.update({
        "strict_leaks_without_filter": strict_no_filter,
        "strict_leaks_with_filter": strict_with_filter,
        "strict_leak_rate_without_filter": strict_no_filter / attack_count if attack_count else 0.0,
        "strict_leak_rate_with_filter": strict_with_filter / attack_count if attack_count else 0.0,
        "token_usage": token_usage,
        "llm_coverage": coverage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "options": {
            "use_llm": True,
            "partial": coverage["status"] == "partial",
            "completion_status": coverage["status"],
            "coverage": coverage,
            "n_rows": int(len(output)),
            "model": model_name,
            "requests_per_minute": args.rpm,
            "input_usd_per_million": args.input_usd_per_million,
            "output_usd_per_million": args.output_usd_per_million,
        },
        "by_dataset": by_dataset(output),
        "by_attack_type": by_attack_type(output),
    })
    save_client = client if client is not None else object()
    saver = BenchmarkRunner(filter=build_default(), ollama=save_client, opts=RunnerOptions(save=True))
    saver._save(output, metrics)
    logger.info(
        "Finalizado: cobertura=%d/%d F1=%.4f ASR=%.4f->%.4f fugas estrictas=%d->%d tokens ahorrados=%d",
        len(required_results), len(jobs),
        metrics["f1"], metrics["asr_without_filter"], metrics["asr_with_filter"],
        strict_no_filter, strict_with_filter, saved_totals["total_tokens"],
    )


if __name__ == "__main__":
    main()
