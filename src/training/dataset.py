"""Dataset loading & preparation.

Expected raw files (CSV):
    data/raw/malicious_prompts.csv -> prompt, dataset, attack_type, source
    data/raw/benign_prompts.csv    -> prompt, category, source

Output:
    data/processed/training_data.csv -> prompt, label, attack_type, category, dataset, source
"""
from pathlib import Path

import pandas as pd

from src.utils.config import load_config
from src.utils.logger import logger

_CONF = load_config()

MAL_COLS = ("prompt", "dataset", "attack_type", "source")
BEN_COLS = ("prompt", "category", "source")


def _read_csv(path: Path, required: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(required))
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    has_header = any(c in first_line for c in ("prompt", "dataset", "attack_type", "category", "source"))
    if has_header:
        try:
            return pd.read_csv(path, encoding="utf-8", engine="python", on_bad_lines="skip")
        except Exception:
            return pd.read_csv(path, encoding="utf-8", encoding_errors="replace")
    return pd.read_csv(path, encoding="utf-8", encoding_errors="replace", names=list(required))


def load_raw_data(data_dir: str | None = None) -> pd.DataFrame:
    raw = Path(data_dir or _CONF["paths"]["raw_data"])
    mal = _read_csv(raw / "malicious_prompts.csv", MAL_COLS)
    ben = _read_csv(raw / "benign_prompts.csv", BEN_COLS)

    def _norm(df: pd.DataFrame, cols: tuple[str, ...], defaults: dict) -> pd.DataFrame:
        for c in cols:
            if c not in df.columns:
                df[c] = defaults.get(c, "")
        return df[list(cols)]

    mal = _norm(mal, MAL_COLS, {"dataset": "OWASP", "attack_type": "direct_request", "source": "local"})
    ben = _norm(ben, BEN_COLS, {"category": "general", "source": "local"})

    mal["label"] = 1
    mal["attack_type"] = mal["attack_type"].fillna(mal["dataset"]).astype(str)
    mal["category"] = mal["attack_type"]
    mal["source"] = mal["source"].fillna("local").astype(str)

    ben["label"] = 0
    ben["dataset"] = "Benigno"
    ben["attack_type"] = "benign"
    ben["source"] = ben["source"].fillna("local").astype(str)

    df = pd.concat([mal, ben], ignore_index=True)
    df["prompt"] = df["prompt"].astype(str).str.strip()
    df = df[df["prompt"].str.len() > 0].drop_duplicates(subset=["prompt"], keep="first").reset_index(drop=True)
    return df[["prompt", "label", "attack_type", "category", "dataset", "source"]]


def prepare_training_data(data_dir: str | None = None, processed_dir: str | None = None) -> Path:
    df = load_raw_data(data_dir)
    out = Path(processed_dir or _CONF["paths"]["processed_data"]) / "training_data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    logger.info("Prepared training dataset: %d rows -> %s", len(df), out)
    return out


def load_training_data(processed_dir: str | None = None) -> pd.DataFrame:
    path = Path(processed_dir or _CONF["paths"]["processed_data"]) / "training_data.csv"
    if not path.exists():
        path = prepare_training_data()
    return pd.read_csv(path, encoding="utf-8")


if __name__ == "__main__":
    df = load_raw_data()
    print(df["label"].value_counts().to_string())
    print(df.groupby(["label", "dataset"]).size().to_string())