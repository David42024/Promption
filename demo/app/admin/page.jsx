"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

// ================ Iconos SVG inline =================
const BackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="19" y1="12" x2="5" y2="12" />
    <polyline points="12 19 5 12 12 5" />
  </svg>
);

const ReloadIcon = ({ spin }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
       style={spin ? { animation: "spin 0.8s linear infinite" } : undefined}>
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

const ShieldCheck = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);

const ShieldAlert = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const AlertIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const PowerIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
    <line x1="12" y1="2" x2="12" y2="12" />
  </svg>
);

const UndoIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7v6h6" />
    <path d="M21 17a9 9 0 0 0-15-6.7L3 13" />
  </svg>
);

const DocsIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
  </svg>
);

const UsersIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const ClockIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const HistoryIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
    <polyline points="22 4 22 10 16 10" />
  </svg>
);

const FilterIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
);

function getLevelBadge(level) {
  switch (level) {
    case "ERROR": return "badge-error";
    case "WARNING": return "badge-warning";
    case "INFO": return "badge-info";
    default: return "badge-default";
  }
}
function getCategoryBadge(cat) {
  switch (cat) {
    case "filter": return "badge-filter";
    case "authorization": return "badge-auth";
    case "output_guard": return "badge-guard";
    default: return "badge-default";
  }
}

