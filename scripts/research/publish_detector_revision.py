"""Publish aggregate paired regression results without participant messages or identities."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def publish():
    directory = ROOT / "output/detector_revision_20261025"
    before = json.loads((directory / "before/summary.json").read_text())
    after = json.loads((directory / "after_v173/summary.json").read_text())
    assert before["source_sha256"] == after["source_sha256"]
    assert before["cases"] == after["cases"] == 5072
    for name, expected in after["code_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    for name, expected in after["model_sha256_by_artifact"].items():
        assert hashlib.sha256((ROOT / "models" / name).read_bytes()).hexdigest() == expected, name
    for report in (before, after):
        for group in report["metrics"].values():
            for matrix in group.values():
                assert sum(matrix[k] for k in ("TP", "FP", "FN", "TN")) == matrix["evaluated"]
                assert matrix["evaluated"] + matrix["operational"] == matrix["n"]
    payload = dict(complete=True, library_version=after["library_version"], planned_cases=after["cases"],
        api_calls=0, source_sha256=after["source_sha256"],
        before=before["metrics"], after=after["metrics"],
        model_sha256_by_artifact=after["model_sha256_by_artifact"], limits=after["limits"])
    for path in (ROOT / "demo/data/detector-regression-latest.json", ROOT / "data/results/detector_revision_20261025.json"):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    ratio = lambda x: "—" if x is None else f"{x * 100:.2f}%"
    lines = ["# Promption 1.7.3 — regresión local", "", "Fecha: 25/10/2026, hora de Perú.", "",
        "## Cambios", "",
        "- Interpretación de citas analíticas con formulaciones naturales y de instrucciones negadas; una operación afirmativa posterior conserva el veto.",
        "- Aislamiento de preguntas nuevas y completas respecto de ataques antiguos. El texto actual conserva ML, política de riesgo, revisión de alcance y Output Guard; el historial se elimina del contexto enviado al generador únicamente mediante el protocolo de aislamiento.",
        "- Se conserva el clasificador principal. Se incorpora un detector suplementario TF-IDF + ExtraTrees, entrenado con el entrenamiento público y candidatos autónomos depurados de Lúmina. Solo analiza mensajes de usuario; no se aplica su modelo de un turno al historial acumulado o a herramientas.",
        "- Umbral suplementario 0.90 seleccionado en validación: 658 registros públicos y 283 de Lúmina, sin FP adicionales en ninguna de esas dos particiones; 37 VP adicionales. Las etiquetas se conservan y son provisionales.",
        "- Los benchmarks reutilizan el modelo instalado; reentrenar requiere `--retrain` o `--train-only`. Se conserva `--no-train`.",
        "- Dashboard: versión local actual y evaluación histórica con DeepSeek diferenciadas; Output Guard ejecutado se muestra separado del veto de entrada.", "",
        "## Comparación pareada de la política de entrada", "",
        "Mismos 5.072 mensajes e historiales antes/después. Los FP/FN pertenecen al veto local: no son medidas de exfiltración ni de respuesta del modelo.", "",
        "| Conjunto | Evaluables | FP antes → ahora | FPR antes → ahora | FN antes → ahora | FNR antes → ahora | Recall antes → ahora |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for key, name in [("public_test", "Públicos test"), ("lumina_participant_test", "Lúmina participantes test"),
                      ("lumina_all_regression", "Lúmina completo, incluye exposición de entrenamiento")]:
        old, new = before["metrics"][key]["guarded_input"], after["metrics"][key]["guarded_input"]
        lines.append(f"| {name} | {new['evaluated']}/{new['n']} | {old['FP']} → {new['FP']} | {ratio(old['fpr'])} → {ratio(new['fpr'])} | {old['FN']} → {new['FN']} | {ratio(old['fnr'])} → {ratio(new['fnr'])} | {ratio(old['recall'])} → {ratio(new['recall'])} |")
    lines += ["", "## Verificación y límites", "",
        "- Suite Python: 1.296 aprobadas y 10 omitidas; las pruebas con proveedores de pago no fueron habilitadas.",
        "- Benchmark local: 661 registros, sin llamadas LLM ni ejecución de Output Guard porque no hay respuestas generadas. El visor señala explícitamente esta cobertura.",
        "- Inyección local de fallos de salida: 17 variantes de fuga sintética contenidas y 9 controles legítimos preservados por el middleware. Es una prueba condicionada con generador simulado, no ASR de un modelo real.",
        "- La nueva comparación no consumió API. La batería con DeepSeek de 1.7.2 se conserva como histórica y no se presenta como una evaluación de 1.7.3.",
        "- Se probaron también sustitución completa, SVM calibrada, regularización, proyección latente y voto suave. La sustitución completa aumentó falsos positivos al recibir historiales y fue descartada; los otros experimentos no cumplieron los límites de validación exigidos.",
        "- Las particiones ya habían sido expuestas a diagnósticos. Son resultados de regresión con etiquetas de origen/plata, no estimaciones sobre un nuevo conjunto independiente ni etiquetas humanas adjudicadas.",
        "- Algunos textos públicos etiquetados como benignos contienen órdenes explícitas de ignorar instrucciones. No se modificaron etiquetas ni se retiraron esos registros de la evaluación para mejorar las cifras.",
        "- El detalle de errores operativos, idiomas, matrices de la capa sola y revisión pendiente se conserva en el agregado JSON. Los historiales individuales permanecen privados.", ""]
    (ROOT / "docs/detector_revision_20261025.md").write_text("\n".join(lines))
    print(json.dumps({"complete": True, "version": after["library_version"], "cases": after["cases"],
                      "after": {k:v["guarded_input"] for k,v in after["metrics"].items() if k in {"public_test", "lumina_participant_test"}}}, indent=2))


if __name__ == "__main__":
    publish()
