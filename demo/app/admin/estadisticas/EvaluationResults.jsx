"use client";

import { useEffect, useState } from "react";

const conditions = ["unprotected", "prompt_only", "promption"];
const names = { unprotected: "Sin protección", prompt_only: "Solo prompt", promption: "Prompt + Promption" };
const percent = value => typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—";
const number = value => typeof value === "number" ? value.toLocaleString("es-PE") : "—";

function ComparisonTable({ title, groups, columns, type }) {
  return <div className="analytics-table-wrap"><table className="analytics-table"><caption>{title}</caption>
    <thead><tr><th scope="col">Condición</th>{columns.map(([key, label]) => <th scope="col" key={key}>{label}</th>)}</tr></thead>
    <tbody>{conditions.map(condition => {
      const values = groups[condition]?.[type] || {};
      return <tr key={condition} data-protected={condition === "promption"}><th scope="row">{names[condition]}</th>{columns.map(([key, , format = number]) => <td key={key}>{format(values[key], values)}</td>)}</tr>;
    })}</tbody></table></div>;
}

export default function EvaluationResults() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [corpus, setCorpus] = useState("pooled_descriptive");
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetch("/api/admin/evaluations", { signal: controller.signal, cache: "no-store" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        if (controller.signal.aborted) return;
        setReport(payload);
        setError("");
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause.message);
      }
    };
    load();
    return () => controller.abort();
  }, []);
  if (error) return <div role="alert" className="analytics-notice analytics-error">{error}</div>;
  if (!report) return <div className="analytics-empty" role="status">Cargando evaluación…</div>;
  const groups = report.conditions?.[corpus] || {};
  const metrics = groups.promption?.observed_refusal_confusion || {};
  return <section aria-label="Resultados de evaluación controlada">
    <div className="analytics-section-header"><h2>Evaluación con DeepSeek · versión {report.library_version}</h2><span className="hint">Resultados históricos con generación real</span></div>
    <div className="analytics-toolbar"><label>Conjunto de evaluación<select className="select" value={corpus} onChange={event => setCorpus(event.target.value)}><option value="pooled_descriptive">Lúmina + datasets públicos</option><option value="lumina">Lúmina · conversaciones</option><option value="public">Datasets públicos</option></select></label>
      <div className="analytics-updated">Promption {report.library_version} · {report.provider}<br />{report.complete ? "Evaluación terminada" : "Evaluación parcial"} · {number(report.completed_episodes)} / {number(report.planned_episodes)} ejecuciones</div>
    </div>
    {report.library_version !== report.installed_library_version && <div role="status" className="analytics-notice">Esta batería con DeepSeek corresponde a {report.library_version}. La app utiliza {report.installed_library_version}; estos resultados no evalúan la versión instalada.</div>}
    {!report.complete && <div role="status" className="analytics-notice">Resultados parciales: las condiciones pueden contener casos distintos mientras termina la batería. No compares sus porcentajes como si ya tuvieran la misma cobertura.</div>}
    <div className="analytics-kpis">{[
      ["Casos por condición", number(metrics.n), report.complete ? "Mismos casos en las tres condiciones" : "Cobertura parcial de Promption", "var(--text-primary)"],
      ["Recall de rechazo", percent(metrics.recall), "Referencias positivas rechazadas", "var(--success-text)"],
      ["Falsos positivos", percent(metrics.fpr), "FP / (FP + VN) · menor es mejor", "var(--danger-text)"],
      ["F1 de rechazo", percent(metrics.f1), "Balance entre precisión y recall", "var(--brand-400)"],
    ].map(([label, value, note, tone]) => <div className="analytics-kpi" key={label}><div className="analytics-kpi-label">{label}</div><div className="analytics-kpi-value" style={{ color: tone }}>{value}</div><p className="analytics-kpi-note">{note}</p></div>)}</div>
    <div className="analytics-section-header"><h2>Comparación de protecciones</h2><span className="hint">Porcentajes sobre casos evaluables</span></div>
    <ComparisonTable title="Rechazos frente a etiquetas de referencia" groups={groups} type="observed_refusal_confusion" columns={[["evaluated", "Evaluables", (value, all) => `${number(value)} / ${number(all.n)}`], ["fpr", "FPR ↓", percent], ["fnr", "FNR ↓", percent], ["recall", "Recall ↑", percent], ["precision", "Precisión ↑", percent], ["f1", "F1 ↑", percent]]} />
    <div className="analytics-notice"><strong>Interpretación.</strong> Se comparan rechazos con etiquetas provisionales. Un falso negativo de rechazo no implica una filtración. Una referencia negativa tampoco garantiza que toda petición esté autorizada. Los errores y casos sin clasificación se excluyen del cálculo y se muestran abajo.</div>
    <section className="analytics-section"><div className="analytics-section-header"><h2>Exfiltración y permisos</h2><span className="hint">Resultados efectivos del episodio</span></div>
      <ComparisonTable title="Filtraciones de la clave sintética y efectos de herramientas" groups={groups} type="exfiltration" columns={[["all_case_disclosures", "Filtraciones / casos", (value, all) => `${number(value)} / ${number(all.n_all)}`], ["eligible_exfil_targets", "Objetivos predefinidos"], ["target_disclosures", "Filtraciones en objetivos"], ["unauthorized_tool_episodes", "Herramientas no autorizadas"], ["delivered_files", "Archivos entregados"]]} />
    </section>
    <details className="analytics-details"><summary>Matriz de confusión, errores y cobertura</summary><div><ComparisonTable title="Conteos por condición" groups={groups} type="observed_refusal_confusion" columns={[["TP", "VP"], ["FP", "FP"], ["FN", "FN"], ["TN", "VN"], ["operational", "Fallos operativos"], ["unclassified", "Sin clasificación"]]} /></div></details>
    <details className="analytics-details"><summary>Metodología y límites del estudio</summary><div><p className="hint">{report.selection}</p><ul style={{ paddingLeft: 20, marginTop: 12 }}>{(report.limitations || []).map(text => <li className="hint" key={text}>{text}</li>)}</ul><p className="hint" style={{ marginTop: 12 }}>Modelo: {report.models?.generation_model}. Coste superior estimado: US${Number(report.new_cost_upper_usd || 0).toFixed(4)}. {number(report.api_calls)} llamadas API.</p><p className="hint">Resultados agregados; no se publican chats ni la clave del reto.</p></div></details>
  </section>;
}
