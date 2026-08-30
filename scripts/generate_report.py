"""Generate a Markdown (and optional PDF) report from the latest benchmark.

Usage:
    python scripts/generate_report.py [--out reports/benchmark_report.md] [--pdf]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import load_config  # noqa: E402
from src.utils.logger import logger  # noqa: E402

_CONF = load_config()


def fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def build_markdown(results_dir: Path, plots_dir: Path) -> str:
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads((results_dir / "benchmark_results_latest.json").read_text(encoding="utf-8"))
    o = payload["overall"]
    lines = [
        "# Reporte de Benchmark — Prompt Injection Filter",
        "",
        f"**Generado:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Ejecución del benchmark:** `{payload.get('timestamp')}`",
        f"**Muestras:** {o.get('n_total', '?')} prompts "
        f"({o.get('n_malicious', '?')} maliciosos / {o.get('n_benign', '?')} benignos)",
        "",
        "## Métricas globales",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| ASR sin filtro | {fmt_pct(o.get('asr_without_filter', 0))} |",
        f"| ASR con filtro | {fmt_pct(o.get('asr_with_filter', 0))} |",
        f"| Reducción de ASR | {fmt_pct(o.get('asr_reduction', 0))} |",
        f"| Precisión | {fmt_pct(o.get('precision', 0))} |",
        f"| Recall | {fmt_pct(o.get('recall', 0))} |",
        f"| F1-Score | {fmt_pct(o.get('f1', 0))} |",
        f"| Falsos positivos (FPR) | {fmt_pct(o.get('fpr', 0))} |",
        f"| Falsos negativos (FNR) | {fmt_pct(o.get('fnr', 0))} |",
        f"| Latencia media del filtro | {o.get('latency', {}).get('mean', 0) / 1000:.1f} ms |",
        "",
    ]
    lines.append("## Desglose por dataset y tipo de ataque\n")
    lines.append("| Dataset | ASR sin filtro | ASR con filtro | Precisión | Recall | F1 |")
    lines.append("|---|---|---|---|---|---|")
    for d in payload.get("by_dataset", []):
        lines.append(
            f"| {d['dataset']} | {fmt_pct(d.get('asr_without_filter', 0))} | "
            f"{fmt_pct(d.get('asr_with_filter', 0))} | {fmt_pct(d.get('precision', 0))} | "
            f"{fmt_pct(d.get('recall', 0))} | {fmt_pct(d.get('f1', 0))} |"
        )
    lines.append("")
    lines.append("## Gráficas generadas\n")
    for p in sorted(plots_dir.glob("*.png")):
        lines.append(f"![{p.stem}](../{p.relative_to(ROOT).as_posix()})")
        lines.append("")
    lines.append("## Notas metodológicas")
    lines.append("")
    lines.append("- Filtro en dos capas: reglas heurísticas (regex) + embeddings (all-MiniLM-L6-v2) con Random Forest.")
    lines.append("- Al filtrar un ataque, el prompt no llega al LLM, por lo que el ataque se contabiliza como fallido.")
    lines.append("- Sin LLM disponible, se usa un proxy determinista (el ataque 'tiene éxito' si no es bloqueado).")
    return "\n".join(lines)


def build_pdf(md_path: Path) -> Path | None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate
    except ImportError:
        logger.warning("reportlab no instalado; solo se generó el Markdown.")
        return None

    styles = getSampleStyleSheet()
    pdf_path = md_path.with_suffix(".pdf")
    parts = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            parts.append(Paragraph(f"<h1>{line[2:]}</h1>", styles["Title"]))
        elif line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            html = "&nbsp; | &nbsp;".join(f"<b>{c}</b>" if i == 0 else c for i, c in enumerate(cells))
            parts.append(Paragraph(html, styles["BodyText"]))
        elif line.startswith("## "):
            parts.append(Paragraph(line[3:], styles["Heading2"]))
        elif line:
            parts.append(Paragraph(line, styles["BodyText"]))
    SimpleDocTemplate(str(pdf_path), pagesize=letter).build(parts)
    logger.info("PDF generado: %s", pdf_path)
    return pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(_CONF["paths"]["reports"]) / "benchmark_report.md"))
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()

    results = Path(_CONF["paths"]["results"])
    plots = Path(_CONF["paths"]["plots"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_markdown(results, plots), encoding="utf-8")
    logger.info("Reporte guardado: %s", out)
    if args.pdf:
        build_pdf(out)