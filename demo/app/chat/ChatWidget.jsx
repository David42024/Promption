"use client";
import { useChat } from "./ChatContext";
import { useState, useEffect } from "react";
import Link from "next/link";
import PermissionsConfig from "./PermissionsConfig";

const SendIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const ExpandIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h6v6" />
    <path d="M9 21H3v-6" />
    <path d="M21 3l-7 7" />
    <path d="M3 21l7-7" />
  </svg>
);

const CloseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const SettingsIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

// Función para formatear mensajes del bot de manera más bonita y estructurada
function formatBotMessage(text) {
  if (!text) return "";
  
  // Dividir en secciones basadas en encabezados
  const sections = text.split(/(?=### |## |\*\*[^*]+\*\*:)/);
  
  // Si no hay secciones claras, dividir por párrafos
  if (sections.length <= 1) {
    const paragraphs = text.split('\n\n').filter(p => p.trim());
    if (paragraphs.length > 1) {
      return paragraphs.map((p, i) => {
        if (i === 0) return p; // Primer párrafo normal
        return `\n\n${p}`; // Resto con separación
      }).join('');
    }
    return text;
  }
  
  // Formatear secciones con encabezados
  return sections.map((section, index) => {
    if (index === 0) return section; // Primera sección normal
    
    // Detectar si es un encabezado
    const headerMatch = section.match(/^(#{1,3})\s+(.+)$/m);
    if (headerMatch) {
      const [, hashes, title] = headerMatch;
      const level = hashes.length;
      const emoji = level === 1 ? '🎯' : level === 2 ? '📋' : '📌';
      return `\n\n${emoji} **${title}**\n${section.replace(headerMatch[0], '').trim()}`;
    }
    
    // Detectar si es lista con negritas como títulos
    const boldMatch = section.match(/^\*\*([^*]+)\*\*:/);
    if (boldMatch) {
      const [, title] = boldMatch;
      const emoji = '📋';
      return `\n\n${emoji} **${title}**\n${section.replace(boldMatch[0], '').trim()}`;
    }
    
    return `\n\n${section.trim()}`;
  }).join('');
}

export default function ChatWidget() {
  const { msgs, setMsgs, isOpen, setIsOpen } = useChat();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [showConfig, setShowConfig] = useState(false);

  useEffect(() => {
    // Verificar si hay usuario autenticado
    const checkAuth = async () => {
      try {
        const r = await fetch("/api/login/status");
        if (r.ok) {
          const data = await r.json();
          setCurrentUser(data.user);
          window.__userLoggedIn = !!data.user;
        }
      } catch {
        setCurrentUser(null);
        window.__userLoggedIn = false;
      }
    };
    checkAuth();
  }, []);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs((m) => [...m, { from: "user", text }]);
    setBusy(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await r.json();
      if (!r.ok) {
        setMsgs((m) => [
          ...m,
          {
            from: "blocked",
            text: data.friendly
              ? "⏳ Nuestro asistente está algo saturado en estos momentos. Vuelve a intentarlo en 10-15 segundos."
              : data.error || "Parece que ha habido un problema temporal. Vuelve a intentarlo.",
          },
        ]);
      } else if (data.blocked) {
        const score = Number.isFinite(Number(data.confidence))
          ? ` · score ${Number(data.confidence).toFixed(2)}`
          : "";
        const fallbackScore = data.filter_layers?.ensemble?.score
          ?? data.filter_layers?.heuristic?.score
          ?? data.filter_layers?.ml?.probability;
        const blockingScore = Number.isFinite(Number(data.confidence ?? fallbackScore))
          ? ` · score ${Number(data.confidence ?? fallbackScore).toFixed(2)}`
          : "";
        const blockedText = data.block_type === "authorization"
          ? `Acceso denegado por Policy Engine · recurso ${data.policy?.resource || "protegido"} [${data.policy?.tier || "scope restringido"}]. ${data.reply} Tu mensaje no llegó al LLM.`
          : data.block_type === "security_review"
            ? `Solicitud no clasificada con suficiente confianza${score}. ${data.reply} Por seguridad, no se consultó información protegida ni se llamó al LLM.`
          : data.block_type === "output_guard"
            ? data.reason === "output_guard_unavailable"
              ? data.reply
              : data.reason === "output_scope_violation"
                ? "La respuesta fue bloqueada porque contenía información fuera de tu alcance."
                : "La respuesta fue bloqueada por Output Guard porque contenía información sensible."
          : data.block_type === "filter_unavailable"
              ? data.reply
              : `Bloqueado por el filtro${blockingScore}.`;
        setMsgs((m) => [
          ...m,
          {
            from: "blocked",
            text: blockedText,
          },
        ]);
      } else {
        const trail = (data.audit || [])
          .map(
            (a) =>
              `\n🔧 ${a.tool} → ${
                a.allowed ? "ejecutada" : `denegada (${a.reason || "sin permiso"})`
              }`
          )
          .join("");
        // Ocultar siempre el span del modelo por defecto
        const modelTag = ""; 
        
        // Formatear la respuesta para que sea más bonita y estructurada
        const formattedReply = formatBotMessage(data.reply);
        
        // Indicador de estado del filtro
        const filterIndicator = data.filter_skipped 
          ? "\n\n⚠️ Filtro de seguridad DESACTIVADO (timeout del Filter API)" 
          : data.filter_enabled 
            ? "\n\n🛡️ Filtro de seguridad ACTIVO" 
            : "\n\n⚠️ Filtro de seguridad DESACTIVADO";
        
        setMsgs((m) => [
          ...m,
          {
            from: "bot",
            text:
              formattedReply +
              filterIndicator +
              (data.leaked ? "\n\n⚠️ (el modelo filtró el secreto)" : "") +
              (data.guard === "BLOCK" || data.guard === "REDACT" ? "\n\n🛡️ (Respuesta filtrada por seguridad)" : "") +
              trail +
              modelTag,
          },
        ]);
      }
    } catch {
      setMsgs((m) => [...m, { from: "blocked", text: "⚠️ Error de red. Comprueba tu conexión e inténtalo de nuevo." }]);
    } finally {
      setBusy(false);
    }
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="chat-fab"
        aria-label="Abrir chat"
        style={{
          position: "fixed",
          bottom: 28,
          right: 28,
          width: 62,
          height: 62,
          borderRadius: "var(--radius-full)",
          background: "linear-gradient(135deg, var(--brand-500), var(--brand-600))",
          border: "none",
          cursor: "pointer",
          zIndex: 1000,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 26,
          boxShadow: "0 8px 28px rgba(99, 102, 241, 0.5)",
          transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          color: "white",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "translateY(-3px) scale(1.05)";
          e.currentTarget.style.boxShadow =
            "0 12px 36px rgba(99, 102, 241, 0.55)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "translateY(0) scale(1)";
          e.currentTarget.style.boxShadow =
            "0 8px 28px rgba(99, 102, 241, 0.5)";
        }}
      >
        💬
      </button>
    );
  }

  return (
    <div
      className="chat-widget"
      style={{
        position: "fixed",
        bottom: 28,
        right: 28,
        width: 400,
        height: 560,
        maxWidth: "calc(100vw - 56px)",
        maxHeight: "calc(100vh - 56px)",
        background: "var(--bg-card-solid)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-xl)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 12px 48px rgba(0, 0, 0, 0.5), 0 0 60px rgba(99, 102, 241, 0.12)",
        backdropFilter: "blur(20px)",
        overflow: "hidden",
      }}
    >
      <div className="chat-header">
        <div className="chat-header-title">
          <div className="avatar">🤖</div>
          <div className="chat-header-info">
            <h4>Promption Assistant</h4>
            <p>
              <span className="status-dot"></span>
              En línea · Protegido
              {currentUser && (
                <span style={{ marginLeft: 8, fontSize: "0.75rem", opacity: 0.8 }}>
                  · {currentUser.name}
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="chat-actions">
          <button
            className="icon-btn"
            onClick={() => setShowConfig(true)}
            title="Configuración de permisos"
          >
            <SettingsIcon />
          </button>
          <a
            href="/chat"
            className="icon-btn"
            title="Abrir en pantalla completa"
          >
            <ExpandIcon />
          </a>
          <button
            className="icon-btn"
            onClick={() => setIsOpen(false)}
            title="Cerrar chat"
          >
            <CloseIcon />
          </button>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 18,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          background:
            "radial-gradient(ellipse 100% 50% at 50% 0%, rgba(99, 102, 241, 0.06), transparent)",
        }}
      >
        {msgs.length === 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
            }}
          >
            <div className="avatar sm">🤖</div>
            <div className="msg bot">
              {currentUser ? (
                currentUser.roles.includes("customer") ? (
                  <>
                    Hola {currentUser.name} 👋 Soy el asistente de Promption Shop. 
                    Puedo ayudarte con información pública de nuestros productos, 
                    horarios, envíos y garantías. ¿En qué puedo ayudarte hoy?
                  </>
                ) : currentUser.roles.includes("admin") ? (
                  <>
                    Hola {currentUser.name} 👑 Soy el asistente de Promption Shop. 
                    Tengo acceso a toda la información de la empresa. ¿Qué necesitas?
                  </>
                ) : (
                  <>
                    Hola {currentUser.name} 👋 Soy el asistente de Promption Shop. 
                    Tengo datos 🟢 públicos y 🟡 internos de la empresa. Pregunta lo que necesites…
                  </>
                )
              ) : (
                <>
                  Hola 👋 Soy el asistente de Promption Shop. 
                  Como visitante, puedo ayudarte con información pública: horarios, 
                  catálogo, garantías y contacto. Si necesitas acceso a información 
                  interna, inicia sesión en <Link href="/login" style={{ color: "var(--brand-400)", textDecoration: "underline" }}>
                    /login
                  </Link>. ¿En qué puedo ayudarte?
                </>
              )}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-end",
              gap: 8,
              justifyContent: m.from === "user" ? "flex-end" : "flex-start",
            }}
          >
            {m.from !== "user" && (
              <div className="avatar sm" style={{ width: 26, height: 26, fontSize: 12 }}>
                {m.from === "blocked" ? "🛡️" : "🤖"}
              </div>
            )}
            <div
              className={`msg ${
                m.from === "user"
                  ? "user"
                  : m.from === "blocked"
                    ? "blocked"
                    : "bot"
              }`}
            >
              {m.text}
            </div>
            {m.from === "user" && (
              <div className="avatar sm" style={{ width: 26, height: 26, fontSize: 12 }}>
                👤
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
            <div className="avatar sm" style={{ width: 26, height: 26, fontSize: 12 }}>
              🤖
            </div>
            <div className="msg bot typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
      </div>

      <form
        onSubmit={send}
        style={{
          padding: 14,
          borderTop: "1px solid var(--border)",
          background: "rgba(15, 21, 36, 0.8)",
          display: "flex",
          gap: 10,
          margin: 0,
        }}
      >
        <input
          className="input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu mensaje…"
          style={{ margin: 0, flex: 1, padding: "10px 14px" }}
        />
        <button
          className="btn send-btn"
          type="submit"
          disabled={busy || !input.trim()}
          title="Enviar"
          style={{ width: 44, height: 44, padding: 0, borderRadius: "var(--radius-md)" }}
        >
          <SendIcon />
        </button>
      </form>
      
      <PermissionsConfig 
        isOpen={showConfig} 
        onClose={() => setShowConfig(false)} 
        currentRole={currentUser?.roles?.[0] || "guest"}
      />
    </div>
  );
}
