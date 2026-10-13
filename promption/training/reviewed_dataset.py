"""Validated corrected datasets with connected family and translation groups."""
import hashlib
from pathlib import Path

import pandas as pd
import numpy as np


def load_reviewed_dataset(path: Path) -> pd.DataFrame:
    """Treat corrected labels as authoritative and reject invalid inputs."""
    df = pd.read_csv(path).reset_index(drop=True)
    required = {"row_id", "prompt", "label", "lang", "source", "dataset", "attack_type", "family_id", "group_id", "split_group", "split", "generation_method"}
    if not required.issubset(df.columns) or df.empty:
        raise ValueError("Corrected dataset is incomplete")
    if df[list(required)].isna().any().any() or not df.label.isin([0, 1]).all():
        raise ValueError("Corrected dataset has missing values or invalid labels")
    if not df.lang.isin(["es", "en"]).all() or not df.split.isin(["train", "validation", "val", "test", "external"]).all():
        raise ValueError("Invalid corrected language or split")
    if df.prompt.str.strip().eq("").any() or df.prompt.duplicated().any():
        raise ValueError("Corrected prompts must be nonempty and unique")
    if not df.row_id.is_unique:
        raise ValueError("Corrected row identifiers must be unique")
    if df[["family_id", "group_id", "split_group"]].apply(lambda c: c.astype(str).str.strip().eq("")).any().any():
        raise ValueError("Corrected family identifiers must be nonempty")
    df.attrs["reviewed_authoritative"] = True
    return df


def connect_families(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Unite all declared identifiers and original-translation links before splitting."""
    df = df.copy()
    parents = list(range(len(df)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def join(a, b):
        parents[root(b)] = root(a)

    seen = {}
    digests = {}
    for i, row in df.iterrows():
        for column in ("group_id", "family_id", "split_group"):
            key = str(row[column])
            if key in seen:
                join(i, seen[key])
            seen[key] = i
        digests[hashlib.sha256(row.prompt.strip().encode()).hexdigest()] = i
    if "original_prompt_sha256" in df:
        for i, digest in df.original_prompt_sha256.items():
            if isinstance(digest, str) and digest in digests:
                join(i, digests[digest])
    components = {}
    for i in range(len(df)):
        components.setdefault(root(i), []).append(i)
    changed = 0
    rank = {"train": 0, "val": 1, "validation": 1, "test": 2, "external": 3}
    row_ids = df.row_id.astype(str).tolist()
    partitions = df.split.tolist()
    groups = [None] * len(df)
    corrected_partitions = [None] * len(df)
    for indices in components.values():
        group = "corrected-" + hashlib.sha256("|".join(sorted(row_ids[i] for i in indices)).encode()).hexdigest()[:20]
        partition = max((partitions[i] for i in indices), key=rank.get)
        partition = "val" if partition == "validation" else partition
        for i in indices:
            changed += ("val" if partitions[i] == "validation" else partitions[i]) != partition
            groups[i] = group
            corrected_partitions[i] = partition
    for column in ("group_id", "family_id", "split_group"):
        df[column] = groups
    df["split"] = corrected_partitions
    df.attrs["reviewed_authoritative"] = True
    df["partition_scheme"] = "reviewed_connected_v1"
    return df, changed


def reserve_test_cases(df: pd.DataFrame, per_class: int, seed: int = 42, language: str = "all") -> tuple[pd.DataFrame, int]:
    """Expand test using whole training families before fitting a fresh model."""
    if per_class < 1 or language not in ("all", "es", "en"):
        raise ValueError("Invalid test reservation")
    if not df.index.equals(pd.RangeIndex(len(df))):
        raise ValueError("Test reservation requires a contiguous row index")
    if df.groupby("group_id").split.nunique().gt(1).any():
        raise ValueError("A family crosses partitions before reservation")
    result = df.copy()
    eligible_language = result.lang.eq(language) if language != "all" else pd.Series(True, index=result.index)
    rng = np.random.RandomState(seed)
    moved = 0
    for label in (0, 1):
        eligible = eligible_language & result.label.eq(label)
        count = int((eligible & result.split.eq("test")).sum())
        groups = sorted(result.loc[eligible & result.split.eq("train"), "group_id"].unique())
        rng.shuffle(groups)
        for group in groups:
            if count >= per_class:
                break
            mask = result.group_id.eq(group)
            result.loc[mask, "split"] = "test"
            moved += int(mask.sum())
            count += int((eligible & mask).sum())
        if count < per_class:
            raise ValueError("Insufficient independent test rows without using validation")
    if result.groupby("group_id").split.nunique().gt(1).any():
        raise ValueError("Test reservation separated a family")
    return result, moved
