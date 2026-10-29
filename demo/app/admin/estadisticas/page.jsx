"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AdminNavigation from "../components/AdminNavigation.jsx";
import EvaluationResults from "./EvaluationResults.jsx";

const integer = value => typeof value === "number" ? value.toLocaleString("es-PE") : "—";
const labels = { MALICIOUS: "Malicioso", BENIGN: "Benigno", UNCERTAIN: "Incierto", PASS: "Sin cambios", REDACT: "Redactado", BLOCK: "Bloqueado", filter: "Filtro de entrada", scope: "Alcance y permisos", output_guard: "Protección de salida", authorization: "Autorización" };

function MetricCard({ label, value, note, tone = "var(--text-primary)" }) {
  return <div className="analytics-kpi"><div className="analytics-kpi-label">{label}</div><div className="analytics-kpi-value" style={{ color: tone }}>{value}</div><p className="analytics-kpi-note">{note}</p></div>;
}

function Distribution({ title, values = {} }) {
  const rows = Object.entries(values).filter(([, value]) => typeof value === "number" && value >= 0).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, value]) => value));
  return <div className="analytics-panel"><h3>{title}</h3>{rows.length ? <div className="analytics-distribution">{rows.map(([name, value]) => <div key={name}><div className="analytics-row-label"><span>{labels[name] || name}</span><strong>{integer(value)}</strong></div><div className="analytics-track" aria-hidden="true"><div style={{ width: `${value / max * 100}%` }} /></div></div>)}</div> : <p className="hint">Sin datos para el periodo seleccionado.</p>}</div>;
}

function Timeline({ points = [], period }) {
  const grouped = new Map();
  for (const point of points) {
    const date = new Date(point.bucket);
    if (!Number.isFinite(date.getTime())) continue;
    const key = period === "24h" ? date.toISOString().slice(0, 13) : date.toISOString().slice(0, 10);
    grouped.set(key, (grouped.get(key) || 0) + point.count);
  }
  const data = [...grouped].sort(([a], [b]) => a.localeCompare(b)).map(([key, count]) => ({ key, count, label: period === "24h" ? `${key.slice(11)}h` : `${key.slice(8, 10)}/${key.slice(5, 7)}` }));
  const max = Math.max(1, ...data.map(row => row.count));
  return <section className="analytics-section analytics-panel"><div className="analytics-section-header"><h2>Actividad en el tiempo</h2><span className="hint">Eventos de auditoría · UTC · {period === "24h" ? "por hora" : "por día"}</span></div>{data.length ? <div className="analytics-chart-scroll"><div className="analytics-chart" role="img" aria-label={`${data.reduce((sum, row) => sum + row.count, 0)} eventos en ${data.length} intervalos`} style={{ minWidth: Math.max(540, data.length * 25) }}>{data.map((row, index) => <div key={row.key} title={`${row.key} UTC: ${row.count} eventos`} className="analytics-chart-column"><strong>{integer(row.count)}</strong><div className="analytics-chart-bar" style={{ height: `${Math.max(2, row.count / max * 130)}px` }} /><span>{data.length <= 24 || index % Math.ceil(data.length / 16) === 0 ? row.label : "\u00a0"}</span></div>)}</div></div> : <div className="analytics-empty">Todavía no hay eventos en este periodo.</div>}</section>;
}

