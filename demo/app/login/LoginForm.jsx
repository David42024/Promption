"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const MailIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
    <polyline points="22,6 12,13 2,6" />
  </svg>
);

const LockIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

const ArrowRight = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="12 5 19 12 12 19" />
  </svg>
);

const BackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="19" y1="12" x2="5" y2="12" />
    <polyline points="12 19 5 12 12 5" />
  </svg>
);

const AlertIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

export default function LoginForm() {
  const [email, setEmail] = useState("ana@demo.shop");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!r.ok) {
        setError((await r.json()).error || "Error de autenticación");
        return;
      }
      const data = await r.json();
      const user = data.user;
      // Redirigir al panel admin si es admin, sino al chat
      if (user.roles && user.roles.includes("admin")) {
        router.push("/admin");
      } else {
        router.push("/chat");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div style={{ marginBottom: 24 }}>
          <Link href="/" className="linkbtn" style={{ padding: 0 }}>
            <BackIcon />
            Volver a la tienda
          </Link>
        </div>

        <div className="auth-header">
          <div className="auth-logo">🔐</div>
          <h1>Bienvenido de nuevo</h1>
          <p>Inicia sesión para acceder al chat y tus datos</p>
        </div>

        <form className="form" onSubmit={submit}>
          <div className="input-group">
            <label className="input-label" htmlFor="email">
              Correo electrónico
            </label>
            <div style={{ position: "relative" }}>
              <span
                style={{
                  position: "absolute",
                  left: 14,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--text-muted)",
                  pointerEvents: "none",
                }}
              >
                <MailIcon />
              </span>
              <input
                id="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@email.com"
                style={{ paddingLeft: 46 }}
                autoComplete="email"
              />
            </div>
          </div>

          <div className="input-group">
            <label className="input-label" htmlFor="password">
              Contraseña
            </label>
            <div style={{ position: "relative" }}>
              <span
                style={{
                  position: "absolute",
                  left: 14,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--text-muted)",
                  pointerEvents: "none",
                }}
              >
                <LockIcon />
              </span>
              <input
                id="password"
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{ paddingLeft: 46 }}
                autoComplete="current-password"
              />
            </div>
          </div>

          {error && (
            <div className="error">
              <AlertIcon />
              {error}
            </div>
          )}

          <button className="btn" type="submit" disabled={loading} style={{ marginTop: 8 }}>
            {loading ? (
              <>
                <span
                  style={{
                    width: 16,
                    height: 16,
                    border: "2px solid rgba(255,255,255,0.3)",
                    borderTopColor: "white",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                ></span>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                Entrando…
              </>
            ) : (
              <>
                Entrar al chat <ArrowRight />
              </>
            )}
          </button>
        </form>

        <div className="demo-accounts">
          <h5>Cuentas de demostración</h5>
          <div className="demo-account">
            <span className="role">�️ Cliente</span>
            <span className="creds">cliente@demo.shop / demo123</span>
          </div>
          <div className="demo-account">
            <span className="role">�💼 Ventas</span>
            <span className="creds">ana@demo.shop / demo123</span>
          </div>
          <div className="demo-account">
            <span className="role">👑 Admin</span>
            <span className="creds">jefe@demo.shop / demo123</span>
          </div>
        </div>

        <div className="auth-footer">
          <p className="hint" style={{ margin: 0 }}>
            ¿Necesitas ayuda? Contacta con el{" "}
            <Link href="/admin">equipo técnico</Link>.
          </p>
        </div>
      </div>
    </div>
  );
}
