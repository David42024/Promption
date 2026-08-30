"""End-to-end pipeline: prepare data -> train model -> run benchmark.

Usage:
    python scripts/run_benchmark.py                # train + full benchmark (uses LLM)
    python scripts/run_benchmark.py --no-llm        # skip LLM queries (proxy ASR)
    python scripts/run_benchmark.py --prepare-only  # only build training data
    python scripts/run_benchmark.py --train-only    # only train the model
    python scripts/run_benchmark.py --sample 30     # limit benchmark rows
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.runner import BenchmarkRunner, RunnerOptions  # noqa: E402
from src.filter.ensemble_filter import build_default  # noqa: E402
from src.training import train as train_mod  # noqa: E402
from src.training import dataset as dataset_mod  # noqa: E402
from src.utils.config import load_config  # noqa: E402
from src.utils.logger import logger  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="Disable Ollama queries")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--train-only", action="store_true")
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--no-train", action="store_true", help="Skip model training if a model file exists")
    args = parser.parse_args()

    dataset_mod.prepare_training_data()
    if args.prepare_only:
        logger.info("Dataset built. Run `python src/training/train.py` to train.")
        return

    model_path = Path(load_config()["paths"]["classifier"])
    if args.train_only or not model_path.exists() or not args.no_train:
        train_mod.main()

    if args.train_only:
        return

    runner = BenchmarkRunner(filter=build_default(), opts=RunnerOptions(sample_size=args.sample, use_llm=not args.no_llm))
    df, metrics = runner.run()
    logger.info("ASR sin filtro: %.3f | ASR con filtro: %.3f | Reducción: %.1f%%",
                metrics["asr_without_filter"], metrics["asr_with_filter"], metrics["asr_reduction"] * 100)
    logger.info("Precisión: %.3f | Recall: %.3f | F1: %.3f",
                metrics["precision"], metrics["recall"], metrics["f1"])


if __name__ == "__main__":
    main()