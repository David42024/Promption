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
      <p className="hint" style={{ marginTop: 4 }}>Resultado real frente a la decisión simulada del filtro.</p>
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
                <th>ASR con filtro</th>
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
      const params = new URLSearchParams({ threshold: threshold.toFixed(2) });
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
  }, [dataset, threshold]);

  useEffect(() => {
    if (authLoading) return undefined;
    const timer = setTimeout(loadMetrics, 180);
    return () => clearTimeout(timer);
  }, [authLoading, loadMetrics]);

  const metrics = payload?.overall || {};
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
          <label style={{ display: "grid", gap: 7 }}>
            <span className="hint">Umbral ensemble: <strong style={{ color: "var(--text-primary)" }}>{threshold.toFixed(2)}</strong></span>
            <input
              aria-label="Umbral ensemble"
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={threshold}
              onChange={event => setThreshold(Number(event.target.value))}
              style={{ width: "100%", accentColor: "#6366f1" }}
            />
          </label>
          <div className="hint" style={{ textAlign: "right" }}>
            <div>{metrics.n_total || 0} casos · {metrics.n_malicious || 0} ataques · {metrics.n_benign || 0} benignos</div>
            <div>Benchmark: {generatedAt}</div>
          </div>
        </div>
        <div style={{ marginTop: 16, padding: "13px 15px", borderRadius: "var(--radius-md)", border: "1px solid rgba(99,102,241,.28)", background: "rgba(99,102,241,.08)", color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.55 }}>
          <strong style={{ color: "var(--text-primary)" }}>¿Qué hace el umbral?</strong>{" "}
          Simula que un caso se bloquea cuando su score ensemble alcanza el valor elegido. Al bajarlo aumenta la sensibilidad y el recall, pero pueden crecer los falsos positivos; al subirlo se bloquea con más cautela, aunque pueden escapar más ataques. El filtro real también aplica una lógica OR fail-safe, donde la heurística o el ML pueden bloquear por separado, así que sus decisiones pueden diferir de esta simulación. El control no cambia producción; ASR y latencia son mediciones de la ejecución original y no varían.
        </div>
      </section>

      {error && <div className="card" style={{ padding: 18, marginBottom: 22, color: "#fca5a5", borderColor: "rgba(239,68,68,.45)" }}>{error}</div>}

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 14, marginBottom: 22, opacity: loading ? .62 : 1 }}>
        {PERCENT_METRICS.map(([key, label, note, tone]) => (
          <MetricCard key={key} label={label} value={percentage(metrics[key])} note={note} tone={tone} />
        ))}
        <MetricCard label="ROC-AUC" value={metrics.roc?.auc == null ? "—" : decimal(metrics.roc.auc)} note="Capacidad de separar ambas clases" tone="#c084fc" />
        <MetricCard label="Reducción ASR" value={percentage(metrics.asr_reduction)} note={`Medición original · ${percentage(metrics.asr_without_filter)} → ${percentage(metrics.asr_with_filter)}`} tone="#34d399" />
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(360px,1fr))", gap: 18 }}>
        <ConfusionMatrix metrics={metrics} />
        <RocCurve roc={metrics.roc} />
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14, marginTop: 20 }}>
        <MetricCard label="Latencia media" value={`${decimal(metrics.latency?.mean, 1)} ms`} note="Tiempo promedio por prompt" tone="#22d3ee" />
        <MetricCard label="Latencia p95" value={`${decimal(metrics.latency?.p95, 1)} ms`} note="El 95% termina antes de este valor" tone="#818cf8" />
        <MetricCard label="ASR sin filtro" value={percentage(metrics.asr_without_filter)} note="Ataques exitosos sin protección" tone="#fb7185" />
        <MetricCard label="ASR con filtro" value={percentage(metrics.asr_with_filter)} note="Ataques exitosos tras aplicar el filtro" tone="#34d399" />
      </section>

      <ComparisonTable title="Rendimiento por dataset" rows={payload?.by_dataset} nameKey="dataset" nameLabel="Dataset" />
      <ComparisonTable title="Rendimiento por tipo de ataque" rows={payload?.by_attack_type} nameKey="attack_type" nameLabel="Tipo de ataque" />
    </main>
  );
}
