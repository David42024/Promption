"""Generate PDF test payloads from the raw corpus.

Renders one prompt per PDF document so the filter can be validated end-to-end
on real files (``scripts/run_benchmark.py --pdf-dir <out>``) instead of plain text.

Usage:
    python scripts/generate_pdf_payloads.py [--samples-per-class 40] [--out data/pdf_payloads]
"""
import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.training.dataset import load_raw_data  # noqa: E402
from src.utils.config import load_config  # noqa: E402
from src.utils.logger import logger  # noqa: E402

_CONF = load_config()


def _pick_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for plain, bold, name in (
        (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf"), "SegoeUI"),
        (Path("C:/Windows/Fonts/DejaVuSans.ttf"), Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"), "DejaVuSans"),
    ):
        if plain.exists() and bold.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(plain)))
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold)))
                return name
            except Exception:  # noqa: BLE001
                continue
    return "Helvetica"


def render_pdf(path: Path, text: str, font: str = "Helvetica") -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    style = ParagraphStyle("body", fontName=font, fontSize=10, leading=14, textColor="#22304A")
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
    )
    doc.build([Paragraph(escape(text), style)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-class", type=int, default=40,
                        help="PDFs por clase (maliciosos / benignos), si hay suficientes")
    parser.add_argument("--out", type=Path, default=Path(_CONF["paths"].get("pdf_payloads", "data/pdf_payloads")))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = load_raw_data()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    font = _pick_font()

    rows = []
    for label in (1, 0):
        sub = df[df["label"] == label]
        sub = sub.sample(n=min(args.samples_per_class, len(sub)), random_state=args.seed)
        prefix = "mal" if label == 1 else "ben"
        for i, (_, src) in enumerate(sub.reset_index(drop=True).iterrows()):
            fname = f"{prefix}_{i:03d}.pdf"
            render_pdf(out / fname, src["prompt"], font=font)
            rows.append({
                "file": fname,
                "prompt": src["prompt"],
                "label": int(src["label"]),
                "dataset": src["dataset"],
                "attack_type": src["attack_type"],
                "source": src["source"],
            })

    meta_path = out / "metadata.csv"
    pd.DataFrame(rows).to_csv(meta_path, index=False, encoding="utf-8")
    counts = {0: sum(r["label"] == 0 for r in rows), 1: sum(r["label"] == 1 for r in rows)}
    logger.info("PDFs generados: %d maliciosos / %d benignos -> %s", counts[1], counts[0], out)
    logger.info("Metadatos: %s", meta_path)


if __name__ == "__main__":
    main()