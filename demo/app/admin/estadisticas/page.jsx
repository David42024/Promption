"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import AdminNavigation from "../components/AdminNavigation.jsx";


function MetricCard({ label, value, note, tone = "#818cf8" }) {
  return (
    <div className="card" style={{ padding: 20, minHeight: 130 }}>
      <div style={{ color: "var(--text-muted)", fontSize: 13, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: "2rem", fontWeight: 850, marginTop: 10, color: tone }}>{value}</div>
      <div className="hint" style={{ marginTop: 7 }}>{note}</div>
    </div>
  );
}


function Distribution({ title, values = {}, empty = "Sin datos para el periodo" }) {
  const rows = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, value]) => value));
  return (
    <div className="card" style={{ padding: 22 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {rows.length === 0 ? <p className="hint">{empty}</p> : rows.map(([name, value]) => (
        <div key={name} style={{ marginTop: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
            <span style={{ color: "var(--text-secondary)" }}>{name}</span>
            <strong>{value}</strong>
          </div>
          <div style={{ height: 8, marginTop: 6, borderRadius: 99, background: "rgba(148,163,184,.14)", overflow: "hidden" }}>
            <div style={{ width: `${Math.max(3, (value / max) * 100)}%`, height: "100%", borderRadius: 99, background: "linear-gradient(90deg,#6366f1,#22d3ee)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}


function aggregateTimeline(points, period) {
  const grouped = new Map();
  for (const point of points || []) {
    const date = new Date(point.bucket);
    const key = period === "24h"
      ? date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
      : date.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit" });
    grouped.set(key, (grouped.get(key) || 0) + point.count);
  }
  return [...grouped.entries()].map(([label, count]) => ({ label, count }));
}


function Timeline({ points, period }) {
  const data = aggregateTimeline(points, period);
  const max = Math.max(1, ...data.map(item => item.count));
  return (
    <div className="card" style={{ padding: 22, overflowX: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h3 style={{ marginTop: 0 }}>Actividad en el tiempo</h3>
        <span className="hint">UTC · {period === "24h" ? "por hora" : "por día"}</span>
      </div>
      {data.length === 0 ? <p className="hint">Todavía no hay eventos en este periodo.</p> : (
        <div style={{ display: "flex", alignItems: "end", gap: 8, height: 210, minWidth: Math.max(620, data.length * 28), paddingTop: 20 }}>
          {data.map((item, index) => (
            <div key={`${item.label}-${index}`} title={`${item.label}: ${item.count}`} style={{ flex: 1, minWidth: 18, height: "100%", display: "flex", flexDirection: "column", justifyContent: "end", alignItems: "center", gap: 7 }}>
              <strong style={{ fontSize: 11 }}>{item.count}</strong>
              <div style={{ width: "100%", maxWidth: 34, height: `${Math.max(4, (item.count / max) * 150)}px`, borderRadius: "7px 7px 2px 2px", background: "linear-gradient(180deg,#22d3ee,#6366f1)" }} />
              {(data.length <= 24 || index % Math.ceil(data.length / 16) === 0) && (
                <span style={{ fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{item.label}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


export default function AdminStatistics() {
  const router = useRouter();
  const [authLoading, setAuthLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [period, setPeriod] = useState("24h");
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/login/status")
      .then(response => response.json())
      .then(data => {
        if (!data.user?.roles?.includes("admin")) router.push("/login");
      })
      .catch(() => router.push("/login"))
      .finally(() => setAuthLoading(false));
  }, [router]);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const hours = period === "24h" ? 24 : period === "7d" ? 168 : 720;
      const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
      const params = new URLSearchParams({ since, ...(tenant && { tenant_id: tenant }) });
      const response = await fetch(`/api/admin/log-stats?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      setStats(payload);
      if (!tenant) setTenants(Object.keys(payload.by_tenant || {}));
      setError("");
    } catch (cause) {
      setError(`No se pudieron cargar las estadísticas: ${cause.message}`);
    } finally {
      setLoading(false);
    }
  }, [period, tenant]);

  useEffect(() => {
    if (authLoading) return undefined;
    loadStats();
    const timer = setInterval(loadStats, 30000);
    return () => clearInterval(timer);
  }, [authLoading, loadStats]);

  const summary = stats?.summary || {};
  const blockRate = useMemo(() => {
    if (!summary.requests) return "0.0%";
    return `${((summary.blocked / summary.requests) * 100).toFixed(1)}%`;
  }, [summary.blocked, summary.requests]);

  if (authLoading) return <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>Verificando autenticación…</div>;

  return (
    <main className="admin-container">
      <Link href="/" className="linkbtn" style={{ padding: 0, marginBottom: 14 }}>← Volver a la tienda</Link>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 18, flexWrap: "wrap", marginBottom: 22 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.8rem" }}>📊 Estadísticas de seguridad</h1>
          <p className="hint" style={{ marginBottom: 0 }}>Tendencias del filtro, autorización, MCP y Output Guard.</p>
        </div>
        <button className="btn secondary" onClick={loadStats} disabled={loading}>{loading ? "Actualizando…" : "↻ Actualizar"}</button>
      </div>

      <AdminNavigation />

      <div className="card" style={{ padding: 16, marginBottom: 22, display: "flex", gap: 14, flexWrap: "wrap", alignItems: "end" }}>
        <label style={{ display: "grid", gap: 6, minWidth: 180 }}>
          <span className="hint">Periodo</span>
          <select className="select" value={period} onChange={event => setPeriod(event.target.value)}>
            <option value="24h">Últimas 24 horas</option>
            <option value="7d">Últimos 7 días</option>
            <option value="30d">Últimos 30 días</option>
          </select>
        </label>
        <label style={{ display: "grid", gap: 6, minWidth: 220 }}>
          <span className="hint">Tenant</span>
          <select className="select" value={tenant} onChange={event => setTenant(event.target.value)}>
            <option value="">Todos los tenants</option>
            {tenants.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <span className="hint" style={{ marginLeft: "auto" }}>Actualización automática cada 30 segundos</span>
      </div>

      {error && <div className="card" style={{ padding: 18, marginBottom: 22, color: "#fca5a5", borderColor: "rgba(239,68,68,.45)" }}>{error}</div>}

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 14, marginBottom: 22 }}>
        <MetricCard label="Solicitudes" value={summary.requests || 0} note={`${stats?.total || 0} eventos de auditoría`} />
        <MetricCard label="Permitidas" value={summary.allowed || 0} note="Finalizaron sin bloqueo" tone="#34d399" />
        <MetricCard label="Bloqueadas" value={summary.blocked || 0} note={`Tasa de bloqueo ${blockRate}`} tone="#f87171" />
        <MetricCard label="Inciertas" value={summary.uncertain || 0} note="Requieren revisión" tone="#fbbf24" />
        <MetricCard label="Redactadas" value={summary.redacted || 0} note="Output Guard eliminó valores" tone="#a78bfa" />
        <MetricCard label="Latencia media" value={`${stats?.latency?.average_ms || 0} ms`} note={`p95 ${stats?.latency?.p95_ms || 0} ms`} tone="#22d3ee" />
        <MetricCard label="Errores" value={summary.errors || 0} note="Eventos de nivel ERROR" tone="#fb7185" />
      </section>

      <Timeline points={stats?.timeline || []} period={period} />

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 18, marginTop: 18 }}>
        <Distribution title="Tipos de bloqueo" values={stats?.block_reasons} />
        <Distribution title="Clasificación de seguridad" values={stats?.classifications} />
        <Distribution title="Acciones de Output Guard" values={stats?.guard_actions} />
        <Distribution title="Eventos por categoría" values={stats?.by_category} />
        <Distribution title="Reglas heurísticas principales" values={stats?.top_rules} />
        <Distribution title="Actividad por usuario" values={stats?.top_users} />
        <Distribution title="Actividad por rol" values={stats?.by_role} />
        <Distribution title="Eventos por tenant" values={stats?.by_tenant} />
      </section>
    </main>
  );
}
