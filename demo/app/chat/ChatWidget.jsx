"use client";
import { useChat } from "./ChatContext";
import { useState } from "react";

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

export default function ChatWidget() {
  const { msgs, setMsgs, isOpen, setIsOpen } = useChat();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

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
          { from: "blocked", text: `⚠️ ${data.error || "Error"}` },
        ]);
      } else if (data.blocked) {
        setMsgs((m) => [
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
            (a) =>
              `\n🔧 ${a.tool} → ${
                a.allowed ? "ejecutada" : `denegada (${a.reason || "sin permiso"})`
              }`
          )
          .join("");
        setMsgs((m) => [
          ...m,
          {
            from: "bot",
            text:
              data.reply +
              (data.leaked ? "\n\n⚠️ (el modelo filtró el secreto)" : "") +
              (trail ? `\n${trail}` : ""),
          },
        ]);
      }
    } catch {
      setMsgs((m) => [...m, { from: "blocked", text: "⚠️ Error de red" }]);
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
            </p>
          </div>
        </div>
        <div className="chat-actions">
          <a
            href="/chat"
            className="icon-btn"
            title="Abrir en pantalla completa"
            onClick={(e) => {
              if (!window.__userLoggedIn) {
                e.preventDefault();
                window.location.href = "/login";
              }
            }}
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
              Hola 👋 Soy el asistente de Promption Shop. Tengo datos 🟢 públicos, 🟡
              internos y 🔴 confidenciales. Pregunta lo que necesites… o si quieres
              probar la seguridad, intenta sonsacarme algo que no debas ver 😏
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
    </div>
  );
}
