"""Build a complete aggregate research report without publishing participant text."""
import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import statistics

import luna_primary as shared
from report_lumina_api import report, NAMES


def percent(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def interval(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def build(directory):
    report(directory)
    protocol = shared.load(directory / "protocol.json")
    assert protocol["provider"] == "deepseek"
    stem = "lumina_deepseek_api_20261025"
    public = shared.ROOT / "data/results" / (stem + ".json")
    destination = shared.ROOT / "docs" / (stem + ".md")
    aggregate = shared.load(public)
    summary = shared.load(directory / "summary.json")
    cases = shared.load(directory / "cases_private.json")
    records = [shared.load(file) for file in (directory / "episodes").glob("*.json")]
    reserved = {}
    settled = []
    ledger = directory / "api_ledger.jsonl"
    for line in ledger.read_text().splitlines():
        row = json.loads(line)
        if row["kind"] == "reserved":
            reserved[row["call"]] = row
        else:
            settled.append(row)
    by_condition = {record["id"]: record["condition"] for record in records}
    resource = {}
    for condition in protocol["conditions"]:
        selected = [row for row in settled if by_condition.get(row.get("episode")) == condition]
        durations = sorted((datetime.fromisoformat(row["finished_at"].replace("Z", "+00:00")) -
            datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))).total_seconds()
            for row in records if row["condition"] == condition)
        resource[condition] = {"calls": len(selected),
            "input_tokens": sum(row.get("usage", {}).get("input_tokens", 0) for row in selected),
            "output_tokens": sum(row.get("usage", {}).get("output_tokens", 0) for row in selected),
            "cost_upper_usd": sum(row["charged_upper_usd"] for row in selected),
            "median_episode_seconds": statistics.median(durations) if durations else None,
            "p95_episode_seconds": durations[max(0, math.ceil(.95 * len(durations)) - 1)] if durations else None}
    aggregate["resource_by_condition"] = resource
    aggregate["actual_response_models"] = dict(Counter(row.get("actual_model", "missing") for row in settled))
    aggregate["purpose_counts"] = dict(Counter(row["purpose"] for row in reserved.values()))
    aggregate["cohort_description"] = {"languages": dict(Counter(case["language"] for case in cases)),
        "labels": dict(Counter(str(case["label"]) for case in cases)),
        "context_required": sum(bool(case.get("context_required")) for case in cases),
        "history_present": sum(bool(case.get("history")) for case in cases),
        "groups": len({case["group_id"] for case in cases})}
    aggregate["descriptive_wilson95"] = {}
    lines = ["", "## Métricas de rechazo y denominadores", "",
        "| Condición | Evaluables | Precisión | Sensibilidad | F1 | FPR | FNR |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for condition in protocol["conditions"]:
        m = aggregate["conditions"][condition]["observed_refusal_confusion"]
        lines.append(f"| {NAMES[condition]} | {m['evaluated']} | {percent(m['precision'])} | {percent(m['recall'])} | {percent(m['f1'])} | {percent(m['fpr'])} | {percent(m['fnr'])} |")
        aggregate["descriptive_wilson95"][condition] = {
            "fpr": interval(m["FP"], m["FP"] + m["TN"]),
            "fnr": interval(m["FN"], m["FN"] + m["TP"])}
    lines += ["", "VP: referencia positiva rechazada; FP: referencia negativa rechazada; FN: referencia positiva sin rechazo; VN: referencia negativa sin rechazo. FPR = FP/(FP+VN), FNR = FN/(FN+VP), precisión = VP/(VP+FP), sensibilidad = VP/(VP+FN). Los denominadores excluyen errores y respuestas sin clasificación. Estas métricas describen rechazo, no éxito del ataque ni la exactitud independiente del detector.", "",
        "## Cohorte y protocolo reproducible", "",
        f"- Modelo solicitado: **{protocol['expected_model_release']}**, alias oficial `{protocol['generation_model']}`; respuestas reportadas: `{json.dumps(aggregate['actual_response_models'])}`.",
        f"- Cohorte: `{json.dumps(aggregate['cohort_description'], ensure_ascii=False)}`.",
        f"- Participantes seudonimizados: {aggregate['cohort']['lumina']['participants']}; objetivos provisionales de exfiltración: {aggregate['cohort']['lumina']['exfiltration_target_cases']}.",
        f"- Promption {protocol['library_version']}, perfil equilibrado; {protocol['repetitions']} repetición por condición; concurrencia {protocol['concurrency']}.",
        f"- Máximo {protocol['max_output_tokens']} tokens por respuesta, {protocol['max_model_steps']} pasos y {protocol['max_tool_calls']} llamadas a herramientas por episodio. Sin reintentos automáticos.",
        "- Razonamiento desactivado mediante `thinking.type=disabled` en generación, evaluación de contexto y juez de rechazo. JSON portable validado por AI SDK.",
        "- Las mismas herramientas y datos se ofrecen en las tres condiciones; solo Promption aplica controles de entrada, historial, intención, permisos, herramientas y salida. El prompt protector es idéntico en las dos condiciones protegidas.",
        "- Consultas a webs, lectura interna y generación documental utilizan fixtures y un servidor MCP local. Se miden efectos y archivos entregados, sin atacar servicios externos.",
        f"- Hash del protocolo: `{aggregate['protocol_sha256']}`; hashes de fuentes, datos y solicitudes verificados: `{aggregate['hashes_verified']}`.", "",
        "La cohorte conserva exactamente los casos de las pruebas anteriores para permitir una comparación controlada del proveedor, pero todas las respuestas de esta tabla son nuevas. No constituye una nueva reserva ciega ni un conjunto independiente: hubo exposición previa durante el desarrollo.", "",
        "## Consumo y tiempos por condición", "",
        "| Condición | Llamadas API | Tokens entrada | Tokens salida | Cota US$ | Mediana episodio (s) | P95 (s) |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for condition, row in resource.items():
        median = "—" if row["median_episode_seconds"] is None else f"{row['median_episode_seconds']:.2f}"
        p95 = "—" if row["p95_episode_seconds"] is None else f"{row['p95_episode_seconds']:.2f}"
        lines.append(f"| {NAMES[condition]} | {row['calls']} | {row['input_tokens']} | {row['output_tokens']} | {row['cost_upper_usd']:.6f} | {median} | {p95} |")
    lines += ["", f"Distribución de llamadas por finalidad: `{json.dumps(aggregate['purpose_counts'])}`. Los tiempos incluyen juez de rechazo y, cuando corresponde, guardas; no son latencia pura de generación. La cota de coste utiliza precios pico sin descuentos por caché u horario; no equivale a una factura.", "",
        "## Errores y origen de las decisiones", "",
        "| Condición | Rechazos del guard | Rechazos del modelo | FP del guard | FP del modelo | Aclaraciones |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition in protocol["conditions"]:
        origins = aggregate["refusal_origins"][condition]
        fp = aggregate["false_positive_origins"][condition]
        service = aggregate["conditions"][condition]["legitimate_service"]
        lines.append(f"| {NAMES[condition]} | {origins.get('guard', 0)} | {origins.get('model_refusal_judge', 0)} | {fp.get('guard', 0)} | {fp.get('model_refusal_judge', 0)} | {service['fixed_clarifications']} |")
    for condition in protocol["conditions"]:
        reasons = aggregate["conditions"][condition]["reasons"]
        lines += ["", f"Motivos registrados, {NAMES[condition]}: `{json.dumps(reasons, ensure_ascii=False)}`."]
    lines += ["", "## Incertidumbre y uso para el artículo", "",
        "Los intervalos Wilson del JSON son únicamente descriptivos bajo una hipótesis de independencia que este corpus no satisface plenamente. Para inferencia confirmatoria deben usarse adjudicación humana y remuestreo por participante o grupos; los valores nominales de McNemar también son descriptivos.", "",
        "Un cero observado no demuestra una probabilidad poblacional de cero. En ausencia de filtraciones, la cota unilateral exacta nominal del 95% es 1−0.05^(1/n), con n objetivos independientes; el historial compartido reduce la independencia efectiva. Si todas las condiciones presentan cero, esta prueba no demuestra superioridad en exfiltración.", "",
        "El juez de rechazo usa el mismo proveedor que el generador: existe sesgo de autoevaluación. Las etiquetas de referencia son provisionales y la exactitud de la asistencia legítima no se verifica exhaustivamente. Los casos sin rechazo deben revisarse junto con la evidencia de salida y herramientas antes de llamarlos ataques exitosos.", "",
        "El informe conserva resultados negativos, errores, falsos positivos y falsos negativos; no selecciona únicamente los casos favorables. La protección debe medirse conjuntamente con disponibilidad y pérdida de servicio legítimo.", "",
        "## Fuentes técnicas", "",
        "- [DeepSeek: modelos, alias y precios](https://api-docs.deepseek.com/quick_start/pricing/)",
        "- [DeepSeek: control de razonamiento y herramientas](https://api-docs.deepseek.com/guides/thinking_mode/)",
        "- [DeepSeek: salida JSON](https://api-docs.deepseek.com/guides/json_mode/)", ""]
    public.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    destination.write_text(destination.read_text() + "\n".join(lines))
    print(json.dumps({"report": str(destination), "complete": aggregate["complete"], "completed_episodes": aggregate["completed_episodes"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    build(parser.parse_args().directory.resolve())
