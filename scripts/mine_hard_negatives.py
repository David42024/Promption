"""Fase minera reproducible de hard negatives.

Corre el benchmark fijo (data/eval/redteam_100.csv), extrae los falsos
positivos con su embedding, scores y posible causa, y los exporta a
data/eval/fp_current.csv para curaduría. Nunca modifica el benchmark.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.filter.ensemble_filter import EnsembleFilter  # noqa: E402
from src.filter.ml_filter import MLFilter  # noqa: E402


def guess_cause(row: pd.Series, rules: list) -> str:
    p = row["prompt"].lower()
    if any(k in p for k in ("contrase", "password", "clave privada", "credencial", "api key")):
        return "credential_mention"
    if any(k in p for k in ("ignora", "ignore", "olvida", "forget")):
        return "bypass_verb_no_target"
    if any(k in p for k in ("developer", "desarrollador", "depur", "debug", "log")):
        return "dev_debug_vocab"
    if any(k in p for k in ("digo", "secreto", "confidencial", "vestimenta")):
        return "secret_word_no_request"
    if rules:
        return "heuristic:" + ",".join(rules[:2])
    return "ml_borderline"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/eval/fp_current.csv")
    args = ap.parse_args()

    df = pd.read_csv(ROOT / "data/eval/redteam_100.csv", encoding="utf-8")
    flt = EnsembleFilter()
    mlf = MLFilter()
    rows = []
    for _, r in df[df.label == 0].iterrows():
        res = flt.analyze(r["prompt"])
        if not res.blocked:
            continue
        emb = mlf.embed(r["prompt"])[0]
        rows.append({
            "id": r["id"], "family_id": r["family_id"], "subcategory": r["subcategory"],
            "language": r["language"], "prompt": r["prompt"],
            "ensemble_score": round(res.score, 3),
            "ml_probability": round(res.ml.probability, 3) if res.ml else None,
            "heuristic_score": round(res.heuristic.score, 3),
            "heuristic_rules": ",".join(x["name"] for x in res.heuristic.matched_rules),
            "embedding": ",".join(f"{v:.4f}" for v in emb),
            "likely_cause": guess_cause(r, [x["name"] for x in res.heuristic.matched_rules]),
        })
    out = ROOT / args.out
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8")
    print(f"FP exportados: {len(rows)} -> {out}")


if __name__ == "__main__":
    main()
