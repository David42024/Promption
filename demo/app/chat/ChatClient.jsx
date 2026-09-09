"use client";
import { useEffect, useRef, useState } from "react";
import { useChat } from "./ChatContext";

const SendIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const LogoutIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const FileIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);

const CloseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ShieldOn = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);

const ShieldOff = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const docLevelStyles = {
  publico: {
    icon: "🌐",
    bg: "linear-gradient(135deg, rgba(16, 185, 129, 0.18), rgba(16, 185, 129, 0.05))",
    border: "1px solid rgba(16, 185, 129, 0.35)",
    color: "var(--success-400)",
    label: "Público",
  },
  interno: {
    icon: "🔐",
    bg: "linear-gradient(135deg, rgba(245, 158, 11, 0.18), rgba(245, 158, 11, 0.05))",
    border: "1px solid rgba(245, 158, 11, 0.35)",
    color: "#fbbf24",
    label: "Interno",
  },
  confidencial: {
    icon: "🛑",
    bg: "linear-gradient(135deg, rgba(239, 68, 68, 0.18), rgba(239, 68, 68, 0.05))",
    border: "1px solid rgba(239, 68, 68, 0.35)",
    color: "var(--danger-400)",
    label: "Confidencial",
  },
};

function pickDocStyle(id, title = "", tier = "publico") {
  const key = `${id} ${title} ${tier}`.toLowerCase();
  if (key.includes("confidencial") || tier === "confidencial")
    return docLevelStyles.confidencial;
  if (key.includes("interno") || tier === "interno")
    return docLevelStyles.interno;
  return docLevelStyles.publico;
}

