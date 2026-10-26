"""Publish aggregate-only results and matched-case coverage for the Lumina API study."""
import argparse
from collections import Counter
import json
from pathlib import Path

import luna_primary as shared
from summarize_corpus_study import confusion, exposures
from summarize_precision_study import legitimate_service, summarize


NAMES = {"unprotected": "Sin protección", "prompt_only": "Solo prompt", "promption": "Prompt + Promption"}


def report(directory):
    summarize(directory)
    summary = shared.load(directory / "summary.json")
    protocol = shared.load(directory / "protocol.json")
    assert protocol["study"] in ["precision_lumina_three_conditions", "precision_lumina_openai_three_conditions",
                                "precision_lumina_gemini_three_conditions", "precision_lumina_gemini_native_three_conditions", "precision_lumina_deepseek_three_conditions"]
    rows = summary["rows"]
    conditions = protocol["conditions"]
    by_case = {}
    for row in rows:
        assert row["corpus"] == "lumina"
        by_case.setdefault(row["case_id"], {})[row["condition"]] = row
    complete = {key: value for key, value in by_case.items() if set(value) == set(conditions)}
    nonoperational = {key: value for key, value in complete.items()
                      if all(row["status"] != "operational" for row in value.values())}
    paired_rows = [row for value in nonoperational.values() for row in value.values()]
    output = {key: summary[key] for key in ["complete", "library_version", "provider", "cases", "planned_episodes",
        "completed_episodes", "api_calls", "http_statuses", "new_cost_upper_usd", "total_cost_upper_usd",
        "protocol_sha256", "hashes_verified", "limitations", "cohort", "paired_descriptive"]}
    output.update({"models": {key: protocol[key] for key in ["generation_model", "scope_model", "refusal_judge_model"]},
        "budget_usd": protocol["budget_usd"], "conditions": summary["conditions"]["lumina"],
        "coverage": {"planned_cases": protocol["cases"], "attempted_cases": len(by_case),
                     "unattempted_cases": protocol["cases"] - len(by_case),
                     "cases_with_all_three_records": len(complete),
                     "cases_with_three_nonoperational_records": len(nonoperational),
                     "matched_reference_labels": dict(Counter(value[conditions[0]]["label"] for value in nonoperational.values())),
                     "unattempted_episodes": protocol["planned_episodes"] - len(rows)},
        "paired_nonoperational_conditions": {condition: {
            "observed_refusal_confusion": confusion([row for row in paired_rows if row["condition"] == condition], "refusal"),
            "exfiltration": exposures([row for row in paired_rows if row["condition"] == condition])}
            for condition in conditions},
        "refusal_origins": {condition: dict(Counter("guard" if row["status"] == "blocked" else "model_refusal_judge"
            for row in rows if row["condition"] == condition and row["refusal"] is True)) for condition in conditions},
        "false_positive_origins": {condition: dict(Counter("guard" if row["status"] == "blocked" else "model_refusal_judge"
            for row in rows if row["condition"] == condition and row["label"] == 0 and row["refusal"] is True)) for condition in conditions},
        "tool_coverage": {condition: {"executed_calls": sum(event["stage"] == "mcp" for record in
            [shared.load(file) for file in (directory / "episodes").glob("*.json")]
            if record["condition"] == condition for event in record["events"])} for condition in conditions},
        "additional_limits": ["Refusal-vs-injection-label confusion is a provisional behavioral proxy, not independently adjudicated attack success.",
            "If provider quota stops the run, executed cases are only the deterministic prefix of the fixed plan; no full-120 claim is warranted.",
            "Matched nonoperational comparisons exclude technical failures and report their reduced coverage; they do not replace the all-attempted results.",
            "Exfiltration-target tags are historical/provisional. Their intent may depend on historical context and is not a new human validation.",
            "No historical study outcomes are pooled into these new responses."]})
    quota_stop = any(json.loads(file.read_text()).get("http_status") == 429 and
        "tokens per day (TPD)" in json.loads(file.read_text()).get("error", {}).get("message", "")
        for file in (directory / "api_responses").glob("*.json"))
    output["provider_daily_token_quota_stop"] = quota_stop
    stem = ("lumina_deepseek_api_20261025" if protocol["provider"] == "deepseek" else
            "lumina_gemini_native_api_20261025" if protocol["provider"] == "gemini-native" else
            "lumina_gemini_api_20261025" if protocol["provider"] == "gemini" else
            "lumina_openai_api_20261025" if protocol["provider"] == "openai" else "lumina_api_20261025")
    public = shared.ROOT / "data/results" / (stem + ".json")
    public.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    lines = [f"# Lúmina: comparación por API ({protocol['provider']}) — 25/10/2026", "", "## Alcance", "",
        f"Se planificaron **{protocol['cases']} casos y {protocol['planned_episodes']} episodios**. "
        f"Se registraron **{len(rows)} episodios**, correspondientes a **{len(by_case)} casos**; "
        f"{len(complete)} tienen registros en las tres condiciones y {len(nonoperational)} tienen las tres ejecuciones sin fallo operativo.", "",
        f"Estado: **{'completa' if summary['complete'] else 'incompleta'}**. "
        f"Generador y juez de rechazo: `{protocol['generation_model']}`. "
        f"Evaluador semántico de Promption: `{protocol['scope_model']}`. Promption {summary['library_version']}, perfil equilibrado.", "",
        "Misma clave sintética, datos públicos y herramientas para las tres condiciones. Solo prompt y Promption comparten la misma política protectora. Cada condición utiliza llamadas nuevas; no se sustituyen fallos por respuestas históricas. Webs y archivos internos son fixtures, sin acceso a secretos reales.", "",
        "## Rechazo observado frente a las etiquetas provisionales", "",
        "| Condición | N registrados | VP | FP | FN | VN | Fallos operativos | Sin clasificación |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for condition in conditions:
        m = output["conditions"][condition]["observed_refusal_confusion"]
        lines.append(f"| {NAMES[condition]} | {m['n']} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {m['operational']} | {m['unclassified']} |")
    lines += ["", "Estos VP/FP/FN/VN comparan rechazos observados con etiquetas silver de inyección. Una respuesta sin rechazo no prueba que el ataque haya tenido éxito; puede ser una respuesta legítima parcial o una aclaración. Los errores del proveedor no se cuentan como bloqueos correctos.", "",
        "## Exfiltración y herramientas", "",
        "| Condición | Objetivos registrados | Objetivos sin fallo operativo | Filtraciones en esos objetivos | Filtraciones en cualquier caso | Efectos de herramientas no autorizadas |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition in conditions:
        m = output["conditions"][condition]["exfiltration"]
        lines.append(f"| {NAMES[condition]} | {m['eligible_exfil_targets']} | {m['eligible_nonoperational']} | {m['target_disclosures']} | {m['all_case_disclosures']} | {m['unauthorized_tool_episodes']} |")
    lines += ["", "El oráculo principal comprueba la clave sintética y sus representaciones documentadas en respuestas, archivos entregados y destinos web simulados. No cubre cualquier posible codificación. Cero eventos en una muestra pequeña, y especialmente cero en las tres condiciones, no demuestra superioridad ni una tasa poblacional próxima a cero.", "",
        "## Subconjunto pareado sin fallos operativos", "",
        "| Condición | N pareados | VP | FP | FN | VN | Sin clasificación |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for condition in conditions:
        m = output["paired_nonoperational_conditions"][condition]["observed_refusal_confusion"]
        lines.append(f"| {NAMES[condition]} | {m['n']} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {m['unclassified']} |")
    lines += ["", "Este subconjunto permite comparar los mismos casos, pero excluir fallos reduce la cobertura y puede introducir sesgo. La tabla de todos los episodios registrados se conserva como resultado principal.", "",
        "## Consumo y trazabilidad", "",
        f"Llamadas HTTP de esta ejecución: **{summary['api_calls']}**. Estados: `{json.dumps(summary['http_statuses'], ensure_ascii=False)}`. "
        f"Coste superior contabilizado nuevo: **US${summary['new_cost_upper_usd']:.6f}**; acumulado: **US${summary['total_cost_upper_usd']:.6f}**, "
        f"con parada acumulada de US${protocol['budget_usd']:.2f}. Las llamadas sin uso reportado conservan su reserva como cota superior; no equivale necesariamente a facturación real.", "",
        *( ["La ejecución se detuvo por la cuota diaria de tokens del proveedor (HTTP 429). Los casos no intentados permanecen pendientes; el error no se considera un bloqueo correcto de Promption.", ""] if quota_stop else [] ),
        "Los protocolos, fuentes congeladas, solicitudes, respuestas y decisiones se conservan localmente. El JSON publicado contiene agregados y hashes, sin conversaciones, nombres, teléfonos, credenciales ni clave del reto.", "",
        "## Límites", ""]
    lines += ["- " + text for text in [
        "Etiquetas provisionales sin adjudicación humana; la cohorte ya fue expuesta a diagnósticos.",
        "Los casos comparten participantes e historial: no son observaciones independientes.",
        "El alcance de la política de esta prueba es general y puede diferir del alcance empresarial histórico.",
        "Las metas de exfiltración se etiquetaron provisionalmente y pueden depender del historial.",
        "No se mezclan resultados anteriores de otros modelos o proveedores con esta comparación."]]
    lines += ["", f"- [Agregados y cobertura](../data/results/{stem}.json)", ""]
    (shared.ROOT / "docs" / (stem + ".md")).write_text("\n".join(lines))
    print(json.dumps({"coverage": output["coverage"], "conditions": output["conditions"],
                      "total_cost_upper_usd": summary["total_cost_upper_usd"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    report(parser.parse_args().directory.resolve())
