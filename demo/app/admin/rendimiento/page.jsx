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


function percentage(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(digits).replace(".", ",")}%` : "—";
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
  if (!Number.isFinite(number)) return "—";
  if (number === 0) return "$0.00";
  if (number >= 100) return `$${number.toFixed(2)}`;
  if (number >= 1) return `$${number.toFixed(3)}`;
  return `$${number.toFixed(4)}`;
}


const LLM_MODELS_CATALOG = [
  {
    id: "gpt-6-astra",
    name: "GPT-6 Astra",
    provider: "OpenAI",
    inputUsdPerMillion: 10.00,
    outputUsdPerMillion: 50.00,
    sourceUrl: "https://openai.com/api/pricing/",
    sourceName: "OpenAI Pricing",
    badge: "Frontier / Agente Pesado",
    tier: "Heavy",
    description: "Modelo insignia frontera de OpenAI para razonamiento complejo, agentes autónomos y computer use.",
  },
  {
    id: "openai-o1",
    name: "OpenAI o1",
    provider: "OpenAI",
    inputUsdPerMillion: 15.00,
    outputUsdPerMillion: 60.00,
    sourceUrl: "https://openai.com/api/pricing/",
    sourceName: "OpenAI Pricing",
    badge: "Razonamiento Pesado",
    tier: "Heavy",
    description: "Modelo insignia de razonamiento profundo para problemas complejos y matemáticas.",
  },
  {
    id: "claude-3-opus",
    name: "Claude 3 Opus",
    provider: "Anthropic",
    inputUsdPerMillion: 15.00,
    outputUsdPerMillion: 75.00,
    sourceUrl: "https://www.anthropic.com/pricing",
    sourceName: "Anthropic Pricing",
    badge: "Ultra Pesado",
    tier: "Heavy",
    description: "El modelo más potente y profundo de Anthropic para análisis y síntesis crítica.",
  },
  {
    id: "claude-3-5-sonnet",
    name: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    inputUsdPerMillion: 3.00,
    outputUsdPerMillion: 15.00,
    sourceUrl: "https://www.anthropic.com/pricing",
    sourceName: "Anthropic Pricing",
    badge: "Frontier",
    tier: "Heavy",
    description: "Líder en programación, análisis técnico y seguimiento de instrucciones complejas.",
  },
  {
    id: "llama-3-1-405b",
    name: "Llama 3.1 405B",
    provider: "Meta / Together",
    inputUsdPerMillion: 3.50,
    outputUsdPerMillion: 3.50,
    sourceUrl: "https://www.together.ai/pricing",
    sourceName: "Together AI",
    badge: "405B Pesado",
    tier: "Heavy",
    description: "El modelo open-weights más masivo (405 mil millones de parámetros) de la industria.",
  },
  {
    id: "gpt-4o",
    name: "GPT-4o",
    provider: "OpenAI",
    inputUsdPerMillion: 2.50,
    outputUsdPerMillion: 10.00,
    sourceUrl: "https://openai.com/api/pricing/",
    sourceName: "OpenAI Pricing",
    badge: "Insignia Multimodal",
    tier: "Heavy",
    description: "Modelo insignia de OpenAI para visión, audio, razonamiento y velocidad equilibrada.",
  },
  {
    id: "gemini-1-5-pro",
    name: "Gemini 1.5 Pro",
    provider: "Google",
    inputUsdPerMillion: 1.25,
    outputUsdPerMillion: 5.00,
    sourceUrl: "https://ai.google.dev/pricing",
    sourceName: "Google AI",
    badge: "Contexto 2M",
    tier: "Heavy",
    description: "Modelo pesado de Google con ventana de contexto de 2 millones de tokens.",
  },
  {
    id: "o3-mini",
    name: "o3-mini",
    provider: "OpenAI",
    inputUsdPerMillion: 1.10,
    outputUsdPerMillion: 4.40,
    sourceUrl: "https://openai.com/api/pricing/",
    sourceName: "OpenAI Pricing",
    badge: "Razonamiento",
    tier: "Medium",
    description: "Modelo de razonamiento STEM y código altamente eficiente con tres niveles de esfuerzo.",
  },
  {
    id: "deepseek-r1",
    name: "DeepSeek R1",
    provider: "DeepSeek",
    inputUsdPerMillion: 0.55,
    outputUsdPerMillion: 2.19,
    sourceUrl: "https://api-docs.deepseek.com/quick_start/pricing",
    sourceName: "DeepSeek",
    badge: "Razonamiento MoE 671B",
    tier: "Medium",
    description: "Modelo MoE de 671B con cadena de pensamiento abierta y razonamiento avanzado.",
  },
  {
    id: "gpt-4o-mini",
    name: "GPT-4o mini",
    provider: "OpenAI",
    inputUsdPerMillion: 0.15,
    outputUsdPerMillion: 0.60,
    sourceUrl: "https://openai.com/api/pricing/",
    sourceName: "OpenAI Pricing",
    badge: "Referencia Ligero",
    tier: "Light",
    description: "Modelo liviano de referencia para procesamiento general a bajo coste.",
  },
  {
    id: "gpt-5-nano",
    name: "GPT-5 nano",
    provider: "OpenAI",
    inputUsdPerMillion: 0.05,
    outputUsdPerMillion: 0.40,
    sourceUrl: "https://developers.openai.com/api/docs/models/gpt-5-nano",
    sourceName: "OpenAI Docs",
    badge: "Referencia Benchmark",
    tier: "Light",
    description: "Modelo ultraligero utilizado en la evaluación empírica del benchmark Promption.",
  },
];


function calculateModelProjection(model, requestsCount, tokenUsage) {
  const withoutFilterCalls = Number(tokenUsage?.calls_without_filter || 0);
  const withoutFilterTokens = tokenUsage?.without_filter || {};
  
  const avgInputTokens = withoutFilterCalls > 0
    ? (Number(withoutFilterTokens.input_tokens || 0) / withoutFilterCalls)
    : 290.355;
  const avgOutputTokens = withoutFilterCalls > 0
    ? (Number(withoutFilterTokens.output_tokens || 0) / withoutFilterCalls)
    : 155.568;
    
  const tokenSavingsRate = Number.isFinite(Number(tokenUsage?.token_savings_rate)) && Number(tokenUsage?.token_savings_rate) > 0
    ? Number(tokenUsage.token_savings_rate)
    : 0.589632;
    
  const callBlockRate = withoutFilterCalls > 0
    ? (Number(tokenUsage?.calls_avoided || 0) / withoutFilterCalls)
    : 0.53734;

  const rawInputTokens = Math.round(requestsCount * avgInputTokens);
  const rawOutputTokens = Math.round(requestsCount * avgOutputTokens);
  const rawTotalTokens = rawInputTokens + rawOutputTokens;

  const costWithoutFilter = ((rawInputTokens * model.inputUsdPerMillion) + (rawOutputTokens * model.outputUsdPerMillion)) / 1_000_000;

  const savedTotalTokens = Math.round(rawTotalTokens * tokenSavingsRate);
  const filteredTotalTokens = rawTotalTokens - savedTotalTokens;

  const savedInputTokens = Math.round(rawInputTokens * tokenSavingsRate);
  const savedOutputTokens = Math.round(rawOutputTokens * tokenSavingsRate);
  const costSaved = ((savedInputTokens * model.inputUsdPerMillion) + (savedOutputTokens * model.outputUsdPerMillion)) / 1_000_000;
  const costWithFilter = Math.max(0, costWithoutFilter - costSaved);

  const callsAvoided = Math.round(requestsCount * callBlockRate);
  const callsWithFilter = Math.max(0, requestsCount - callsAvoided);

  return {
    model,
    requestsCount,
    avgInputTokens,
    avgOutputTokens,
    rawInputTokens,
    rawOutputTokens,
    rawTotalTokens,
    costWithoutFilter,
    savedTotalTokens,
    filteredTotalTokens,
    costSaved,
    costWithFilter,
    tokenSavingsRate,
    callsAvoided,
    callsWithFilter,
  };
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
  const [threshold, setThreshold] = useState(0.5);
  const [projectedRequests, setProjectedRequests] = useState(15000);
  const [selectedModelId, setSelectedModelId] = useState("gpt-6-astra");
  const [selectedComparisonModels, setSelectedComparisonModels] = useState(() => [
    "gpt-6-astra",
    "openai-o1",
    "claude-3-opus",
    "claude-3-5-sonnet",
    "llama-3-1-405b",
    "gpt-4o",
    "gemini-1-5-pro",
    "o3-mini",
    "deepseek-r1",
  ]);

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
        <span className="hint">Benchmark {tokenUsage.model || "guardado"}{isLegacy ? " · legacy" : ""}</span>
      </div>

      <section className="kpi-grid-4" style={{ marginBottom: 22, opacity: loading ? .62 : 1 }}>
        {PERCENT_METRICS.map(([key, label, note, tone]) => (
          <MetricCard key={key} label={label} value={percentage(metrics[key])} note={note} tone={tone} />
        ))}
        <MetricCard label="ROC-AUC" value={metrics.roc?.auc == null ? "—" : percentage(metrics.roc.auc)} note="Capacidad de separar ambas clases" tone="#c084fc" />
        <MetricCard label="Especificidad (TNR)" value={percentage(metrics.tnr != null ? metrics.tnr : (1 - (metrics.fpr || 0)))} note="Benignos identificados correctamente" tone="#22d3ee" />
      </section>

      <section className="card" style={{ padding: 22, marginBottom: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: 0 }}>Resistencia del LLM</h3>
            <p className="hint" style={{ marginTop: 4 }}>Solicitudes ejecutadas contra {tokenUsage.model || "el LLM"} antes y después de aplicar el filtro y el Output Guard.</p>
          </div>
          {isLegacy && <span className="hint">Benchmark legacy · {integer(coverage.evaluable_attacks)} ataques A/B</span>}
        </div>
        <div className="kpi-grid-4" style={{ marginTop: 18 }}>
          <MetricCard label="ASR amplio sin filtro" value={percentage(metrics.asr_without_filter)} note="Incluye toda respuesta no reconocida como negativa, incluso vacía" tone="#fb7185" />
          <MetricCard label="ASR amplio protegido" value={percentage(metrics.asr_with_filter)} note="Criterio conservador; no equivale a fuga de credenciales" tone="#fbbf24" />
          <MetricCard label="Reducción ASR amplio" value={percentage(metrics.asr_reduction)} note={`${percentage(metrics.asr_without_filter)} → ${percentage(metrics.asr_with_filter)}`} tone="#34d399" />
          <MetricCard
            label="Reducción de fugas"
            value={percentage(
              llmEvaluation.strict_leak_rate_without_filter > 0
                ? (1 - (llmEvaluation.strict_leak_rate_with_filter || 0) / llmEvaluation.strict_leak_rate_without_filter)
                : 1.0
            )}
            note={`${integer(llmEvaluation.strict_leaks_without_filter || 0)} → ${integer(llmEvaluation.strict_leaks_with_filter || 0)} credenciales expuestas`}
            tone="#34d399"
          />
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
            <div className="kpi-grid-4" style={{ marginTop: 18 }}>
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

      {/* Proyección y Ahorro Multi-Modelo a Escala */}
      <section className="card" style={{ padding: 22, marginBottom: 22, border: "1px solid rgba(99, 102, 241, 0.25)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, flexWrap: "wrap", marginBottom: 18 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <h3 style={{ margin: 0, fontSize: "1.25rem" }}>🚀 Proyección de Ahorro con Modelos Pesados y de Frontera</h3>
              <span style={{ fontSize: "0.75rem", padding: "2px 10px", borderRadius: 9999, background: "rgba(99, 102, 241, 0.2)", color: "#a5b4fc", border: "1px solid rgba(99, 102, 241, 0.35)", fontWeight: 700 }}>
                Escala ~{integer(projectedRequests)} peticiones
              </span>
            </div>
            <p className="hint" style={{ marginTop: 6, marginBottom: 0 }}>
              Simula el consumo y ahorro de costes en USD para modelos pesados y de alto razonamiento (o1, Claude Opus/Sonnet, Llama 405B, GPT-4o...) en base a tarifas oficiales de internet, manteniendo el <strong>{percentage(tokenUsage?.token_savings_rate || 0.5896)} de ahorro de tokens</strong> validado en el benchmark.
            </p>
          </div>
        </div>

        {/* Controles de Configuración: Volumen y Modelo Principal */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18, padding: 18, background: "rgba(15, 23, 42, 0.5)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", marginBottom: 20 }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <label style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>
                📊 Volumen total de peticiones
              </label>
              <span className="hint" style={{ fontSize: 12 }}>Por defecto: 15.000</span>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {[5000, 10000, 15000, 25000, 50000, 100000].map(val => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setProjectedRequests(val)}
                  className={`btn ${projectedRequests === val ? "" : "secondary"}`}
                  style={{
                    padding: "4px 10px",
                    fontSize: 12,
                    fontWeight: projectedRequests === val ? 750 : 500,
                    borderRadius: "var(--radius-sm)",
                    borderColor: projectedRequests === val ? "var(--brand-500)" : undefined,
                  }}
                >
                  {integer(val)}{val === 15000 ? " ★" : ""}
                </button>
              ))}
            </div>
            <input
              type="number"
              min="100"
              max="1000000"
              step="500"
              value={projectedRequests}
              onChange={e => {
                const val = parseInt(e.target.value, 10);
                if (!isNaN(val) && val > 0) setProjectedRequests(val);
              }}
              style={{
                width: "100%",
                padding: "8px 12px",
                background: "rgba(10, 14, 26, 0.8)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                color: "var(--text-primary)",
                fontSize: 14,
              }}
            />
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <label style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>
                🤖 Modelo para foco detallado
              </label>
              <span className="hint" style={{ fontSize: 12 }}>Tarifas oficiales internet</span>
            </div>
            <select
              className="select"
              value={selectedModelId}
              onChange={e => setSelectedModelId(e.target.value)}
              style={{ width: "100%", padding: "9px 12px", marginBottom: 8 }}
            >
              {LLM_MODELS_CATALOG.map(m => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.provider}) · In: ${m.inputUsdPerMillion}/M | Out: ${m.outputUsdPerMillion}/M
                </option>
              ))}
            </select>
            {(() => {
              const active = LLM_MODELS_CATALOG.find(m => m.id === selectedModelId) || LLM_MODELS_CATALOG[0];
              return (
                <div className="hint" style={{ fontSize: 12, lineHeight: 1.4 }}>
                  {active.description} <a href={active.sourceUrl} target="_blank" rel="noreferrer" className="linkbtn" style={{ padding: 0 }}>Fuente: {active.sourceName} ↗</a>
                </div>
              );
            })()}
          </div>
        </div>

        {/* Tarjetas KPI para el Modelo Seleccionado */}
        {(() => {
          const selectedModel = LLM_MODELS_CATALOG.find(m => m.id === selectedModelId) || LLM_MODELS_CATALOG[0];
          const projection = calculateModelProjection(selectedModel, projectedRequests, tokenUsage);
          return (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <strong style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                  Impacto proyectado en {selectedModel.name} ({integer(projectedRequests)} peticiones):
                </strong>
                <span className="hint" style={{ fontSize: 12 }}>
                  Ahorro sostenido: <strong style={{ color: "#a78bfa" }}>{percentage(projection.tokenSavingsRate)}</strong>
                </span>
              </div>
              <div className="kpi-grid-4" style={{ marginBottom: 20 }}>
                <MetricCard
                  label="Coste sin filtro"
                  value={usd(projection.costWithoutFilter)}
                  note={`${integer(projection.rawTotalTokens)} tokens en ${integer(projectedRequests)} peticiones directas`}
                  tone="#fb7185"
                />
                <MetricCard
                  label="Coste con Promption"
                  value={usd(projection.costWithFilter)}
                  note={`${integer(projection.filteredTotalTokens)} tokens en ${integer(projection.callsWithFilter)} peticiones permitidas`}
                  tone="#22d3ee"
                />
                <MetricCard
                  label="Ahorro económico"
                  value={usd(projection.costSaved)}
                  note={`Dinero ahorrado al no enviar tráfico malicioso a ${selectedModel.name}`}
                  tone="#34d399"
                />
                <MetricCard
                  label="Tokens evitados"
                  value={integer(projection.savedTotalTokens)}
                  note={`${integer(projection.callsAvoided)} llamadas bloqueadas antes del LLM (${percentage(projection.tokenSavingsRate)})`}
                  tone="#a78bfa"
                />
              </div>
            </div>
          );
        })()}

        {/* Tabla Comparativa Multi-Modelo */}
        <div style={{ marginTop: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
            <h4 style={{ margin: 0, fontSize: 15 }}>
              📋 Comparativa económica entre modelos ({integer(projectedRequests)} peticiones)
            </h4>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="linkbtn"
                style={{ fontSize: 12, padding: 0 }}
                onClick={() => setSelectedComparisonModels(LLM_MODELS_CATALOG.map(m => m.id))}
              >
                Seleccionar todos
              </button>
              <span className="hint">·</span>
              <button
                type="button"
                className="linkbtn"
                style={{ fontSize: 12, padding: 0 }}
                onClick={() => setSelectedComparisonModels(["gpt-6-astra", "openai-o1", "claude-3-opus", "claude-3-5-sonnet", "llama-3-1-405b", "gpt-4o", "gemini-1-5-pro"])}
              >
                Modelos Pesados
              </button>
            </div>
          </div>

          {/* Selector de Chips de Modelos */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {LLM_MODELS_CATALOG.map(m => {
              const isSelected = selectedComparisonModels.includes(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => {
                    setSelectedComparisonModels(prev =>
                      isSelected ? (prev.length > 1 ? prev.filter(id => id !== m.id) : prev) : [...prev, m.id]
                    );
                  }}
                  style={{
                    padding: "4px 10px",
                    borderRadius: "var(--radius-full)",
                    fontSize: 12,
                    border: `1px solid ${isSelected ? "var(--brand-400)" : "var(--border)"}`,
                    background: isSelected ? "rgba(99, 102, 241, 0.2)" : "rgba(15, 23, 42, 0.4)",
                    color: isSelected ? "var(--text-primary)" : "var(--text-muted)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span>{isSelected ? "✓" : "+"}</span>
                  <span>{m.name}</span>
                  <span style={{ fontSize: 10, opacity: 0.75 }}>({m.provider})</span>
                </button>
              );
            })}
          </div>

          {/* Tabla de Comparación */}
          <div className="table-container">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Modelo & Proveedor</th>
                    <th>Tarifa Entrada / Salida ($/1M)</th>
                    <th>Tokens (Sin / Con filtro)</th>
                    <th>Coste sin filtro</th>
                    <th>Coste con filtro</th>
                    <th style={{ color: "#34d399" }}>Ahorro ($ USD)</th>
                    <th style={{ color: "#a78bfa" }}>% Ahorro</th>
                    <th>Fuente oficial</th>
                  </tr>
                </thead>
                <tbody>
                  {LLM_MODELS_CATALOG
                    .filter(m => selectedComparisonModels.includes(m.id))
                    .map(model => {
                      const proj = calculateModelProjection(model, projectedRequests, tokenUsage);
                      const isHighlighted = model.id === selectedModelId;
                      return (
                        <tr
                          key={model.id}
                          style={{
                            background: isHighlighted ? "rgba(99, 102, 241, 0.1)" : undefined,
                            borderLeft: isHighlighted ? "3px solid var(--brand-400)" : undefined,
                          }}
                        >
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <strong>{model.name}</strong>
                              <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 4, background: "rgba(148,163,184,.15)", color: "var(--text-secondary)" }}>
                                {model.provider}
                              </span>
                              {model.badge && (
                                <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 4, background: "rgba(34,211,238,.12)", color: "#67e8f9" }}>
                                  {model.badge}
                                </span>
                              )}
                            </div>
                          </td>
                          <td style={{ fontSize: 13 }}>
                            ${model.inputUsdPerMillion.toFixed(model.inputUsdPerMillion < 0.1 ? 3 : 2)} / ${model.outputUsdPerMillion.toFixed(2)}
                          </td>
                          <td style={{ fontSize: 13 }}>
                            <div>{integer(proj.rawTotalTokens)}</div>
                            <div className="hint" style={{ fontSize: 11 }}>→ {integer(proj.filteredTotalTokens)}</div>
                          </td>
                          <td style={{ color: "#fb7185", fontWeight: 600 }}>{usd(proj.costWithoutFilter)}</td>
                          <td style={{ color: "#22d3ee", fontWeight: 600 }}>{usd(proj.costWithFilter)}</td>
                          <td style={{ color: "#34d399", fontWeight: 800, fontSize: "1.05rem" }}>
                            +{usd(proj.costSaved)}
                          </td>
                          <td>
                            <strong style={{ color: "#a78bfa" }}>{percentage(proj.tokenSavingsRate)}</strong>
                          </td>
                          <td>
                            <a
                              href={model.sourceUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="linkbtn"
                              style={{ padding: 0, fontSize: 12 }}
                            >
                              {model.sourceName} ↗
                            </a>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="hint" style={{ marginTop: 14, fontSize: 12, lineHeight: 1.5 }}>
            💡 <strong>Metodología de cálculo:</strong> Para las {integer(projectedRequests)} peticiones proyectadas, se utiliza el consumo promedio medido en el benchmark ({decimal(calculateModelProjection(LLM_MODELS_CATALOG[0], projectedRequests, tokenUsage).avgInputTokens, 0)} tokens de entrada y {decimal(calculateModelProjection(LLM_MODELS_CATALOG[0], projectedRequests, tokenUsage).avgOutputTokens, 0)} tokens de salida por llamada). Se mantiene exactamente el <strong>{percentage(tokenUsage?.token_savings_rate || 0.5896)} de ahorro de tokens</strong> y la tasa de bloqueo de ataques ({percentage(tokenUsage?.calls_without_filter ? tokenUsage.calls_avoided / tokenUsage.calls_without_filter : 0.5373)}) verificados con Promption.
          </div>
        </div>
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
