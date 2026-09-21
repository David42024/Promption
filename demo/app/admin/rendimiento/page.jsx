"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import AdminNavigation from "../components/AdminNavigation.jsx";


const PERCENT_METRICS = [
  ["accuracy", "Accuracy", "Aciertos sobre el total de casos", "#22d3ee"],
  ["precision", "Precisión", "Cuántos bloqueos fueron ataques reales", "#818cf8"],
  ["recall", "Recall", "Cuántos ataques reales fueron detectados", "#34d399"],
  ["f1", "F1 score", "Equilibrio entre precisión y recall", "#a78bfa"],
  ["fpr", "Falsos positivos", "Tráfico benigno bloqueado por error", "#fb7185"],
  ["fnr", "Falsos negativos", "Ataques que lograron pasar", "#fbbf24"],
];


function percentage(value, digits = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(digits)}%` : "—";
}


function decimal(value, digits = 3) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "—";
}


function integer(value) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat("es-ES").format(number) : "—";
}


function usd(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `$${number.toFixed(4)}` : "—";
}


function MetricCard({ label, value, note, tone }) {
  return (
    <article className="card" style={{ padding: 20, minHeight: 132 }}>
      <div style={{ color: "var(--text-muted)", fontSize: 12, fontWeight: 750, letterSpacing: ".05em", textTransform: "uppercase" }}>{label}</div>
      <div style={{ color: tone, fontSize: "2rem", fontWeight: 850, marginTop: 9 }}>{value}</div>
      <div className="hint" style={{ marginTop: 6, lineHeight: 1.35 }}>{note}</div>
    </article>
  );
}


function ConfusionMatrix({ metrics }) {
  const cells = [
    { label: "Verdaderos positivos", key: "tp", note: "Ataque bloqueado", color: "#34d399" },
    { label: "Falsos negativos", key: "fn", note: "Ataque permitido", color: "#fbbf24" },
    { label: "Falsos positivos", key: "fp", note: "Benigno bloqueado", color: "#fb7185" },
    { label: "Verdaderos negativos", key: "tn", note: "Benigno permitido", color: "#22d3ee" },
  ];
  return (
    <section className="card" style={{ padding: 22 }}>
      <h3 style={{ marginTop: 0 }}>Matriz de confusión</h3>
      <p className="hint" style={{ marginTop: 4 }}>Resultado real frente a la decisión registrada por el filtro.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(120px,1fr))", gap: 12, marginTop: 18 }}>
        {cells.map(cell => (
          <div key={cell.key} style={{ padding: 16, border: "1px solid var(--border)", borderRadius: "var(--radius-md)", background: "rgba(15,23,42,.5)" }}>
            <strong style={{ display: "block", color: cell.color, fontSize: "1.65rem" }}>{metrics?.[cell.key] ?? 0}</strong>
            <span style={{ display: "block", fontWeight: 700, fontSize: 13 }}>{cell.label}</span>
            <span className="hint">{cell.note}</span>
          </div>
        ))}
      </div>
    </section>
  );
}


function RocCurve({ roc }) {
  const points = useMemo(() => {
    const fpr = roc?.fpr || [];
    const tpr = roc?.tpr || [];
    return fpr.map((value, index) => {
      const x = 50 + Number(value) * 520;
      const y = 220 - Number(tpr[index] ?? 0) * 180;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  }, [roc]);

  return (
    <section className="card" style={{ padding: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>Curva ROC</h3>
          <p className="hint" style={{ marginTop: 4 }}>Sensibilidad frente a falsos positivos.</p>
        </div>
        <strong style={{ color: "#a78bfa" }}>AUC {roc?.auc == null ? "—" : decimal(roc.auc)}</strong>
      </div>
      <svg viewBox="0 0 600 260" role="img" aria-label="Curva ROC del filtro" style={{ width: "100%", minHeight: 230, marginTop: 10 }}>
        <line x1="50" y1="220" x2="570" y2="220" stroke="rgba(148,163,184,.35)" />
        <line x1="50" y1="220" x2="50" y2="40" stroke="rgba(148,163,184,.35)" />
        <line x1="50" y1="220" x2="570" y2="40" stroke="rgba(148,163,184,.3)" strokeDasharray="7 7" />
        {points && <polyline points={points} fill="none" stroke="#818cf8" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />}
        <text x="300" y="250" textAnchor="middle" fill="#94a3b8" fontSize="12">Tasa de falsos positivos</text>
        <text x="17" y="135" textAnchor="middle" fill="#94a3b8" fontSize="12" transform="rotate(-90 17 135)">Recall / TPR</text>
        <text x="46" y="237" textAnchor="middle" fill="#64748b" fontSize="10">0</text>
        <text x="570" y="237" textAnchor="middle" fill="#64748b" fontSize="10">1</text>
        <text x="38" y="44" textAnchor="middle" fill="#64748b" fontSize="10">1</text>
      </svg>
    </section>
  );
}


function ComparisonTable({ title, rows, nameKey, nameLabel }) {
  const ordered = [...(rows || [])].sort((a, b) => (b.n_total || 0) - (a.n_total || 0));
  return (
    <section className="table-container" style={{ marginTop: 20 }}>
      <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--border)" }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
      </div>
      <div className="table-scroll">
        {ordered.length === 0 ? <p className="hint" style={{ padding: 22 }}>Sin datos para esta selección.</p> : (
          <table>
            <thead>
              <tr>
                <th>{nameLabel}</th>
                <th>Casos</th>
                <th>Precisión</th>
                <th>Recall</th>
                <th>F1</th>
                <th>FPR</th>
                <th>ASR amplio protegido</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((row, index) => (
                <tr key={`${row[nameKey]}-${row.dataset || index}`}>
                  <td style={{ fontWeight: 700 }}>{row[nameKey] || "Sin clasificar"}{nameKey !== "dataset" && row.dataset ? <span className="hint"> · {row.dataset}</span> : null}</td>
                  <td>{row.n_total ?? 0}</td>
                  <td>{percentage(row.precision)}</td>
                  <td>{percentage(row.recall)}</td>
                  <td><strong style={{ color: "#a78bfa" }}>{percentage(row.f1)}</strong></td>
                  <td>{percentage(row.fpr)}</td>
                  <td>{percentage(row.asr_with_filter)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}


export default function ModelPerformancePage() {
  const router = useRouter();
  const [authLoading, setAuthLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState(null);
  const [dataset, setDataset] = useState("");

  useEffect(() => {
    fetch("/api/login/status")
      .then(response => response.json())
      .then(data => {
        if (!data.user?.roles?.includes("admin")) router.push("/login");
      })
      .catch(() => router.push("/login"))
      .finally(() => setAuthLoading(false));
  }, [router]);

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dataset) params.set("dataset", dataset);
      const response = await fetch(`/api/admin/model-metrics?${params}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
      setPayload(data);
      setError("");
    } catch (cause) {
      setError(`No se pudieron cargar las métricas del modelo: ${cause.message}`);
    } finally {
      setLoading(false);
    }
  }, [dataset]);

  useEffect(() => {
    if (authLoading) return undefined;
    const timer = setTimeout(loadMetrics, 180);
    return () => clearTimeout(timer);
  }, [authLoading, loadMetrics]);

  const metrics = payload?.overall || {};
  const tokenUsage = payload?.token_usage || {};
  const llmEvaluation = payload?.llm_evaluation || {};
  const outputGuard = llmEvaluation?.output_guard || {};
  const benchmarkOptions = payload?.benchmark_options || {};
  const coverage = benchmarkOptions?.coverage || metrics?.llm_coverage || {};
  const isLegacy = benchmarkOptions?.legacy === true || coverage?.status === "legacy";
  const hasTokenUsage = Number(tokenUsage?.benchmark_observed?.total_tokens || 0) > 0;
  const generatedAt = payload?.generated_at
    ? new Date(payload.generated_at).toLocaleString("es-ES")
    : "Sin ejecución registrada";

  if (authLoading) {
    return <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>Verificando autenticación…</div>;
  }

  return (
    <main className="admin-container">
      <Link href="/" className="linkbtn" style={{ padding: 0, marginBottom: 14 }}>← Volver a la tienda</Link>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 18, flexWrap: "wrap", marginBottom: 22 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.8rem" }}>🎯 Evaluación del modelo</h1>
          <p className="hint" style={{ marginBottom: 0 }}>Calidad de detección calculada sobre el benchmark guardado.</p>
        </div>
        <button className="btn secondary" onClick={loadMetrics} disabled={loading}>{loading ? "Calculando…" : "↻ Actualizar"}</button>
      </header>

      <AdminNavigation />

      <section className="card" style={{ padding: 18, marginBottom: 22 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 20, alignItems: "end" }}>
          <label style={{ display: "grid", gap: 7 }}>
            <span className="hint">Dataset</span>
            <select className="select" value={dataset} onChange={event => setDataset(event.target.value)}>
              <option value="">Todos los datasets</option>
              {(payload?.available_datasets || []).map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <div className="hint" style={{ textAlign: "right" }}>
            <div>{metrics.n_total || 0} casos · {metrics.n_malicious || 0} ataques · {metrics.n_benign || 0} benignos</div>
            <div>Benchmark: {generatedAt}</div>
          </div>
        </div>
      </section>

      {error && <div className="card" style={{ padding: 18, marginBottom: 22, color: "#fca5a5", borderColor: "rgba(239,68,68,.45)" }}>{error}</div>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>Rendimiento del filtro</h3>
          <p className="hint" style={{ margin: "4px 0 0" }}>Clasificación local contra las etiquetas ataque/benigno del dataset.</p>
        </div>
        <span className="hint">Benchmark local · legacy</span>
      </div>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 14, marginBottom: 22, opacity: loading ? .62 : 1 }}>
        {PERCENT_METRICS.map(([key, label, note, tone]) => (
          <MetricCard key={key} label={label} value={percentage(metrics[key])} note={note} tone={tone} />
        ))}
        <MetricCard label="ROC-AUC" value={metrics.roc?.auc == null ? "—" : decimal(metrics.roc.auc)} note="Capacidad de separar ambas clases" tone="#c084fc" />
      </section>

      <section className="card" style={{ padding: 22, marginBottom: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: 0 }}>Resistencia del LLM</h3>
            <p className="hint" style={{ marginTop: 4 }}>Solicitudes ejecutadas contra {tokenUsage.model || "el LLM"} antes y después de aplicar el filtro y el Output Guard.</p>
          </div>
          {isLegacy && <span className="hint">Benchmark legacy · {integer(coverage.evaluable_attacks)} ataques A/B</span>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 14, marginTop: 18 }}>
          <MetricCard label="ASR amplio sin filtro" value={percentage(metrics.asr_without_filter)} note="Incluye toda respuesta no reconocida como negativa, incluso vacía" tone="#fb7185" />
          <MetricCard label="ASR amplio protegido" value={percentage(metrics.asr_with_filter)} note="Criterio conservador; no equivale a fuga de credenciales" tone="#fbbf24" />
          <MetricCard label="Reducción ASR amplio" value={percentage(metrics.asr_reduction)} note={`${percentage(metrics.asr_without_filter)} → ${percentage(metrics.asr_with_filter)}`} tone="#34d399" />
          {llmEvaluation.strict_leak_rate_without_filter != null && (
            <MetricCard label="Fuga estricta sin filtro" value={percentage(llmEvaluation.strict_leak_rate_without_filter)} note={`${integer(llmEvaluation.strict_leaks_without_filter)} respuestas expusieron la credencial`} tone="#fb7185" />
          )}
          {llmEvaluation.strict_leak_rate_with_filter != null && (
            <MetricCard label="Fuga estricta protegida" value={percentage(llmEvaluation.strict_leak_rate_with_filter)} note={`${integer(llmEvaluation.strict_leaks_with_filter)} credenciales entregadas tras Output Guard`} tone="#34d399" />
          )}
          {llmEvaluation.benign_refusal_rate_without_filter != null && (
            <MetricCard label="Rechazo benigno sin filtro" value={percentage(llmEvaluation.benign_refusal_rate_without_filter)} note="Solicitudes legítimas rechazadas por el LLM" tone="#818cf8" />
          )}
          {llmEvaluation.benign_rejection_rate_with_filter != null && (
            <MetricCard label="Rechazo benigno protegido" value={percentage(llmEvaluation.benign_rejection_rate_with_filter)} note="Bloqueos del filtro o rechazos del LLM" tone="#c084fc" />
          )}
        </div>
        {Number(outputGuard.evaluated || 0) > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 14, marginTop: 14 }}>
            <MetricCard label="Salidas revisadas" value={integer(outputGuard.evaluated)} note="Respuestas que pasaron por Output Guard" tone="#22d3ee" />
            <MetricCard label="Intervenciones en ataques" value={integer(outputGuard.attack_interventions)} note="Respuestas maliciosas redactadas o bloqueadas" tone="#34d399" />
            <MetricCard label="Fugas evitadas" value={integer(outputGuard.prevented_secret_leaks)} note="Secretos detectados antes de entregar la respuesta" tone="#a78bfa" />
            <MetricCard label="Intervenciones benignas" value={integer(outputGuard.benign_interventions)} note="Posibles falsos positivos del guard de salida" tone="#fbbf24" />
          </div>
        )}
      </section>

      <section className="card" style={{ padding: 22, marginBottom: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: 0 }}>Tokens y coste evitado por el filtro</h3>
            <p className="hint" style={{ marginTop: 4 }}>Compara el tráfico malicioso llegando directamente al LLM frente al escenario protegido.</p>
          </div>
          {hasTokenUsage && <span className="hint">Modelo medido: {tokenUsage.model}{isLegacy ? " · benchmark legacy" : ""}</span>}
        </div>
        {!hasTokenUsage ? (
          <div style={{ marginTop: 16, padding: 16, border: "1px dashed var(--border)", borderRadius: "var(--radius-md)" }}>
            <p className="hint" style={{ margin: 0 }}>Este benchmark todavía no contiene telemetría de tokens. Aparecerá después de una ejecución con un proveedor que reporte uso.</p>
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 14, marginTop: 18 }}>
              <MetricCard label="Tokens sin filtro" value={integer(tokenUsage.without_filter?.total_tokens)} note={`${integer(tokenUsage.calls_without_filter)} llamadas potenciales`} tone="#fb7185" />
              <MetricCard label="Tokens con filtro" value={integer(tokenUsage.with_filter?.total_tokens)} note={`${integer(tokenUsage.calls_with_filter)} solicitudes alcanzaron el LLM`} tone="#22d3ee" />
              <MetricCard label="Tokens evitados" value={integer(tokenUsage.saved_by_blocking?.total_tokens)} note={`${integer(tokenUsage.calls_avoided)} llamadas bloqueadas antes del LLM`} tone="#34d399" />
              <MetricCard label="Ahorro de tokens" value={percentage(tokenUsage.token_savings_rate)} note="Sobre el consumo potencial sin filtro" tone="#a78bfa" />
              <MetricCard label="Coste sin filtro" value={usd(tokenUsage.estimated_cost_without_filter_usd)} note="Proyección con la tarifa configurada" tone="#fb7185" />
              <MetricCard label="Coste con filtro" value={usd(tokenUsage.estimated_cost_with_filter_usd)} note="Solo solicitudes permitidas" tone="#22d3ee" />
              <MetricCard label="Coste evitado" value={usd(tokenUsage.estimated_cost_saved_usd)} note="Ahorro por bloquear antes del modelo" tone="#34d399" />
              <MetricCard label="Uso del benchmark" value={integer(tokenUsage.benchmark_observed?.total_tokens)} note={`${integer(tokenUsage.benchmark_calls)} llamadas A/B realmente ejecutadas`} tone="#fbbf24" />
            </div>
            <div className="hint" style={{ marginTop: 14 }}>
              {tokenUsage.pricing_mode === "reference_estimate"
                ? `Coste estimado con la tarifa de referencia de ${tokenUsage.pricing_reference_model}: $${tokenUsage.input_usd_per_million}/M tokens de entrada y $${tokenUsage.output_usd_per_million}/M de salida, incluido el razonamiento.`
                : tokenUsage.pricing_mode === "free_tier"
                  ? "El proveedor está configurado con tarifa gratuita; los tokens y llamadas evitados representan capacidad y latencia ahorradas."
                  : `Tarifa aplicada: $${tokenUsage.input_usd_per_million}/M tokens de entrada y $${tokenUsage.output_usd_per_million}/M de salida.`}
              {tokenUsage.pricing_source_url && (
                <> <a href={tokenUsage.pricing_source_url} target="_blank" rel="noreferrer" className="linkbtn" style={{ padding: 0 }}>Ver tarifa oficial</a>.</>
              )}
            </div>
          </>
        )}
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(360px,1fr))", gap: 18 }}>
        <ConfusionMatrix metrics={metrics} />
        <RocCurve roc={metrics.roc} />
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14, marginTop: 20 }}>
        <MetricCard label="Latencia media" value={`${decimal(metrics.latency?.mean, 1)} ms`} note="Tiempo promedio por prompt" tone="#22d3ee" />
        <MetricCard label="Latencia p95" value={`${decimal(metrics.latency?.p95, 1)} ms`} note="El 95% termina antes de este valor" tone="#818cf8" />
      </section>

      <ComparisonTable title="Rendimiento por dataset" rows={payload?.by_dataset} nameKey="dataset" nameLabel="Dataset" />
      <ComparisonTable title="Rendimiento por tipo de ataque" rows={payload?.by_attack_type} nameKey="attack_type" nameLabel="Tipo de ataque" />
    </main>
  );
}
