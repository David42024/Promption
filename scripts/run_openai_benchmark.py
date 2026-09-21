"""Ejecuta el benchmark balanceado 300/300 con GPT-5 nano.

La clave se lee exclusivamente de ``PIF_LLM_API_KEY``. El checkpoint se
escribe después de cada respuesta válida y los resultados activos solo se
reemplazan cuando todas las llamadas terminan correctamente.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_gemma_benchmark import main  # noqa: E402


DEFAULT_ARGUMENTS = {
    "--input-csv": "data/results/benchmark_results.csv",
    "--checkpoint": "data/results/backups/openai_gpt5nano_balanced_600_checkpoint.jsonl",
    "--rpm": "30",
    "--tpm": "120000",
    "--max-output-tokens": "200",
    "--workers": "4",
    "--max-attempts": "7",
    "--input-usd-per-million": "0.05",
    "--output-usd-per-million": "0.40",
    "--pricing-source-url": "https://developers.openai.com/api/docs/models/gpt-5-nano",
    "--malicious-sample": "300",
    "--benign-sample": "300",
    "--sample-seed": "42",
}


def configure() -> None:
    if not os.environ.get("PIF_LLM_API_KEY", "").strip():
        raise SystemExit("Falta PIF_LLM_API_KEY en el entorno del proceso")
    os.environ["PIF_LLM_PROVIDER"] = "openai"
    os.environ["PIF_LLM_BASE_URL"] = "https://api.openai.com/v1"
    os.environ["PIF_LLM_MODEL"] = "gpt-5-nano"
    present = set(sys.argv[1:])
    for flag, value in DEFAULT_ARGUMENTS.items():
        if flag not in present:
            sys.argv.extend([flag, value])
    if "--include-benign-llm" not in present:
        sys.argv.append("--include-benign-llm")


def backup_active_results() -> None:
    checkpoint = ROOT / DEFAULT_ARGUMENTS["--checkpoint"]
    if checkpoint.exists():
        return
    results = ROOT / "data" / "results"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = results / "backups" / f"before_openai_gpt5nano_{stamp}"
    copied = False
    for name in ("benchmark_results.csv", "benchmark_results_latest.json"):
        source = results / name
        if source.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup / name)
            copied = True
    if copied:
        print(f"Respaldo previo creado en {backup}", flush=True)


if __name__ == "__main__":
    configure()
    backup_active_results()
    main()