export default function ChatClient({ user }) {
  const { msgs, setMsgs } = useChat();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState([]);
  const [docView, setDocView] = useState(null);
  const [filterStatus, setFilterStatus] = useState({ filterEnabled: true, outputGuardEnabled: true });
  const scrollRef = useRef(null);

  const loadFilterStatus = async () => {
    try {
      const r = await fetch("/api/filter-status");
      if (r.ok) setFilterStatus(await r.json());
    } catch { /* ignore */ }
  };

  useEffect(() => {
    loadFilterStatus();
    const t = setInterval(loadFilterStatus, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (msgs.length === 0) {
      setMsgs([
        {
          from: "bot",
          text: `Hola ${user.name} 👋 Soy tu asistente **Promption Copilot**.\nTengo acceso a TODA la base de conocimientos de la empresa (igual que Copilot accede a tu Microsoft 365). Tu rol actual es **[${user.roles.join(", ")}]**.\n\nMi misión: ser útil PERO respetando siempre el scope. Si me preguntas por datos fuera de tu alcance, te responderé con datos genéricos.\n\n💡 Prueba: pregúntame por sueldos sin ser admin (será rechazado), o como admin pide el reporte mensual de facturación.`,
        },
      ]);
    }
    fetch("/api/docs")
      .then(r => r.json())
      .then(d => setDocs(d.docs || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [msgs, busy]);

  async function viewDoc(id) {
    const r = await fetch(`/api/docs?id=${encodeURIComponent(id)}`);
    const d = await r.json();
    setDocView(
      r.ok
        ? { title: d.title, body: d.body, id, tier: d.tier }
        : { title: id, body: `⛔ ${d.error}`, id, denied: true, tier: "confidencial" }
    );
  }

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs(m => [...m, { from: "user", text }]);
    setBusy(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await r.json();

      // Refrescamos estado del filtro en cada respuesta
      if (typeof data.filterEnabled === "boolean") {
        setFilterStatus(s => ({
          filterEnabled: data.filterEnabled,
          outputGuardEnabled: data.outputGuardEnabled ?? s.outputGuardEnabled,
        }));
      }

      if (!r.ok) {
        setMsgs(m => [...m, { from: "blocked", text: `⚠️ ${data.error || "Error"}` }]);
      } else if (data.blocked) {
        setMsgs(m => [
          ...m,
          {
            from: "blocked",
            text: `Bloqueado por el filtro (${data.reason}) · score ${Number(
              data.confidence
            ).toFixed(2)}. Tu mensaje nunca llegó al LLM.`,
          },
        ]);
      } else {
        const trail = (data.audit || [])
          .map(
            a =>
              `\n🔧 ${a.tool} → ${a.allowed ? "ejecutada" : `denegada (${a.reason || "sin permiso"})`}${a.tier ? ` [${a.tier}]` : ""}`
          )
          .join("");
        setMsgs(m => [
          ...m,
          {
            from: "bot",
            text:
              data.reply +
              (data.leaked ? "\n\n⚠️ (el modelo filtró el secreto pero la comprobación local lo detectó)" : "") +
              (trail ? `\n${trail}` : ""),
          },
        ]);
      }
    } catch {
      setMsgs(m => [...m, { from: "blocked", text: "⚠️ Error de red" }]);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await fetch("/api/login", { method: "DELETE" });
    window.location.href = "/";
  }

  return (
    <div className="chat-container">
      <div className="topbar" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <div className="avatar lg">🤖</div>
          <div>
            <div className="logo" style={{ fontSize: "1.05rem" }}>
              <span
                className="logo-icon"
                style={{ width: 24, height: 24, fontSize: 12 }}
              >
                🛡️
              </span>
              Promption Copilot · Chat empresarial
            </div>
            <p
              className="hint"
              style={{ margin: "4px 0 0", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}
            >
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: "var(--success-500)",
                    boxShadow: "0 0 6px var(--success-500)",
                    animation: "pulse 2s infinite",
                  }}
                ></span>
                En línea · LLM conectado con KB corporativa
              </span>

              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "7px 16px",
                  borderRadius: "var(--radius-full)",
                  fontSize: "0.78rem",
                  fontWeight: 800,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  background: filterStatus.filterEnabled
                    ? "linear-gradient(135deg, rgba(16, 185, 129, 0.28), rgba(16, 185, 129, 0.1))"
                    : "linear-gradient(135deg, rgba(239, 68, 68, 0.35), rgba(245, 158, 11, 0.18))",
                  border: `2px solid ${
                    filterStatus.filterEnabled
                      ? "rgba(16, 185, 129, 0.55)"
                      : "rgba(239, 68, 68, 0.7)"
                  }`,
                  color: filterStatus.filterEnabled ? "var(--success-400)" : "var(--danger-400)",
                  boxShadow: filterStatus.filterEnabled
                    ? "0 0 18px rgba(16, 185, 129, 0.25), inset 0 0 12px rgba(16, 185, 129, 0.08)"
                    : "0 0 22px rgba(239, 68, 68, 0.35), inset 0 0 12px rgba(239, 68, 68, 0.1)",
                  animation: !filterStatus.filterEnabled ? "dangerPulse 1.6s ease-in-out infinite" : "none",
                }}
              >
                <span style={{
                  display: "inline-flex",
                  width: 8, height: 8,
                  borderRadius: "50%",
                  background: filterStatus.filterEnabled ? "var(--success-500)" : "var(--danger-500)",
                  boxShadow: filterStatus.filterEnabled
                    ? "0 0 8px var(--success-500)"
                    : "0 0 10px var(--danger-500)",
                  animation: filterStatus.filterEnabled ? "pulse 2s infinite" : "pulse 0.8s infinite",
                }}></span>
                {filterStatus.filterEnabled ? <ShieldOn /> : <ShieldOff />}
                {filterStatus.filterEnabled ? "FILTRO ACTIVADO" : "FILTRO DESACTIVADO"}
                {!filterStatus.filterEnabled && (
                  <span style={{
                    padding: "1px 7px",
                    borderRadius: "var(--radius-full)",
                    background: "rgba(245, 158, 11, 0.25)",
                    border: "1px solid rgba(245, 158, 11, 0.5)",
                    color: "#fbbf24",
                    fontSize: "0.65rem",
                    fontWeight: 800,
                  }}>
                    MODO DEMO
                  </span>
                )}
              </span>

              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  padding: "5px 12px",
                  borderRadius: "var(--radius-full)",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                  background: filterStatus.outputGuardEnabled
                    ? "rgba(34, 211, 238, 0.16)"
                    : "rgba(245, 158, 11, 0.16)",
                  border: `1.5px solid ${
                    filterStatus.outputGuardEnabled
                      ? "rgba(34, 211, 238, 0.4)"
                      : "rgba(245, 158, 11, 0.45)"
                  }`,
                  color: filterStatus.outputGuardEnabled ? "var(--accent-400)" : "#fbbf24",
                }}
              >
                <span style={{
                  width: 6, height: 6,
                  borderRadius: "50%",
                  background: filterStatus.outputGuardEnabled ? "var(--accent-400)" : "#fbbf24",
                  boxShadow: `0 0 6px ${filterStatus.outputGuardEnabled ? "var(--accent-400)" : "#fbbf24"}`,
                  animation: "pulse 2.2s infinite",
                }}></span>
                OUTPUT GUARD · {filterStatus.outputGuardEnabled ? "ON" : "OFF"}
              </span>
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 14px",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-full)",
            }}
          >
            <div className="avatar sm" style={{ background: user.roles.includes("admin")
              ? "linear-gradient(135deg, var(--warning-500), var(--brand-500))"
              : "linear-gradient(135deg, var(--brand-500), var(--accent-500))" }}>
              {user.avatar || (user.roles.includes("admin") ? "👑" : "💼")}
            </div>
            <div style={{ lineHeight: 1.2 }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 600 }}>{user.name}</div>
              <div className="hint" style={{ fontSize: "0.7rem" }}>
                {user.puesto || user.roles.join(", ")}
              </div>
            </div>
          </div>
          <button className="icon-btn" onClick={logout} title="Cerrar sesión">
            <LogoutIcon />
          </button>
        </div>
      </div>

      <div className="chat-messages" ref={scrollRef}>
        {msgs.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-end",
              gap: 10,
              justifyContent: m.from === "user" ? "flex-end" : "flex-start",
            }}
          >
            {m.from !== "user" && (
              <div className="avatar sm">
                {m.from === "blocked" ? "🛡️" : "🤖"}
              </div>
            )}
            <div className={`msg ${
              m.from === "user" ? "user"
                : m.from === "blocked" ? "blocked"
                : "bot"
            }`}>
              {m.text}
            </div>
            {m.from === "user" && (
              <div className="avatar sm" style={{
                background: user.roles.includes("admin")
                  ? "linear-gradient(135deg, var(--warning-500), var(--brand-500))"
                  : "linear-gradient(135deg, var(--brand-500), var(--accent-500))",
              }}>
                {user.avatar || (user.roles.includes("admin") ? "👑" : "💼")}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            <div className="avatar sm">🤖</div>
            <div className="msg bot typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-wrapper">
        <form className="chat-input-row" onSubmit={send}>
          <input
            className="input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={
              filterStatus.filterEnabled
                ? "Pregunta lo que necesites… incluso prueba un jailbreak 😉 el filtro te protegerá."
                : "⚠️ MODO DEMO SIN FILTRO: cualquier prompt llega DIRECTAMENTE al LLM. Pruébalo."
            }
            style={{ margin: 0 }}
          />
          <button
            className="btn send-btn"
            type="submit"
            disabled={busy || !input.trim()}
            title="Enviar"
            style={!filterStatus.filterEnabled ? {
              background: "linear-gradient(135deg, var(--warning-500), var(--danger-500))",
            } : undefined}
          >
            <SendIcon />
          </button>
        </form>
        <p
          className="hint"
          style={{
            textAlign: "center",
            fontSize: "0.75rem",
            margin: "10px 0 0",
            color: filterStatus.filterEnabled ? "var(--text-muted)" : "var(--danger-400)",
          }}
        >
          {filterStatus.filterEnabled
            ? "🛡️ Cada mensaje se analiza en 3 capas antes de tocar el LLM. Nada escapa."
            : "🚨 Modo DEMO sin protección. Ideal para demostrar cómo el filtro evita fugas. Actívalo en Panel Admin."}
        </p>
      </div>

      <div className="doc-section">
        <div className="card" style={{ padding: 24 }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 12,
              marginBottom: 4,
            }}
          >
            <div>
              <h3
                style={{
                  margin: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: "1.05rem",
                }}
              >
                <FileIcon />
                Base de conocimientos (por niveles)
                <span
                  style={{
                    fontSize: "0.75rem",
                    padding: "3px 10px",
                    borderRadius: "var(--radius-full)",
                    background: "rgba(99, 102, 241, 0.15)",
                    color: "var(--brand-400)",
                    fontWeight: 600,
                  }}
                >
                  Tu acceso: {user.roles.join(", ")}
                </span>
              </h3>
              <p className="hint" style={{ margin: "6px 0 0" }}>
                3 tiers: 🌐 público (todos) · 🔐 interno (ventas+) · 🛑 confidencial (solo admin).
              </p>
            </div>
          </div>

          <div className="doc-list">
            {docs.map(d => {
              const s = pickDocStyle(d.id, d.title, d.tier);
              return (
                <button
                  key={d.id}
                  className="doc-item"
                  onClick={() => viewDoc(d.id)}
                >
                  <div
                    className="doc-icon"
                    style={{ background: s.bg, border: s.border, color: s.color }}
                  >
                    <FileIcon />
                  </div>
                  <div className="doc-info">
                    <strong>{d.title}</strong>
                    <span>{s.label} · {d.id}</span>
                  </div>
                </button>
              );
            })}
            {docs.length === 0 && (
              <div className="empty-state" style={{ gridColumn: "1 / -1", padding: "32px 24px" }}>
                <div className="empty-icon">📭</div>
                <h4>No hay documentos disponibles</h4>
                <p>Tu rol no tiene acceso a ningún documento en este momento.</p>
              </div>
            )}
          </div>

          {docView && (
            <div className="doc-viewer">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div
                    className="doc-icon"
                    style={{
                      background: docView.denied
                        ? docLevelStyles.confidencial.bg
                        : pickDocStyle(docView.id, docView.title, docView.tier).bg,
                      border: docView.denied
                        ? docLevelStyles.confidencial.border
                        : pickDocStyle(docView.id, docView.title, docView.tier).border,
                      color: docView.denied
                        ? docLevelStyles.confidencial.color
                        : pickDocStyle(docView.id, docView.title, docView.tier).color,
                    }}
                  >
                    {docView.denied ? "🚫" : <FileIcon />}
                  </div>
                  <div>
                    <h4
                      style={{
                        margin: 0, padding: 0, border: 0,
                        color: docView.denied ? "var(--danger-400)" : "var(--text-primary)",
                      }}
                    >
                      {docView.title}
                    </h4>
                    {!docView.denied && (
                      <span className="hint" style={{ fontSize: "0.75rem" }}>
                        {pickDocStyle(docView.id, docView.title, docView.tier).label}
                      </span>
                    )}
                  </div>
                </div>
                <button className="icon-btn" onClick={() => setDocView(null)} title="Cerrar">
                  <CloseIcon />
                </button>
              </div>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  marginTop: 16,
                  background: docView.denied
                    ? "rgba(239, 68, 68, 0.08)"
                    : "var(--bg-secondary)",
                  borderColor: docView.denied
                    ? "rgba(239, 68, 68, 0.25)"
                    : "var(--border)",
                  color: docView.denied ? "#fecaca" : "var(--text-secondary)",
                  maxHeight: 280,
                }}
              >
                {docView.body}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
