"""Deterministic, leakage-aware dataset splitting."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from promption.utils.config import load_config
from promption.utils.logger import logger

SYNTH_SOURCES = {
    "redteam_synth", "hard_negative", "translated_es", "translated_es2",
    "translated_gemini", "local", "synth_v2",
}

def create_splits(df: pd.DataFrame, seed: int = 42, test_frac: float = 0.15, val_frac: float = 0.15, external_sources: set = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return train, val, test, external indices strictly stratified by label and language without group leakage."""
    rng = np.random.RandomState(seed)
    if "group_id" not in df.columns:
        df["group_id"] = [str(i) for i in range(len(df))]
    if "source" not in df.columns:
        df["source"] = "custom"

    if external_sources is None:
        external_sources = SYNTH_SOURCES

    # Group-level classification:
    # Any group with at least one record from an external source belongs entirely to external
    grp_sources = df.groupby("group_id")["source"].unique().to_dict()
    ext_groups = {g for g, srcs in grp_sources.items() if any(str(s) in external_sources for s in srcs)}
    int_groups = set(grp_sources.keys()) - ext_groups

    ext_idx = np.flatnonzero(df["group_id"].isin(ext_groups).to_numpy())

    # Internal groups partitioned into train, val, and test
    internal_df = df[df["group_id"].isin(int_groups)]
    groups = internal_df.groupby("group_id")
    group_labels = []
    group_langs = []
    group_ids = []
    for g_id, g_df in groups:
        group_ids.append(g_id)
        group_labels.append(g_df["label"].iloc[0])
        group_langs.append(g_df["lang"].iloc[0] if "lang" in g_df.columns else "en")

    g_info = pd.DataFrame({"group_id": group_ids, "label": group_labels, "lang": group_langs})

    train_parts = []
    val_parts = []
    test_parts = []

    # Stratify internal groups by label and lang
    for (lbl, lng), st_df in g_info.groupby(["label", "lang"]):
        indices = st_df.index.to_numpy().copy()
        rng.shuffle(indices)

        n_total = len(indices)
        n_test = int(n_total * test_frac)
        n_val = int(n_total * val_frac)
        n_train = n_total - n_test - n_val

        train_parts.extend(indices[:n_train])
        val_parts.extend(indices[n_train:n_train + n_val])
        test_parts.extend(indices[n_train + n_val:])

    train_groups = set(g_info.iloc[train_parts]["group_id"])
    val_groups = set(g_info.iloc[val_parts]["group_id"])
    test_groups = set(g_info.iloc[test_parts]["group_id"])

    tr_idx = np.flatnonzero(df["group_id"].isin(train_groups).to_numpy())
    v_idx = np.flatnonzero(df["group_id"].isin(val_groups).to_numpy())
    te_idx = np.flatnonzero(df["group_id"].isin(test_groups).to_numpy())

    return tr_idx, v_idx, te_idx, ext_idx


def calculate_manifest_hash(manifest: dict) -> str:
    """Calcula el hash SHA-256 canónico del contenido del manifiesto (excluyendo el campo 'hash')."""
    records = manifest.get("records", {})
    norm_records = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in records.items()}
    content = {
        "seed": manifest.get("seed"),
        "splits": manifest.get("splits"),
        "records": norm_records,
    }
    manifest_str = json.dumps(content, sort_keys=True)
    return hashlib.sha256(manifest_str.encode("utf-8")).hexdigest()


def save_manifest(df: pd.DataFrame, tr_idx, v_idx, te_idx, ext_idx, seed: int, out_dir: Path) -> dict:
    manifest = {
        "seed": seed,
        "splits": {
            "train": int(len(tr_idx)),
            "val": int(len(v_idx)),
            "test": int(len(te_idx)),
            "external": int(len(ext_idx))
        },
        "records": {}
    }
    for idx, part in zip([tr_idx, v_idx, te_idx, ext_idx], ["train", "val", "test", "external"]):
        for i in idx:
            row = df.iloc[i]
            manifest["records"][int(i)] = {
                "group_id": str(row.get("group_id", "")),
                "source": str(row.get("source", "")),
                "partition": part,
                "label": int(row["label"])
            }

    manifest["hash"] = calculate_manifest_hash(manifest)

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "split_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Saved split manifest to %s", out_dir / "split_manifest.json")
    return manifest
