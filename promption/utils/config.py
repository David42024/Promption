"""Configuration with bundled defaults and explicit application overrides."""
import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import yaml

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY = _PACKAGE_ROOT.parent
_RESOURCES = _PACKAGE_ROOT / "resources"
_IS_CHECKOUT = (_REPOSITORY / "pyproject.toml").exists() and (_REPOSITORY / "config/config.yaml").exists()
ROOT_DIR = Path(os.environ.get("PROMPTION_ROOT", str(_REPOSITORY if _IS_CHECKOUT else Path.cwd()))).resolve()
CONFIG_PATH = Path(os.environ.get("PROMPTION_CONFIG_FILE", str(
    ROOT_DIR / "config/config.yaml" if (ROOT_DIR / "config/config.yaml").exists()
    else _RESOURCES / "config.yaml"))).resolve()
HEURISTICS_PATH = Path(os.environ.get("PROMPTION_HEURISTICS_FILE", str(
    ROOT_DIR / "config/heuristics.yaml" if (ROOT_DIR / "config/heuristics.yaml").exists()
    else _RESOURCES / "heuristics.yaml"))).resolve()


@lru_cache(maxsize=2)
def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source) or {}


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Resolve writable data paths against the application root, never site-packages."""
    cfg = deepcopy(_read_yaml(CONFIG_PATH))
    paths = cfg.setdefault("paths", {})
    paths["root"] = str(ROOT_DIR)
    for key, value in list(paths.items()):
        if key != "root":
            paths[key] = str((ROOT_DIR / value).resolve())
    model = cfg.setdefault("model", {})
    for key in ("classifier_path", "lightweight_classifier_path"):
        if model.get(key):
            model[key] = str((ROOT_DIR / model[key]).resolve())
    if model.get("classifier_path"):
        paths["classifier"] = model["classifier_path"]
    paths["cfg"] = str(CONFIG_PATH)
    paths["heuristics"] = str(HEURISTICS_PATH)
    logging = cfg.setdefault("logging", {})
    if logging.get("file"):
        logging["file"] = str((ROOT_DIR / logging["file"]).resolve())
    benchmark = cfg.setdefault("benchmark", {})
    if benchmark.get("history_dir"):
        benchmark["history_dir"] = str((ROOT_DIR / benchmark["history_dir"]).resolve())
    return cfg


@lru_cache(maxsize=1)
def load_heuristics() -> dict:
    return _read_yaml(HEURISTICS_PATH)


def reload_heuristics() -> dict:
    """Discard cached rule files before rebuilding filters in a running service."""
    _read_yaml.cache_clear()
    load_heuristics.cache_clear()
    return load_heuristics()


def load_embedding_model_name() -> str:
    return str(load_config()["model"].get("embedding_model", "all-MiniLM-L6-v2"))


def load_classifier_path() -> Path:
    return Path(load_config()["model"]["classifier_path"])
