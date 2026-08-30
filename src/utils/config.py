"""Centralized configuration loading."""
from functools import lru_cache
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "config" / "config.yaml"
HEURISTICS_PATH = ROOT_DIR / "config" / "heuristics.yaml"


@lru_cache(maxsize=2)
def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Load the main config.yaml and resolve relative paths to absolute ones."""
    cfg = _read_yaml(CONFIG_PATH)
    for key in ("paths", "llm", "model"):
        if key in cfg:
            cfg[key] = dict(cfg[key])
    paths = cfg.setdefault("paths", {})
    paths["root"] = str(ROOT_DIR)
    for k, v in list(paths.items()):
        if k == "root":
            continue
        paths[k] = str((ROOT_DIR / v).resolve())
    model = cfg.setdefault("model", {})
    if model.get("classifier_path"):
        paths["classifier"] = str((ROOT_DIR / model["classifier_path"]).resolve())
    paths["cfg"] = str(CONFIG_PATH)
    paths["heuristics"] = str(HEURISTICS_PATH)
    return cfg


@lru_cache(maxsize=1)
def load_heuristics() -> dict:
    """Load heuristics.yaml containing regex detection rules."""
    return _read_yaml(HEURISTICS_PATH)


def load_embedding_model_name() -> str:
    return str(load_config()["model"].get("embedding_model", "all-MiniLM-L6-v2"))


def load_classifier_path() -> Path:
    return Path(load_config()["model"]["classifier_path"])