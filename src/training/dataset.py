"""Dataset loading & preparation.

Expected raw files (CSV):
    data/raw/malicious_prompts.csv -> prompt, dataset, attack_type, source
    data/raw/benign_prompts.csv    -> prompt, category, source

Output:
    data/processed/training_data.csv -> prompt, label, attack_type, category, dataset, source
"""
import hashlib
from pathlib import Path

import pandas as pd

from src.utils.config import load_config
from src.utils.lang import detect_lang
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
    df["lang"] = df["prompt"].map(detect_lang)
    return df[["prompt", "label", "attack_type", "category", "dataset", "source", "lang"]]


def apply_quarantine(df: pd.DataFrame, processed_dir: str | None = None) -> pd.DataFrame:
    """Excluye filas en data/processed/quarantine.csv (ruido de etiqueta auditado)."""
    qpath = Path(processed_dir or _CONF["paths"]["processed_data"]) / "quarantine.csv"
    if not qpath.exists():
        return df
    banned = set(pd.read_csv(qpath, encoding="utf-8")["prompt"].astype(str))
    before = len(df)
    df = df[~df["prompt"].astype(str).isin(banned)].reset_index(drop=True)
    logger.info("Quarantine: %d filas excluidas (%s)", before - len(df), qpath)
    return df


def apply_label_overrides(df: pd.DataFrame, processed_dir: str | None = None) -> pd.DataFrame:
    """Apply reviewed label corrections identified by prompt SHA-256."""
    path = Path(processed_dir or _CONF["paths"]["processed_data"]) / "label_overrides.csv"
    if not path.exists():
        return df
    overrides = pd.read_csv(path, encoding="utf-8")
    required = {"prompt_sha256", "label", "dataset", "attack_type"}
    if not required.issubset(overrides.columns):
        raise ValueError(f"Invalid label override schema: {path}")
    mapping = overrides.set_index("prompt_sha256").to_dict(orient="index")
    out = df.copy()
    hashes = out["prompt"].astype(str).str.strip().map(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    )
    changed = 0
    for index, digest in hashes.items():
        override = mapping.get(digest)
        if override is None:
            continue
        label = int(override["label"])
        out.at[index, "label"] = label
        out.at[index, "dataset"] = str(override["dataset"])
        out.at[index, "attack_type"] = str(override["attack_type"])
        if "category" in out.columns:
            out.at[index, "category"] = str(override["attack_type"])
        changed += 1
    if changed:
        logger.info("Label overrides: %d filas corregidas (%s)", changed, path)
    return out


def prepare_training_data(data_dir: str | None = None, processed_dir: str | None = None) -> Path:
    df = apply_quarantine(apply_label_overrides(load_raw_data(data_dir), processed_dir), processed_dir)
    out = Path(processed_dir or _CONF["paths"]["processed_data"]) / "training_data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    logger.info("Prepared training dataset: %d rows -> %s", len(df), out)
    return out


def load_training_data(processed_dir: str | None = None) -> pd.DataFrame:
    path = Path(processed_dir or _CONF["paths"]["processed_data"]) / "training_data.csv"
    if not path.exists():
        path = prepare_training_data()
    df = pd.read_csv(path, encoding="utf-8")
    if "lang" not in df.columns:  # CSVs generados antes de la columna lang
        df["lang"] = df["prompt"].map(detect_lang)
    return apply_quarantine(apply_label_overrides(df, processed_dir), processed_dir)


if __name__ == "__main__":
    df = load_raw_data()
    print(df["label"].value_counts().to_string())
    print(df.groupby(["label", "dataset"]).size().to_string())