export default function AdminPanel() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloading, setReloading] = useState(false);
  const [filters, setFilters] = useState({ level: "", category: "", tenant_id: "", limit: 100 });
  const [categories, setCategories] = useState([]);
  const [tenants, setTenants] = useState([]);

  // ---- Estado del filtro (nuevo) ----
  const [filterState, setFilterState] = useState(null);
  const [toggling, setToggling] = useState(false);

  // Verificar autenticación
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const r = await fetch("/api/login/status");
        if (r.ok) {
          const data = await r.json();
          if (data.user && data.user.roles && data.user.roles.includes("admin")) {
            setCurrentUser(data.user);
          } else {
            router.push("/login");
          }
        } else {
          router.push("/login");
        }
      } catch {
        router.push("/login");
      } finally {
        setAuthLoading(false);
      }
    };
    checkAuth();
  }, [router]);

  const fetchLogs = async () => {
    try {
      setLoading(true);
      setReloading(true);
      const params = new URLSearchParams({
        limit: filters.limit,
        ...(filters.level && { level: filters.level }),
        ...(filters.category && { category: filters.category }),
        ...(filters.tenant_id && { tenant_id: filters.tenant_id }),
      });
      const r = await fetch(`/api/admin/log-events?${params}`);
      if (!r.ok) {
        const errorText = await r.text().catch(() => "Error desconocido");
        throw new Error(`API Error ${r.status}: ${errorText}`);
      }
      const d = await r.json();
      setLogs(d.logs || []);
      setCategories(d.categories || []);
      setTenants(d.tenants || []);
      setError(null);
    } catch (err) {
      setError(`Error cargando logs: ${err.message}. Verifica PROMPTION_ADMIN_API_KEY en Vercel y PROMPTION_ADMIN_API_KEYS en Render.`);
    } finally {
      setLoading(false);
      setReloading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const r = await fetch("/api/admin/log-stats");
      if (!r.ok) {
        const errorText = await r.text().catch(() => "Error desconocido");
        console.error("Error fetching stats:", errorText);
        return;
      }
      setStats(await r.json());
    } catch (err) {
      console.error("Error fetching stats:", err);
    }
  };

  const fetchFilterState = async () => {
    try {
      const r = await fetch("/api/admin/filter-state");
      if (r.ok) setFilterState(await r.json());
    } catch { /* silencioso */ }
  };

  useEffect(() => {
    fetchLogs();
    fetchStats();
    fetchFilterState();
  }, []);

  if (authLoading) {
    return (
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        fontSize: "1.2rem"
      }}>
        Verificando autenticación...
      </div>
    );
  }

  const toggleFilter = async () => {
    if (!filterState || toggling) return;
    setToggling(true);
    try {
      const nuevoValor = !filterState.filterEnabled;
      const r = await fetch("/api/admin/filter-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "filter", enabled: nuevoValor }),
      });
      if (r.ok) setFilterState(await r.json());
    } finally {
      setToggling(false);
    }
  };

  const toggleOutputGuard = async () => {
    if (!filterState || toggling) return;
    setToggling(true);
    try {
      const nuevoValor = !filterState.outputGuardEnabled;
      const r = await fetch("/api/admin/filter-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "output-guard", enabled: nuevoValor }),
      });
      if (r.ok) setFilterState(await r.json());
    } finally {
      setToggling(false);
    }
  };

  const resetAll = async () => {
    if (!window.confirm("¿Reiniciar filtros a su estado seguro por defecto (TODO activado)?")) return;
    setToggling(true);
    try {
      const r = await fetch("/api/admin/filter-toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "reset" }),
      });
      if (r.ok) setFilterState(await r.json());
    } finally {
      setToggling(false);
    }
  };

  const handleFilterChange = (k, v) => setFilters(p => ({ ...p, [k]: v }));
  const applyFilters = () => fetchLogs();

  return (
    <div className="admin-container">
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* ============== HEADER ============== */}
      <div style={{ marginBottom: 24 }}>
        <Link href="/" className="linkbtn" style={{ padding: 0, marginBottom: 14 }}>
          <BackIcon />
          Volver a la tienda
        </Link>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div
              className="logo-icon"
              style={{
                width: 52, height: 52,
                borderRadius: "var(--radius-lg)",
                fontSize: 24,
              }}
            >
              ⚙️
            </div>
            <div>
              <h1
                style={{
                  fontSize: "1.75rem",
                  fontWeight: 800,
                  margin: 0,
                  letterSpacing: "-0.01em",
                }}
              >
                Panel de Administración
              </h1>
              <p className="hint" style={{ margin: "4px 0 0" }}>
                Estado del filtro · Decisiones · Logs de seguridad · ACL por roles
              </p>
            </div>
          </div>
          <button className="btn secondary" onClick={() => { fetchLogs(); fetchFilterState(); fetchStats(); }} disabled={reloading}>
            <ReloadIcon spin={reloading} />
            {reloading ? "Cargando…" : "Recargar todo"}
          </button>
        </div>
      </div>

      {/* ============== TARJETA DE CONTROL DEL FILTRO (nueva) ============== */}
      {filterState && (
        <div
          className="card"
          style={{
            padding: 28,
            marginBottom: 24,
            background: filterState.filterEnabled
              ? "linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(99, 102, 241, 0.08))"
              : "linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(245, 158, 11, 0.08))",
            borderColor: filterState.filterEnabled
              ? "rgba(16, 185, 129, 0.4)"
              : "rgba(239, 68, 68, 0.45)",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.3fr 1fr",
              gap: 28,
              alignItems: "center",
            }}
            className="responsive-grid"
          >
            {/* Lado izquierdo: Estado grande + explicación */}
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 18,
                  marginBottom: 18,
                  flexWrap: "wrap",
                }}
              >
                <div
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: "var(--radius-xl)",
                    background: filterState.filterEnabled
                      ? "linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(16, 185, 129, 0.05))"
                      : "linear-gradient(135deg, rgba(239, 68, 68, 0.25), rgba(239, 68, 68, 0.05))",
                    border: `2px solid ${
                      filterState.filterEnabled ? "rgba(16, 185, 129, 0.45)" : "rgba(239, 68, 68, 0.55)"
                    }`,
                    color: filterState.filterEnabled ? "var(--success-400)" : "var(--danger-400)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    boxShadow: filterState.filterEnabled
                      ? "0 0 24px rgba(16, 185, 129, 0.25)"
                      : "0 0 24px rgba(239, 68, 68, 0.3)",
                  }}
                >
                  {filterState.filterEnabled ? <ShieldCheck /> : <ShieldAlert />}
                </div>
                <div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: filterState.filterEnabled ? "var(--success-400)" : "var(--danger-400)",
                      marginBottom: 4,
                    }}
                  >
                    Filtro Anti Prompt-Injection
                  </div>
                  <div
                    style={{
                      fontSize: "2.3rem",
                      fontWeight: 800,
                      lineHeight: 1.1,
                      color: filterState.filterEnabled ? "var(--success-400)" : "var(--danger-400)",
                    }}
                  >
                    {filterState.filterEnabled ? "ACTIVADO" : "DESACTIVADO"}
                  </div>
                </div>
              </div>

              <p
                className="hint"
                style={{
                  fontSize: "0.92rem",
                  marginBottom: 12,
                  lineHeight: 1.6,
                  color: filterState.filterEnabled ? "var(--text-secondary)" : "#fecaca",
                }}
              >
                {filterState.filterEnabled
                  ? "🛡️ Protección completa: cada prompt pasa por Heurística → RandomForest (ML) → Ensemble OR → Output Guard. Nada llega al LLM sin ser auditado."
                  : "⚠️ MODO DEMO SIN PROTECCIÓN: se ha DESACTIVADO el filtro para pruebas de ataque. Cualquier jailbreak o inyección llegará DIRECTAMENTE a Groq con toda la KB confidencial visible. Actívalo antes de producción."}
              </p>

              {/* Output Guard row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 18px",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  marginBottom: 10,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: "var(--radius-sm)",
                      background: filterState.outputGuardEnabled
                        ? "rgba(34, 211, 238, 0.15)"
                        : "rgba(245, 158, 11, 0.15)",
                      border: `1px solid ${
                        filterState.outputGuardEnabled
                          ? "rgba(34, 211, 238, 0.35)"
                          : "rgba(245, 158, 11, 0.4)"
                      }`,
                      color: filterState.outputGuardEnabled
                        ? "var(--accent-400)"
                        : "#fbbf24",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <FilterIcon />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>Output Guard</div>
                    <div className="hint" style={{ fontSize: "0.8rem" }}>
                      Revisa la respuesta del LLM antes de entregarla al usuario (Block / Redact)
                    </div>
                  </div>
                </div>
                <button
                  onClick={toggleOutputGuard}
                  disabled={toggling}
                  className={`btn ${filterState.outputGuardEnabled ? "success" : "warning"}`}
                  style={{
                    padding: "9px 16px",
                    fontSize: "0.85rem",
                    margin: 0,
                    background: filterState.outputGuardEnabled
                      ? "linear-gradient(135deg, var(--success-500), #059669)"
                      : "linear-gradient(135deg, var(--warning-500), #d97706)",
                  }}
                >
                  {filterState.outputGuardEnabled ? "ON · Encendido" : "OFF · Apagado"}
                </button>
              </div>

              {/* Historial últimos cambios */}
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  fontSize: "0.8rem",
                  color: "var(--text-muted)",
                  marginTop: 6,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    flexShrink: 0,
                    marginTop: 1,
                  }}
                >
                  <HistoryIcon />
                  Último cambio:
                </span>
                <span
                  style={{
                    color: "var(--text-secondary)",
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: "0.78rem",
                  }}
                >
                  {filterState.updatedAt
                    ? new Date(filterState.updatedAt).toLocaleString("es-ES")
                    : "—"}
                </span>
                {filterState.updatedBy && (
                  <>
                    <span>· por</span>
                    <span style={{ color: "var(--brand-400)", fontWeight: 600 }}>
                      {filterState.updatedBy}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Lado derecho: Botón toggle enorme + acciones */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 14,
                alignItems: "stretch",
              }}
            >
              <button
                onClick={toggleFilter}
                disabled={toggling}
                style={{
                  padding: "28px 22px",
                  fontSize: "1.2rem",
                  fontWeight: 800,
                  borderRadius: "var(--radius-lg)",
                  border: `3px solid ${
                    filterState.filterEnabled
                      ? "rgba(239, 68, 68, 0.6)"
                      : "rgba(16, 185, 129, 0.6)"
                  }`,
                  background: filterState.filterEnabled
                    ? "linear-gradient(135deg, #1f2937, #111827)"
                    : "linear-gradient(135deg, var(--success-500), var(--brand-600))",
                  color: filterState.filterEnabled ? "#fca5a5" : "white",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 10,
                  transition: "all 0.25s ease",
                  boxShadow: filterState.filterEnabled
                    ? "inset 0 0 0 1px rgba(239, 68, 68, 0.25)"
                    : "0 10px 30px rgba(16, 185, 129, 0.35)",
                  fontFamily: "inherit",
                  letterSpacing: "0.02em",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "translateY(-2px)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "translateY(0)";
                }}
              >
                <div style={{ fontSize: "1.9rem" }}>
                  <PowerIcon />
                </div>
                <div>
                  {filterState.filterEnabled
                    ? "▶ DESACTIVAR el filtro (riesgo de fuga)"
                    : "🛡️ ACTIVAR el filtro ahora"}
                </div>
                <div
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 500,
                    opacity: 0.8,
                  }}
                >
                  {filterState.filterEnabled
                    ? "Solo para demo de ataques. No dejar en OFF."
                    : "Volver a modo seguro (recomendado)."}
                </div>
              </button>

              <button
                className="btn secondary"
                onClick={resetAll}
                disabled={toggling}
                style={{ fontSize: "0.875rem" }}
              >
                <UndoIcon />
                Restablecer modo seguro por defecto
              </button>

              {/* Historial  */}
              <div
                style={{
                  padding: 16,
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  maxHeight: 180,
                  overflowY: "auto",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 10,
                    fontSize: "0.8rem",
                    fontWeight: 700,
                    color: "var(--text-secondary)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  <HistoryIcon />
                  Historial de cambios
                </div>
                {filterState.history && filterState.history.length > 0 ? (
                  filterState.history.map((h, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "0.78rem",
                        padding: "6px 8px",
                        borderRadius: 6,
                        marginBottom: 4,
                        background: i === 0 ? "rgba(99, 102, 241, 0.1)" : "transparent",
                        gap: 8,
                        flexWrap: "wrap",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 8,
                          fontWeight: 600,
                          color:
                            String(h.action || "").endsWith("OFF") || String(h.action || "").endsWith(":OFF")
                              ? "var(--danger-400)"
                              : h.action === "filter:RESET"
                                ? "var(--warning-500)"
                                : "var(--success-400)",
                        }}
                      >
                        <span
                          style={{
                            width: 8, height: 8, borderRadius: "50%",
                            background:
                              String(h.action || "").endsWith("OFF") ? "var(--danger-500)"
                                : h.action === "filter:RESET" ? "var(--warning-500)"
                                : "var(--success-500)",
                          }}
                        />
                        {h.action || "cambio"}
                      </span>
                      <span style={{ color: "var(--text-muted)", fontFamily: "'JetBrains Mono', monospace" }}>
                        {h.by || "admin"} · {h.at ? new Date(h.at).toLocaleString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "—"}
                      </span>
                    </div>
                  ))
                ) : (
                  <span className="hint" style={{ fontSize: "0.8rem" }}>
                    No hay cambios recientes.
                  </span>
                )}
              </div>
            </div>
          </div>

          <style jsx>{`
            @media (max-width: 860px) {
              .responsive-grid {
                grid-template-columns: 1fr !important;
                gap: 24px !important;
              }
            }
          `}</style>
        </div>
      )}

      {/* ============== STATS ============== */}
      <div className="stats-grid">
        <div className="stat-card brand">
          <div className="stat-label">Total de eventos</div>
          <div className="stat-value">{stats?.total?.toLocaleString() || "—"}</div>
          <div className="stat-sub">
            <DocsIcon style={{ width: 14, height: 14 }} />
            Registrados en el sistema
          </div>
        </div>
        <div className="stat-card accent">
          <div className="stat-label">Últimas 24 horas</div>
          <div className="stat-value">{stats?.recent_24h?.toLocaleString() || "—"}</div>
          <div className="stat-sub">
            <ClockIcon style={{ width: 14, height: 14 }} />
            Actividad reciente
          </div>
        </div>
        <div className="stat-card success">
          <div className="stat-label">Tenants activos</div>
          <div className="stat-value">
            {stats?.by_tenant ? Object.keys(stats.by_tenant).length : "—"}
          </div>
          <div className="stat-sub">
            <UsersIcon style={{ width: 14, height: 14 }} />
            Instancias conectadas
          </div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">Eventos críticos</div>
          <div className="stat-value">
            {stats?.by_level?.ERROR?.toLocaleString() || "0"}
          </div>
          <div className="stat-sub">
            <ShieldAlert style={{ width: 14, height: 14 }} />
            Requieren atención
          </div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Warnings</div>
          <div className="stat-value">
            {stats?.by_level?.WARNING?.toLocaleString() || "0"}
          </div>
          <div className="stat-sub">
            <AlertIcon style={{ width: 14, height: 14 }} />
            Advertencias detectadas
          </div>
        </div>
      </div>

      {/* ============== FILTROS ============== */}
      <div className="filters-card">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <FilterIcon />
          <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: 0 }}>
            Filtros de búsqueda
          </h3>
          <span className="hint">· {logs.length} resultados</span>
        </div>
        <div className="filters-row">
          <div className="input-group">
            <label className="input-label">Nivel</label>
            <select className="select" value={filters.level} onChange={e => handleFilterChange("level", e.target.value)}>
              <option value="">Todos los niveles</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>
          <div className="input-group">
            <label className="input-label">Categoría</label>
            <select className="select" value={filters.category} onChange={e => handleFilterChange("category", e.target.value)}>
              <option value="">Todas</option>
              {categories.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="input-group">
            <label className="input-label">Tenant</label>
            <select className="select" value={filters.tenant_id} onChange={e => handleFilterChange("tenant_id", e.target.value)}>
              <option value="">Todos</option>
              {tenants.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div className="input-group">
            <label className="input-label">Límite</label>
            <input
              type="number" className="input"
              value={filters.limit}
              onChange={e => handleFilterChange("limit", parseInt(e.target.value) || 100)}
              min={1}
            />
          </div>
          <div style={{ display: "flex", gap: 10, flex: "0 0 auto" }}>
            <button className="btn" onClick={applyFilters}>Aplicar filtros</button>
            <button className="btn secondary" onClick={() => {
              setFilters({ level: "", category: "", tenant_id: "", limit: 100 });
              setTimeout(fetchLogs, 0);
            }}>Limpiar</button>
          </div>
        </div>
      </div>

      {error && (
        <div
          className="card"
          style={{
            marginBottom: 22,
            background: "linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05))",
            borderColor: "rgba(239, 68, 68, 0.35)",
          }}
        >
          <p className="error" style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <AlertIcon />
            <strong>Error:</strong> {error}
          </p>
          <p className="hint" style={{ marginTop: 8, marginBottom: 0 }}>
            Asegúrate de que el Filter API esté corriendo y que <code>PROMPTION_ADMIN_API_KEY</code>{" "}
            en Vercel coincida con una entrada de <code>PROMPTION_ADMIN_API_KEYS</code> en Render.
          </p>
        </div>
      )}

      {/* ============== TABLA ============== */}
      <div className="table-container">
        <div
          style={{
            padding: "18px 22px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <DocsIcon />
            <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: 0 }}>Logs del sistema</h3>
            <span
              style={{
                fontSize: "0.8rem", padding: "3px 10px",
                borderRadius: "var(--radius-full)",
                background: "rgba(99, 102, 241, 0.15)",
                color: "var(--brand-400)", fontWeight: 600,
              }}
            >
              {logs.length} registros
            </span>
          </div>
        </div>
        <div className="table-scroll">
          {loading ? (
            <div className="empty-state">
              <div className="empty-icon">⏳</div>
              <h4>Cargando logs…</h4>
              <p>Conectando con el Filter API.</p>
            </div>
          ) : logs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📭</div>
              <h4>No hay logs que coincidan</h4>
              <p>
                Intenta quitar filtros o aumenta el límite. Si el API no tiene logs, aparecerá aquí.
              </p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th style={{ width: 170 }}>Timestamp</th>
                  <th style={{ width: 110 }}>Nivel</th>
                  <th style={{ width: 150 }}>Categoría</th>
                  <th style={{ width: 140 }}>Tenant</th>
                  <th style={{ width: 130 }}>Usuario</th>
                  <th>Mensaje</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log, i) => (
                  <tr key={i}>
                    <td className="timestamp">
                      {log.timestamp
                        ? new Date(log.timestamp).toLocaleString("es-ES", {
                            year: "numeric", month: "2-digit", day: "2-digit",
                            hour: "2-digit", minute: "2-digit", second: "2-digit",
                          })
                        : "—"}
                    </td>
                    <td>
                      <span className={`badge ${getLevelBadge(log.level)}`}>
                        {log.level || "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${getCategoryBadge(log.category)}`}>
                        {log.category || "—"}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                      {log.tenant_id || "—"}
                    </td>
                    <td style={{ color: "var(--text-secondary)" }}>
                      {log.user_id || "—"}
                    </td>
                    <td className="message">{log.message || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