export default function AdminStatistics() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [view, setView] = useState("activity");
  const [stats, setStats] = useState(null);
  const [period, setPeriod] = useState("24h");
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState(null);
  const controller = useRef(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/login/status", { signal: abort.signal }).then(response => response.json()).then(data => {
      if (data.user?.roles?.includes("admin")) setAuthorized(true); else router.replace("/login");
    }).catch(() => { if (!abort.signal.aborted) router.replace("/login"); });
    return () => abort.abort();
  }, [router]);
  const loadStats = useCallback(async () => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setLoading(true);
    try {
      const hours = period === "24h" ? 24 : period === "7d" ? 168 : 720;
      const params = new URLSearchParams({ since: new Date(Date.now() - hours * 3600000).toISOString(), ...(tenant && { tenant_id: tenant }) });
      const response = await fetch(`/api/admin/log-stats?${params}`, { cache: "no-store", signal: abort.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (abort.signal.aborted) return;
      setStats(payload);
      if (!tenant) setTenants(Object.keys(payload.by_tenant || {}));
      setUpdated(new Date());
      setError("");
    } catch (cause) {
      if (!abort.signal.aborted) setError(`No se pudieron cargar los datos del servicio (${cause.message}). Puedes volver a intentar.`);
    } finally { if (!abort.signal.aborted) setLoading(false); }
  }, [period, tenant]);
  useEffect(() => {
    if (!authorized || view !== "activity") return;
    loadStats();
    const timer = setInterval(() => { if (!document.hidden) loadStats(); }, 30000);
    return () => { clearInterval(timer); controller.current?.abort(); };
  }, [authorized, view, loadStats]);
  if (!authorized) return <div className="analytics-empty" role="status">Verificando acceso de administración…</div>;
  const summary = stats?.summary || {};
  const blockRate = summary.requests ? `${((summary.blocked || 0) / summary.requests * 100).toFixed(1)}%` : "—";
  return <main className="admin-container">
    <Link href="/" className="linkbtn" style={{ padding: 0 }}>← Volver a la tienda</Link>
    <header className="analytics-header"><div><span className="analytics-eyebrow">Promption Shop · administración</span><h1>Estadísticas de seguridad</h1><p className="hint">Actividad del servicio y resultados de evaluaciones controladas.</p></div>{view === "activity" && <button className="btn secondary" onClick={loadStats} disabled={loading}>{loading ? "Actualizando…" : "Actualizar datos"}</button>}</header>
    <AdminNavigation />
    <div className="analytics-tabs" role="tablist" aria-label="Tipo de estadísticas" onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const buttons = [...event.currentTarget.querySelectorAll("button")]; const index = buttons.indexOf(document.activeElement); const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + 2) % 2; buttons[next].focus(); buttons[next].click(); }}><button role="tab" tabIndex={view === "activity" ? 0 : -1} id="activity-tab" aria-controls="activity-panel" aria-selected={view === "activity"} onClick={() => setView("activity")}>Actividad del servicio</button><button role="tab" tabIndex={view === "evaluation" ? 0 : -1} id="evaluation-tab" aria-controls="evaluation-panel" aria-selected={view === "evaluation"} onClick={() => setView("evaluation")}>Evaluaciones con etiquetas</button></div>
    {view === "evaluation" ? <div role="tabpanel" id="evaluation-panel" aria-labelledby="evaluation-tab"><EvaluationResults /></div> : <div role="tabpanel" id="activity-panel" aria-labelledby="activity-tab" aria-busy={loading}>
      <div className="analytics-toolbar"><label>Periodo<select className="select" value={period} onChange={event => setPeriod(event.target.value)}><option value="24h">Últimas 24 horas</option><option value="7d">Últimos 7 días</option><option value="30d">Últimos 30 días</option></select></label><label>Espacio de trabajo<select className="select" value={tenant} onChange={event => setTenant(event.target.value)}><option value="">Todos los tenants</option>{tenants.map(item => <option key={item} value={item}>{item}</option>)}</select></label><p className="analytics-updated" role="status">{updated ? `Actualizado ${updated.toLocaleTimeString("es-PE")}` : "Esperando datos"}<br />Actualización automática cada 30 s</p></div>
      {error && <div role="alert" className="analytics-notice analytics-error">{error}{stats && " Se conservan los últimos datos cargados."}</div>}
      <div className="analytics-kpis"><MetricCard label="Solicitudes registradas" value={integer(summary.requests)} note={`${integer(stats?.total)} eventos de auditoría en el periodo`} /><MetricCard label="Permitidas" value={integer(summary.allowed)} note="Solicitudes que finalizaron sin bloqueo" tone="var(--success-text)" /><MetricCard label="Bloqueadas" value={integer(summary.blocked)} note={`Tasa de bloqueo: ${blockRate}`} tone="var(--danger-text)" /><MetricCard label="Latencia media" value={stats?.latency?.count > 0 ? `${stats.latency.average_ms} ms` : "—"} note={stats?.latency?.count > 0 ? `Percentil 95: ${stats.latency.p95_ms} ms` : "Sin mediciones de latencia"} tone="var(--info-text)" /></div>
      <div className="analytics-secondary"><span>Inciertas: <strong>{integer(summary.uncertain)}</strong></span><span>Salidas redactadas: <strong>{integer(summary.redacted)}</strong></span><span>Eventos de error: <strong>{integer(summary.errors)}</strong></span></div>
      <Timeline points={stats?.timeline} period={period} />
      <section className="analytics-section"><div className="analytics-section-header"><h2>Decisiones de protección</h2><span className="hint">Conteos de eventos, no etiquetas de verdad</span></div><div className="analytics-panels"><Distribution title="Motivos de bloqueo" values={stats?.block_reasons} /><Distribution title="Clasificación de entradas" values={stats?.classifications} /><Distribution title="Acciones de Output Guard" values={stats?.guard_actions} /><Distribution title="Reglas heurísticas principales" values={stats?.top_rules} /></div></section>
      <details className="analytics-details"><summary>Desglose de actividad y auditoría</summary><div className="analytics-panels"><Distribution title="Categorías de eventos" values={stats?.by_category} /><Distribution title="Actividad por usuario" values={stats?.top_users} /><Distribution title="Actividad por rol" values={stats?.by_role} /><Distribution title="Actividad por tenant" values={stats?.by_tenant} /></div></details>
      <p className="analytics-notice">La tasa de bloqueo del servicio no equivale a la tasa de falsos positivos. FPR, FNR y recall necesitan etiquetas de referencia; consulta la sección de evaluaciones.</p>
    </div>}
  </main>;
}
