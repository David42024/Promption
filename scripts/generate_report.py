"""Generate a Markdown (and styled PDF) report from the latest benchmark.

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

HEX_PRIMARY = "#1F3864"
HEX_ACCENT = "#2CA58D"
HEX_RED = "#D64550"
HEX_GREEN = "#27AE60"
HEX_BORDER = "#B9C4E0"
HEX_LIGHT = "#F2F5FB"


def fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def load_payload(results_dir: Path) -> dict:
    with open(results_dir / "benchmark_results_latest.json", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------- charts
def build_charts(results_dir: Path, plots_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    payload = load_payload(results_dir)
    overall = payload["overall"]
    by_dataset = [d for d in payload.get("by_dataset", [])]

    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#C5CCE3"

    rows = [("Toda la muestra", overall)] + [
        (d["dataset"], d) for d in by_dataset if d.get("precision") is not None
    ]
    labels = [r[0] for r in rows]
    without = [r[1].get("asr_without_filter", 0) or 0 for r in rows]
    with_filter = [r[1].get("asr_with_filter", 0) or 0 for r in rows]

    x = range(len(rows))
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    b1 = ax.bar([i - width / 2 for i in x], without, width,
                label="ASR sin filtro", color=HEX_RED)
    b2 = ax.bar([i + width / 2 for i in x], with_filter, width,
                label="ASR con filtro", color=HEX_GREEN)
    ax.set_title("ASR por dataset: sin filtro vs con filtro", fontsize=13, fontweight="bold", color=HEX_PRIMARY)
    ax.set_ylabel("Promedio de ataques que tuve éxito", fontsize=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, max(max(without), 1.0) * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v * 100:.0f}%")
    ax.grid(axis="y", color="#E4E8F3", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    for bars in (b1, b2):
        for bar in bars:
            ax.annotate(f"{bar.get_height() * 100:.1f}%",
                        (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        ha="center", va="bottom", fontsize=8)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(plots_dir / "asr_comparison.png")
    plt.close(fig)

    n_mal = overall.get("n_malicious", 0)
    n_ben = overall.get("n_benign", 0)
    fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
    total = n_mal + n_ben
    wedges, _ = ax.pie(
        [n_mal, n_ben],
        colors=[HEX_RED, HEX_GREEN],
        startangle=90, counterclock=False,
        wedgeprops={"width": 0.35, "edgecolor": "white", "linewidth": 2},
    )
    ax.text(0, 0.08, f"{total:,}", ha="center", va="center",
            fontsize=20, fontweight="bold", color=HEX_PRIMARY)
    ax.text(0, -0.12, "prompts", ha="center", va="center", fontsize=9, color="#5A6B8C")
    ax.legend(wedges,
              [f"Maliciosos  {n_mal:,}  ({n_mal / total * 100:.1f}%)",
               f"Benignos    {n_ben:,}  ({n_ben / total * 100:.1f}%)"],
              loc="center left", bbox_to_anchor=(0.95, 0.5), frameon=False, fontsize=9)
    ax.set_title("Composición del corpus", fontsize=13, fontweight="bold", color=HEX_PRIMARY)
    fig.tight_layout()
    fig.savefig(plots_dir / "distribution.png")
    plt.close(fig)


# ------------------------------------------------------------------- markdown
def build_markdown(results_dir: Path, plots_dir: Path) -> str:
    payload = load_payload(results_dir)
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
        "## Desglose por dataset y tipo de ataque",
        "",
        "| Dataset | ASR sin filtro | ASR con filtro | Precisión | Recall | F1 |",
        "|---|---|---|---|---|---|",
    ]
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


# ------------------------------------------------------------------------ pdf
class _PdfStyle:
    """Nicer look for reportlab documents."""

    def __init__(self):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_paths = {
            "Main": (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
            "DejaVu": (Path("C:/Windows/Fonts/DejaVuSans.ttf"), Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf")),
        }
        main = bold = None
        for name, (plain, b) in font_paths.items():
            if plain.exists() and b.exists():
                pdfmetrics.registerFont(TTFont(f"{name}", str(plain)))
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(b)))
                main, bold = f"{name}", f"{name}-Bold"
                break
        if main is None:
            main, bold = "Helvetica", "Helvetica-Bold"

        self.main = main
        self.bold = bold
        self.colors = colors
        self.C = {
            "primary": colors.HexColor(HEX_PRIMARY),
            "accent": colors.HexColor(HEX_ACCENT),
            "red": colors.HexColor(HEX_RED),
            "green": colors.HexColor(HEX_GREEN),
            "border": colors.HexColor(HEX_BORDER),
            "light": colors.HexColor(HEX_LIGHT),
            "muted": colors.HexColor("#5A6B8C"),
            "white": colors.white,
        }
        self.title = ParagraphStyle("Title", fontName=self.bold, fontSize=20, leading=24,
                                    textColor=self.C["primary"])
        self.section = ParagraphStyle("Section", fontName=self.bold, fontSize=13, leading=17,
                                      textColor=self.C["primary"], spaceBefore=14, spaceAfter=6)
        self.body = ParagraphStyle("Body", fontName=self.main, fontSize=9.5, leading=13,
                                   textColor=colors.HexColor("#22304A"), alignment=TA_LEFT)
        self.body_c = ParagraphStyle("BodyC", parent=self.body, alignment=TA_CENTER)
        self.cell = ParagraphStyle("Cell", fontName=self.main, fontSize=8.8, leading=11,
                                   textColor=colors.HexColor("#22304A"))
        self.cell_c = ParagraphStyle("CellC", parent=self.cell, alignment=TA_CENTER)
        self.cell_b = ParagraphStyle("CellB", parent=self.cell, fontName=self.bold)
        self.header = ParagraphStyle("Header", fontName=self.bold, fontSize=8.8, leading=11,
                                     textColor=self.C["white"], alignment=TA_CENTER)


def _styled_table(s, data, header, col_widths, numeric_cols=()):
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = [[Paragraph(header[i], s.header) for i in range(len(header))]]
    for r in data:
        row = []
        for i in range(len(r)):
            cell = r[i]
            if not isinstance(cell, Paragraph):
                cell = Paragraph(str(cell), s.cell_c if i in numeric_cols else s.cell)
            row.append(cell)
        rows.append(row)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), s.C["primary"]),
        ("GRID", (0, 0), (-1, -1), 0.6, s.C["border"]),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, s.C["primary"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), s.C["light"]))
    return Table(rows, colWidths=col_widths, repeatRows=1, style=TableStyle(style))


def build_pdf(results_dir: Path, plots_dir: Path, md_path: Path) -> Path | None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import (HRFlowable, Image, Paragraph, SimpleDocTemplate,
                                        Spacer, Table, TableStyle)
        from reportlab.lib.utils import ImageReader
    except ImportError:
        logger.warning("reportlab no instalado; solo se generó el Markdown.")
        return None

    try:
        from reportlab.lib.enums import TA_CENTER
    except ImportError:  # pragma: no cover
        TA_CENTER = 1

    payload = load_payload(results_dir)
    o = payload["overall"]
    s = _PdfStyle()

    pdf_path = md_path.with_suffix(".pdf")
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=letter,
        leftMargin=54, rightMargin=54, topMargin=48, bottomMargin=48,
        title="Reporte de Benchmark — Prompt Injection Filter",
        author="Prompt Injection Filter",
    )
    avail = doc.width

    def tick():
        return Spacer(1, 6)

    story = [Paragraph("Reporte de Benchmark", s.title),
             Paragraph("Detección de Prompt Injection — filtro heurístico + ML", s.body)]
    story.append(Spacer(1, 10))
    meta = [
        f"Generado:   {datetime.now().isoformat(timespec='seconds')}",
        f"Ejecución del benchmark:   {payload.get('timestamp')}",
        f"Muestras:   {o.get('n_total', '?')} prompts "
        f"({o.get('n_malicious', '?')} maliciosos / {o.get('n_benign', '?')} benignos)",
    ]
    for line in meta:
        story.append(Paragraph(line, s.body))
    story.append(HRFlowable(width="100%", thickness=1.2, color=s.C["accent"], spaceBefore=8, spaceAfter=4))

    summary = Table(
        [[Paragraph(
            f"El filtro reduce drásticamente la tasa de éxito de los ataques: "
            f"del <b>{fmt_pct(o.get('asr_without_filter', 0))}</b> sin filtro al "
            f"<b><font color='{HEX_GREEN}'>{fmt_pct(o.get('asr_with_filter', 0))}</font></b> con filtro "
            f"(reducción del <b><font color='{HEX_GREEN}'>{fmt_pct(o.get('asr_reduction', 0))}</font></b>). "
            f"Precisión <b>{fmt_pct(o.get('precision', 0))}</b>, recall <b>{fmt_pct(o.get('recall', 0))}</b>, "
            f"F1 <b>{fmt_pct(o.get('f1', 0))}</b>.",
            s.body)]],
        colWidths=[avail],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), s.C["light"]),
            ("BOX", (0, 0), (-1, -1), 0.8, s.C["border"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )
    story.append(Spacer(1, 6))
    story.append(summary)

    story.append(Paragraph("Métricas globales", s.section))
    metrics = [
        (Paragraph("ASR sin filtro", s.cell), Paragraph(f"<font color='{HEX_RED}'><b>{fmt_pct(o.get('asr_without_filter', 0))}</b></font>", s.cell_c)),
        (Paragraph("ASR con filtro", s.cell), Paragraph(f"<font color='{HEX_GREEN}'><b>{fmt_pct(o.get('asr_with_filter', 0))}</b></font>", s.cell_c)),
        (Paragraph("Reducción de ASR", s.cell), Paragraph(f"<font color='{HEX_GREEN}'><b>{fmt_pct(o.get('asr_reduction', 0))}</b></font>", s.cell_c)),
        (Paragraph("Precisión", s.cell), Paragraph(fmt_pct(o.get('precision', 0)), s.cell_c)),
        (Paragraph("Recall", s.cell), Paragraph(fmt_pct(o.get('recall', 0)), s.cell_c)),
        (Paragraph("F1-Score", s.cell), Paragraph(fmt_pct(o.get('f1', 0)), s.cell_c)),
        (Paragraph("Falsos positivos (FPR)", s.cell), Paragraph(fmt_pct(o.get('fpr', 0)), s.cell_c)),
        (Paragraph("Falsos negativos (FNR)", s.cell), Paragraph(fmt_pct(o.get('fnr', 0)), s.cell_c)),
        (Paragraph("Latencia media del filtro", s.cell), Paragraph(f"{o.get('latency', {}).get('mean', 0) / 1000:.1f} ms", s.cell_c)),
    ]
    story.append(_styled_table(s, [[c[0], c[1]] for c in metrics], ["Métrica", "Valor"], [avail * 0.65, avail * 0.35], numeric_cols=(1,)))

    story.append(Paragraph("Desglose por dataset", s.section))
    header = ["Dataset", "ASR sin filtro", "ASR con filtro", "Precisión", "Recall", "F1"]
    rows = [
        [d["dataset"], fmt_pct(d.get("asr_without_filter", 0)), fmt_pct(d.get("asr_with_filter", 0)),
         fmt_pct(d.get("precision", 0)), fmt_pct(d.get("recall", 0)), fmt_pct(d.get("f1", 0))]
        for d in payload.get("by_dataset", [])
    ]
    story.append(_styled_table(s, rows, header, [avail * 0.16] + [avail * 0.168] * 5, numeric_cols=(1, 2, 3, 4, 5)))

    story.append(Paragraph("Gráficas", s.section))
    for name in ("asr_comparison.png", "distribution.png", "confusion_matrix.png", "feature_importance.png"):
        img = plots_dir / name
        if not img.exists():
            continue
        ir = ImageReader(str(img))
        w, h = ir.getSize()
        height = avail * h / w
        story.append(Image(str(img), width=avail, height=height))
        story.append(tick())

    story.append(Paragraph("Notas metodológicas", s.section))
    for note in (
        "Filtro en dos capas: reglas heurísticas (regex) + embeddings (all-MiniLM-L6-v2) con Random Forest.",
        "Al filtrar un ataque, el prompt no llega al LLM, por lo que el ataque se contabiliza como fallido.",
        "Sin LLM disponible, se usa un proxy determinista (el ataque 'tiene éxito' si no es bloqueado).",
    ):
        story.append(Paragraph(f"•  {note}", s.body))

    doc.build(story)
    logger.info("PDF generado: %s", pdf_path)
    return pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(_CONF["paths"]["reports"]) / "benchmark_report.md"))
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()

    results = Path(_CONF["paths"]["results"])
    plots = Path(_CONF["paths"]["plots"])
    plots.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    build_charts(results, plots)
    out.write_text(build_markdown(results, plots), encoding="utf-8")
    logger.info("Reporte guardado: %s", out)
    if args.pdf:
        build_pdf(results, plots, out)