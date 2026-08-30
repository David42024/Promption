"""Test payload loading.

Evaluation set = all malicious prompts (labelled 1) + all benign prompts (labelled 0).
The ``dataset`` column identifies the source collection: OWASP, BIANCA, Jailbreak,
GitHub, Custom (attacks) or Benigno (legit).
"""
from src.training.dataset import load_raw_data


def load_evaluation_set(data_dir: str | None = None):
    df = load_raw_data(data_dir)
    df = df[["prompt", "label", "dataset", "attack_type", "source"]].reset_index(drop=True)
    return df


def summary(df):
    rows = []
    for (label, dataset), grp in df.groupby(["label", "dataset"]):
        rows.append({"label": label, "dataset": dataset, "count": len(grp)})
    out = {}
    for r in rows:
        out.setdefault(r["dataset"], {})[r["label"]] = r["count"]
    return out