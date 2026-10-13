"""Build authored Spanish augmentation without touching evaluation partitions."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from promption.training.spanish_corpus import build_spanish_corpus
from promption.utils.config import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    target = args.out or Path(load_config()["paths"]["raw_data"]) / "spanish_augmentation.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    df = build_spanish_corpus()
    df.to_csv(target, index=False, encoding="utf-8")
    print(f"{len(df)} synthetic variants; {df.family_id.nunique()} authored families; {target}")


if __name__ == "__main__":
    main()
