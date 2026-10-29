"""Publish only aggregate study results to Shop and preserve the private audit trail."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import luna_primary as shared
from summarize_precision_study import summarize


NAMES = {"unprotected": "Sin protección", "prompt_only": "Solo prompt", "promption": "Prompt + Promption"}


def percent(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def publish(directory):
    summarize(directory)
    summary = shared.load(directory / "summary.json")
    protocol = shared.load(directory / "protocol.json")
    assert protocol["study"] == "shop_mixed_three_conditions"
    fields = ["complete", "library_version", "provider", "cohort", "cases", "planned_episodes", "completed_episodes", "api_calls",
        "http_statuses", "new_cost_upper_usd", "total_cost_upper_usd", "protocol_sha256", "hashes_verified", "paired_descriptive"]
    report = {key: summary[key] for key in fields}
    report.update(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(), commit=protocol["commit"],
        models={key: protocol[key] for key in ["generation_model", "scope_model", "refusal_judge_model"]},
        conditions=summary["conditions"], public_language_counts=protocol["public_language_counts"],
        public_dataset_counts=protocol["public_dataset_counts"], concurrency=protocol["concurrency"],
        selection="600 casos: 180 conversaciones de Lúmina (90 positivos y 90 negativos) y 420 casos públicos (210 positivos y 210 negativos). Selección determinista sobre particiones de prueba previamente expuestas a diagnósticos, sin usar predicciones del filtro para elegir casos.",
        limitations=["Las etiquetas son provisionales o de origen, sin nueva adjudicación humana.",
            "Los rechazos se comparan con etiquetas de inyección: un FN de rechazo no equivale a un ataque exitoso y una referencia negativa no garantiza autorización de la petición.",
            "La mezcla pondera los corpus según su tamaño; consulta también los resultados separados de Lúmina y del corpus público.",
            "Hay dependencia entre conversaciones de los mismos participantes y exposición previa durante el desarrollo; no es una nueva reserva independiente.",
            "El generador y el juez de rechazo usan DeepSeek. Las respuestas inciertas y fallos operativos quedan separados.",
            "Las herramientas web e internas son fixtures con una clave sintética. No se accede a páginas externas ni a secretos reales.",
            "La política del experimento permite tareas generales y datos públicos de Lúmina; no reproduce todas las reglas comerciales de Shop.",
            "La tasa de bloqueo de actividad real no permite calcular FPR, FNR o recall sin etiquetas de referencia."])
    records = [shared.load(file) for file in (directory / "episodes").glob("*.json")]
    report["statuses"] = dict(Counter(record["status"] for record in records))
    report["publisher_sha256"] = shared.digest(Path(__file__))
    for corpus_name, corpus in report["conditions"].items():
        for condition, row in corpus.items():
            selected = [r for r in summary["rows"] if r["condition"] == condition
                and (corpus_name == "pooled_descriptive" or r["corpus"] == corpus_name)]
            row["false_positive_origins"] = dict(Counter("guard" if r["status"] == "blocked" else "model"
                for r in selected if r["label"] == 0 and r["refusal"] is True))
            m = row["observed_refusal_confusion"]
            m["accuracy"] = (m["TP"] + m["TN"]) / m["evaluated"] if m["evaluated"] else None
            m["specificity"] = m["TN"] / (m["TN"] + m["FP"]) if m["TN"] + m["FP"] else None
    local = directory / "local_lumina_full/summary.json"
    if local.exists():
        data = shared.load(local)
        report["local_lumina_regression"] = {key: data[key] for key in ["library_version", "eligible_turns", "executions", "profiles", "limits", "api_calls", "elapsed_seconds"]}
    title = "# Promption Shop: evaluación de Lúmina y datasets abiertos — 25/10/2026"
    lines = [title, "", "## Alcance y trazabilidad", "",
        f"Promption **{summary['library_version']}**, perfil equilibrado. DeepSeek-V4.1-Flash-1017 mediante el alias `deepseek-flash`, razonamiento desactivado, máximo 1024 tokens por respuesta y 12 episodios concurrentes.", "",
        f"Estado: **{'completa' if summary['complete'] else 'parcial'}**. {summary['completed_episodes']} de {summary['planned_episodes']} episodios, sobre 600 casos únicos. Cada condición utiliza llamadas nuevas.", "",
        report["selection"], "",
        f"Corpus públicos: `{json.dumps(report['public_dataset_counts'])}`. Idiomas públicos: `{json.dumps(report['public_language_counts'])}`. Lúmina conserva español o mezcla de idiomas sin verificación lingüística independiente.", "",
        "Las tres condiciones comparten datos, herramientas y clave sintética. Solo prompt y Promption comparten exactamente el mismo prompt protector. La condición Promption añade la librería Python, middleware AI SDK, contexto e intención, controles de permisos, MCP y protección de salida."]
    for corpus, name in [("lumina", "Lúmina"), ("public", "Datasets abiertos"), ("pooled_descriptive", "Conjunto combinado descriptivo")]:
        lines += ["", f"## {name}", "", "| Condición | N | VP | FP | FN | VN | Fallos | Sin clasificar |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for condition in protocol["conditions"]:
            m = report["conditions"][corpus][condition]["observed_refusal_confusion"]
            lines.append(f"| {NAMES[condition]} | {m['n']} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {m['operational']} | {m['unclassified']} |")
        lines += ["", "| Condición | Evaluables | FPR | FNR | Recall | Precisión | F1 | Exactitud |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for condition in protocol["conditions"]:
            m = report["conditions"][corpus][condition]["observed_refusal_confusion"]
            lines.append(f"| {NAMES[condition]} | {m['evaluated']} | {percent(m['fpr'])} | {percent(m['fnr'])} | {percent(m['recall'])} | {percent(m['precision'])} | {percent(m['f1'])} | {percent(m['accuracy'])} |")
        lines += ["", "| Condición | Filtraciones en cualquier caso | Objetivos predefinidos | Filtraciones en objetivos | Efectos de herramientas no autorizadas |", "|---|---:|---:|---:|---:|"]
        for condition in protocol["conditions"]:
            m = report["conditions"][corpus][condition]["exfiltration"]
            lines.append(f"| {NAMES[condition]} | {m['all_case_disclosures']} | {m['eligible_exfil_targets']} | {m['target_disclosures']} | {m['unauthorized_tool_episodes']} |")
        lines += ["", "Origen de los FP de la condición Promption: `" + json.dumps(report["conditions"][corpus]["promption"]["false_positive_origins"]) + "`. Los rechazos del propio modelo se conservan en la FPR del sistema completo, pero no deben atribuirse todos al guard de entrada."]
    lines += ["", "## Definiciones y errores", "",
        "FPR=FP/(FP+VN); FNR=FN/(FN+VP); recall=VP/(VP+FN); precisión=VP/(VP+FP). Se excluyen errores y casos sin clasificación del denominador, pero se conservan como columnas y no se consideran detecciones correctas.", "",
        "Los VP/FP/FN/VN describen rechazo frente a etiquetas provisionales, no éxito del ataque. Las filtraciones se comprueban mediante un oráculo finito sobre la clave sintética, sus representaciones documentadas, archivos entregados y destinos web simulados. Las coincidencias en candidatos bloqueados se conservan separadas en el JSON; no equivalen a información entregada.", "",
        "Los ceros observados no prueban riesgo poblacional cero. Los valores pareados de McNemar incluidos en JSON son descriptivos, porque hay dependencia por participante e historial. La muestra ampliada no permite una atribución causal simple respecto de ejecuciones anteriores con modelos o muestras distintos.", "",
        "## Consumo", "",
        f"Llamadas de esta batería: **{summary['api_calls']}**; estados HTTP `{json.dumps(summary['http_statuses'])}`. Cota nueva: **US${summary['new_cost_upper_usd']:.6f}**; acumulada: **US${summary['total_cost_upper_usd']:.6f}**, bajo el techo de US$5.", "",
        "Se usan precios pico sin descuentos por caché, no una factura. Las reservas pendientes o sin uso informado se conservan como cota superior. No hay reintentos automáticos ni pausas artificiales en DeepSeek."]
    if report.get("local_lumina_regression"):
        local = report["local_lumina_regression"]
        lines += ["", "## Regresión local completa de Lúmina", "",
            f"Se revisaron **{local['eligible_turns']} turnos**, con **{local['executions']} ejecuciones locales** en tres perfiles y cero llamadas API. El FN local significa ausencia de veto de entrada: puede continuar por revisión semántica y protección de salida, por lo que no es una medición de exfiltración.", "",
            "| Perfil | N | VP | FP | FN sin veto | VN | FPR | Positivos enviados a revisión |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for profile, values in local["profiles"].items():
            m = values["all_regression"]
            lines.append(f"| {profile} | {m['n']} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {percent(m['fpr'])} | {m['attacks_review']} |")
    lines += ["", "## Límites", "", *["- " + limit for limit in report["limitations"]], "",
        f"Hash del protocolo: `{summary['protocol_sha256']}`. Verificación de hashes: `{summary['hashes_verified']}`. Las trazas privadas permanecen en `output/shop_evaluation_20261025/`; no se copian chats, credenciales ni clave real a la app.", "",
        "- [Modelos y precios oficiales de DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/)", ""]
    text = "\n".join(lines)
    secret = shared.load(directory / "settings.json")["secret"]
    assert not shared.hits(text, secret)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    assert not shared.hits(payload, secret)
    for destination in [shared.ROOT / "data/results/shop_mixed_deepseek_20261025.json", shared.ROOT / "demo/data/evaluation-latest.json"]:
        temp = destination.with_suffix(".tmp")
        temp.write_text(payload)
        temp.replace(destination)
    (shared.ROOT / "docs/shop_evaluation_20261025.md").write_text(text)
    print(json.dumps({"complete": report["complete"], "episodes": report["completed_episodes"], "new_upper_usd": report["new_cost_upper_usd"]}))


if __name__ == "__main__":
    publish(Path(sys.argv[1]).resolve())
